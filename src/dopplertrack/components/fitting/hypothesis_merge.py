"""Each event's hypotheses, local optima with pointwise profile-likelihood intervals (Raue 2009), in place of
independent rectangular speed, distance and f0 gates (Blackman & Popoli 1999, §6.3.1; PLAN Phase 2, item 7, stage B).

An event's hypotheses are up to MAX_OPTIMA optima from each of two sources:
- "ls": the least-squares fit of ridge_track's track (fit_track), when it says identified. It is the
  better estimator when the track stays on the pass, and item 4 showed the track sometimes doesn't;
- "fit_event": fit_event's optima, from its coarse grid's best emission-CPA times, each refined.

Each optimum gets a box of pointwise profile-likelihood intervals (Raue 2009, eq. 10): for each of v, k = v^2/d (which the steep middle of a pass
pins even when v and d separately aren't, PLAN 6.1), tau (emission CPA) and f0, the range over which the
objective, re-optimised over the other parameters, stays within a threshold of the optimum:
- for "ls", the track's residual sum of squares within LS_DCHI2 times its residual variance;
- for "fit_event", the curve integral under the ideal curve (EventWindow.curve_score, the scale of the event's
  decoy null, event_decoy_null) within NULL_DELTA null sigmas.
The thresholds are heuristic and neither objective is a calibrated likelihood, so these are not confidence
intervals. An interval that runs into its bound before the objective rises past the threshold is practically
non-identifiable (Raue 2009, Def. 1), flagged weak and widened to the bound. Optima from the two sources at nearly the same place (each inside the other's v, k and tau ranges) merge
into one hypothesis with the wider ranges.

A CPA row (grid point, flight) is admitted for an event if some hypothesis holds both its speed and its
v^2/d: each candidate flight's own ground speed gives the distance it implies."""
from __future__ import annotations

from dopplertrack.components.fitting.fit_event_hypotheses import MIN_SEP_S, NULL_DELTA, fit_event_hypotheses
from dopplertrack.components.fitting.hypothesis import D_BOUNDS, MAX_OPTIMA, MODEL_ERROR_FACTOR, TAU_REACH_S, V_BOUNDS, Hypothesis
from dopplertrack.components.fitting.ls_hypotheses import LS_DCHI2, ls_hypotheses
from dopplertrack.components.fitting.track_regression import LS_Z_SPAN_MIN
from dopplertrack.components.search.pair_gate import rectangular_gate
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit


def merge(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Optima at nearly the same place, each inside the other's v, k and tau ranges, become one hypothesis with the
    wider ranges; the first one's optimum is kept."""
    out: list[Hypothesis] = []
    for h in hyps:
        for o in out:
            if o.contains(h) and h.contains(o):
                o.sources = sorted(set(o.sources) | set(h.sources))
                for r in ("v_range", "k_range", "tau_range", "f0_range"):
                    a, b = getattr(o, r), getattr(h, r)
                    setattr(o, r, (min(a[0], b[0]), max(a[1], b[1])))
                o.weak = sorted(set(o.weak) | set(h.weak))
                if o.corr_v_d is None:
                    o.corr_v_d, o.identified = h.corr_v_d, h.identified
                break
        else:
            out.append(h)
    return out


def gate_hypothesis(ev: EventFit, v_tol: float, d_tol: tuple, c: float) -> Hypothesis:
    """The rectangular speed and distance gate (rectangular_gate) as a hypothesis: an event without an informative
    one admits as the gate does."""
    v_range, d_range = rectangular_gate(ev, v_tol, d_tol)
    return Hypothesis(sources=["gate"], f0=ev.f0, v=ev.v, d=ev.d, t_cpa_emit=ev.t_cpa_emit, t_cpa=ev.t_cpa,
                      v_range=v_range, k_range=(v_range[0] ** 2 / d_range[1], v_range[1] ** 2 / d_range[0]),
                      tau_range=(ev.t_cpa_emit, ev.t_cpa_emit), f0_range=(0.95 * ev.f0, 1.05 * ev.f0), d_range=d_range)


def informative(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Drop a hypothesis non-identifiable (weak) in v, k and tau together: its box is the whole table."""
    return [h for h in hyps if not {"v", "k", "tau"} <= set(h.weak)]


def event_hypotheses(sp: Spectrogram, w, ev: EventFit, c: float, null_sigma: float, harmonic: int = 1,
                     v_tol: float = 0.35, d_tol: tuple = (0.4, 2.5), *, max_optima: int = MAX_OPTIMA,
                     ls_dchi2: float = LS_DCHI2, null_delta: float = NULL_DELTA,
                     model_error_factor: float = MODEL_ERROR_FACTOR, min_sep_s: float = MIN_SEP_S,
                     v_bounds: tuple = V_BOUNDS, d_bounds: tuple = D_BOUNDS, tau_reach_s: float = TAU_REACH_S,
                     coarse_v=None, coarse_d=None, z_span_min: float = LS_Z_SPAN_MIN,
                     spectral_floor: float = 0.0) -> list[Hypothesis]:
    """Both sources' hypotheses for one event, merged, without uninformative ones; with none left, the rectangular gate
    (gate_hypothesis). The band is 0.85 f_post to 1.15 f_pre of the event's fit. The keyword settings are the two
    sources' (ls_hypotheses, fit_event_hypotheses), defaulting to their module constants."""
    f_lo, f_hi = 0.85 * ev.f_post, 1.15 * ev.f_pre
    ls = ls_hypotheses(sp, ev, f_lo, f_hi, c, harmonic, max_optima=max_optima, ls_dchi2=ls_dchi2,
                       model_error_factor=model_error_factor, v_bounds=v_bounds, d_bounds=d_bounds,
                       tau_reach_s=tau_reach_s, z_span_min=z_span_min, spectral_floor=spectral_floor)
    fe = fit_event_hypotheses(sp, w, ev, f_lo, f_hi, c, null_sigma, harmonic, max_optima=max_optima,
                              null_delta=null_delta, model_error_factor=model_error_factor, min_sep_s=min_sep_s,
                              v_bounds=v_bounds, d_bounds=d_bounds, tau_reach_s=tau_reach_s, coarse_v=coarse_v,
                              coarse_d=coarse_d, spectral_floor=spectral_floor)
    hyps = informative(merge(ls + fe))
    return hyps or [gate_hypothesis(ev, v_tol, d_tol, c)]
