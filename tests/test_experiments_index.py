"""tools/data/experiments_index.py: the experiments table comes from the records' own index blocks."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("experiments_index", Path(__file__).resolve().parents[1] / "tools" / "data" / "experiments_index.py")
index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(index)


def record(docs: Path, name: str, q: str, o: str):
    (docs / f"{name}.md").write_text(f"# {name}\n\n<!-- index\nquestion: {q}\noutcome: {o}\n-->\n\nbody\n")


def test_the_table_is_rebuilt_newest_first_and_by_name(tmp_path):
    record(tmp_path, "2026-11-03-b", "Q b?", "O b")
    record(tmp_path, "2026-11-04-z", "Q z?", "O z")
    record(tmp_path, "2026-11-04-a", "Q a?", "O a")
    readme = "# Records\n\nintro\n\n" + index.HEADER + "| [old](old.md) | x | y |\n\nafter\n"
    out = index.rebuilt(readme, tmp_path)
    rows = [ln for ln in out.splitlines() if ln.startswith("| [")]
    assert rows == ["| [2026-11-04-a](2026-11-04-a.md) | Q a? | O a |", "| [2026-11-04-z](2026-11-04-z.md) | Q z? | O z |",
                    "| [2026-11-03-b](2026-11-03-b.md) | Q b? | O b |"]
    assert out.startswith("# Records\n\nintro\n\n") and out.endswith("\nafter\n")


def test_a_record_without_its_block_is_refused(tmp_path):
    (tmp_path / "2026-11-04-x.md").write_text("# x\n\nno block\n")
    with pytest.raises(SystemExit, match="no index block"):
        index.entries(tmp_path)


def test_the_committed_table_matches_the_records():
    path = index.DOCS / "README.md"
    assert index.rebuilt(path.read_text()) == path.read_text()
