<p align="center">
  <img src="docs/landing.png" alt="TrialTwin matching a protocol to historical Alzheimer's Phase III trials" width="920">
</p>

<h1 align="center">TrialTwin</h1>

<p align="center">
  <strong>Stress-test a proposed Alzheimer's Phase III protocol against history.</strong>
</p>

<p align="center">
  <a href="https://amedeone03-amass-trialcore-demo-app-yxl5za.streamlit.app/">
    <img alt="Live demo" src="https://img.shields.io/badge/LIVE%20DEMO-Open%20TrialTwin-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white">
  </a>
</p>

<p align="center">
  <img alt="2nd place" src="https://img.shields.io/badge/DTU%20Skylab-2nd%20place-7C3AED?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Amass" src="https://img.shields.io/badge/data-Amass%20TrialCore-06B6D4?style=flat-square">
</p>

<p align="center">
  <em>AI in Life Sciences</em> · DTU Skylab × Cursor × Amass · September 2026
</p>

---

## What this app is

TrialTwin is a **historical protocol sandbox**. You describe a hypothetical Alzheimer's Phase III trial. The app finds past trials whose *designs* look most like yours, then lets you change one setting and see whether that set of lookalikes changes.

It compares **protocols**, not patients and not drugs' efficacy.

**The app is saying:**  
*If you design a trial like this, these past trials look most like it.*

**When you change a parameter, it is saying:**  
*That change made your design look like a different set of past trials.*

It is **not** saying the protocol will succeed, that a drug is better, or that 95% similarity means a 95% chance of working. The number is only how alike the designs are on the fields both sides actually have.

---

## What you compare

The same design fields on your hypothetical protocol and on each historical trial:

| Field | Role |
| --- | --- |
| Disease and phase | Locked here to Alzheimer's · Phase III |
| Disease stage | Early vs late |
| Biomarker confirmation | Required or not |
| Duration | Follow-up in months |
| Primary endpoint | CDR-SB or ADAS-Cog |
| Sample size | Planned enrollment |
| Target | Intervention / target name |

Each field is **exact**, **similar** (numbers only), **different**, or **unknown**. Unknown values are left out of the score instead of being guessed.

**Why compare them?** A protocol is a bundle of choices. The only way this prototype can “test” a choice is to ask: *if I set the knobs this way, which registered or completed trials look like that bundle?* That is the neighborhood. Changing one knob is useful only if you can see the neighborhood move.

---

## How to use it

1. Open the [live demo](https://amedeone03-amass-trialcore-demo-app-yxl5za.streamlit.app/).
2. Set the knobs on the left, or click **Demo scenario**.
3. **Find historical matches** loads Alzheimer's Phase III records from [Amass TrialCore](https://amass.tech) when a key is available, otherwise a small labeled prototype set.
4. Open **Why this match?** — that table *is* the score.
5. Change **one** control. **What if?** shows who entered and left the top three.

<p align="center">
  <img src="docs/what-if.png" alt="What-if: duration 18 to 36 months moves the neighborhood" width="920">
</p>

---

## How scoring works

The scorer in `trialtwin/engine.py` is a **weighted checklist**, not a learned model. It answers: *on the fields we can see, how much does this historical protocol look like yours?* The result is a number in 0–100%. It is **not** a probability that the trial succeeds.

### 1. Compare each field

| Field | Weight | How it scores |
| --- | ---: | --- |
| Disease stage | 20% | Exact match or 0 |
| Biomarker confirmation | 20% | Exact match or 0 |
| Disease | 15% | Exact match or 0 |
| Primary endpoint | 15% | Exact match or 0 |
| Phase | 10% | Exact match or 0 |
| Duration | 10% | Partial: `max(0, 1 − \|your months − theirs\| / 18)` |
| Sample size | 5% | Partial: `max(0, 1 − \|your N − theirs\| / 2000)` |
| Target | 5% | Exact match or 0 |

Weights add to 100%. Categories are all-or-nothing. Numbers fade linearly: 18 vs 18 months is full credit; 18 vs 36 months is 0 duration credit.

Each row is tagged **exact**, **similar** (numbers only), **different**, or **unknown**.

### 2. Drop unknowns, then renormalize

If a field is missing on either side (`unknown`, empty, or `ambiguous: …`), it is **not guessed**. That weight is taken out of the denominator, and the remaining weights are scaled so they still sum to 1.

Example: live TrialCore often has no stage and no biomarker (40% of the checklist). Those 40% are dropped. Disease + phase still match almost every Alzheimer's Phase III row, so they suddenly make up a large share of the score. That is why live matches can sit in the 85–97% band even when the drugs are unrelated.

### 3. Add it up and rank

For every historical trial:

`similarity = sum( (weight / comparable_weights) × field_score )`

Trials are sorted by that score, then by trial id. The UI shows the top three as the **historical neighborhood**. **What if?** runs the same ranking twice (before vs after one knob) and reports which neighbors moved.

**Why this match?** is the honest view of the percentage: green checks are the weight you actually received; question marks did not enter the score.

---

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional: copy `.env.example` to `.env` and set `AMASS_API_KEY`. Without a key, the app uses `trialtwin/data/alzheimer_trials.json`.

```bash
python -m unittest discover -s trialtwin/tests -v
```

Prototype — not medical software.
