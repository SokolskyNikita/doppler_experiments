"""Rebuild the table in docs/experiments/README.md from the records themselves, so branches never conflict on it.

Each record docs/experiments/<date>-<topic>.md carries, right under its title line, a block that renders as nothing:

    <!-- index
    question: one line
    outcome: one line
    -->

The table lists every record, newest date first and by name within a date, as | [name](name.md) | question | outcome |.
Everything in README.md outside the table is left as it is.

usage: experiments_index.py [--check]     rewrite the table, or exit 1 if the committed one differs"""
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "experiments"
HEADER = "| Record | Question | Outcome |\n|---|---|---|\n"
BLOCK = re.compile(r"\A# [^\n]*\n\n?<!-- index\nquestion: (?P<q>[^\n]+)\noutcome: (?P<o>[^\n]+)\n-->\n")


def entries(docs: Path = DOCS) -> list[tuple[str, str, str]]:
    out, problems = [], []
    for p in sorted(docs.glob("[0-9]*.md")):
        m = BLOCK.match(p.read_text())
        if not m:
            problems.append(f"{p.name}: no index block under its title (see tools/data/experiments_index.py)")
            continue
        if "|" in m["q"] + m["o"]:
            problems.append(f"{p.name}: a '|' in the index block would break the table")
        out.append((p.stem, m["q"].strip(), m["o"].strip()))
    if problems:
        sys.exit("\n".join(problems))
    # newest first, by name within a date
    return sorted(out, key=lambda e: (-int(e[0][:10].replace("-", "")), e[0]))


def table(docs: Path = DOCS) -> str:
    return HEADER + "".join(f"| [{n}]({n}.md) | {q} | {o} |\n" for n, q, o in entries(docs))


def rebuilt(readme: str, docs: Path = DOCS) -> str:
    """readme with its table replaced: the header line and every table line after it."""
    start = readme.index(HEADER)
    end = start + len(HEADER)
    lines = readme[end:].splitlines(keepends=True)
    k = 0
    while k < len(lines) and lines[k].startswith("|"):
        k += 1
    return readme[:start] + table(docs) + "".join(lines[k:])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = DOCS / "README.md"
    now, new = path.read_text(), rebuilt(path.read_text())
    if "--check" in argv:
        if now != new:
            sys.exit(f"{path} is not the table the records give: run tools/data/experiments_index.py")
        return
    path.write_text(new)


if __name__ == "__main__":
    main()
