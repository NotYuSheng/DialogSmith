# demo/

Assets and the (dev-only) scripts used to generate the README banner/GIF. None of
this is needed to run Doppelganger — it's tooling for regenerating the visuals.

| File | What it is |
|------|------------|
| `parrot-mirror.jpg` | Source image for the mascot |
| `mascot.txt` | The parrot converted to braille ASCII (committed art) |
| `sample_export.json` | **Synthetic** Telegram export used by the demo (safe, fake PII) |
| `demo.gif` | The README demo (ingest + sensitive-data scan) |
| `img2ascii.py` | Convert an image to ASCII (brightness ramp) |
| `build_final.py` | Rebuild `ingest/banner.py` and `demo/demo.gif` |

## Regenerating

These scripts need extra dev dependencies that the app itself does **not** require:

```bash
pip install pillow pyfiglet          # img2ascii.py / build_final.py
# plus the asciinema 'agg' renderer (https://github.com/asciinema/agg):
#   cargo install --git https://github.com/asciinema/agg
#   or download a release binary and set:  export AGG=/path/to/agg
```

Then:

```bash
python demo/img2ascii.py parrot-mirror.jpg 72   # preview the mascot conversion
python demo/build_final.py                      # rewrite the banner + demo.gif
```
