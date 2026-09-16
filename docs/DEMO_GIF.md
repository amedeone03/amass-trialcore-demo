# Capture a ProtocolNeighbor demo GIF

Target path: `docs/assets/protocol-neighbor-demo.gif`  
Length: about 8–15 seconds.

Do not generate a fake UI image. Record the running app.

## Suggested flow

1. `streamlit run app.py` and open the local URL.
2. Show the proposed protocol panel.
3. Click **Find historical matches**.
4. Ranked historical matches appear (similarity + coverage).
5. Expand **Why this match?**
6. Change one protocol parameter.
7. Confirm the What-if neighborhood reranks.

## Capture (macOS)

QuickTime Player → File → New Screen Recording, crop to the browser window, export a short clip, then:

```bash
ffmpeg -i capture.mov -vf "fps=10,scale=960:-1:flags=lanczos" -loop 0 docs/assets/protocol-neighbor-demo.gif
```

Keep the file reasonably small. After the GIF exists, replace the screenshot-first block in `README.md` with the GIF near the top.
