#!/usr/bin/env python3
"""Build the final banner (ingest/banner.py) and demo GIF (demo/demo.gif).

Layout: parrot (left) + ansi_shadow "Doppel"/"ganger" (right), amber wordmark,
tagline centered beneath. Renders the GIF with agg's dracula theme.
"""
import json
import os
import subprocess

import pyfiglet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "venv", "bin", "python")
AGG = "/tmp/agg"
GAP = "   "
TAG = "fine-tune an LLM to write like you"
CMD = "python -m ingest --source telegram --input demo/sample_export.json"
AMBER, RESET = "\x1b[1;38;2;242;176;76m", "\x1b[0m"

with open(os.path.join(ROOT, "demo/mascot.txt"), encoding="utf-8") as _f:
    parrot = _f.read().rstrip("\n").split("\n")
PW = max(len(l) for l in parrot)


def _fig(t):
    ls = [l.rstrip() for l in pyfiglet.figlet_format(t, font="ansi_shadow", width=200).rstrip("\n").split("\n")]
    while ls and not ls[-1].strip(): ls.pop()
    while ls and not ls[0].strip(): ls.pop(0)
    return ls


word = _fig("Doppel") + _fig("ganger")
TOP = (len(parrot) - len(word)) // 2
TOTAL_W = PW + len(GAP) + max(len(l) for l in word)


def rows(on, off):
    r = []
    for i, pl in enumerate(parrot):
        wl = word[i - TOP] if 0 <= i - TOP < len(word) else ""
        wl = f"{on}{wl}{off}" if wl else ""
        r.append((pl.ljust(PW) + GAP + wl).rstrip())
    r.append("")
    r.append(TAG.center(TOTAL_W).rstrip())  # tagline centred under the whole logo
    return r


def write_banner_module():
    body = "\n".join(rows("<C>", "<R>"))  # sentinels; colourised at runtime
    mod = (
        '"""ASCII startup banner: a parrot in a mirror (it mimics your voice; the\n'
        'mirror is the doppelganger) beside the wordmark. The wordmark is amber via\n'
        'truecolor ANSI. Regenerate via demo/build_final.py.\n'
        'Set DOPPELGANGER_NO_BANNER=1 to silence it."""\n\n'
        'import os\n\n'
        '_AMBER = "\\x1b[1;38;2;242;176;76m"  # truecolor amber\n'
        '_RESET = "\\x1b[0m"\n\n'
        '_BANNER = r"""\n' + body + '\n"""\n\n\n'
        'def print_banner() -> None:\n'
        '    if os.environ.get("DOPPELGANGER_NO_BANNER"):\n'
        '        return\n'
        '    print(_BANNER.replace("<C>", _AMBER).replace("<R>", _RESET) + "\\n")\n'
    )
    open(os.path.join(ROOT, "ingest/banner.py"), "w", encoding="utf-8").write(mod)


def render_gif():
    env = dict(os.environ, LLM_VALIDATE="false", DOPPELGANGER_NO_BANNER="1")
    out = subprocess.run([PY] + CMD.split()[1:], cwd=ROOT, env=env, capture_output=True, text=True)
    report = ((out.stdout or "") + (out.stderr or "")).split("\n")

    events, t = [], 0.0
    def emit(d, dt):
        nonlocal t
        t += dt
        events.append([round(t, 3), "o", d])
    emit("\x1b[32m$\x1b[0m ", 0.3)
    for ch in CMD:
        emit(ch, 0.026)
    emit("\r\n", 0.5)
    for line in rows(AMBER, RESET) + report:
        emit(line + "\r\n", 0.05)
    emit("\x1b[32m$\x1b[0m ", 1.6)

    cast = os.path.join(ROOT, "demo/demo.cast")
    with open(cast, "w", encoding="utf-8") as f:
        f.write(json.dumps({"version": 2, "width": 94, "height": 34}) + "\n")
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    subprocess.run([AGG, "--font-size", "18", "--theme", "dracula", cast,
                    os.path.join(ROOT, "demo/demo.gif")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    write_banner_module()
    render_gif()
    print("=== layout preview ===")
    print("\n".join(rows("", "")))
