import os
import re
import sys
import time
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

if sys.platform == "win32":
    os.system("")

FONT_FAMILY = "PixelCat"
STYLE = "Regular"
UPM = 1024  # Units per em
GRID_W = 8
GRID_H = 16
PIXEL_SIZE = UPM // GRID_H  # 64 единицы на 1 пиксель

BASELINE_ROW = 12

UI_THEME = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "success": "\033[38;2;166;227;161m",
    "path": "\033[38;2;137;180;250m",
    "number": "\033[38;2;249;226;175m",
    "time": "\033[38;2;203;166;247m",
}


def print_success_banner(output_path: Path, glyph_count: int, elapsed_sec: float):
    c = UI_THEME

    if elapsed_sec < 1.0:
        time_str = f"{elapsed_sec * 1000:.1f} ms"
    else:
        time_str = f"{elapsed_sec:.2f} s"

    print()
    print(f"{c['success']}BUILD SUCCESSFUL{c['reset']} in {c['time']}{time_str}{c['reset']}")
    print(f"{c['dim']}Artifacts:{c['reset']}    {c['path']}{output_path.as_posix()}{c['reset']}")
    print(f"{c['dim']}Glyphs count:{c['reset']} {c['number']}{glyph_count}{c['reset']}")
    print()

def parse_glyph_file(path: Path):
    match = re.search(r"U\+([0-9A-Fa-f]{4,6})", path.name)
    if not match:
        return None, None
    codepoint = int(match.group(1), 16)

    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(("#", "width", "height"))
    ]

    if len(lines) != GRID_H:
        return None, None

    pixels = []
    for r_idx, row in enumerate(lines):
        for c_idx, char in enumerate(row[:GRID_W]):
            if char == "#":
                pixels.append((c_idx, r_idx))
    return codepoint, pixels


def build():
    start_time = time.perf_counter()

    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)

    glyph_files = list(Path(".").glob("*/glyphs/U+*.txt"))
    glyph_data = {}

    for gf in glyph_files:
        cp, pixels = parse_glyph_file(gf)
        if cp is not None:
            glyph_name = f"uni{cp:04X}"
            glyph_data[glyph_name] = (cp, pixels)

    glyph_order = [".notdef"] + sorted(glyph_data.keys())

    pen_glyphs = {}

    pen = TTGlyphPen(None)
    pen.moveTo((PIXEL_SIZE, 0))
    pen.lineTo((GRID_W * PIXEL_SIZE - PIXEL_SIZE, 0))
    pen.lineTo((GRID_W * PIXEL_SIZE - PIXEL_SIZE, (GRID_H - 4) * PIXEL_SIZE))
    pen.lineTo((PIXEL_SIZE, (GRID_H - 4) * PIXEL_SIZE))
    pen.closePath()
    pen_glyphs[".notdef"] = pen.glyph()

    cmap = {}
    for gname, (cp, pixels) in glyph_data.items():
        cmap[cp] = gname
        pen = TTGlyphPen(None)

        for col, row in pixels:
            x0 = col * PIXEL_SIZE
            x1 = x0 + PIXEL_SIZE
            y1 = (BASELINE_ROW - row) * PIXEL_SIZE
            y0 = y1 - PIXEL_SIZE

            pen.moveTo((x0, y0))
            pen.lineTo((x0, y1))
            pen.lineTo((x1, y1))
            pen.lineTo((x1, y0))
            pen.closePath()

        pen_glyphs[gname] = pen.glyph()

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(pen_glyphs)

    advance_width = GRID_W * PIXEL_SIZE
    metrics = {gname: (advance_width, 0) for gname in glyph_order}
    fb.setupHorizontalMetrics(metrics)

    fb.setupHorizontalHeader(
        ascent=BASELINE_ROW * PIXEL_SIZE,
        descent=-(GRID_H - BASELINE_ROW) * PIXEL_SIZE,
    )

    name_strings = {
        "familyName": FONT_FAMILY,
        "styleName": STYLE,
        "uniqueFontIdentifier": f"{FONT_FAMILY}-{STYLE}:2026",
        "fullName": f"{FONT_FAMILY} {STYLE}",
        "psName": f"{FONT_FAMILY}-{STYLE}",
        "version": "Version 0.1.0",
    }
    fb.setupNameTable(name_strings)
    fb.setupOS2(
        sTypoAscender=BASELINE_ROW * PIXEL_SIZE,
        sTypoDescender=-(GRID_H - BASELINE_ROW) * PIXEL_SIZE,
        sTypoLineGap=0,
        usWeightClass=400,
        usWidthClass=5,
    )
    fb.setupPost()

    output_path = build_dir / f"{FONT_FAMILY}-{STYLE}.ttf"
    fb.save(output_path)

    elapsed_time = time.perf_counter() - start_time
    print_success_banner(output_path, len(cmap), elapsed_time)


if __name__ == "__main__":
    build()
