# Capture a TrialTwin demo GIF

Target path: `docs/assets/trialtwin-demo.gif`

Target duration: 8–15 seconds.

Do not generate a fake UI image. Record the real running app.

## Suggested flow

1. Run:
   `streamlit run app.py`
2. Show the hypothetical protocol.
3. Click **Find historical matches**.
4. Show historical similarity + comparison coverage.
5. Expand **Why this match?**
6. Expand **Evidence**.
7. Change one protocol parameter.
8. Show the historical neighborhood rerank.

## Capture (macOS)

QuickTime Player → File → New Screen Recording, crop to the browser window, export a short clip, then:

```bash
ffmpeg -i capture.mov -vf "fps=10,scale=960:-1:flags=lanczos" -loop 0 docs/assets/trialtwin-demo.gif
```

Keep the file reasonably small. After the GIF exists, it can replace the hero screenshot in `README.md`.
