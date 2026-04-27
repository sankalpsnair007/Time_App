import os
import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import easyocr
import numpy as np
from PIL import Image

app = FastAPI(title="Time App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load EasyOCR model purely onto CPU at server boot
ocr_reader = easyocr.Reader(['en'], gpu=False)

@app.post("/api/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert('RGB')
        img_np = np.array(image)
        img_width = img_np.shape[1]
        
        # Use EasyOCR with full bounding box detail (detail=1)
        try:
            results = ocr_reader.readtext(img_np, detail=1)
        except Exception as e:
            return {"status": "error", "message": f"OCR engine failed: {repr(e)}"}
        
        # OCR Optical artifact correction (dark-mode hallucinates letters as numbers)
        def fix_ocr(text):
            # Only fix potential digit substitutions near h/m markers
            # Use a targeted approach: fix obvious single-char swaps
            replacements = {'O': '0', 'o': '0', 'S': '5', 'l': '1', 'I': '1'}
            result = []
            for ch in text:
                result.append(replacements.get(ch, ch))
            return ''.join(result)
        
        # Pattern to detect a time value like "8h 41m" or "10h 44m"
        TIME_PATTERN = re.compile(r'(\d+)\s*[hH]\s*(\d+)\s*[mMm]')
        
        left_col = []   # effective hours
        right_col = []  # gross hours
        
        for bbox, text, conf in results:
            cleaned = fix_ocr(text.strip())
            m = TIME_PATTERN.search(cleaned)
            if not m:
                continue
            h_val = int(m.group(1))
            min_val = int(m.group(2))
            # Determine horizontal center of this bounding box
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            
            if cx < img_width / 2:
                left_col.append((cy, h_val, min_val))
            else:
                right_col.append((cy, h_val, min_val))
        
        # Sort each column top to bottom by Y coordinate
        left_col.sort(key=lambda x: x[0])
        right_col.sort(key=lambda x: x[0])
        
        # Pair rows: zip left (effective) with right (gross)
        parsed_days = []
        for (_, eff_h, eff_m), (_, gross_h, gross_m) in zip(left_col, right_col):
            parsed_days.append({
                "eff_h": eff_h, "eff_m": eff_m,
                "gross_h": gross_h, "gross_m": gross_m
            })
        
        # If column detection found nothing, fall back to sequential pairing
        if not parsed_days:
            all_nums = []
            for bbox, text, conf in results:
                cleaned = fix_ocr(text.strip())
                m = TIME_PATTERN.search(cleaned)
                if m:
                    all_nums.append((int(m.group(1)), int(m.group(2))))
            for i in range(0, len(all_nums) - 1, 2):
                parsed_days.append({
                    "eff_h": all_nums[i][0], "eff_m": all_nums[i][1],
                    "gross_h": all_nums[i+1][0], "gross_m": all_nums[i+1][1]
                })

        raw_text = " | ".join([text for _, text, _ in results])
        return {"status": "success", "raw_text": raw_text, "parsed_days": parsed_days}
        
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        return {"status": "error", "message": repr(e), "trace": err}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
