#!/usr/bin/env python3
"""Build the CLI banner (ingest/banner.py) and the README title-card GIF.

- ingest/banner.py: lean parrot + amber wordmark, printed at CLI startup.
- demo/demo.gif: a richer "title card" — tagline, parrot + gradient wordmark,
  a keyword line, a version box, and a made-by line — rendered with agg.
"""
import json
import os
import subprocess

import pyfiglet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG = os.environ.get("AGG", "agg")
GAP = "   "

TAGLINE = "fine-tune an LLM on your chat history to write like you"
KEYWORDS = "ingest  ·  scan  ·  redact  ·  audit  ·  fine-tune"
VERSIONS = "Python 3.11–3.13   ·   LLaMA-Factory 0.9.4   ·   local LLM"
MADEBY = "made by @NotYuSheng"

AMBER = (242, 176, 76)
GRAD0, GRAD1 = (255, 196, 84), (233, 84, 64)   # gold -> coral, vertical gradient
DIM = (140, 140, 150)

RESET = "\x1b[0m"

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
WW = max(len(l) for l in word)
BLOCK_W = PW + len(GAP) + WW


def _solid(rgb, s):
    return f"\x1b[1;38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{s}{RESET}" if s.strip() else s


def _lerp(t):
    """Colour at fraction t along the top->bottom gradient."""
    return tuple(round(GRAD0[k] + (GRAD1[k] - GRAD0[k]) * t) for k in range(3))


def _center(plain, rgb=None, width=BLOCK_W):
    pad = max(0, (width - len(plain)) // 2)
    body = _solid(rgb, plain) if rgb else plain
    return " " * pad + body


def lean_rows(on, off):
    """Parrot + wordmark only (for the CLI banner)."""
    r = []
    for i, pl in enumerate(parrot):
        wl = word[i - TOP] if 0 <= i - TOP < len(word) else ""
        wl = f"{on}{wl}{off}" if wl else ""
        r.append((pl.ljust(PW) + GAP + wl).rstrip())
    return r


def card_rows():
    """The richer title card (coloured) for the GIF."""
    rows = ["", _center(TAGLINE, DIM), ""]
    n = max(1, len(word) - 1)
    for i, pl in enumerate(parrot):
        j = i - TOP
        wl = _solid(_lerp(j / n), word[j]) if 0 <= j < len(word) else ""
        rows.append(pl.ljust(PW) + GAP + wl)
    rows += ["", _center(KEYWORDS, AMBER), ""]
    box = len(VERSIONS) + 2
    rows.append(_center("┌" + "─" * box + "┐", DIM))
    rows.append(_center("│ " + VERSIONS + " │", DIM))
    rows.append(_center("└" + "─" * box + "┘", DIM))
    rows += ["", _center(MADEBY, DIM)]
    return rows


def write_banner_module():
    body = "\n".join(lean_rows("<C>", "<R>"))
    mod = (
        '"""ASCII startup banner: a parrot in a mirror (it mimics your voice; the\n'
        'mirror is the doppelganger) beside the wordmark, in truecolor amber.\n'
        'Regenerate via demo/build_final.py. DOPPELGANGER_NO_BANNER=1 silences it."""\n\n'
        'import os\n\n'
        '_AMBER = "\\x1b[1;38;2;242;176;76m"  # truecolor amber\n'
        '_RESET = "\\x1b[0m"\n\n'
        '_BANNER = r"""\n' + body + '\n"""\n\n\n'
        'def print_banner() -> None:\n'
        '    if os.environ.get("DOPPELGANGER_NO_BANNER"):\n'
        '        return\n'
        '    print(_BANNER.replace("<C>", _AMBER).replace("<R>", _RESET) + "\\n")\n'
    )
    with open(os.path.join(ROOT, "ingest/banner.py"), "w", encoding="utf-8") as f:
        f.write(mod)


def render_gif():
    card = card_rows()
    events, t = [], 0.0
    def emit(d, dt):
        nonlocal t
        t += dt
        events.append([round(t, 3), "o", d])
    emit("\x1b[?25l", 0.2)            # hide cursor
    for line in card:
        emit(line + "\r\n", 0.08)
    emit("", 2.4)                     # hold on the finished card
    emit("\x1b[?25h", 0.0)            # restore cursor

    cast = os.path.join(ROOT, "demo/demo.cast")
    with open(cast, "w", encoding="utf-8") as f:
        f.write(json.dumps({"version": 2, "width": BLOCK_W + 6, "height": len(card) + 2}) + "\n")
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    subprocess.run(
        [AGG, "--font-size", "18", "--theme", "dracula", cast,
         os.path.join(ROOT, "demo/demo.gif")],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True,
    )


if __name__ == "__main__":
    write_banner_module()
    render_gif()
    print("\n".join(r for r in card_rows()))
