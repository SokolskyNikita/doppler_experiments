"""Peak tracker on one event window: Viterbi tracks over spectral peaks with a zero state (Streit & Barrett 1990;
Iatsenko 2016 §3), then the segment rules (segment_rules), then harmonic sets (Eddy 1980)."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.tracking.harmonic_links import harmonic_groups, harmonic_links
from dopplertrack.components.tracking.segment_rules import custom_cut_hop, custom_cut_rise, custom_cut_weak, link_gaps, resolve_crossings
from dopplertrack.components.tracking.types import EventTracks, SampleSTFT, TrackParams
from dopplertrack.components.tracking.viterbi import find_tracks

# Rules that flag instead of cutting. Rise and hop both cut true curves on Livermore, where the 2.048 s
# window smears a pass's steep part, but cutting measured better than flagging there
# (docs/experiments/2026-11-04-freqtrack.md), so by default they cut; pass flag=("rise", "hop") to flag.
FLAG_ONLY: tuple[str, ...] = ()


def track_window(sp: Spectrogram, stft: SampleSTFT, t_start: float, t_end: float, f_lo: float, f_hi: float,
                 p: TrackParams = TrackParams(), rules: tuple[str, ...] = ("weak", "rise", "hop", "link", "crossing"),
                 flag: tuple[str, ...] = FLAG_ONLY) -> EventTracks:
    """Tracks between t_start and t_end with fundamentals or harmonics in [f_lo, f_hi], after the
    segment rules named in `rules`, with harmonic links. The rules named in `flag` ("rise", "hop")
    record where they fire in each track's flags instead of cutting it."""
    from dopplertrack.components.whitening.local_median import local_whiten
    win = local_whiten(sp.crop(t_start, t_end), spectral_floor=-np.inf)
    df, dt = win.df, win.dt
    tracks = find_tracks(win, stft, f_lo, f_hi, p)
    if "weak" in rules:
        tracks = [q for tr in tracks for q in custom_cut_weak(tr, p)]
    if "rise" in rules:
        tracks = [q for tr in tracks for q in custom_cut_rise(tr, p, df, flag_only="rise" in flag)]
    if "hop" in rules:
        tracks = [q for tr in tracks for q in custom_cut_hop(tr, p, df, flag_only="hop" in flag)]
    if "link" in rules:
        tracks = link_gaps(tracks, p, df, dt)
    if "crossing" in rules:
        tracks = resolve_crossings(tracks, p, df)
    links = harmonic_links(tracks, p)
    return EventTracks(tracks, links, harmonic_groups(tracks, links))
