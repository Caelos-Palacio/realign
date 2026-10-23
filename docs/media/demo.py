#!/usr/bin/env python3
# ---- suite kit (identical in every repo): 800x450, 15 fps, pure render(t) -> image ----
import os, sys, shutil, subprocess, tempfile, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, S = 800, 450, 15, 2          # S = supersampling factor
BG, TEXT, MUTED = '#0d1117', '#e6edf3', '#8b949e'
ACCENT, OK, ERROR, WARN = '#58a6ff', '#3fb950', '#f85149', '#d29922'
FONT_DIRS = [Path.home() / '.local/share/fonts/JetBrainsMonoNerd']
FALLBACK = ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
FONT_FILES = {False: 'JetBrainsMonoNerdFont-Regular.ttf', True: 'JetBrainsMonoNerdFont-Bold.ttf'}


def rgb(h, a=1.0):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(255 * max(0, min(1, a))))


def clamp(x): return max(0.0, min(1.0, x))
def seg(t, a, b): return clamp((t - a) / (b - a))
def ease(x): x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2   # cubic in-out
def lerp(a, b, k): return a + (b - a) * k
def typed(s, t, t0, cps=55): return s[:max(0, int((t - t0) * cps))]


_fonts = {}
def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        cands = [d / FONT_FILES[bold] for d in FONT_DIRS] + [Path(p) for p in FALLBACK]
        path = next(p for p in cands if p.exists())
        _fonts[key] = ImageFont.truetype(str(path), round(size * S))
    return _fonts[key]


class Cv:
    def __init__(self):
        self.img = Image.new('RGB', (W * S, H * S), BG)
        self.d = ImageDraw.Draw(self.img, 'RGBA')

    def text(self, x, y, s, size=13, color=TEXT, a=1.0, bold=False, anchor='la'):
        if a > .01 and s:
            self.d.text((x * S, y * S), s, font=font(size, bold), fill=rgb(color, a), anchor=anchor)

    def width(self, s, size=13, bold=False): return font(size, bold).getlength(s) / S

    def box(self, x0, y0, x1, y1, outline=MUTED, a=1.0, fill=None, fa=1.0, r=6, w=1):
        self.d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S,
                                 outline=rgb(outline, a), width=round(w * S),
                                 fill=rgb(fill, fa) if fill else None)

    def line(self, x0, y0, x1, y1, color=MUTED, a=1.0, w=1, dash=0):
        if not dash:
            self.d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=rgb(color, a), width=round(w * S))
            return
        n = int(max(abs(x1 - x0), abs(y1 - y0)) // dash)
        for i in range(0, n, 2):
            p, q = i / n, min(1, (i + 1) / n)
            self.d.line([lerp(x0, x1, p) * S, lerp(y0, y1, p) * S, lerp(x0, x1, q) * S, lerp(y0, y1, q) * S],
                        fill=rgb(color, a), width=round(w * S))

    def arrow(self, x0, y0, x1, y1, color=MUTED, a=1.0):
        self.line(x0, y0, x1, y1, color, a)
        s = 1 if x1 > x0 else -1
        self.d.polygon([(x1 * S, y1 * S), ((x1 - 7 * s) * S, (y1 - 4) * S), ((x1 - 7 * s) * S, (y1 + 4) * S)], fill=rgb(color, a))

    def dot(self, x, y, color=ACCENT, a=1.0, r=4.5):
        self.d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=rgb(color, a))
        self.d.ellipse([(x - r * 2) * S, (y - r * 2) * S, (x + r * 2) * S, (y + r * 2) * S], fill=rgb(color, a * .16))


def envelope(t, T, fade=.5):
    """Loop envelope: blank at t=0 and t=T, so the GIF loops seamlessly."""
    return ease(seg(t, 0, fade)) * (1 - ease(seg(t, T - fade, T)))


def finish(cv, t, T):
    blank = Image.new('RGB', cv.img.size, BG)
    img = Image.blend(blank, cv.img, envelope(t, T))
    return img.resize((W, H), Image.LANCZOS)


def build(render, T, out, frame=None):
    if frame is not None:
        render(frame).save(out); return
    n = round(T * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            render(i / FPS).save(f'{tmp}/f{i:04d}.png')
        pal = f'{tmp}/pal.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', f'{tmp}/f%04d.png',
                        '-vf', 'palettegen=max_colors=128:stats_mode=full', pal], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', f'{tmp}/f%04d.png', '-i', pal,
                        '-lavfi', 'paletteuse=dither=none', '-loop', '0', str(out)], check=True)
    print(f'{out}: {n} frames, {T}s, {Path(out).stat().st_size / 1e6:.2f} MB')


