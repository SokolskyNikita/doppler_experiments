"""The --jobs default and the single-threaded workers every process pool uses."""
import os

import pytest

from dopplertrack.runtime import parallel


def _thread_vars(_):
    return {k: os.environ.get(k) for k in parallel.THREAD_VARS}


def test_jobs_default_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(parallel.JOBS_ENV, "3")
    assert parallel.default_jobs() == 3 and parallel.resolve_jobs(None) == 3 and parallel.resolve_jobs(5) == 5
    for bad in ("0", "-2", "many"):
        monkeypatch.setenv(parallel.JOBS_ENV, bad)
        with pytest.raises(ValueError, match=parallel.JOBS_ENV):
            parallel.default_jobs()
    monkeypatch.delenv(parallel.JOBS_ENV)
    assert 1 <= parallel.default_jobs() <= (os.cpu_count() or 1)
    with pytest.raises(ValueError):
        parallel.resolve_jobs(0)


def _topology(root, siblings):
    for cpu, sib in siblings.items():
        d = root / f"cpu{cpu}" / "topology"
        d.mkdir(parents=True)
        (d / "core_cpus_list").write_text(sib + "\n")


def test_linux_jobs_count_physical_cores_in_the_affinity_mask(tmp_path):
    # two cores with two hyperthreads each: CPUs 0 and 2 share a core, as do 1 and 3
    _topology(tmp_path, {0: "0,2", 1: "1,3", 2: "0,2", 3: "1,3"})
    assert parallel.linux_physical_cores({0, 1, 2, 3}, str(tmp_path)) == 2
    assert parallel.linux_physical_cores({0, 2}, str(tmp_path)) == 1
    assert parallel.linux_physical_cores({1, 2}, str(tmp_path)) == 2
    # no SMT (Graviton, AMD c7a): every CPU is its own core
    nosmt = tmp_path / "nosmt"
    _topology(nosmt, {i: str(i) for i in range(4)})
    assert parallel.linux_physical_cores({0, 1, 2, 3}, str(nosmt)) == 4
    # an unreadable topology falls back to os.cpu_count() in default_jobs
    assert parallel.linux_physical_cores({0, 7}, str(tmp_path)) is None


def test_pool_workers_are_pinned_to_one_thread(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.delenv("VECLIB_MAXIMUM_THREADS", raising=False)
    with parallel.process_pool(1) as ex:
        seen = ex.submit(_thread_vars, None).result()
    assert set(seen.values()) == {"1"}
    assert os.environ["OMP_NUM_THREADS"] == "8" and "VECLIB_MAXIMUM_THREADS" not in os.environ
