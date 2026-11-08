"""The derived-artefact cache (dopplertrack.cache): keyed on contents and producer source, atomic,
locked, and a damaged entry is a miss. The CPA table's own cache is tested in test_cache.py."""
import subprocess
import sys

import numpy as np
import pytest
import scipy.io.wavfile

from dopplertrack import cache
from dopplertrack.audio import Spectrogram
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


def _fake_detect(sp, f_lo, f_hi, top=10, workers=None, progress=None):
    _fake_detect.calls += 1
    return [("event", float(sp.S.sum()), f_lo, f_hi, top)]


def test_detections_follow_spectrogram_params_and_detector_source(tmp_path, monkeypatch):
    mod = tmp_path / "fake_detector_mod.py"
    mod.write_text("THRESHOLD = 1\n\ndef detect():\n    return THRESHOLD\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cache, "DETECTOR_CODE", {"fake_detector_mod": ("detect",)})
    _fake_detect.calls = 0
    sp = Spectrogram(np.arange(5) * 0.5, np.array([50.0, 51.0]), np.ones((2, 5), np.float32))

    def detect(sp, **kw):
        return cache.cached_detections(sp, _fake_detect, root=tmp_path / "c", f_lo=60, f_hi=300, **kw)

    first = detect(sp)
    assert detect(sp, workers=4, progress=print) == first and _fake_detect.calls == 1   # how, not what
    detect(sp, top=5); assert _fake_detect.calls == 2
    other = Spectrogram(sp.t, sp.f, sp.S, np.array([1, 1, 0, 1, 1], bool))              # only the mask differs
    detect(other); assert _fake_detect.calls == 3
    mod.write_text("THRESHOLD = 2\n\ndef detect():\n    return THRESHOLD\n")             # a constant the detector reads changes
    detect(sp); assert _fake_detect.calls == 4
    detect(sp); assert _fake_detect.calls == 4


_CONTENDER = """
import sys, time
from dopplertrack import cache
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
