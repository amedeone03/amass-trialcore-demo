# Capture the TrialTwin demo GIF

Recommended recording: 10–15 seconds.

Use **Run demo**. It is deterministic, local, and synthetic. It does not need Amass.

Target path: `docs/assets/trialtwin-demo.gif`

Do not generate a fake UI image. Record the real running app.

## Scenario (real engine, not staged ranks)

Scenario A: Late · amyloid-beta · ADAS-Cog · 12 months · biomarker **Required**.

Scenario B: the same protocol except biomarker **Not required**.

That one field swap is the strongest honest neighborhood movement on the bundled six-record set: all three top neighbors change, and the top match changes.

## Exact flow

1. Open the deployed or local app (`streamlit run app.py`).
2. Position the browser at about 90% zoom if needed (~1100–1400 px wide).
3. Show the TrialTwin hero and protocol panel (0–2 s).
4. Click **Run demo**.
5. Pause briefly on historical match cards, similarity, and coverage (4–6 s).
6. Open **Why this match?** to show the **Match profile** radar (6–8 s).
7. Show the protocol change card: Biomarker confirmation **Required → Not required** (8–10 s).
8. Show **Historical neighborhood shift** and **3 of 3 top historical neighbors changed**.
9. End on the rank-flow graph (10–14 s). Do not open **Explore evidence** or the scatter plot — the synthetic demo hides it because coverage does not vary.
10. Stop recording.

Do not show the terminal, API keys, desktop clutter, Streamlit errors, long loading delays, or unrelated tabs.

## macOS recording

QuickTime Player → File → New Screen Recording.

Record only the browser region.

Save as `trialtwin-demo.mov` in the repo root.

```bash
brew install ffmpeg   # if ffmpeg is missing

ffmpeg -i trialtwin-demo.mov \
  -vf "fps=10,scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
  -loop 0 \
  docs/assets/trialtwin-demo.gif
```

If the GIF is too large, use `fps=8` and `scale=850:-1`.

```bash
ls -lh docs/assets/trialtwin-demo.gif

git add docs/assets/trialtwin-demo.gif README.md
git commit -m "Add TrialTwin demo GIF"
git push
```

After the GIF exists, use it near the top of `README.md` in place of the hero screenshot.
