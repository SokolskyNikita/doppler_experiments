"""The grid_pair recipe's parameters (research readiness R2): every setting that can change its result, by stage, with
today's library defaults; the named profiles; and their resolution, default then profile then case then the run's
explicit overrides.

A default is the keyword default of the function the setting comes from (its name is given beside it where the
field's differs, and where a stored output key keeps the old name). A method choice is a name looked up in a small
dict in the recipe module (pipeline.py, runner.py); `check` refuses a name no dict holds. Run settings that cannot
change a result (workers, cache paths, progress, logs, output folders) are not parameters."""
from __future__ import annotations

from dataclasses import dataclass, field

from dopplertrack.components.detection.custom_contrast_zscore import OFF_CURVE
from dopplertrack.components.detection.custom_curve_contrast import CONTRAST_DF, SWEEP_FLOOR
from dopplertrack.components.fitting.fit_event_hypotheses import MIN_SEP_S, NULL_DELTA
from dopplertrack.components.fitting.hypothesis import D_BOUNDS, MAX_OPTIMA, MODEL_ERROR_FACTOR, TAU_REACH_S, V_BOUNDS
from dopplertrack.components.fitting.ls_hypotheses import LS_DCHI2
from dopplertrack.components.fitting.track_regression import LS_Z_SPAN_MIN
from dopplertrack.components.nulls.event_decoy_null import NULL_N
from dopplertrack.components.scoring.doppler_inflection import INFLECTION_FLAT_RATIO
from dopplertrack.methods.parameters import SpectrogramParameters, apply, check_choices, from_dict, to_dict


@dataclass(frozen=True)
class DetectionParameters:
    """Sliding-window detection (components/detection/grid_scan.detect_events) and its refining fit (event_fit.fit_event),
    then the detection statistic. Grids are stored as (start, stop, step) for np.arange and (lo, hi, n) for
    np.geomspace."""
    band_hz: tuple = (60.0, 300.0)                 # detect_events f_lo, f_hi (no library default: locate's band)
    harmonics: int = 1
    window_s: float = 240.0
    step_s: float = 120.0
    speed_grid_mps: tuple = (40.0, 170.0, 13.0)    # v_grid, np.arange
    slant_range_grid_m: tuple = (400.0, 9000.0, 10)  # d_grid, np.geomspace
    f0_step_hz: float = 2.0                        # f0_step
    t0_step_s: float = 2.0                         # t0_step
    n_curve: int = 80
    top: int = 20
    per_window: int = 3
    min_sep_s: float = 60.0
    min_score: float = 0.0
    refine: bool = True
    refine_speed_bounds_mps: tuple = (35.0, 200.0)       # fit_event v_bounds as detect_events calls it
    refine_slant_range_bounds_m: tuple = (200.0, 15000.0)  # fit_event d_bounds as detect_events calls it
    refine_half_window_s: float = 120.0            # the refining fit's window, the candidate's CPA +- this
    objective: str = "contrast"                    # fit_event and grid_search objective: "contrast" or "brightness"
    statistic: str = "contrast"                    # DETECTION_STATISTICS: the fit's contrast, S1 or the surrogate's D
    contrast_df: float = CONTRAST_DF               # custom_curve_contrast's sideband offset
    sweep_floor: float = SWEEP_FLOOR               # custom_sweep_weights' floor
    off_curve: tuple = OFF_CURVE                   # S1's reference offsets (custom_contrast_zscore)


@dataclass(frozen=True)
class EventSourceParameters:
    """Where the two searched events come from, and locate's checks around them (methods/grid_pair/runner.py)."""
    source: str = "saved_fits"                     # EVENT_SOURCES: "saved_fits", "top2" or "comparable_pairs"
    report_top2: bool = False                      # also search top2 and report it beside the source's answer
                                                   # (locate --pair-rule both)
    top_k: int = 5                                 # comparable_pairs: every pair of the top k usable events (TOP_K)
    usable_valid_share: float = 0.5                # a recording more than half gaps is not searched (USABLE_VALID_SHARE)
    day_slack_s: float = 600.0                     # flight data covers a day if it reaches within this (DAY_SLACK_S)
    gate_pad_s: float = 300.0                      # with a stated start, how far past the recording (GATE_PAD_S)
    start_utc: float | None = None                 # the clock gate (clock_gate): the stated start, unix s; None: off
    start_tol_s: float | None = None               # and its stated uncertainty


