"""The collective recipe's parameters (research readiness R2): every setting that can change its result, by stage, with
today's library defaults, and their resolution, default then the config's `parameters` (the run's explicit
overrides). A method choice is a name looked up in a small dict in methods/collective/search.py. Run settings that
cannot change a result (workers, the CPA cache file, the log) and the fleet split (only_cells) are not parameters.
R5's mode-rule settings join the planning stage when R5 adds them."""
from __future__ import annotations

from dataclasses import dataclass, field

from dopplertrack.components.assignment.clock_vote import CLOCK_BIN_S
from dopplertrack.components.assignment.pass_window import AGREE_S, PASS_FALLBACK
from dopplertrack.components.nulls.window_decoy_null import NULL_N
from dopplertrack.components.planning.coarse_cells import MARGIN_SIGMA, MAX_CELLS
from dopplertrack.components.planning.fine_grid import COARSE_M, FINE_M
from dopplertrack.components.planning.modes import MAX_MODES, MODE_SEPARATION_M
from dopplertrack.components.scoring.log_view import SUB_S
from dopplertrack.components.scoring.sweeps import F0_SPAN
from dopplertrack.methods.parameters import SpectrogramParameters, apply, check_choices, from_dict, to_dict


@dataclass(frozen=True)
class SweepParameters:
    """One level's residual shift, f0 sweep and curve samples (components/scoring/sweeps.Sweep): the shift over
    +-shift_s by shift_step, the f0 sweep over +-(scoring.f0_span + f0_span_extra) by about f0_step, n samples per
    sub-stretch."""
    shift_s: float
    shift_step_s: float
    f0_span_extra: float
    f0_step: float
    n: int


@dataclass(frozen=True)
class ScoringParameters:
    """The curve integral each window scores a pass by: the view (VIEWS), its crop and log-frequency grid, the
    best-stretch length, and the coarse and fine sweeps (sweeps.coarse_sweep and fine_sweep)."""
    view: str = "log_view"                         # VIEWS: "log_view" (LogView) or "event_window" (EventWindowView)
    f0_span: float = F0_SPAN                       # each candidate's own tone, +- this about the window's coarse tone
    log_step: float = 0.0025                       # LOG_DU = log1p(log_step): the log-frequency grid's step
    sub_s: float = SUB_S                           # a (flight, window) scores its best stretch this long
    crop_pad_s: float = 40.0                       # the view's crop: the window padded by this,
    crop_f_lo: float = 0.45                        #   from crop_f_lo to crop_f_hi times the coarse tone
    crop_f_hi: float = 2.0
    coarse_sweep: SweepParameters = field(default_factory=lambda: SweepParameters(14.0, 1.0, 0.02, 0.01, 60))
    fine_sweep: SweepParameters = field(default_factory=lambda: SweepParameters(8.0, 0.5, 0.0, 0.005, 80))


@dataclass(frozen=True)
class NullParameters:
    null_n: int = NULL_N                           # window_decoy_nulls draws per window (NULL_N)


@dataclass(frozen=True)
class AssignmentParameters:
    """The clock vote (clock_vote.clock_votes) and the window-pass assignment (ASSIGNMENTS)."""
    method: str = "greedy_assignment"              # ASSIGNMENTS: one entry until PLAN.md G4 adds exact matching
    clock_bin_s: float = CLOCK_BIN_S
    agree_s: float = AGREE_S
    pass_fallback: int = PASS_FALLBACK


@dataclass(frozen=True)
class PlanningParameters:
    """The coarse-to-fine grids (fine_grid), the cells the fine stage visits (coarse_cells.keep_cells) and the
    distinct peaks (modes)."""
    coarse_m: float = COARSE_M
    fine_m: float = FINE_M
    margin_sigma: float = MARGIN_SIGMA
    max_cells: int = MAX_CELLS
    mode_separation_m: float = MODE_SEPARATION_M
    max_modes: int = MAX_MODES


@dataclass(frozen=True)
class CollectiveParameters:
    spectrogram: SpectrogramParameters = field(default_factory=SpectrogramParameters)
    scoring: ScoringParameters = field(default_factory=ScoringParameters)
    null: NullParameters = field(default_factory=NullParameters)
    assignment: AssignmentParameters = field(default_factory=AssignmentParameters)
    planning: PlanningParameters = field(default_factory=PlanningParameters)
    max_range_m: float = 12000.0
    speed_of_sound_m_s: float | None = None        # c; None is the 15 C default

    def speed_of_sound(self) -> float:
        from dopplertrack.core.propagation import speed_of_sound
        return speed_of_sound() if self.speed_of_sound_m_s is None else float(self.speed_of_sound_m_s)

    def to_dict(self) -> dict:
        return to_dict(self)


def check(params: CollectiveParameters) -> CollectiveParameters:
    from dopplertrack.methods.collective import search
    from dopplertrack.methods.parameters import WHITENINGS
    check_choices(params, {"spectrogram.whitening": WHITENINGS, "scoring.view": search.VIEWS,
                           "assignment.method": search.ASSIGNMENTS})
    return params


def resolve_collective(overrides: dict | None = None, base: CollectiveParameters | None = None) -> CollectiveParameters:
    """The defaults (or base), then the run's explicit overrides, {"stage.field": value} or a bare field name one
    stage alone has; unknown names are refused."""
    return check(apply(base or CollectiveParameters(), overrides, where="the collective parameters"))


def from_record(data: dict) -> CollectiveParameters:
    return check(from_dict(CollectiveParameters, data))
