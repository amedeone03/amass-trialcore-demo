# TrialTwin

**Historical protocol sandbox for Alzheimer's Phase III trial design.**

TrialTwin lets you propose a hypothetical protocol, find the closest historical trials, and change one design choice to see whether that **neighborhood** moves.

It compares **designs**, not outcomes. Similarity is resemblance, not a probability of success.

2nd place · [AI in Life Sciences](https://www.skylab.dtu.dk/) hackathon at DTU Skylab (Cursor × Amass) · September 2026

---

## What the app is saying

> If you design a trial like this, these past trials look most like it.  
> Change one parameter, and you may now sit next to a different set of historical trials.

It is **not** saying the protocol will work, that a drug is better, or that 95% similarity means a 95% chance of success.

---

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

**Find historical matches** loads live Alzheimer's Phase III records from [Amass TrialCore](https://amass.tech) when `AMASS_API_KEY` is set. If the API is unavailable, the app falls back to a labeled prototype dataset.

**Demo scenario** picks a one-parameter flip that actually moves the top matches.

### Live Amass (optional)

```bash
cp .env.example .env
# put your TrialCore key in .env
```

```
AMASS_API_KEY=your_key_here
```

Without a key, use **Demo scenario** or expect the local JSON fallback.

### Offline pipeline (no UI)

```bash
python demo.py
python -m unittest discover -s trialtwin/tests -v
```

---

## How it works

1. You set a locked **Alzheimer's disease · Phase III** protocol (stage, biomarker, duration, endpoint, sample size, target).
2. TrialTwin scores every historical trial with a **transparent weighted heuristic** (exact / similar / different / unknown per feature).
3. You see the top neighbors, a feature-by-feature “why this match?”, and a descriptive outcome profile when labels exist.
4. **What if?** freezes the first search, then re-ranks after you change a control.

Matching lives in `trialtwin/engine.py`. The Streamlit app does not score. The Amass adapter does not invent clinical fields: missing values stay `unknown` / `None`.

Live TrialCore does **not** classify success or failure, and often has no structured disease stage or biomarker flag. Those gaps are shown as unknown. The mock file `trialtwin/data/alzheimer_trials.json` is synthetic and labeled for the sandbox only.

---

## Repository layout

```
app.py                      Streamlit entrypoint
demo.py                     Offline ranking + what-if (local JSON)
requirements.txt
.env.example
trialtwin/
  app.py                    UI
  engine.py                 Similarity, ranking, scenario compare
  models.py                 Protocol and HistoricalTrial
  amass_client.py           TrialCore HTTP + local fallback
  normalize.py              Amass JSON → HistoricalTrial
  data/alzheimer_trials.json
  tests/
```

---

## Team

Built in one afternoon at DTU Skylab: students using Cursor and Amass TrialCore. Prototype, not medical software.