def cli(render, T, default_out):
    a = sys.argv[1:]
    if a[:1] == ['--frame']:          # python demo.py --frame 5.5 out.png
        build(render, T, a[2], float(a[1]))
    else:
        build(render, T, a[0] if a else default_out)
# ---- end kit ----

# ---- local helpers (per-demo): terminal panel, node boxes ----
HERE = Path(__file__).resolve().parent
PANEL, LINE = '#161b22', '#30363d'


def header(cv, title, subtitle):
    cv.text(32, 20, title, 22, ACCENT)
    cv.text(32, 52, subtitle, 13, MUTED)
    cv.line(32, 82, W - 32, 82, LINE)


def panel(cv, box, label):
    x0, y0, x1, y1 = box
    cv.box(x0, y0, x1, y1, LINE, 1, fill=PANEL, r=8)
    cv.text(x0 + 14, y0 + 8, label, 11, MUTED)


def node(cv, x0, y0, x1, y1, label, sub, color, idle=False):
    cv.box(x0, y0, x1, y1, LINE if idle else color, 1, fill=PANEL, r=6, w=2)
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    cv.text(cx, cy - 10, label, 13, MUTED if idle else TEXT, anchor='mm')
    if sub:
        cv.text(cx, cy + 12, sub, 12, MUTED if idle else color, anchor='mm')


def _plain(cv, x, y, s, size, color, a):
    """terminal text without programming ligatures (so '<!--' stays literal)"""
    if a <= .01 or not s:
        return
    try:
        cv.d.text((x * S, y * S), s, font=font(size), fill=rgb(color, a), features=['-liga', '-calt'])
    except (KeyError, ValueError, OSError):
        cv.text(x, y, s, size, color, a)


def term(cv, t, lines, x, y, lh, size, cps=55, al=1.0):
    """lines: [{t, segs:[(text,color)], type?}]; typed lines reveal at cps with a block cursor."""
    cur = None
    for i, L in enumerate(lines):
        if t < L['t']:
            break
        segs = L['segs']
        n = sum(len(s) for s, _ in segs)
        k = n if not L.get('type') else min(n, max(0, int((t - L['t']) * cps)))
        if L.get('type') and k < n + 1:
            cur = (i, k)
        cx = x
        left = k
        for s, c in segs:
            if left <= 0:
                break
            part = s[:left]
            _plain(cv, cx, y + i * lh, part, size, c, al)
            cx += cv.width(part, size)
            left -= len(s)
    if cur and int(t * 2.5) % 2 == 0:
        i, k = cur
        cx = x + cv.width('M', size) * k
        cv.d.rectangle([(cx + 1) * S, (y + i * lh + 1) * S, (cx + 8) * S, (y + i * lh + size + 3) * S], fill=rgb(TEXT, .8 * al))


def window(t, a, b, f=.35):
    return ease(seg(t, a, a + f)) * (1 - ease(seg(t, b - f, b)))


def wrap(s, cols):
    out, cur = [], ''
    for w in s.split(' '):
        if cur and len(cur) + 1 + len(w) > cols:
            out.append(cur); cur = w
        else:
            cur = (cur + ' ' + w).strip()
    return out + [cur]

# ---------------------------------------------------------------------------
# realign demo.
#   python3 docs/media/demo.py capture   -> runs the REAL CLI on a copy of examples/, writes capture.json
#   python3 docs/media/demo.py [out.gif] -> renders docs/media/demo.gif from capture.json
#   python3 docs/media/demo.py --frame 5.5 out.png   (single frame)
# render(t) is a pure function of time; no randomness, no wall clock.
# ---------------------------------------------------------------------------
CAP = HERE / 'capture.json'
SRC = HERE.parent.parent / 'src'
GROUPS = [[0, 1], [2, 3], [4]]
COMMANDS = [
    "grep realign:version examples/README.md",
    "realign check --root examples --json | grep -E '\"(status|code)\"'",
    'realign fix --root examples --json | grep status',
    "grep realign:version examples/README.md",
    'realign check --root examples',
]


