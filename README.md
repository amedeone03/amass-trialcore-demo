<p align="center">
  <img src="docs/landing.png" alt="TrialTwin matching a protocol to historical Alzheimer's Phase III trials" width="920">
</p>

<h1 align="center">TrialTwin</h1>

<p align="center">
  <strong>A historical protocol sandbox for Alzheimer's Phase III.</strong><br>
  Propose a trial design. See which past trials it resembles.<br>
  Change one knob — watch the neighborhood move.
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

### What it says

> If you design a trial like this, these past trials look most like it.  
> Change one parameter, and you may now sit next to a different set of historical trials.

Similarity is **resemblance**, not a probability of success. 95% does not mean the trial will work.

---

### What if?

<p align="center">
  <img src="docs/what-if.png" alt="What-if: one protocol change shifts the historical neighborhood" width="920">
</p>

<p align="center">
  <img src="docs/neighborhood-shift.png" alt="Before and after historical similarity" width="920">
</p>

---

### How it works

```mermaid
flowchart LR
  P[Your protocol] --> E[Explainable scorer]
  H[Amass TrialCore or local JSON] --> E
  E --> N[Closest historical neighbors]
  N --> W[What if? one design change]
  W --> N
```

Alzheimer's disease and Phase III stay locked. You set stage, biomarker, duration, endpoint, sample size, and target. Each historical trial is scored feature by feature (exact / similar / different / unknown). **Demo scenario** flips one parameter so the top matches actually move.

Live TrialCore often has no success/failure label, disease stage, or biomarker flag. Those stay `unknown`. The engine never invents clinical facts.

---

### Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional: copy `.env.example` to `.env` and set `AMASS_API_KEY`. Without it, the app uses `trialtwin/data/alzheimer_trials.json` (synthetic sandbox labels).

```bash
python -m unittest discover -s trialtwin/tests -v
```

Prototype — not medical software.
