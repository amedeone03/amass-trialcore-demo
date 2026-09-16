# TrialTwin

### Historical benchmarking for clinical-trial design

🥈 **2nd Place · 16 September 2026**  
**AI in Life Sciences Hackathon**  
Copenhagen, Denmark

<p align="center">
  <img src="docs/assets/dtu-skylab-logo.png"
       alt="DTU Skylab"
       height="42">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/assets/cursor-logo.svg"
       alt="Cursor"
       height="44">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/assets/amass-logo.svg"
       alt="Amass"
       height="36">
</p>

> **Change your protocol. See which historical trials it starts to resemble.**

TrialTwin is an interactive sandbox for comparing a hypothetical clinical-trial protocol with historical trial designs. It finds the closest historical neighbors, explains what drives each match, and shows how the neighborhood changes when one design decision changes.

<p align="center">
  <a href="https://amedeone03-amass-trialcore-demo-app-yxl5za.streamlit.app/">
    <img alt="Live demo" src="https://img.shields.io/badge/LIVE%20DEMO-Open%20TrialTwin-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white">
  </a>
</p>

<p align="center">
  <img src="docs/assets/trialtwin-demo.gif"
       alt="TrialTwin demo: protocol design, match profile, and historical neighborhood shift"
       width="920">
</p>

## What TrialTwin does

A researcher defines a hypothetical **Alzheimer's disease Phase III** protocol using characteristics such as:

- disease stage
- biomarker confirmation
- duration
- primary endpoint
- sample size
- intervention

TrialTwin compares that design with historical trial records and surfaces the closest matches.

For each match, it shows where the resemblance comes from. Change one protocol decision and TrialTwin recomputes the historical neighborhood, making the resulting rank shift visible.

## How it works

**Design → Match → Explain → What-if**

**Design** a hypothetical protocol.  
**Match** it against retrieved historical trial designs.  
**Explain** feature-level resemblance and source evidence.  
**What-if** one design decision changes? Recompute the neighborhood and visualize which trials move in or out.

Alzheimer's disease and Phase III define the candidate pool; they are not part of the similarity score.

## Similarity vs coverage

| Metric | Meaning |
| --- | --- |
| **Historical similarity** | Resemblance among fields that can actually be compared |
| **Comparison coverage** | How much of the intended comparison had usable historical data |

> **High similarity does not necessarily mean high comparison coverage.**

See [`docs/SCORING.md`](docs/SCORING.md) for the scoring methodology.

## Under the hood

| Layer | Role |
| --- | --- |
| **Streamlit** | Interactive protocol and what-if interface |
| **Amass TrialCore** | Historical clinical-trial records |
| **TrialTwin Python package** | Normalization, similarity, ranking, and explanation |
| **Local synthetic dataset** | Deterministic demo mode |
| **Plotly** | Match-profile and neighborhood-shift visualizations |

The matching pipeline preserves missing information rather than silently inventing clinical values.

## Data modes

| Mode | Data source | Purpose |
| --- | --- | --- |
| **Live Amass** | Amass TrialCore | Explore retrieved historical trial records |
| **Run demo** | Bundled synthetic records | Deterministic, reproducible walkthrough |

`Run demo` never calls Amass.

Where available, live records include registry provenance and source links.

## Quick start

```bash
git clone https://github.com/amedeone03/trialtwin.git
cd trialtwin

python3 -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

streamlit run app.py
```

`AMASS_API_KEY` is optional for the synthetic demo. Live Amass mode requires it in `.env`.

Run the test suite:

```bash
python -m unittest discover -s trialtwin/tests -v
```

## Team

**Amedeo Bozzoli · Christian Deluca · Marcos Cuervo Santos**

Built in one day at the **AI in Life Sciences Hackathon** at DTU Skylab on 16 September 2026.

## Scope

- Research/hackathon prototype, not a clinical decision-support product.
- Historical similarity is **not** a probability of trial success.
- Live TrialCore fields may be incomplete.
- Candidate retrieval is capped (`TRIALTWIN_CANDIDATE_LIMIT`, default `100`), not exhaustive.

## License

MIT. See [`LICENSE`](LICENSE). The license covers this source code, not Amass data or third-party services.
