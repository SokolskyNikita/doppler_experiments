"""The derived-artefact cache (dopplertrack.runtime.cache): keyed on contents and on the producer's code, which is
derived from its imports; atomic, locked, and a damaged entry is a miss. The CPA table's own cache is tested in
test_cache.py."""
import subprocess
import sys

import numpy as np
import pytest
import scipy.io.wavfile

from dopplertrack.runtime import cache
from dopplertrack.components.spectrogram import Spectrogram
import dopplertrack.components.spectrogram_cache as spectrogram_cache
import dopplertrack.components.stft as stft


def _counting(calls, value):
    def produce():
        calls.append(1)
        return value
    return produce


def test_hit_then_miss_when_an_input_changes(tmp_path):
    src = tmp_path / "input.bin"
    src.write_bytes(b"a" * 1000)
    calls = []

    def get(**extra):
        return cache.cached("thing", {"input": cache.file_sha256(src), "n": 3, **extra},
                            _counting(calls, {"x": np.arange(3)}), root=tmp_path / "c")

    assert np.array_equal(get()["x"], np.arange(3)) and len(calls) == 1
    get(); assert len(calls) == 1                                   # identical inputs: a hit
    src.write_bytes(b"b" * 1000)                                    # same size, other contents
    get(); assert len(calls) == 2
    get(n=4); assert len(calls) == 3                                # a parameter changes
    assert len(list((tmp_path / "c" / "thing").rglob("metadata.json"))) == 3  # one folder per entry


def test_truncated_entry_is_rebuilt(tmp_path):
    calls = []
    parts = {"a": 1}
    cache.cached("thing", parts, _counting(calls, [1, 2, 3]), root=tmp_path)
    (pkl,) = tmp_path.rglob("output.pkl")
    with open(pkl, "r+b") as f:
        f.truncate(10)
    assert cache.cached("thing", parts, _counting(calls, [1, 2, 3]), root=tmp_path) == [1, 2, 3]
    assert len(calls) == 2
    assert cache.cached("thing", parts, _counting(calls, None), root=tmp_path) == [1, 2, 3]   # rebuilt entry is good
    assert len(calls) == 2


_DETECTOR = """THRESHOLD = 1
CALLS = []


def detect(sp, f_lo, f_hi, top=10, workers=None, progress=None):
    CALLS.append(1)
    return [("event", float(sp.S.sum()), f_lo, f_hi, top, THRESHOLD)]
"""


def test_detections_follow_spectrogram_params_and_detector_source(tmp_path, monkeypatch):
    import importlib
    mod = tmp_path / "fake_detector_mod.py"
    mod.write_text(_DETECTOR)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    fake = importlib.import_module("fake_detector_mod")
    monkeypatch.delitem(sys.modules, "fake_detector_mod")     # gone again after the test
    sys.modules["fake_detector_mod"] = fake
    sp = Spectrogram(np.arange(5) * 0.5, np.array([50.0, 51.0]), np.ones((2, 5), np.float32))

    def detect(sp, **kw):
        return cache.cached_detections(sp, fake.detect, root=tmp_path / "c", f_lo=60, f_hi=300, **kw)

    first = detect(sp)
    assert detect(sp, workers=4, progress=print) == first and len(fake.CALLS) == 1      # how, not what
    detect(sp, top=5); assert len(fake.CALLS) == 2
    other = Spectrogram(sp.t, sp.f, sp.S, np.array([1, 1, 0, 1, 1], bool))              # only the mask differs
    detect(other); assert len(fake.CALLS) == 3
    mod.write_text(_DETECTOR.replace("THRESHOLD = 1", "THRESHOLD = 2"))                 # the producer passed is the code keyed
    detect(sp); assert len(fake.CALLS) == 4
    detect(sp); assert len(fake.CALLS) == 4
    key = cache.detection_key(sp, fake.detect, f_lo=60, f_hi=300)
    monkeypatch.setattr(cache.sys, "version_info", (3, 99, 0))                          # an AST dump differs between Pythons
    assert cache.detection_key(sp, fake.detect, f_lo=60, f_hi=300) != key