@dataclass(frozen=True)
class GateParameters:
    """The association gates of the two-event grid search (pipeline.pair_grid_search) and the single-event search."""
    time_gate_s: float = 6.0                       # tol_s: the time-difference gate's half-width
    single_event_time_gate_s: float = 30.0         # single_grid_search tol_s
    speed_gate_fraction: float = 0.35              # v_tol (rectangular_gate)
    slant_range_gate_factors: tuple = (0.4, 2.5)   # d_tol (rectangular_gate)
    negative_information_distance_m: float | None = 6000.0   # silence_d_m; None turns the filter off
    negative_information_margin_s: float = 40.0    # silence_margin_s
    max_range_m: float = 12000.0
    time_convention: str = "heard"                 # TIME_CONVENTIONS: "heard" or "emission"
    event_gate: str = "rectangular"                # EVENT_GATES: "rectangular" or "profile_intervals" (hypotheses=True)
    clock_anchor: str = "heard_cpa"                # CLOCK_ANCHORS: "heard_cpa" (CLI "heard") or "doppler_inflection"
                                                   # (CLI "steepest")
    inflection_tol_s: float | None = None          # sf_tol_s: the inflection gate; None: off
    inflection_window_s: float = 60.0              # sf_window_s
    inflection_smooth_s: float = 3.0               # sf_smooth_s
    inflection_flat_ratio: float = INFLECTION_FLAT_RATIO   # sf_flat_ratio
    alive_pad_s: float = 300.0                     # single_grid_search: segments alive within this of the event
    harmonics: tuple = (1, 1)                      # each event's harmonics: the pair's, then any extra events'


@dataclass(frozen=True)
class HypothesisParameters:
    """Profile-interval hypotheses (components/fitting/), event_gate "profile_intervals"."""
    max_optima: int = MAX_OPTIMA                   # MAX_OPTIMA (old name K)
    ls_delta_chi2: float = LS_DCHI2                # LS_DCHI2, Raue's Delta for the track RSS
    null_delta: float = NULL_DELTA                 # NULL_DELTA, Raue's Delta for the curve integral
    model_error_factor: float = MODEL_ERROR_FACTOR
    min_sep_s: float = MIN_SEP_S                   # MIN_SEP_S
    speed_bounds_mps: tuple = V_BOUNDS             # V_BOUNDS
    slant_range_bounds_m: tuple = D_BOUNDS         # D_BOUNDS
    tau_reach_s: float = TAU_REACH_S
    coarse_speed_grid_mps: tuple = (40.0, 170.0, 13.0)   # COARSE_V, np.arange
    coarse_slant_range_grid_m: tuple = (400.0, 9000.0, 10)  # COARSE_D, np.geomspace
    ls_z_span_min: float = LS_Z_SPAN_MIN


@dataclass(frozen=True)
class ScoringParameters:
    """The curve integral (EventWindow), its nuisance sweeps, the normalisation and the decoy null."""
    normalisation: str = "raw"                     # SCORE_NORMALISATIONS: "raw" or "pair_zscore" (comparable=True)
    shift_grid_s: tuple = (-8.0, 8.0, 0.5)         # custom_locked_score shifts, inclusive (lo, hi, step)
    f0_scale_grid: tuple = (0.95, 1.05, 0.005)     # custom_locked_score f0_scales, inclusive
    crop_pad_s: float = 40.0                       # EventWindow.from_fit pad_s
    curve_samples: int = 160                       # EventWindow.sweep_scores n
    null_n: int = NULL_N                           # event_decoy_null draws per event


@dataclass(frozen=True)
class RefinementParameters:
    """The fine square grid around the winner (pipeline.refine) and the extra events' association (pick_flight)."""
    spacing_m: float = 50.0
    half_width_m: float = 400.0                    # half_m
    rank: int = 1                                  # which flight pair to refine, by rank
    extra_f0_scale_grid: tuple = (0.95, 1.05, 0.005)   # the extra events' f0 sweep, inclusive
    alive_pad_s: float = 300.0                     # pick_flight: flights alive within this of the extra event


@dataclass(frozen=True)
class GridParameters:
    """The search grid over the box (Grid.make)."""
    spacing_m: float = 200.0
    dem: bool = True                               # terrain heights; False: sea level


