document.addEventListener('DOMContentLoaded', () => {
    // --- Constants ---
    const GROSS_HOURS_PER_DAY = 9;
    const EFF_HOURS_PER_DAY = 8;

    // --- Init Daily Goal Dropdowns ---
    const goalHoursSelect = document.getElementById('goalHours');
    const goalMinutesSelect = document.getElementById('goalMinutes');
    if (goalHoursSelect) {
        for (let h = 0; h <= 12; h++) {
            goalHoursSelect.innerHTML += `<option value="${h}" ${h === 8 ? 'selected' : ''}>${h} Hours</option>`;
        }
    }
    if (goalMinutesSelect) {
        for (let m = 0; m < 60; m++) {
            goalMinutesSelect.innerHTML += `<option value="${m}">${m} Minutes</option>`;
        }
    }

    // --- Init Break Time Dropdowns ---
    const breakHoursSelect = document.getElementById('breakHours');
    const breakMinsSelect = document.getElementById('breakMinutes');
    if (breakHoursSelect) {
        for (let h = 0; h <= 4; h++) {
            breakHoursSelect.innerHTML += `<option value="${h}" ${h === 0 ? 'selected' : ''}>${h}h</option>`;
        }
    }
    if (breakMinsSelect) {
        for (let m = 0; m < 60; m += 5) {
            breakMinsSelect.innerHTML += `<option value="${m}">${m < 10 ? '0' + m : m}m</option>`;
        }
    }

    // --- Daily Calculator Logic ---
    const calculateDailyBtn = document.getElementById('calculateDailyBtn');

    calculateDailyBtn.addEventListener('click', () => {
        const goalH = parseInt(document.getElementById('goalHours').value);
        const goalM = parseInt(document.getElementById('goalMinutes').value);
        const firstLoginStr = document.getElementById('firstLogin').value;
        const lastPunchInStr = document.getElementById('lastPunchIn').value;
        const breakH = parseInt(document.getElementById('breakHours').value) || 0;
        const breakM = parseInt(document.getElementById('breakMinutes').value) || 0;
        const actualBreakMins = (breakH * 60) + breakM;

        // Assume default logic: Gross target is always 9h. Effective target is goalH.
        // We will calculate remaining based on elapsed time from first login to last punch in.
        if (firstLoginStr && lastPunchInStr) {
            let [h, m] = firstLoginStr.split(':').map(Number);
            let firstLoginDate = new Date();
            firstLoginDate.setHours(h, m, 0, 0);

            let [h2, m2] = lastPunchInStr.split(':').map(Number);
            let lastPunchInDate = new Date();
            lastPunchInDate.setHours(h2, m2, 0, 0);

            if (lastPunchInDate < firstLoginDate) {
                lastPunchInDate.setDate(lastPunchInDate.getDate() + 1);
            }

            let elapsedMs = lastPunchInDate.getTime() - firstLoginDate.getTime();
            let elapsedGrossMins = Math.floor(elapsedMs / 60000);
            if (elapsedGrossMins < 0) elapsedGrossMins = 0;

            // Gross time stats
            const DAILY_GROSS_TARGET = 9 * 60; // 9h mandatory gross
            document.getElementById('grossTotal').innerText = formatMins(elapsedGrossMins);
            let remainGrossMins = DAILY_GROSS_TARGET - elapsedGrossMins;
            document.getElementById('grossRemain').innerText = remainGrossMins > 0 ? formatMins(remainGrossMins) : "Goal Met!";
            // Gross Punchout = First Login + 9h (fixed daily mandatory)
            let grossPunchoutDate = new Date(firstLoginDate.getTime() + DAILY_GROSS_TARGET * 60000);
            document.getElementById('grossPunchout').innerText = formatTimeAMPM(grossPunchoutDate);

            // Effective time stats — use ACTUAL break time entered by user
            let elapsedEffMins = Math.max(0, elapsedGrossMins - actualBreakMins);
            document.getElementById('effTotal').innerText = formatMins(elapsedEffMins);

            let targetEffMins = (goalH * 60) + goalM;
            let remainEffMins = targetEffMins - elapsedEffMins;
            document.getElementById('effRemain').innerText = remainEffMins > 0 ? formatMins(remainEffMins) : "Goal Met!";

            // Effective Punchout = First Login + effectiveGoal + actual break
            let effPunchoutDate = new Date(firstLoginDate.getTime() + (targetEffMins + actualBreakMins) * 60000);
            document.getElementById('effPunchout').innerText = formatTimeAMPM(effPunchoutDate);
        } else {
            alert("Please calculate using an initial login time and last punch in time.");
        }
    });

    // --- Weekly OCR & Calculator Logic ---
    const workedDaysSelect = document.getElementById('workedDays');
    const daysRowsContainer = document.getElementById('daysRows');

    function renderDaysRows(count) {
        daysRowsContainer.innerHTML = '';
        let minOptions = '';
        for (let m = 0; m < 60; m++) { minOptions += `<option value="${m}">${m < 10 ? '0' + m : m}</option>`; }
        let hourOptions = '';
        for (let h = 0; h <= 24; h++) { hourOptions += `<option value="${h}">${h}</option>`; }
        for (let i = 1; i <= count; i++) {
            daysRowsContainer.innerHTML += `
                <div class="day-row">
                    <div>${i}</div>
                    <div style="display:flex; justify-content:center; gap:4px;">
                        <select id="eff_h_${i}" style="flex:1; padding:6px; border-radius:4px; border:1px solid #ccc;">${hourOptions}</select>
                        <select id="eff_m_${i}" style="flex:1; padding:6px; border-radius:4px; border:1px solid #ccc;">${minOptions}</select>
                    </div>
                    <div style="display:flex; justify-content:center; gap:4px;">
                        <select id="gross_h_${i}" style="flex:1; padding:6px; border-radius:4px; border:1px solid #ccc;">${hourOptions}</select>
                        <select id="gross_m_${i}" style="flex:1; padding:6px; border-radius:4px; border:1px solid #ccc;">${minOptions}</select>
                    </div>
                </div>
            `;
        }
    }

    workedDaysSelect.addEventListener('change', (e) => {
        renderDaysRows(e.target.value);
    });

    // Initialize default rows
    renderDaysRows(5);

    // OCR Upload Logic
    document.getElementById('screenshotUpload').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('http://127.0.0.1:8000/api/ocr', {
                method: 'POST',
                body: formData
            });
            
            if (!res.ok) {
                throw new Error("Backend returned HTTP " + res.status);
            }
            
            const data = await res.json();

            if (data.status === 'success') {
                let days = data.parsed_days || [];
                for (let i = 0; i < 5; i++) {
                    let d = i + 1;
                    let eh = document.getElementById(`eff_h_${d}`), em = document.getElementById(`eff_m_${d}`);
                    let gh = document.getElementById(`gross_h_${d}`), gm = document.getElementById(`gross_m_${d}`);
                    if (days[i]) {
                        if (eh) eh.value = days[i].eff_h;
                        if (em) em.value = days[i].eff_m;
                        if (gh) gh.value = days[i].gross_h;
                        if (gm) gm.value = days[i].gross_m;
                    } else {
                        if (eh) eh.value = 0;
                        if (em) em.value = 0;
                        if (gh) gh.value = 0;
                        if (gm) gm.value = 0;
                    }
                }
                document.getElementById('calculateWeeklyBtn').click();
                alert("OCR auto-fill complete! Values have been parsed and calculations triggered.");
            } else {
                throw new Error("Backend parsing error: " + (data.message || "Unknown error"));
            }
        } catch (err) {
            console.error(err);
            alert("Ensure backend is running at :8000. Filling mock data instead.");
            for (let i = 1; i <= 3; i++) { // Using 3 rows from image mock
                let eh = document.getElementById(`eff_h_${i}`), em = document.getElementById(`eff_m_${i}`);
                let gh = document.getElementById(`gross_h_${i}`), gm = document.getElementById(`gross_m_${i}`);
                if (eh) eh.value = i===3 ? "8" : "7";
                if (em) em.value = i===1 ? "52" : (i===2 ? "53" : "22");
                if (gh) gh.value = i===1 ? "10" : "9";
                if (gm) gm.value = i===1 ? "4" : (i===2 ? "25" : "3");
            }
            document.getElementById('calculateWeeklyBtn').click();
        }
    });

    // Weekly Calculate Logic
    document.getElementById('calculateWeeklyBtn').addEventListener('click', () => {
        let count = parseInt(workedDaysSelect.value);
        let totalEffMins = 0;
        let totalGrossMins = 0;

        for (let i = 1; i <= count; i++) {
            let eh = parseInt(document.getElementById(`eff_h_${i}`).value) || 0;
            let em = parseInt(document.getElementById(`eff_m_${i}`).value) || 0;
            let gh = parseInt(document.getElementById(`gross_h_${i}`).value) || 0;
            let gm = parseInt(document.getElementById(`gross_m_${i}`).value) || 0;

            totalEffMins += (eh * 60) + em;
            totalGrossMins += (gh * 60) + gm;
        }

        // Render totals
        document.getElementById('totalEff').innerText = formatMins(totalEffMins);
        document.getElementById('totalGross').innerText = formatMins(totalGrossMins);

        // Weekly goals scale with number of worked days (9h gross / 8h effective per day)
        let remainEffMins = (EFF_HOURS_PER_DAY * 60 * count) - totalEffMins;
        let remainGrossMins = (GROSS_HOURS_PER_DAY * 60 * count) - totalGrossMins;

        let formatRemain = (m) => m > 0 ? formatMins(m) : "Goal Met!";
        document.getElementById('remainEff').innerText = formatRemain(remainEffMins);
        document.getElementById('remainGross').innerText = formatRemain(remainGrossMins);
    });



    // --- Utilities ---
    function parseHHMM(val) {
        const parts = val.split(':');
        let h = parseInt(parts[0]) || 0;
        let m = parseInt(parts[1]) || 0;
        return (h * 60) + m;
    }

    function formatMins(totalMins) {
        if (totalMins < 0) totalMins = 0;
        let h = Math.floor(totalMins / 60);
        let m = totalMins % 60;
        return `${h}h ${m}m 00s`;
    }

    function formatTimeAMPM(date) {
        let hours = date.getHours();
        let minutes = date.getMinutes();
        let ampm = hours >= 12 ? 'pm' : 'am';
        hours = hours % 12;
        hours = hours ? hours : 12;
        minutes = minutes < 10 ? '0' + minutes : minutes;
        return `${hours}:${minutes} ${ampm}`;
    }

    // Toggle logic
    const weekCalculatorToggle = document.getElementById('weekCalculatorToggle');
    if (weekCalculatorToggle) {
        weekCalculatorToggle.addEventListener('change', (e) => {
            document.getElementById('weeklyCard').style.display = e.target.checked ? 'block' : 'none';
            if (!e.target.checked) {
                const sUpload = document.getElementById('screenshotUpload');
                if (sUpload) sUpload.value = '';
            }
        });
    }

    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        // Load Preference
        if (localStorage.getItem('theme') === 'dark') {
            document.body.classList.add('dark-mode');
            darkModeToggle.checked = true;
        }
        
        darkModeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                document.body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
            } else {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
            }
        });
    }
});