# ---- a producer's code: derived from its imports, not listed ----------------------------------------------------

_PACKAGE = {
    "__init__.py": "",
    "produce.py": ("from kpkg.method import step\nfrom kpkg.runtime import pool\n\n\n"
                   'def produce(x):\n    """Doc."""\n    if x < 0:\n        raise ValueError(f"bad {x}")\n'
                   "    return step(x) if pool.WORKERS else None\n"),
    "method.py": "from . import constants\n\n\ndef step(x):\n    return constants.K * x\n",      # a relative import
    "constants.py": "K = 2\n",
    "extra.py": "E = 1\n",
    "unused.py": "Z = 1\n",
    "runtime/__init__.py": "",
    "runtime/pool.py": "WORKERS = 1\n",
}


@pytest.fixture
def package(tmp_path, monkeypatch):
    """A small package, kpkg, on sys.path and never imported. write(file, source) edits one of its files;
    key() and modules() are its producer's code hash and derived files."""
    import importlib
    import types
    root = tmp_path / "kpkg"

    def write(name, source):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(source)
    for name, source in _PACKAGE.items():
        write(name, source)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield types.SimpleNamespace(write=write, key=lambda: cache.code_sha256("kpkg.produce"),
                                modules=lambda: set(cache.code_modules("kpkg.produce")))
    assert "kpkg" not in sys.modules                                    # read from source, never imported


def test_a_producers_code_is_what_its_module_imports_without_the_runtime(package):
    assert package.modules() == {"kpkg.produce", "kpkg.method", "kpkg.constants"}


def test_a_code_edit_to_an_imported_file_changes_the_key(package):
    base = package.key()
    package.write("constants.py", "K = 3\n")                            # reached through method.py only
    changed = package.key()
    assert changed != base
    package.write("method.py", _PACKAGE["method.py"].replace("constants.K * x", "constants.K * x + 1"))
    assert package.key() not in (base, changed)


def test_docstring_comment_and_message_edits_keep_the_key(package):
    base = package.key()
    package.write("produce.py", _PACKAGE["produce.py"].replace('"""Doc."""', '"""Another doc."""  # and a comment')
                  .replace('f"bad {x}"', 'f"x must be >= 0, got {x}"'))
    package.write("constants.py", '"""The constants."""\nK = 2  # the gain\n')
    assert package.key() == base


def test_files_the_producer_does_not_import_stay_out_of_the_key(package):
    base = package.key()
    package.write("unused.py", "Z = 2\n")
    package.write("runtime/pool.py", "WORKERS = 8\n")                   # imported, but plumbing
    assert package.key() == base


@pytest.mark.parametrize("file, old, new", [
    ("method.py", "from . import constants\n", "from . import constants\nimport kpkg.extra\n"),                # module level
    ("produce.py", '    """Doc."""\n', '    """Doc."""\n    from kpkg import extra\n'),                          # in a function
    ("produce.py", '    """Doc."""\n', '    """Doc."""\n    from .extra import E\n'),                            # relative, a name
])
def test_a_new_import_brings_its_file_into_the_key(package, file, old, new):
    assert "kpkg.extra" not in package.modules()
    package.write(file, _PACKAGE[file].replace(old, new))
    assert package.modules() == {"kpkg.produce", "kpkg.method", "kpkg.constants", "kpkg.extra"}
    with_import = package.key()
    package.write("extra.py", "E = 2\n")
    assert package.key() != with_import