@dataclass(frozen=True)
class AirParameters:
    """The speed of sound. With a ground temperature the fits use its speed and every flight's propagation its own
    mid-height speed; speed_of_sound_m_s, if given, replaces the fits' speed."""
    temperature_c: float | None = None
    speed_of_sound_m_s: float | None = None


@dataclass(frozen=True)
class GridPairParameters:
    spectrogram: SpectrogramParameters = field(default_factory=SpectrogramParameters)
    detection: DetectionParameters = field(default_factory=DetectionParameters)
    event_source: EventSourceParameters = field(default_factory=EventSourceParameters)
    gates: GateParameters = field(default_factory=GateParameters)
    hypotheses: HypothesisParameters = field(default_factory=HypothesisParameters)
    scoring: ScoringParameters = field(default_factory=ScoringParameters)
    refinement: RefinementParameters = field(default_factory=RefinementParameters)
    grid: GridParameters = field(default_factory=GridParameters)
    air: AirParameters = field(default_factory=AirParameters)

    def speed_of_sound(self) -> float:
        """The fits' speed of sound: the stated one, else the ground temperature's, else the 15 C default."""
        from dopplertrack.core.propagation import speed_of_sound
        if self.air.speed_of_sound_m_s is not None:
            return float(self.air.speed_of_sound_m_s)
        return speed_of_sound() if self.air.temperature_c is None else speed_of_sound(self.air.temperature_c)

    def to_dict(self) -> dict:
        return to_dict(self)


# Today's profiles as data: overrides of the defaults. The case and the run's overrides come after them.
PROFILES = {
    "saved-fit": {"event_source.source": "saved_fits"},      # the case's fits and harmonics come from the case
    "raw-audio": {"event_source.source": "top2", "detection.band_hz": (60.0, 300.0), "detection.top": 10,
                  "detection.harmonics": 1, "detection.window_s": 240.0, "gates.harmonics": (1, 1)},
    # LocateConfig's defaults: comparable pairs, the negative-information filter at 6 km, the clock gate on (its
    # start is the case's or the command's), refinement 600 m wide
    "locate": {"event_source.source": "comparable_pairs", "detection.band_hz": (60.0, 300.0), "detection.top": 10,
               "detection.harmonics": 1, "detection.window_s": 240.0, "gates.harmonics": (1, 1),
               "gates.negative_information_distance_m": 6000.0, "grid.spacing_m": 200.0,
               "refinement.spacing_m": 50.0, "refinement.half_width_m": 600.0},
}


def choices() -> dict:
    """Each method-choice field and the names its recipe dict holds."""
    from dopplertrack.methods.grid_pair import pipeline, runner
    from dopplertrack.methods.parameters import WHITENINGS
    return {"spectrogram.whitening": WHITENINGS, "detection.statistic": pipeline.DETECTION_STATISTICS,
            "detection.objective": ("contrast", "brightness"), "event_source.source": runner.EVENT_SOURCES,
            "gates.time_convention": pipeline.TIME_CONVENTIONS, "gates.event_gate": pipeline.EVENT_GATES,
            "gates.clock_anchor": pipeline.CLOCK_ANCHORS, "scoring.normalisation": pipeline.SCORE_NORMALISATIONS}


def check(params: GridPairParameters) -> GridPairParameters:
    check_choices(params, choices())
    if params.gates.event_gate == "profile_intervals" and (params.gates.inflection_tol_s is not None
                                                           or params.gates.clock_anchor != "heard_cpa"):
        raise ValueError("gates.event_gate profile_intervals doesn't combine with the inflection gate or anchor yet")
    return params


def resolve(profile: str | None = None, case: dict | None = None, overrides: dict | None = None,
            base: GridPairParameters | None = None) -> GridPairParameters:
    """The four layers in order: the dataclass defaults (or base), the profile's, the case's and the run's explicit
    overrides. Each layer is {"stage.field": value} (or a bare field name one stage alone has); unknown names are
    refused."""
    p = base or GridPairParameters()
    if profile is not None:
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {sorted(PROFILES)}, not {profile!r}")
        p = apply(p, PROFILES[profile], where=f"the {profile} profile")
    p = apply(p, case, where="the case")
    p = apply(p, overrides, where="the overrides")
    return check(p)


def from_record(data: dict) -> GridPairParameters:
    return check(from_dict(GridPairParameters, data))
