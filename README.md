# dopplertrack (fork)

Acoustic geolocation from the Doppler curves of propeller aircraft: given a recording, its date and a rough
region, find where it was made.

> **Credit.** This is a fork of [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack) by
> MacCallister Higgins (MIT), which built the method, the pipeline and both validations below. That project
> is itself an open reimplementation of the technique in colsto's video
> ["I discovered a sound that leaks your exact location"](https://www.youtube.com/watch?v=UytYrhYLOKI),
> which released no code. Fixes that don't depend on the fork go back upstream.

## The idea

Most outdoor recordings carry faint, usually inaudible tones from passing propeller aircraft: the
blade-pass fundamental and its harmonics, roughly 60–400 Hz. As a plane passes, its tone sweeps down, and
the exact shape of that sweep depends on where the listener stood relative to the plane's real path.
Public ADS-B history records every flight that day, so each candidate spot on the ground predicts its own
curves, and the recording picks out the spot whose curves match. Two flyovers a known time apart (or one,
if the recording's clock time is known) are usually enough to rule out everywhere else.

## What upstream showed

Upstream's numbers, on two recordings with known answers, both searched blind over a 100–150 km box with only the date given:

| Recording | True flight pair | Distance from truth |
|---|---|---|
| Oyster Bay, NY, 1 h ([source](https://youtu.be/4CxVxuMVkMc)), colsto's reference clip | 1st of 328 pairs, 4.9 % margin | 43 m after a 50 m refinement |
| Eagle cam, North Fort Myers, FL, 12 h ([source](https://youtu.be/zs2o5Rhlp5w)), windy and near a busy airport | 1st of 607 pairs, 2.5 % margin | 1.7 km from two flyovers; 592 m with three more |

![Modelled curves at the true Oyster Bay location](docs/results/oyster_bay_known_point.png)

*At the true Oyster Bay location, the curves modelled from two real flights' trajectories (a PC-12 at
6.1 km, a King Air at 3.6 km) sit on the measured ridges with no free parameters but a half-second shift.*

The eagle cam taught two lessons. Aircraft passing nearly overhead pin a location poorly, since the slant
distance hardly changes as the listener moves; low, off-to-the-side passes pin it well, so long recordings
with many flyovers help. And scoring must count the whole measured window, or a flight that leaves the data
mid-pass wins on its bright half. Tables behind these numbers are in [docs/results/](docs/results/).

The fork reproduces both results from the committed event fits (see [PLAN.md](PLAN.md) section 2).

## What this fork is for

Upstream is a proof of concept: it works when a person picks the flyover windows, on the two recordings it
was developed on, and it always returns a top answer, right or not. The aim here is a tool you can trust
on a recording it has never seen:

- **One command.** `dopplertrack locate` takes audio, a UTC date and a box (optionally a start time) and
  does the rest: finds the flyovers, fetches the flight data, searches, and writes a `result.json` and an
  HTML report showing the matched flights, the measured and modelled curves, and the alternatives.
- **A verdict, not just a ranking.** `located` with an uncertainty region, `ambiguous` with every
  plausible location, or `insufficient evidence` with the reason. A wrong answer stated confidently is the
  failure that matters most.
- **Claims measured on held-out data.** Oyster Bay and the eagle cam shaped the method, so they're
  development data only. Accuracy and the confident-wrong rate get measured on independent recordings
  (Eclipse Soundscapes, xeno-canto, A2O, recordings made for the purpose), against criteria fixed in
  advance.
- **Robust to real recordings**: phone codecs, wind, jets and machinery, aircraft that turn or climb.

Out of scope: aircraft without ADS-B, moving microphones, recordings with no date or region, real time.

## Where it stands (November 2026)

**Working:** both published results reproduce; a content-keyed CPA cache cuts a re-search from about
8 min to 2; data lives outside the repo with a hashed manifest, and each experiment gets its own run
folder and record.

**Not yet:** from raw audio alone it can't locate even Oyster Bay. `detect` finds the right flyovers, but
its fits of real passes are biased (event 2's f0 comes out 5–11 % high and its timing 5–10 s short), and
the search turns every fit into hard gates, so the true answer is filtered out without a word. Widening the
gates lets wrong pairs win, and narrowing the fit windows helps one recording and breaks the other. The
leading ideas are pairing on the steepest-fall time instead of the heard CPA, extracting frequency tracks
to fit by least squares, and using the flyovers a search didn't use as a consistency check. Each
experiment is written up in [docs/experiments/](docs/experiments/README.md).

**Route** (detail in [PLAN.md](PLAN.md)):

| Milestone | Delivers |
|---|---|
| M1: a measuring stick | small known bugs fixed, a versioned result record, a seed benchmark with baselines |
| M2: first usable release | `locate`, verdicts with abstention, the report, an installable release |
| M3: validated claims | error rates and region coverage measured on independent recordings |
| M4: further out | uncertain dates, larger regions, jets as a signal, single flyovers with a rough time |

## Pipeline today

1. `spectrogram`: decode with ffmpeg, a high-resolution STFT of 40–450 Hz, whitened per frequency bin so
   only *changing* tones stand out.
2. `detect` / `fit`: grid search plus Nelder–Mead for an ideal straight-pass Doppler curve
   (f0, speed, closest-approach distance and time), over the whole recording or in one window.
3. `fetch-day`: stream one UTC day of [adsb.lol](https://github.com/adsblol) history (about 4 GB, nothing
   stored) and keep the non-jet flights touching the box. `extract-region` does the same from a local
   archive.
4. `search`: for every grid point (200 m) and flight, the closest point of approach, its slant distance
   (with terrain) and propagation-delayed heard time. Keep points that hear the first pass and then, the
   right interval later, the second with no other prop flight between, and score the curves modelled from
   the real trajectories against the spectrogram.
5. `refine`: a 50 m grid around a winner, optionally adding more flyovers locked to the same clock.

`search --point LAT LON` scores one known location, the quickest check on a recording whose answer you
know. `search-single` handles one flyover when the recording's clock time is known.

## Usage

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and `ffmpeg` on `PATH`.

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

These are the Oyster Bay commands. `detect` writes a JSON list, while `search` and `refine` take one
event per file, so for now pick its entries out by hand; the `fit` windows above were chosen by eye.

Tests: `uv run pytest -q` (about 45 s, no data or network).

## Repository

| Path | What |
|---|---|
| `src/dopplertrack/` | the package |
| `tests/` | unit tests, plus an opt-in test on the real Oyster Bay data |
| `docs/results/` | upstream's committed results |
| `docs/superpowers/specs/` | upstream's design spec |
| [PLAN.md](PLAN.md) | the roadmap: destination, open problems, phases, benchmark design |
| [docs/experiments/](docs/experiments/README.md) | one record per experiment: question, numbers, outcome |
| [docs/reference/](docs/reference/README.md) | reading list for the papers behind the physics |
| `tools/`, `bench/` | data handling, experiment scripts, the raw-data manifest |
| [AGENTS.md](AGENTS.md) | working rules: data layout, branches, how experiments are recorded |

Branches: `main` mirrors upstream; `dev` is the fork's line and everything branches from it.

**Data sources, all free:** adsb.lol daily ADS-B archives, the OpenSky mirror of ICAO Doc 8643 for engine
classes, and AWS Terrain Tiles for elevation.

MIT licence, copyright MacCallister Higgins; see [LICENSE](LICENSE).
