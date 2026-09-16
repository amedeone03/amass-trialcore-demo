# Capture the TrialTwin demo GIF

Recommended recording: 8–15 seconds.

Use **Demo scenario** because it is deterministic and does not need Amass.

Target path: `docs/assets/trialtwin-demo.gif`

Do not generate a fake UI image. Record the real running app.

## Exact flow

1. Start the app: `streamlit run app.py`
2. Open the app in the browser.
3. Ensure the TrialTwin title is visible.
4. Click **Demo scenario**.
5. Show historical match cards, similarity, and coverage.
6. Open **Why this match?**
7. Close it if necessary.
8. Show the preset what-if change (biomarker Required → Not required).
9. Show **historical neighborhood changed**.
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
