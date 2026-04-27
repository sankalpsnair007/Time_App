import os
import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


def parse_time_str(t_str, ampm):
    parts = t_str.split(':')
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    if ampm == 'pm' and h != 12: h += 12



from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import make_pipeline

# --- Custom ML Model Training on Startup ---
# We train a simple intent classifier on a minimal dataset to direct chatbot logic
training_data = [
    ("calculate my time from 10 am to 5 pm with 1 hour break", "calculate"),
    ("I logged in at 9, left at 6, 2 hr break", "calculate"),
    ("i started at 8 am and left at 5 pm, 30 min break", "calculate"),
    ("calculate punchout", "calculate"),
    ("what is the 9 hour rule?", "rules"),
    ("tell me about the 45 hour gross requirement", "rules"),
    ("gross vs effective", "rules"),
    ("hello", "greeting"),
    ("hi there", "greeting"),
    ("who are you", "greeting")
]
X_train, y_train = zip(*training_data)
intent_model = make_pipeline(TfidfVectorizer(), LinearSVC())
intent_model.fit(list(X_train), list(y_train))

# --- Custom NER Model Training on Startup (Entity Extraction) ---
import spacy
from spacy.training.example import Example
import random
import dateutil.parser

ner_model = spacy.blank("en")
ner = ner_model.add_pipe("ner")
ner.add_label("START_TIME")
ner.add_label("END_TIME")
ner.add_label("BREAK")

NER_TRAIN_DATA = [
    ("worked 9 am to 6 pm with 1 hr break", {"entities": [(7, 11, "START_TIME"), (15, 19, "END_TIME"), (25, 29, "BREAK")]}),
    ("10am to 7pm 2h break", {"entities": [(0, 4, "START_TIME"), (8, 11, "END_TIME"), (12, 14, "BREAK")]}),
    ("in at 09:00 out at 18:00 no break", {"entities": [(6, 11, "START_TIME"), (19, 24, "END_TIME")]}),
    ("start 8:30 am, end 5:30 pm, 1.5 hr break", {"entities": [(6, 13, "START_TIME"), (19, 26, "END_TIME"), (28, 34, "BREAK")]}),
    ("9am - 5pm, 1h break", {"entities": [(0, 3, "START_TIME"), (6, 9, "END_TIME"), (11, 13, "BREAK")]}),
    ("from 10:00 to 19:00 taking 2.5 hour break", {"entities": [(5, 10, "START_TIME"), (14, 19, "END_TIME"), (27, 35, "BREAK")]})
]

optimizer = ner_model.begin_training()
# Extremely fast 20 epoch loop for empty dictionary
for i in range(20):
    losses = {}
    for text, annotations in NER_TRAIN_DATA:
        doc = ner_model.make_doc(text)
        try:
            example = Example.from_dict(doc, annotations)
            ner_model.update([example], sgd=optimizer, losses=losses)
        except Exception:
            pass # ignore token misalignment edge cases during manual mock iteration
# -------------------------------------------

def convert_to_hours(t_str):
    try:
        dt = dateutil.parser.parse(t_str)
        return dt.hour + (dt.minute / 60.0)
    except:
        return 0

def parse_break_dur(b_str):
    num_match = re.search(r'(\\d+(\\.\\d+)?)', b_str)
    num = float(num_match.group(1)) if num_match else 0
    if "min" in b_str or ("m" in b_str and "ho" not in b_str):
        num /= 60.0
    return num

# Chatbot endpoint utilizing the trained ML models
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    msg = request.message.lower()
    
    # 1. Use the ML model to predict user intent
    intent = intent_model.predict([msg])[0]

    # Initialize calculation variables with fallback logic
    login_val, login_ampm, out_val, out_ampm = 0, 0, 0, 0
    brk_time = 0
    
    if intent == "calculate":
        # 2. Advanced Named Entity Extraction via newly trained Spacy model
        doc = ner_model(msg)
        start_str, end_str, break_str_raw = None, None, None
        
        for ent in doc.ents:
            if ent.label_ == "START_TIME" and not start_str: start_str = ent.text
            elif ent.label_ == "END_TIME" and not end_str: end_str = ent.text
            elif ent.label_ == "BREAK" and not break_str_raw: break_str_raw = ent.text
            
        # Fallback 1: Extremely Generalized Time Pattern matching if ML failed to parse exactly
        if not start_str or not end_str:
            time_matches = re.findall(r'\\b(\\d{1,2}(?:\\:\\d{2})?\\s*(?:am|pm)?)\\b', msg)
            if len(time_matches) >= 2:
                start_str = time_matches[0]
                end_str = time_matches[1]
                
        # Fallback 2: Regex extraction for Break Duration
        if not break_str_raw:
            brk_match = re.search(r'(\\d+(\\.\\d+)?)\\s*[- ]*(hour|hr|h|min|m)', msg)
            if brk_match:
                break_str_raw = brk_match.group(0)
        
        if start_str and end_str:
            brk_time = parse_break_dur(break_str_raw) if break_str_raw else 0
            
            login_t = convert_to_hours(start_str)
            out_t = convert_to_hours(end_str)
            
            gross = out_t - login_t
            if gross < 0: gross += 24
            
            effective = gross - brk_time
            break_str_text = f" Deducting your {brk_time:g}-hour break from your Effective hours," if brk_time else ""
            gross_needed = 9 - gross
            
            st_text = str(start_str).upper()
            en_text = str(end_str).upper()
            
            reply = f"From {st_text} to {en_text} is {gross:g} Gross Hours.{break_str_text} You have {effective:g} Effective Hours remaining! "
            if gross_needed > 0:
                reply += f"You are short by {gross_needed:g} hours for your 9h daily target."
            else:
                reply += "You hit your 9-hour gross goal!"
                
            return ChatResponse(reply=reply)
        else:
            return ChatResponse(reply="It looks like you want to calculate your hours, but my NER model couldn't extract the exact timestamps securely from your phrase. Can you try again clearly indicating start and end times?")

    elif intent == "rules":
        reply = "The strict policy is 9 hours of gross time and 8 hours of effective time per day. Remember, **break hours are deducted ONLY from your Effective time**, never from your Gross time! If you reach 45 hours a week Gross, you are solid!"
    else:
        reply = "Hello! I am a trained Machine Learning Intent Assistant. Ask me to 'calculate my hours' or ask about 'the 9 hour rule' and my local model will assist."
        
    return ChatResponse(reply=reply)


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
