"""No standard name: S1, a fitted curve's sweep-weighted contrast scaled by the MADN of the same contrast along the
curve moved off itself in frequency. Nearest standard idea: a replica correlator normalised by a noise level estimated
from reference samples (Kay 1998 §9.3); ours estimates it robustly (MADN, Maronna 2019 eq. 2.63) from off-curve
samples that share frames with the curve, and corrects for frame overlap."""
# old module: dopplertrack.components.detection.s1_zscore
from __future__ import annotations

import dataclasses

import numpy as np

from dopplertrack.components.detection.custom_curve_contrast import custom_curve_contrast, custom_sweep_weights
from dopplertrack.components.detection.doppler_curve import straight_pass_doppler_curve
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten
from dopplertrack.core.propagation import speed_of_sound

OFF_CURVE = (-0.20, -0.16, -0.12, -0.08, 0.08, 0.12, 0.16, 0.20)    # S1's reference samples: the curve moved off itself


def overlap_weight(hop_s: float, window_s: float = 2.048, n: int = 8192) -> float:
    """1 / (1 + 2 sum_m rho(m hop)^2) of a Hann window, rho the overlap correlation c(r) (Harris 1978 eq. 17): the
    large-K reciprocal of Welch's variance ratio for averaged overlapped transforms (Harris eq. 19), i.e. the share
    of a frame that is independent of its neighbours (0.254 for the package's 2.048 s window at 0.25 s). Harris's
    ratio is for averaged squared magnitudes; applying it to sums of dB contrast is an approximation (ours)."""
    w = np.hanning(n)
    h = max(1, int(round(n * hop_s / window_s)))
    e = float(np.dot(w, w))
    rho = [float(np.dot(w[:-m * h], w[m * h:])) / e for m in range(1, (n - 1) // h + 1)]
    return 1.0 / (1.0 + 2.0 * sum(r * r for r in rho))


# old name: curve_zscore
def custom_contrast_zscore(sp: Spectrogram, ef: EventFit, c: float, harmonics: int = 1, frame_weight: float | None = None
                 ) -> tuple[float, float]:
    """S1 for a fitted curve: sum_k a_k c_k / (sigma_c sqrt(sum_k a_k^2 / w)) over the valid frames k of sp (whitened)
    in [t_start, t_end], with c_k the ridge contrast on the curve (averaged over harmonics), a_k its sweep weights,
    w the frames' overlap weight and sigma_c the MADN (Maronna 2019 eq. 2.63) of the same contrast along the curve
    moved off itself in frequency (OFF_CURVE). Scaled to about unit spread in noise whatever the curve's length or
    the overlap; with an estimated scale it is t-like rather than a unit z (Kay 1998 §9.3), and the reference
    samples share frames with the curve. Returns (S1, sigma_c)."""
    k = (sp.t >= ef.t_start) & (sp.t <= ef.t_end) & sp.valid
    t = sp.t[k]
    if len(t) < 3 or not np.isfinite(ef.f0):
        return float("nan"), float("nan")
    dto, ratio = straight_pass_doppler_curve(ef.v, ef.d, c)
    rat = np.interp(t - ef.t_cpa_emit, dto, ratio, left=np.nan, right=np.nan)
    a = np.where(np.isnan(rat), 0.0, custom_sweep_weights(rat, t))
    rat = np.nan_to_num(rat, nan=1.0)

    def contrast(scale):
        return np.mean([custom_curve_contrast(sp, t, h * ef.f0 * rat * scale) for h in range(1, harmonics + 1)], axis=0)
    on = np.nan_to_num(contrast(1.0))
    off = np.concatenate([contrast(1.0 + s) for s in OFF_CURVE])
    off = off[np.isfinite(off)]
    sigma = 1.4826 * float(np.median(np.abs(off - np.median(off)))) if len(off) else float("nan")
    w = overlap_weight(float(np.median(np.diff(sp.t)))) if frame_weight is None else frame_weight
    den = sigma * np.sqrt(float(np.sum(a * a)) / w)
    return (float(np.sum(a * on) / den) if den > 0 else float("nan")), sigma


# old name: rescore_z
def custom_rescore_zscore(sp: Spectrogram, events: list[EventFit], f_lo: float, f_hi: float, c: float | None = None,
              harmonics: int = 1, min_sep_s: float = 60.0, top: int | None = None, min_score: float = 0.0,
              diagnostics: list | None = None) -> list[EventFit]:
    """detect_events' fits rescored by S1 (custom_contrast_zscore, PLAN item 6), re-ranked, one event per min_sep_s
    (greedy non-maximum suppression), the best
    `top` above min_score. The fits are unchanged; only the score is S1's. Kept apart from detect_events so that
    detect's code, and the detections cache keyed on it, don't change before item 6 is decided. With a
    `diagnostics` list, each event's sigma_c is appended beside the median over the events (the cross-window
    estimate)."""
    c = speed_of_sound() if c is None else c
    pad = 0.3 * (f_hi - f_lo)
    scored, rows = [], []
    for ef in events:
        win = local_whiten(sp.crop(ef.t_start - 30, ef.t_end + 30, max(f_lo - pad, sp.f[0]),
                                   min(f_hi * harmonics + pad, sp.f[-1])))
        z, sigma = custom_contrast_zscore(win, ef, c, harmonics)
        rows.append(dict(t_cpa=ef.t_cpa, s0=ef.score, s1=z, sigma_c=sigma))
        if np.isfinite(z) and z > min_score:
            scored.append(dataclasses.replace(ef, score=z))
    sig = [r["sigma_c"] for r in rows if np.isfinite(r["sigma_c"])]
    if diagnostics is not None:
        med = float(np.median(sig)) if sig else float("nan")
        diagnostics.extend({**r, "sigma_c_cross_window": med} for r in rows)
    scored.sort(key=lambda e: -e.score)
    final: list[EventFit] = []
    for e in scored:
        if all(abs(e.t_cpa - f.t_cpa) >= min_sep_s for f in final):
            final.append(e)
        if top is not None and len(final) >= top:
            break
    return final
