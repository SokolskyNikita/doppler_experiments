"""Plumbing shared by the recipes' parameters (research readiness R2): the spectrogram settings both recipes use, the
four-layer resolution of a parameters dataclass (default, profile, case, the run's explicit overrides), its JSON form,
and the grid helpers that turn a stored (start, stop, step) into the array a method takes. Not a method."""
from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, fields, is_dataclass, replace

import numpy as np

# The spectrogram's whitening, a method choice of both recipes: the name stored in the parameters, and the value
# compute_spectrogram and spectrogram_from_blocks take for it (stft dispatches on it; the methods are
# components/whitening/time_median.whiten_time and components/whitening/frequency_median.whiten_frequency).
WHITENINGS = {"whiten_time": "time", "whiten_frequency": "frequency"}


@dataclass(frozen=True)
class SpectrogramParameters:
    """The STFT spectrogram (components/stft.py, spectrogram_from_blocks) and the per-window local median whitening
    (components/whitening/local_median.local_whiten). Defaults are spectrogram_from_blocks's and local_whiten's.
    They take effect where a recipe builds the spectrogram from audio; a recipe given a spectrogram file records them
    beside it but did not make it (the record's `spectrogram_input` says which). spectral_floor applies to every
    window either way."""
    nperseg: int = 8192
    hop_s: float = 0.25
    fmin: float = 40.0
    fmax: float = 450.0
    nfft: int | None = None
    whitening: str = "whiten_time"          # stft keyword `whiten`: "time" or "frequency" (WHITENINGS)
    whiten_window_s: float | None = 600.0   # the time median's block, whiten_time
    bg_hz: float = 10.0                     # the frequency median's half-width, whiten_frequency
    spectral_floor: float = 0.0             # local_whiten's floor (Vary & Martin 2023 §12.3.4.2)

    def stft_kwargs(self) -> dict:
        """spectrogram_from_blocks's (and cached_spectrogram's) keyword arguments."""
        return {"nperseg": self.nperseg, "hop_s": self.hop_s, "fmin": self.fmin, "fmax": self.fmax,
                "whiten_window_s": self.whiten_window_s, "nfft": self.nfft, "whiten": WHITENINGS[self.whitening],
                "bg_hz": self.bg_hz}


def arange_grid(spec) -> np.ndarray:
    """A stored (start, stop, step) as np.arange(start, stop, step): stop excluded, as the grids it replaces."""
    start, stop, step = spec
    return np.arange(start, stop, step)


def inclusive_grid(spec) -> np.ndarray:
    """A stored (lo, hi, step) as np.arange(lo, hi + step / 50, step), hi included: the same values as the literal
    sweeps it replaces (np.arange(-8, 8.01, 0.5) and np.arange(0.95, 1.0501, 0.005))."""
    lo, hi, step = spec
    return np.arange(lo, hi + step / 50.0, step)


def geometric_grid(spec) -> np.ndarray:
    """A stored (lo, hi, n) as np.geomspace(lo, hi, n)."""
    lo, hi, n = spec
    return np.geomspace(lo, hi, int(n))


def to_dict(params) -> dict:
    """The parameters as one JSON object with the dataclass field names, nested by stage."""
    out = {}
    for f in fields(params):
        v = getattr(params, f.name)
        out[f.name] = to_dict(v) if is_dataclass(v) else (list(v) if isinstance(v, tuple) else v)
    return out


def _paths(params, prefix="") -> dict[str, tuple]:
    """Every leaf field as "stage.field" -> (owning dataclass type, field)."""
    out = {}
    for f in fields(params):
        v = getattr(params, f.name)
        if is_dataclass(v):
            out.update(_paths(v, f"{prefix}{f.name}."))
        else:
            out[prefix + f.name] = f
    return out


def _flatten(layer: dict, prefix="") -> dict:
    """{"gates": {"time_gate_s": 4}} and {"gates.time_gate_s": 4} both as {"gates.time_gate_s": 4}."""
    out = {}
    for k, v in layer.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[prefix + k] = v
    return out


def _coerce(f, value):
    """A JSON value into the field's type: a list into a tuple where the field holds one, ints into floats."""
    default = f.default if f.default is not dataclasses.MISSING else None
    if isinstance(value, list):
        return tuple(_coerce_item(x) for x in value)
    if isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _coerce_item(x):
    return tuple(x) if isinstance(x, list) else x


def apply(params, layer: dict | None, where: str = "overrides"):
    """params with one layer of overrides. A key is "stage.field", or a bare field name that only one stage has; a
    nested {"stage": {"field": value}} is the same. An unknown or ambiguous name is refused, naming it."""
    if not layer:
        return params
    paths = _paths(params)
    leaf = {}
    for path in paths:
        leaf.setdefault(path.rsplit(".", 1)[-1], []).append(path)
    changes: dict[str, object] = {}
    unknown, ambiguous = [], []
    for key, value in _flatten(layer).items():
        if key in paths:
            changes[key] = value
        elif "." not in key and len(leaf.get(key, [])) == 1:
            changes[leaf[key][0]] = value
        elif "." not in key and len(leaf.get(key, [])) > 1:
            ambiguous.append(f"{key} ({', '.join(leaf[key])})")
        else:
            unknown.append(key)
    if unknown or ambiguous:
        msg = []
        if unknown:
            msg.append(f"unknown parameter names in {where}: {sorted(unknown)}")
        if ambiguous:
            msg.append(f"ambiguous parameter names in {where}, give the stage: {sorted(ambiguous)}")
        raise ValueError("; ".join(msg))
    return _replace_paths(params, {k: _coerce(paths[k], v) for k, v in changes.items()})


def _replace_paths(params, changes: dict):
    direct = {k: v for k, v in changes.items() if "." not in k}
    nested: dict[str, dict] = {}
    for k, v in changes.items():
        if "." in k:
            head, rest = k.split(".", 1)
            nested.setdefault(head, {})[rest] = v
    for head, sub in nested.items():
        direct[head] = _replace_paths(getattr(params, head), sub)
    return replace(params, **direct)


def check_choices(params, choices: dict[str, typing.Iterable[str]]) -> None:
    """Refuse a method choice that names no method: choices maps "stage.field" to the names its dict holds."""
    for path, names in choices.items():
        obj = params
        for part in path.split("."):
            obj = getattr(obj, part)
        if obj not in names:
            raise ValueError(f"{path} must be one of {sorted(names)}, not {obj!r}")


def parse_assignments(items, option: str = "--param") -> dict:
    """KEY=VALUE pairs, each value read as JSON when it parses (12, null, [0.4, 2.5]) and as a string otherwise."""
    import json
    out = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise ValueError(f"{option} {item!r} is not KEY=VALUE")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def from_dict(cls, data: dict):
    """The parameters a record's resolved block holds (to_dict's output), for a later run to start from."""
    return apply(cls(), data, where="the resolved parameters")


__all__ = ["WHITENINGS", "SpectrogramParameters", "arange_grid", "inclusive_grid", "geometric_grid", "to_dict",
           "apply", "check_choices", "parse_assignments", "from_dict"]
