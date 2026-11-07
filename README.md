# doppler_experiments

An independent research workspace for testing acoustic aircraft geolocation methods against shared
benchmarks. The goal is to compare separate approaches, preserve negative results, and find out what
works on unfamiliar recordings. This is experimental software, not a validated general-purpose locator.

## Origins and independence

This project began as a fork of [dopplertrack](https://github.com/mjshiggins/dopplertrack) by
**MacCallister Higgins**. He wrote the original implementation, pipeline and the two demonstration
validations described below. His work provided the foundation for these experiments, and the original
MIT copyright and licence are retained in [LICENSE](LICENSE).

Our research directions and code have diverged enough that merging this research workspace back into
the original project has become impractical. We are continuing independently as `doppler_experiments`,
with separate methods and shared evaluation as the intended architecture. This is our project decision,
not a statement that the original author rejected collaboration. Individual reusable improvements may
still be contributed separately.

The original project reimplements the technique colsto demonstrated in
["I discovered a sound that leaks your exact location"](https://www.youtube.com/watch?v=UytYrhYLOKI).

The remaining method and result descriptions document the inherited baseline, not a validation of all
experiments or a description of the original project's latest release. The Python package and CLI remain
named `dopplertrack` for now.

## How it works

Most outdoor recordings pick up faint tones from propeller aircraft overhead, usually too quiet to hear: the
blade-pass frequency and its harmonics, somewhere between 60 and 400 Hz. The tone drops as the plane goes
by. How fast it drops, and when, depends on where the listener stood relative to the plane's actual path.
Public ADS-B archives have every broadcasting flight for a given day, so each point on the ground predicts
its own set of curves, and the recording is compared against all of them. Two flyovers a known interval
apart are usually enough to rule out everywhere else. One is enough if the recording's start time is known.

## Upstream's results

Upstream tested on two recordings whose locations were public, searching blind over a 100–150 km box with
only the date as a hint.

On colsto's one-hour reference clip from Oyster Bay, NY ([source](https://youtu.be/4CxVxuMVkMc)), the true
pair of flights ranked first of 328 candidate pairs, ahead of the runner-up by 4.9 %. A 50 m refinement put
the peak 43 m from the true spot.

![Modelled curves at the true Oyster Bay location](docs/results/oyster_bay_known_point.png)

*At the true Oyster Bay location, curves computed from two real trajectories (a PC-12 at 6.1 km and a King
Air at 3.6 km) lie on the measured ridges. The only free parameter is a half-second time shift.*

The second recording is a 12-hour eagle-cam stream from North Fort Myers, FL
([source](https://youtu.be/zs2o5Rhlp5w)), with wind on the microphone and a flight school 10 km away. The
true pair ranked first of 607 by a 2.5 % margin. Two flyovers only got within 1.7 km. Adding three more,
found by `detect`, brought it to 592 m. Both aircraft in the pair had passed almost straight overhead, and
from overhead passes the slant distance barely changes as you move the listener around, so they can't pin
the spot. Low passes off to one side can. The full tables are in [docs/results/](docs/results/).

Starting from upstream's saved event fits, this project's inherited baseline gets the same rankings on both recordings
([PLAN.md](PLAN.md), section 2).

## Research goals

Upstream is a proof of concept. Someone has to pick the flyover windows by eye, it has only been run on the
two recordings it was developed on and it always prints a top answer whether or not that answer is right.
I want a tool that can be trusted on a recording it has never seen.

Concretely, that means a `dopplertrack locate` command. It takes the audio, a UTC date, a box and
optionally a start time. It finds the flyovers itself, downloads the flight data, runs the search and
writes a `result.json` plus an HTML report with the matched flights, the measured and modelled curves and
the alternatives it rejected. Its answer is one of three verdicts: *located*, with an uncertainty region;
*ambiguous*, listing each location still plausible; or *insufficient evidence*, with the reason. Silence is
better than a confident wrong answer, and that confident-wrong rate is the number I most want measured.

It also has to be measured honestly. Oyster Bay and the eagle cam shaped the method, so they only count as
development data. Accuracy claims will come from recordings the method was never tuned on (Eclipse
Soundscapes, xeno-canto, A2O and some I plan to record), scored against criteria written down beforehand.
And it should keep working on phone audio, in wind, with jets and machinery in the background and when an
aircraft turns or climbs mid-pass.

Some things are out of scope: aircraft without ADS-B, moving microphones, recordings with no date or region
at all and real-time use.

## Status, November 2026

From raw audio alone, the tool can't yet locate even Oyster Bay. `detect` does find the right two flyovers.
Its curve fits of them are off, though: event 2's frequency comes out 5–11 % high and the time between the
events 5–10 s short. The search turns each fit into hard limits on timing and frequency, so the true answer
gets filtered out and nothing says so. Widening those limits let a wrong pair win on both recordings.
Fitting in narrower windows fixed Oyster Bay and broke the eagle cam. Later rounds (trackers, windows,
hypotheses, a whole-search null, a collective trajectory search) are written up, with their failures, in
[docs/experiments/](docs/experiments/README.md).

What does work: both published results reproduce, a cache of the closest-approach table cuts a repeat
search from about 8 minutes to 2 and the data sits outside the repo with a hashed manifest and one folder
per experiment run.

Work now goes in two steps. First, [research readiness](docs/plans/research-readiness.md): every statistical
method in its own file, both recipes configurable, and a small study runner that compares variants with complete
case accounting. Then the [research plan](PLAN.md): the collective-search successor, its matched null, targeted
fixes for measured bottlenecks, and only then independent claims.

## Pipeline

`spectrogram` decodes the file with ffmpeg and computes a fine-grained STFT of 40–450 Hz. Each frequency
bin is whitened so that steady tones such as mains hum fade and only changing tones stand out.

`detect` slides a window over the whole recording and fits an ideal straight-pass Doppler curve
(base frequency, speed, distance and time of closest approach) in each, with a grid search followed by
Nelder–Mead. `fit` does the same in one window you choose.

`fetch-day` streams one UTC day of [adsb.lol](https://github.com/adsblol) history from GitHub, about 4 GB,
and keeps the non-jet flights that touch the box plus the search-range margin (12 km by default), without
writing the archive to disk. `extract-region` does the same with an archive you already have.

`search` lays a 200 m grid over the box. For every point and flight it computes the closest approach, the
slant distance (using terrain elevation) and when that pass would be heard, allowing for the speed of
sound. A point survives if it hears something like event 1, then something like event 2 the right interval
later, with no other propeller flight passing in between. Survivors are scored by how well the curves
computed from the real trajectories line up with the spectrogram.

`refine` searches a 50 m grid around one winner and can add further flyovers, all on the same clock.

Two shortcuts: `search --point LAT LON` scores a single known location, which is the fastest way to check a
recording whose answer you already have, and `search-single` works from one flyover when the start time is
known.

## Usage

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and `ffmpeg` on your `PATH`. These are the
Oyster Bay commands:

```bash
uv sync
uv run dopplertrack spectrogram recording.mp4 rec.npz
uv run dopplertrack detect rec.npz --band 60 300 --top 10 --out detected.json
uv run dopplertrack fit rec.npz --window 2090 2200 --band 95 200 --harmonics 2 --out ev1.json
uv run dopplertrack fit rec.npz --window 3020 3130 --band 95 195 --out ev2.json
uv run dopplertrack fetch-day 2026-09-08 traces_ny.npz --bbox 40.4 41.3 -74.4 -72.6
uv run dopplertrack search rec.npz --events ev1.json ev2.json --traces traces_ny.npz \
    --bbox 40.4 41.3 -74.4 -72.6 --spacing 200 --harmonics 2 1 --cpa-cache cpa_ny.npz --out results.csv
uv run dopplertrack refine rec.npz results.csv --events ev1.json ev2.json --traces traces_ny.npz \
    --bbox 40.4 41.3 -74.4 -72.6 --harmonics 2 1 --extra ev3.json ev4.json --out fine.csv
```

`search --point LAT LON` scores a single known location instead of a grid,
which is the quickest way to validate the data and physics on a recording
whose location you already know. `detect` prints a ranked table of
candidate flyovers; `--out` writes them as a JSON list whose entries can be
selected directly by rank in both `search` and `refine`:

```bash
uv run dopplertrack search rec.npz --events detected.json --pick 1 2 --traces traces_ny.npz \
    --bbox 40.4 41.3 -74.4 -72.6 --out detected_search.csv
uv run dopplertrack refine rec.npz detected_search.csv --events detected.json --pick 1 2 \
    --traces traces_ny.npz --bbox 40.4 41.3 -74.4 -72.6 --out detected_fine.csv
```

Ranks are 1-based and follow the JSON list's score order; the first selected
event anchors the clock. The existing `--events ev1.json ev2.json` syntax
still works. This hand-off does not fix the detector's fit bias described
above; raw-audio localisation remains a development limitation.

`detect --min-score VALUE` keeps only finite contrast scores strictly above
that value and can write `[]`, printing "no flyovers found". The default of
zero rejects zero evidence, including silence; it is not a calibrated
false-alarm threshold for noisy recordings.

Use the same `--max-range METRES` for `fetch-day` (or `extract-region`),
`search`, and `refine` when changing the default 12 km range. Extraction
saves its geographic envelope and scan counts inside the trace NPZ. Search
warns if that envelope is too small or unknown (older files remain readable),
reports malformed traces skipped at extraction, and checks known airborne
coverage gaps near its top 20 candidate rows during each candidate's inferred
recording time: time gaps over 30 s, missing positions/heights and new-leg
boundaries. These use the same validity and boundary rules as segmentation.
Proximity is checked at the gap's endpoints; missing aircraft or gaps beyond those endpoints cannot be ruled
out. A complete archive download does not mean every aircraft broadcast ADS-B.

Trace files also retain each point's altitude source, position source and
readsb flags. Geometric altitude is preferred, including slot-3 heights
flagged as geometric. readsb's stale flag marks a new reliable fix received
after a reception gap; that fix remains usable. Ground points and missing
positions/heights break airborne segments. The data report gives the
barometric-only share and labels unknown provenance in older NPZs. Geometric heights are WGS-84
ellipsoidal, barometric heights are pressure altitudes, and terrain heights
are orthometric; no geoid or pressure correction is applied yet. Field and
flag definitions follow [readsb's trace format](https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons).

Modelled trajectories carry a validity mask and cannot provide evidence
outside their span or across a source-data gap over 30 s. Resampling retains
that support mask, and scoring preserves missing curve samples. Geometry
keeps the existing 90 s segment gap bound: it may interpolate a 30–90 s hole
to propose a CPA inside it, while the unsupported interval contributes zero
acoustic evidence. This avoids moving CPA to a hole's edge. The forward
propagation map solves the retarded-time relation directly.

Terrain no-data pixels are returned as NaN and excluded from search and
refinement grids with a warning. An entirely missing grid, a missing known
point, or a missing centre needed to assign extra flyovers stops with an
error. `--no-dem` explicitly assumes sea level instead.

ffmpeg must be installed separately (`brew install ffmpeg` on macOS,
`sudo apt-get install ffmpeg` on Debian/Ubuntu). For a local fresh-install
check, build a wheel, install it in a separate environment, then run
`tests/install_smoke.py` with that environment's Python from outside the
checkout. It checks the installed CLI, decoding, spectrogram creation and
empty detection. GitHub CI expansion is deferred.

`uv run pytest -q` runs the tests in about 45 s with no data or network.

## Repository

| Path | Contents |
|---|---|
| `src/dopplertrack/` | the package |
| `tests/` | unit tests, plus an opt-in test on the real Oyster Bay data |
| `docs/results/` | upstream's committed results |
| `docs/superpowers/specs/` | upstream's design spec |
| [docs/plans/research-readiness.md](docs/plans/research-readiness.md) | the engineering plan that comes first |
| [PLAN.md](PLAN.md) | the research plan: the target, evidence, gates, owner decisions |
| [docs/experiments/](docs/experiments/README.md) | one write-up per experiment |
| [docs/reference/](docs/reference/README.md) | reading list for the papers behind the physics |
| `tools/`, `bench/` | data handling, experiment scripts, the manifest of raw inputs |
| [AGENTS.md](AGENTS.md) | working rules: where data lives, branches, how experiments get recorded |

`main` is the independent project's default and development branch. The former upstream baseline is preserved under the tag `archive/upstream-main-before-independence`; new work branches off `main`.
Upstream changes are evaluated explicitly rather than routinely merged. See [the package layout](docs/layout.md#running-methods)
for the current layers and method CLI examples.

All inputs are free: adsb.lol's daily ADS-B archives, the OpenSky mirror of ICAO Doc 8643 for engine types
and AWS Terrain Tiles for elevation.

MIT licence, copyright MacCallister Higgins. See [LICENSE](LICENSE).
