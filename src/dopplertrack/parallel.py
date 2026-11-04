"""Process pools for the coarsest independent work: detector windows and CPA-table segments.

A worker always computes serially, with its BLAS and OpenMP threads pinned to one, so pools never nest
and a pool of N workers runs N threads of numerical work. Results never depend on the number of workers."""
from __future__ import annotations

import contextlib
import multiprocessing
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

JOBS_ENV = "DOPPLERTRACK_JOBS"
# Read by Accelerate, OpenBLAS, MKL, BLIS and OpenMP when they start, so they must be in the environment
# a worker is spawned with, not set after numpy is imported.
THREAD_VARS = ("VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
               "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def default_jobs() -> int:
    """$DOPPLERTRACK_JOBS if set, else the performance-core count: efficiency cores would set the pace for
    equal shares of work. Falls back to os.cpu_count() where the core types can't be told apart."""
    env = os.environ.get(JOBS_ENV)
    if env:
        try:
            n = int(env)
        except ValueError:
            n = 0
        if n < 1:
            raise ValueError(f"{JOBS_ENV} must be a positive integer, got {env!r}")
        return n
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True,
                                 check=True).stdout
            return max(1, int(out))
        except (OSError, subprocess.CalledProcessError, ValueError):
            pass
    return os.cpu_count() or 1


def resolve_jobs(jobs: int | None) -> int:
    """None means default_jobs(); anything else must be at least 1."""
    if jobs is None:
        return default_jobs()
    if jobs < 1:
        raise ValueError(f"jobs must be at least 1, got {jobs}")
    return jobs


def _init_worker(initializer, initargs):
    for k in THREAD_VARS:
        os.environ[k] = "1"
    if initializer is not None:
        initializer(*initargs)


def ordered_map(fn, tasks, jobs: int, initializer=None, initargs=()):
    """fn over tasks, results in task order: in this process when jobs == 1, else in a process_pool whose
    workers each run initializer(*initargs) once. Consume the whole iterator so the pool shuts down."""
    if jobs == 1:
        if initializer is not None:
            initializer(*initargs)
        yield from map(fn, tasks)
        return
    with process_pool(jobs, initializer, initargs) as ex:
        yield from ex.map(fn, tasks)


@contextlib.contextmanager
def process_pool(jobs: int, initializer=None, initargs=()):
    """A spawn-context ProcessPoolExecutor of `jobs` single-threaded workers, shut down on exit.

    The thread variables are set in this process's environment while the pool is open, because spawned
    workers copy it when they start, and restored afterwards."""
    saved = {k: os.environ.get(k) for k in THREAD_VARS}
    os.environ.update({k: "1" for k in THREAD_VARS})
    try:
        with ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_init_worker, initargs=(initializer, initargs)) as ex:
            yield ex
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
