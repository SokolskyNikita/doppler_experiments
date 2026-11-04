"""The --jobs default and the single-threaded workers every process pool uses."""
import os

import pytest

from dopplertrack import parallel


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


def test_pool_workers_are_pinned_to_one_thread(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.delenv("VECLIB_MAXIMUM_THREADS", raising=False)
    with parallel.process_pool(1) as ex:
        seen = ex.submit(_thread_vars, None).result()
    assert set(seen.values()) == {"1"}
    assert os.environ["OMP_NUM_THREADS"] == "8" and "VECLIB_MAXIMUM_THREADS" not in os.environ
