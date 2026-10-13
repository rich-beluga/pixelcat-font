import re
import unicodedata
from pathlib import Path

CATEGORIES_ORDER = ["numbers", "latin", "cyrillic", "special"]

def escape_char_for_markdown(char: str, cp: int) -> str:
    if cp == 0x0020:
        return "`[space]`"
    if char == "|":
        return "**\\|**"
    if char == "\\":
        return "**\\\\**"
    if char == "`":
        return "**\\`**"
    if char == "<":
        return "**&lt;**"
    if char == ">":
        return "**&gt;**"
    if char == '"':
        return "**&quot;**"
    if char == "'":
        return "**&#39;**"

    if char in ("*", "_", "~", "$", "[", "]", "{", "}", "#", "+", "-", ".", "!"):
        return f"**\\{char}**"

    return f"**{char}**"

output_lines = [
    "# Pixelcat Unicode Table\n",
    "> Generated automatically from glyph sources.\n"
]

for cat in CATEGORIES_ORDER:
    cat_dir = Path(cat) / "glyphs"
    if not cat_dir.exists():
        continue

    files = sorted(cat_dir.glob("U+*.txt"))
    if not files:
        continue

    output_lines.append(f"## {cat.capitalize()} ({len(files)} characters)\n")
    output_lines.append("| Character | Code | File | Unicode description |")
    output_lines.append("| :---: | :---: | :--- | :--- |")

    for f in files:
        match = re.search(r"U\+([0-9A-Fa-f]{4,6})", f.name)
        if not match:
            continue
        cp = int(match.group(1), 16)
        char = chr(cp)

        char_disp = escape_char_for_markdown(char, cp)

        try:
            desc = unicodedata.name(char)
        except ValueError:
            desc = "UNKNOWN"

        output_lines.append(f"| {char_disp} | `U+{cp:04X}` | `{f.as_posix()}` | {desc} |")

    output_lines.append("")

Path("unicode-table.md").write_text("\n".join(output_lines), encoding="utf-8")
print("unicode-table.md successfully generated!")