def test_a_callable_producer_is_keyed_on_its_own_module_and_a_sourceless_one_is_refused():
    import functools
    from dopplertrack.components.detection.grid_scan import detect_events
    by_name = cache.code_sha256("dopplertrack.components.detection.grid_scan")
    assert cache.code_sha256(detect_events) == by_name == cache.code_sha256(functools.partial(detect_events, top=3))
    assert cache.producer_name(functools.partial(detect_events, top=3)) == \
        "dopplertrack.components.detection.grid_scan.detect_events"
    with pytest.raises(ValueError, match="no source file"):
        cache.code_sha256(len)


def test_each_real_producers_code_follows_imports_through_other_modules():
    from dopplertrack.components.detection.event_fit import fit_event
    from dopplertrack.components.detection.grid_scan import detect_events
    from dopplertrack.components.search.cpa_table import cpa_table
    detect, fit, cpa = (set(cache.code_modules(f)) for f in (detect_events, fit_event, cpa_table))
    spectrogram = set(cache.code_modules(stft.spectrogram_from_files, spectrogram_cache.__name__))
    # each reached only through another module: grid_scan and event_fit don't import doppler_curve, cpa_table doesn't
    # import geometry, and spectrogram_cache doesn't import the whitenings
    assert "dopplertrack.components.detection.doppler_curve" in detect & fit
    assert "dopplertrack.components.detection.grid_scan" in detect - fit
    assert "dopplertrack.core.geometry" in cpa
    assert {"dopplertrack.components.whitening.time_median", "dopplertrack.components.spectrogram_cache"} <= spectrogram
    for modules in (detect, fit, cpa, spectrogram):
        assert not [m for m in modules if m.startswith("dopplertrack.runtime")]     # pools are imported by two of them


_CONTENDER = """
import sys, time
from dopplertrack.runtime import cache
root, log = sys.argv[1], sys.argv[2]
def produce():
    with open(log, "a") as f:
        f.write("built\\n")
    time.sleep(0.4)
    return 42
t0 = time.time()
v = cache.cached("contended", {"same": True}, produce, root=root)
print(v, t0, time.time())
"""


def test_two_processes_build_an_entry_once(tmp_path):
    log = tmp_path / "builds.txt"
    procs = [subprocess.Popen([sys.executable, "-c", _CONTENDER, str(tmp_path / "c"), str(log)],
                              stdout=subprocess.PIPE, text=True) for _ in range(2)]
    outs = [p.communicate(timeout=30)[0].split() for p in procs]
    assert [o[0] for o in outs] == ["42", "42"]
    starts, ends = [float(o[1]) for o in outs], [float(o[2]) for o in outs]
    assert max(starts) < min(ends)                     # the calls overlapped, so one waited on the lock
    assert log.read_text() == "built\n"


def test_spectrogram_cache_hits_and_matches_uncached(tmp_path, monkeypatch):
    sr = 4000
    wav = tmp_path / "a.wav"
    x = 0.3 * np.random.default_rng(0).standard_normal(20 * sr)
    scipy.io.wavfile.write(wav, sr, np.round(x * 32767).astype(np.int16))
    built = []
    real = stft.spectrogram_from_files
    monkeypatch.setattr(spectrogram_cache, "spectrogram_from_files", lambda *a, **k: built.append(1) or real(*a, **k))
    root = tmp_path / "c"
    sp = spectrogram_cache.cached_spectrogram(wav, root=root, hop_s=0.5)
    again = spectrogram_cache.cached_spectrogram(wav, root=root, hop_s=0.5)
    assert len(built) == 1 and np.array_equal(sp.S, again.S) and np.array_equal(sp.valid, again.valid)
    ref = real([(wav, 0.0)], sr, hop_s=0.5)
    assert np.array_equal(sp.S, ref.S) and np.array_equal(sp.t, ref.t)
    spectrogram_cache.cached_spectrogram(wav, root=root, hop_s=0.25)
    assert len(built) == 2
    with pytest.raises(TypeError, match="unknown spectrogram parameters"):
        spectrogram_cache.cached_spectrogram(wav, root=root, hop=0.5)
