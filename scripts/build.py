import argparse
import os
import re
import sys
import time
from collections import defaultdict
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

# Скругление углов как доля пикселя: 0.0 — без скругления, 0.5 — максимум
# (полпикселя превращает отдельно стоящий пиксель в круг).
DEFAULT_CORNER_RADIUS = 0.25
MAX_CORNER_RADIUS = 0.5

UI_THEME = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "success": "\033[38;2;166;227;161m",
    "path": "\033[38;2;137;180;250m",
    "number": "\033[38;2;249;226;175m",
    "time": "\033[38;2;203;166;247m",
}


def print_success_banner(output_path: Path, glyph_count: int, elapsed_sec: float, radius_units: int):
    c = UI_THEME

    if elapsed_sec < 1.0:
        time_str = f"{elapsed_sec * 1000:.1f} ms"
    else:
        time_str = f"{elapsed_sec:.2f} s"

    print()
    print(f"{c['success']}BUILD SUCCESSFUL{c['reset']} in {c['time']}{time_str}{c['reset']}")
    print(f"{c['dim']}Artifacts:{c['reset']}    {c['path']}{output_path.as_posix()}{c['reset']}")
    print(f"{c['dim']}Glyphs count:{c['reset']} {c['number']}{glyph_count}{c['reset']}")
    print(f"{c['dim']}Corner radius:{c['reset']} {c['number']}{radius_units}{c['reset']} units ({radius_units / PIXEL_SIZE:.2f} px)")
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


def sign(v: int) -> int:
    return (v > 0) - (v < 0)


def trace_outlines(pixels):
    """Строит внешние контуры объединения пиксельных квадратов.

    Возвращает список контуров, где каждый контур — это список пар
    ((x, y), скруглять_угол). Координаты уже в единицах шрифта.

    Скруглять можно только выпуклые внешние углы (ровно 1 заполненный
    пиксель из 4 вокруг вершины). Вогнутые углы и точки диагонального
    касания пикселей остаются острыми — иначе диагонали (X, Ж, №)
    распадутся на отдельные капли.
    """
    filled = set(pixels)

    # Граничные рёбра с заливкой строго справа от направления обхода.
    # Тогда внешние контуры получаются по часовой стрелке (как требует TTF),
    # а дырки (O, 8, B) — против часовой.
    edge_starts = defaultdict(list)

    # Горизонтальные рёбра: j — линия между строкой j-1 (сверху) и j (снизу).
    for j in range(GRID_H + 1):
        for c in range(GRID_W):
            top = (c, j - 1) in filled
            bottom = (c, j) in filled
            if top == bottom:
                continue
            if top:
                a, b = (c + 1, j), (c, j)  # заливка сверху (справа) — идём на запад
            else:
                a, b = (c, j), (c + 1, j)  # заливка снизу (справа) — идём на восток
            edge_starts[a].append(b)

    # Вертикальные рёбра: i — линия между столбцом i-1 (слева) и i (справа).
    for i in range(GRID_W + 1):
        for r in range(GRID_H):
            left = (i - 1, r) in filled
            right = (i, r) in filled
            if left == right:
                continue
            if left:
                a, b = (i, r), (i, r + 1)  # заливка слева (справа) — идём на юг
            else:
                a, b = (i, r + 1), (i, r)  # заливка справа — идём на север
            edge_starts[a].append(b)

    # Соединяем рёбра в замкнутые контуры.
    # В вершинах диагонального касания пикселей (степень 4) всегда
    # поворачиваем направо и замыкаемся при возврате в старт — так
    # восьмёрка с самокасанием распадается на отдельные простые контуры,
    # касающиеся друг друга в точке (валидно для TTF).
    contours_idx = []
    remaining = sum(len(v) for v in edge_starts.values())
    while remaining > 0:
        start = next(s for s, outs in edge_starts.items() if outs)
        first = edge_starts[start].pop()
        remaining -= 1
        contour = [start]
        prev, cur = start, first
        while cur != start:
            contour.append(cur)
            outs = edge_starts[cur]
            dx_in, dy_in = sign(cur[0] - prev[0]), sign(cur[1] - prev[1])
            nxt = None
            if len(outs) == 1:
                nxt = outs.pop()
            else:
                # Несколько исходящих — только в точке диагонального
                # касания. Выбираем поворот направо (в координатах сетки,
                # где j растёт вниз, это cross > 0).
                for k in range(len(outs)):
                    ox, oy = outs[k]
                    if dx_in * (oy - cur[1]) - dy_in * (ox - cur[0]) > 0:
                        nxt = outs.pop(k)
                        break
                if nxt is None:
                    nxt = outs.pop()
            remaining -= 1
            prev, cur = cur, nxt
        contours_idx.append(contour)

    # Убираем промежуточные вершины на прямых отрезках, переводим
    # координаты сетки в единицы шрифта и помечаем углы под скругление.
    result = []
    for contour in contours_idx:
        simplified = _simplify_collinear(contour)
        converted = []
        for (i, j) in simplified:
            x = i * PIXEL_SIZE
            y = (BASELINE_ROW - j) * PIXEL_SIZE
            occupancy = sum(
                (c, r) in filled
                for (c, r) in ((i - 1, j - 1), (i, j - 1), (i - 1, j), (i, j))
            )
            converted.append(((x, y), occupancy == 1))
        result.append(converted)
    return result


