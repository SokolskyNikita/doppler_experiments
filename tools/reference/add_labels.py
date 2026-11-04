"""Restore equation numbers that Mistral OCR dropped, at placements checked by eye
against the scans.

A single-row display gets `\\tag{n}`. A row of a multi-row array gets
`\\qquad\\text{(n)}` at the end of that row, since `\\tag` can only label a whole
display. Each spec names the PDF page (1-based), the display block's index on that
page ($$…$$ and \\[…\\] blocks both count), and optionally the row. Numbers that are
already present are skipped, so it is safe to re-run after re-converting a file.

usage: add_labels.py [--dry-run]
"""
import os
import re
import sys

MD = os.path.join(os.environ.get("DOPPLERTRACK_DATA", os.path.expanduser("~/data/dopplertrack")), "reference", "md", "")
SPECS = {
    "kay-1993-ssp-vol1-estimation-theory.md": [
        (437, 2, None, "13.15"),
        (437, 4, 1, "13.16"),
        (437, 5, None, "13.17"),
        (437, 6, None, "13.18"),
        (515, 3, 1, "15.21"),
        (515, 6, None, "15.22"),
        (521, 3, 0, "15.29"),
        (521, 3, 1, "15.30"),
        (521, 5, None, "15.31"),
    ],
    "kay-1998-ssp-vol2-detection-theory.md": [
        (119, 3, None, "4.16"),
        (215, 0, None, "6.14"),
        (215, 2, None, "6.15"),
        (215, 4, "all", "6.16"),
        (324, 0, None, "8.14"),
        (324, 1, 1, "8.15"),
        (324, 2, None, "8.16"),
        (324, 4, None, "8.17"),
        (324, 5, None, "8.18"),
        (386, 1, "all", "9A.1"),
    ],
    "angelopoulos-bates-2021-conformal-prediction.md": [
        (5, 0, None, "2"),
        (18, 3, None, "10"),
        (18, 4, None, "11"),
        (18, 5, None, "12"),
    ],
}
PAGE = re.compile(r"^(\{(\d+)\}-{10,})$", re.M)
BLOCK = re.compile(r"(\$\$)(.+?)(\$\$)|(\\\[)(.+?)(\\\])", re.S)


def bodies(text):
    return [m.group(2) if m.group(1) else m.group(5) for m in BLOCK.finditer(text)]


def row_ends(body):
    """Offsets where each top-level row of the outermost array ends."""
    ends, depth = [], 0
    for m in re.finditer(r"\\begin\s*\{[^}]*\}|\\end\s*\{[^}]*\}|\\\\", body):
        tok = m.group(0)
        if tok.startswith("\\begin"):
            depth += 1
        elif tok.startswith("\\end"):
            if depth == 1:
                ends.append(m.start())
            depth -= 1
        elif depth == 1:
            ends.append(m.start())
    return ends


def label(body, row, num):
    if row in (None, "all"):
        # "all": the number labels the whole multi-row display, as printed.
        assert row == "all" or len(row_ends(body)) <= 1, f"{num}: multi-row block needs a row"
        return body.rstrip() + f" \\tag{{{num}}}"
    ends = row_ends(body)
    assert row < len(ends), f"{num}: block has {len(ends)} rows"
    at = ends[row]
    return body[:at].rstrip() + f" \\qquad\\text{{({num})}} " + body[at:]


def apply(name, specs, dry):
    text = open(MD + name, encoding="utf-8").read()
    parts = PAGE.split(text)  # [pre, marker, idx, body, marker, idx, body, ...]
    by_page, todo = {}, []
    for page, block, row, num in specs:
        if f"\\tag{{{num}}}" in text or f"\\text{{({num})}}" in text:
            continue  # applied on an earlier run
        written = r"(?:\\quad|\\qquad|~)\s*\(\s*%s\s*\)" % re.escape(num)
        assert not re.search(written, "".join(bodies(text))), f"{num} already in math"
        by_page.setdefault(page, []).append((block, row, num))
        todo.append(num)
    for i in range(1, len(parts), 3):
        page = int(parts[i + 1]) + 1
        if page not in by_page:
            continue
        blocks = bodies(parts[i + 2])
        # Apply rows from the bottom of each block up, so row offsets stay valid.
        edits = sorted(by_page[page], key=lambda e: (e[0], -(e[1] if isinstance(e[1], int) else 0)))
        for block, row, num in edits:
            blocks[block] = label(blocks[block], row, num)
            print(f"  p{page} [{block}] row {row}: ({num})")
        it = iter(blocks)
        parts[i + 2] = BLOCK.sub(
            lambda m: (m.group(1) or m.group(4)) + next(it) + (m.group(3) or m.group(6)), parts[i + 2])
    # Drop the captured page indexes: each marker line already contains its own.
    out = "".join(p for k, p in enumerate(parts) if k % 3 != 2)
    # Besides the new labels, only whitespace before them may change.
    if not todo:
        return text, text
    alt = "|".join(re.escape(n) for n in todo)
    added = re.compile(r"\\tag\{(?:%s)\}|\\qquad\\text\{\((?:%s)\)\}" % (alt, alt))
    assert len(added.findall(out)) - len(added.findall(text)) == len(todo), name
    assert re.sub(r"\s", "", added.sub("", out)) == re.sub(r"\s", "", added.sub("", text)), name
    if not dry:
        open(MD + name, "w", encoding="utf-8").write(out)
    return text, out


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for name, specs in SPECS.items():
        print(name)
        apply(name, specs, dry)