def capture():
    root = Path(tempfile.mkdtemp(prefix='realign-demo-'))
    shutil.copytree(HERE.parent.parent / 'examples', root / 'examples', ignore=shutil.ignore_patterns('behavior'))
    bindir = root / 'bin'; bindir.mkdir()
    (bindir / 'realign').write_text(f'#!/bin/sh\nPYTHONPATH={SRC} exec python3 -m realign "$@"\n')
    (bindir / 'realign').chmod(0o755)
    env = {**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}'}
    steps = []
    for c in COMMANDS:
        r = subprocess.run(['bash', '-c', 'set -o pipefail; ' + c], cwd=root, capture_output=True, text=True, env=env)
        steps.append({'cmd': c, 'out': r.stdout.rstrip('\n'), 'rc': r.returncode})
    CAP.write_text(json.dumps(steps, indent=2) + '\n')
    shutil.rmtree(root)


def colorize(line):
    if line.startswith('[exit 0'): return [(line, MUTED)]
    if line.startswith('[exit'): return [(line, ERROR)]
    if 'drift' in line.lower() or '"DRIFT"' in line: return [(line, ERROR)]
    if 'repaired' in line: return [(line, WARN)]
    if 'clean' in line or '1.0.0<!--' in line and 'Version: 1' in line: return [(line, OK)]
    if '0.0.0' in line: return [(line, ERROR)]
    return [(line, TEXT)]


def schedule(cap):
    """pure layout: per step start/out times; per group page window"""
    t = 0.5
    steps, pages = [], []
    for g in GROUPS:
        p0 = t - 0.2
        for i in g:
            n = len(cap[i]['cmd'])
            out_t = t + n / 55 + 0.35
            nlines = len(cap[i]['out'].split('\n')) + 1
            end = out_t + 0.14 * nlines
            steps.append({'i': i, 't': t, 'out': out_t, 'end': end})
            t = end + 0.3
        pages.append((p0, t + 0.5))
        t += 0.5
    return steps, pages


def render(t, cap=None):
    cap = cap or json.loads(CAP.read_text())
    steps, pages = schedule(cap)
    cv = Cv()
    header(cv, 'realign', 'declared file relations, checked; only derived blocks are repaired')
    panel(cv, (32, 96, 768, 266), 'examples/   output captured from the real CLI')
    for g, (a, b) in zip(GROUPS, pages):
        al = window(t, a, b)
        if al <= 0:
            continue
        lines, row = [], 0
        for i in g:
            s = next(x for x in steps if x['i'] == i)
            lines.append({'t': s['t'], 'type': True, 'segs': [('$ ', OK), (cap[i]['cmd'], TEXT)]})
            tt = s['out']
            for raw in cap[i]['out'].split('\n') + [f"[exit {cap[i]['rc']}]"]:
                lines.append({'t': tt, 'segs': colorize(raw.strip())})
                tt += 0.14
        # typed lines address row index; compact them by actual position
        term(cv, t, lines, 46, 122, 19, 12, al=al)
    out = {x['i']: x for x in steps}
    dy = 296
    drift_t, fix_t, clean_t = out[1]['out'] + 0.3, out[2]['out'] + 0.3, out[4]['out'] + 0.3
    node(cv, 32, dy, 242, dy + 84, 'manifest.json', 'version: 1.0.0', ACCENT)
    if t < drift_t: sub, c, idle = 'idle', LINE, True
    elif t < fix_t: sub, c, idle = 'drift (exit 1)', ERROR, False
    elif t < clean_t: sub, c, idle = 'repaired (exit 0)', WARN, False
    else: sub, c, idle = 'clean (exit 0)', OK, False
    node(cv, 295, dy, 505, dy + 84, 'realign', sub, c, idle=idle)
    good = t >= fix_t
    node(cv, 558, dy, 768, dy + 84, 'README block', 'Version: 1.0.0' if good else 'Version: 0.0.0', OK if good else ERROR)
    for (x0, x1, col, a, b) in ((242, 295, ACCENT, drift_t - 0.5, drift_t), (505, 558, WARN, fix_t - 0.5, fix_t)):
        p = ease(seg(t, a, b))
        if p > 0:
            cv.arrow(x0, dy + 42, x0 + (x1 - x0) * max(p, .05), dy + 42, col)
        if 0 < p < 1:
            cv.dot(x0 + (x1 - x0) * p, dy + 42, col)
    cv.text(32, 424, 'Python >= 3.11  |  standard library only  |  exit 0 clean/repaired, 1 drift, 2 error', 12, MUTED)
    return finish(cv, t, DURATION(cap))


def DURATION(cap):
    return round(schedule(cap)[1][-1][1] + 0.5, 1)


if __name__ == '__main__':
    if sys.argv[1:2] == ['capture']:
        capture()
    else:
        cli(render, DURATION(json.loads(CAP.read_text())), HERE / 'demo.gif')