def _simplify_collinear(vertices):
    """Удаляет вершины, в которых контур идёт прямо (без поворота)."""
    n = len(vertices)
    if n <= 2:
        return vertices
    out = []
    for k in range(n):
        px, py = vertices[k - 1]
        cx, cy = vertices[k]
        nx, ny = vertices[(k + 1) % n]
        d_in = (sign(cx - px), sign(cy - py))
        d_out = (sign(nx - cx), sign(ny - cy))
        if d_in != d_out:
            out.append((cx, cy))
    return out or vertices


def draw_outline(pen, contour, radius: int):
    """Рисует один контур. Выпуклые углы срезаются квадратичной кривой
    с контрольной точкой в исходном углу: отступ radius с каждой стороны.
    """
    n = len(contour)
    if n == 0:
        return

    if radius <= 0:
        pen.moveTo(contour[0][0])
        for pt, _ in contour[1:]:
            pen.lineTo(pt)
        pen.closePath()
        return

    entries, exits = [], []
    for k, ((x, y), do_round) in enumerate(contour):
        if not do_round:
            entries.append((x, y))
            exits.append((x, y))
            continue
        (px, py), _ = contour[k - 1]
        (nx, ny), _ = contour[(k + 1) % n]
        dx_in, dy_in = sign(x - px), sign(y - py)
        dx_out, dy_out = sign(nx - x), sign(ny - y)
        entries.append((x - dx_in * radius, y - dy_in * radius))
        exits.append((x + dx_out * radius, y + dy_out * radius))

    pen.moveTo(exits[0] if contour[0][1] else contour[0][0])
    for k in range(1, n + 1):
        i = k % n
        pen.lineTo(entries[i])
        if contour[i][1]:
            pen.qCurveTo(contour[i][0], exits[i])
    pen.closePath()


def rounded_rect_contour(x0: int, y0: int, x1: int, y1: int):
    """Прямоугольник (обход по часовой) со скруглением всех 4 углов."""
    return [
        ((x0, y0), True),
        ((x0, y1), True),
        ((x1, y1), True),
        ((x1, y0), True),
    ]


def build(radius_ratio: float = DEFAULT_CORNER_RADIUS, output: Path | None = None):
    start_time = time.perf_counter()

    if radius_ratio < 0:
        print(f"Радиус не может быть отрицательным: {radius_ratio}", file=sys.stderr)
        sys.exit(2)
    if radius_ratio > MAX_CORNER_RADIUS:
        print(
            f"Радиус {radius_ratio} больше максимума {MAX_CORNER_RADIUS}, "
            f"используется {MAX_CORNER_RADIUS}",
            file=sys.stderr,
        )
        radius_ratio = MAX_CORNER_RADIUS
    radius_units = int(round(radius_ratio * PIXEL_SIZE))

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
    draw_outline(
        pen,
        rounded_rect_contour(
            PIXEL_SIZE, 0,
            GRID_W * PIXEL_SIZE - PIXEL_SIZE, (GRID_H - 4) * PIXEL_SIZE,
        ),
        radius_units,
    )
    pen_glyphs[".notdef"] = pen.glyph()

    cmap = {}
    for gname, (cp, pixels) in glyph_data.items():
        cmap[cp] = gname
        pen = TTGlyphPen(None)

        for contour in trace_outlines(pixels):
            draw_outline(pen, contour, radius_units)

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

    output_path = output or (build_dir / f"{FONT_FAMILY}-{STYLE}.ttf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(output_path)

    elapsed_time = time.perf_counter() - start_time
    print_success_banner(output_path, len(cmap), elapsed_time, radius_units)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сборка PixelCat TTF из пиксельных глифов.")
    parser.add_argument(
        "--radius",
        type=float,
        default=DEFAULT_CORNER_RADIUS,
        help="Радиус скругления углов в долях пикселя "
             f"(0 — без скругления, макс. {MAX_CORNER_RADIUS}). "
             f"По умолчанию: {DEFAULT_CORNER_RADIUS}.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Куда сохранить TTF (по умолчанию build/PixelCat-Regular.ttf).",
    )
    args = parser.parse_args()
    build(radius_ratio=args.radius, output=args.output)
