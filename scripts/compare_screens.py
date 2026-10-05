#!/usr/bin/env python3
"""Compare two sets of screenshots and show what changed on screen.

Usage:
  python3 compare_screens.py --baseline <dir> --current <dir> [--out <dir>]
                             [--threshold 0.01] [--tolerance 24] [--json FILE]

Matches PNGs by file name (manual tours name them <tour>--<step>.png), so the
same screen is compared release to release. For each pair it reports the share
of pixels that changed — a pixel counts when any colour channel moved by more
than --tolerance (0–255), which ignores anti-aliasing noise — and calls the
screen changed at or above --threshold percent (default 0.01%, about 100
pixels of a 1280×800 screen: browsers render the same page identically, so a
restyled counter badge, about 0.08%, is caught while unchanged screens stay
at 0%). Changed screens get a diff
image in --out: the new screenshot faded, with every changed pixel in red.

Why: a UI change nobody asked for (a button moved, a label lost, a layout
broken) is invisible in a test that only checks behaviour. build_manual.py
--compare-to runs this against the previous release's screenshots, marks the
changed steps in the manuals, and the release-manager lists every changed
screen for a person to confirm.

Zero dependencies: decodes and writes PNG itself (8-bit, non-interlaced, which
is what browsers produce); uses Pillow instead when it is installed (faster).
Identical files are skipped without decoding. Exit 0 always (it reports, it
does not judge); --fail-on-change makes any changed screen exit 1.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path

SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


# ── PNG I/O ────────────────────────────────────────────────────────────────

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path: Path):
    """-> (width, height, rows) with rows as RGB bytes. Raises ValueError if unsupported."""
    try:
        if os.environ.get("ASDR_NO_PIL"):
            raise ImportError
        from PIL import Image  # fast path
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            raw = im.tobytes()
        return w, h, [raw[y * w * 3:(y + 1) * w * 3] for y in range(h)]
    except ImportError:
        pass
    data = path.read_bytes()
    if not data.startswith(SIG):
        raise ValueError("not a PNG")
    pos, idat, ihdr = 8, [], None
    while pos < len(data):
        n, = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + n
    if not ihdr:
        raise ValueError("no IHDR")
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or ctype not in CHANNELS or interlace:
        raise ValueError(f"unsupported PNG (depth {depth}, colour type {ctype}, interlace {interlace})")
    ch = CHANNELS[ctype]
    stride = w * ch
    raw = zlib.decompress(b"".join(idat))
    rows, prev = [], bytearray(stride)
    for y in range(h):
        start = y * (stride + 1)
        f = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif f == 3:
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                left = line[i - ch] if i >= ch else 0
                upleft = prev[i - ch] if i >= ch else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
        rows.append(bytes(line))
        prev = line
    if ch == 3:
        return w, h, rows
    rgb = []
    for r in rows:
        if ch == 4:
            rgb.append(b"".join(r[i:i + 3] for i in range(0, len(r), 4)))
        elif ch == 1:
            rgb.append(bytes(v for g in r for v in (g, g, g)))
        else:
            rgb.append(bytes(v for i in range(0, len(r), 2) for v in (r[i], r[i], r[i])))
    return w, h, rgb


def write_png(path: Path, w: int, h: int, rows) -> None:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


FADE = bytes((b + 2 * 255) // 3 for b in range(256))   # fade toward white
RED = b"\xe5\x48\x4d"


# ── comparison ─────────────────────────────────────────────────────────────

def compare_pair(a: Path, b: Path, diff_out: Path | None, tolerance: int) -> dict:
    if a.read_bytes() == b.read_bytes():
        return {"pct": 0.0, "identical": True}
    try:
        wa, ha, ra = read_png(a)
        wb, hb, rb = read_png(b)
    except (ValueError, zlib.error) as e:
        return {"pct": 100.0, "note": f"could not decode: {e}"}
    if (wa, ha) != (wb, hb):
        return {"pct": 100.0, "note": f"size changed {wa}x{ha} → {wb}x{hb}",
                "size_before": [wa, ha], "size_after": [wb, hb]}
    changed, out_rows = 0, []
    for y in range(hb):
        row_a, row_b = ra[y], rb[y]
        faded = row_b.translate(FADE)
        if row_a == row_b:
            out_rows.append(faded)
            continue
        line = bytearray(faded)
        for x in range(0, wb * 3, 3):
            if (abs(row_a[x] - row_b[x]) > tolerance or abs(row_a[x + 1] - row_b[x + 1]) > tolerance
                    or abs(row_a[x + 2] - row_b[x + 2]) > tolerance):
                changed += 1
                line[x:x + 3] = RED
        out_rows.append(bytes(line))
    pct = round(100.0 * changed / (wb * hb), 3)
    res = {"pct": pct, "pixels": changed}
    if diff_out is not None and changed:
        write_png(diff_out, wb, hb, out_rows)
        res["diff"] = diff_out.name
    return res


def compare_dirs(baseline: Path, current: Path, out: Path | None, threshold: float = 0.01,
                 tolerance: int = 24, only: set | None = None) -> dict:
    """only: limit the current side to these file names (screens actually in use)."""
    old = {p.name: p for p in sorted(baseline.glob("*.png"))} if baseline.is_dir() else {}
    new = {p.name: p for p in sorted(current.glob("*.png"))} if current.is_dir() else {}
    if only is not None:
        new = {k: v for k, v in new.items() if k in only}
    report = {"baseline": str(baseline), "current": str(current), "threshold": threshold,
              "tolerance": tolerance, "changed": [], "unchanged": [], "added": sorted(set(new) - set(old)),
              "removed": sorted(set(old) - set(new))}
    for name in sorted(set(old) & set(new)):
        diff_path = (out / f"diff--{name}") if out else None
        r = compare_pair(old[name], new[name], diff_path, tolerance)
        if r["pct"] >= threshold:
            report["changed"].append({"name": name, **r})
        else:
            if diff_path and diff_path.exists():
                diff_path.unlink()
            report["unchanged"].append(name)
    report["changed"].sort(key=lambda r: -r["pct"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare screenshots between two runs or releases.")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--out", default=None, help="folder for diff images")
    ap.add_argument("--threshold", type=float, default=0.01, help="percent of pixels that makes a screen 'changed'")
    ap.add_argument("--tolerance", type=int, default=24, help="per-channel difference treated as noise (0-255)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--fail-on-change", action="store_true")
    args = ap.parse_args()
    rep = compare_dirs(Path(args.baseline), Path(args.current), Path(args.out) if args.out else None,
                       args.threshold, args.tolerance)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2))
    for c in rep["changed"]:
        print(f"CHANGED  {c['name']}  {c['pct']}%" + (f"  ({c['note']})" if c.get("note") else ""))
    for n in rep["added"]:
        print(f"NEW      {n}")
    for n in rep["removed"]:
        print(f"REMOVED  {n}")
    print(f"{len(rep['changed'])} changed, {len(rep['added'])} new, {len(rep['removed'])} removed, "
          f"{len(rep['unchanged'])} unchanged")
    return 1 if args.fail_on_change and (rep["changed"] or rep["added"] or rep["removed"]) else 0


if __name__ == "__main__":
    sys.exit(main())
