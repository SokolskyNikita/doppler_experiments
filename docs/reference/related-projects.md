# Related projects

Reviewed **2026-11-03**. Locator projects are ordered roughly by implemented workflow completeness, **not accuracy**; none has demonstrated our full date-only, large-region target with calibrated verdicts. Research tools and supporting components are listed separately because their scope differs.

Dates are Pacific time: **created** is GitHub repository creation (forks have their own date); **updated** is the latest Git push, not GitHub's broader activity timestamp. These are repository dates, not necessarily the start of the underlying work.

**Origin:** “Video” means the project explicitly credits [colsto's viral video](https://www.youtube.com/watch?v=UytYrhYLOKI) (2026-11-02). “Unclear” means no explicit attribution was found; a new repository or an independent implementation does not establish independent inspiration. “Predates video” describes the project's origin, not its latest update.

## Locator applications

| Project | What it does / completeness | Created | Updated | Origin |
|---|---|---|---|---|
| [Hexay/dopplerprint](https://github.com/Hexay/dopplerprint) | Packaged Rust/Python CLI and browser app: automatic detection, historical ADS-B, terrain/weather, location search and GIS reports. Best-tested with tight time/area priors; automatic localization is not yet benchmarked end to end. | 2026-11-03 | 2026-11-03 | Video |
| [1337isnot1337/DOPPLERGEIST](https://github.com/1337isnot1337/DOPPLERGEIST) | Python upload app and CLI with automatic discovery, regional/country search, persistent jobs, resumability and incomplete-search accounting. Broad infrastructure; independent blind accuracy unestablished. | 2026-11-02 | 2026-11-03 | Video |
| [Espaye/aircraft-doppler](https://github.com/Espaye/aircraft-doppler) | Compact Python CLI/browser workflow: detection, flight acquisition, localization, stability diagnostics and reports. Two real recordings at one site; requires a tightly known recording clock. | 2026-11-02 | 2026-11-03 | Unclear |
| [mojomast/Hermes](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) | Python CLI/plugin with tonal and experimental broadband detection, historical data, date-only search, caches and reports. Complete research workflow; held-out localization mostly fails. | 2026-11-02 | 2026-11-03 | Video |
| [digitalis-p/doppler-locate](https://github.com/digitalis-p/doppler-locate) | Python detector, desktop app and CONUS search with FFT templates, weather and CPU/GPU scoring. Demonstrates Oyster Bay localization from measured event inputs; automatic independent localization unproven. | 2026-11-02 | 2026-11-02 | Video |
| [codyps/echolocate](https://github.com/codyps/echolocate) | Rust/Wasm native and browser tool: ridge extraction, historical-flight acquisition, coherent scoring, shared-site fusion and frozen evaluation. Implemented workflow; unreliable/ambiguous point locations. | 2026-11-03 | 2026-11-03 | Video; credited in NOTICE |
| [gwendall/unheard](https://github.com/gwendall/unheard) | Phone/browser aircraft identification from audio and ADS-B, with multi-resolution matching and extensive evaluation. Also has experimental location/time searches; strongest evidence is for identification at a known receiver. | 2026-11-02 | 2026-11-03 | Video |
| [jdak907/provenance](https://github.com/jdak907/provenance) | Broader recording-forensics app combining acoustic aircraft localization with ENF time/grid matching, video flicker and reports. Acoustic workflow needs supplied flight data. | 2026-11-03 | 2026-11-03 | Video for acoustic locate; other methods from literature |
| [AlanBacker/audio-flyover-geolocation](https://github.com/AlanBacker/audio-flyover-geolocation) | Python pipeline and agent skill with acquisition, tracking, matching, ambiguity diagnostics and synthetic stress tests. No independent real-localization validation. | 2026-11-03 | 2026-11-03 | Video |
| [Mearman/doppler](https://github.com/Mearman/doppler) | TypeScript library, CLI and PWA with ridge tracking, flight-pair indexing and location solving. Substantial app scaffolding; default demonstration uses synthetic flights. | 2026-11-03 | 2026-11-03 | Same colsto challenge used; inspiration unstated |
| [amintt2/flyover-locator](https://github.com/amintt2/flyover-locator) | Python web app with detection, daily flight indexes, terrain, localization and multi-day search. Prototype with restrictive flight prefilters; independent accuracy unestablished. | 2026-11-02 | 2026-11-03 | Unclear |
| [Goprogabriel/echotrace](https://github.com/Goprogabriel/echotrace) | Browser workbench for measured spectra, manually selected tonal tracks, historical-flight import/search and spectral-control diagnostics. No established real-world accuracy. | 2026-11-02 | 2026-11-03 | Video **and** Paras Chopra's X example |
| [WebForks/the-listener](https://github.com/WebForks/the-listener) | Small Python CLI for flyover analysis, historical-flight matching and ranked location hypotheses. Synthetic/development demonstrations; real accuracy unverified. | 2026-11-03 | 2026-11-03 | Video |
| [y0d4a/doppler-locator](https://github.com/y0d4a/doppler-locator) | Experimental workbench combining recording-time metadata, audio analysis, ADS-B retrieval and bounded location search. Requires a genuine recording timestamp. | 2026-11-03 | 2026-11-03 | Unclear |
| [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack) — our upstream | Python spectrogram/detect/fit/fetch/search/refine commands with two published development examples. Working proof of concept; manual event inputs and separate stages remain. | 2026-11-03 | 2026-11-03 | Video |

## Research implementations and narrower experiments

Ordered from broader implemented pipelines toward focused experiments and foundations; these are not interchangeable with locator applications.

| Project | What it does / completeness | Created | Updated | Origin |
|---|---|---|---|---|
| [kmkholm/overpass](https://github.com/kmkholm/overpass) | Research extension of dopplertrack: learned ridge detection, contrast scoring, location verification/search, conformal sets and tone scrubbing. Depends on an external dopplertrack checkout; validation claims need auditing. | 2026-11-03 | 2026-11-03 | Via video-derived dopplertrack; same reference audio |
| [jmarcoz1/doppler-geolocate](https://github.com/jmarcoz1/doppler-geolocate) | Python/notebook pipeline with trajectory splines, ridge extraction, variable-projection localization and multipath experiments. Synthetic end-to-end demo; free historical acquisition unfinished. | 2026-11-03 | 2026-11-03 | Unclear |
| [Bortlesboat/Hermes fork](https://github.com/Bortlesboat/hermes-aircraft-doppler-geolocation) | Fork of the earlier Hermes scripts; the `fix/smooth-adsb-velocity` branch adds position smoothing before Doppler prediction. A targeted patch, not a separate finished app. | 2026-11-02 | 2026-11-02 | Video, via Hermes |
| [Bortlesboat/aircraft-doppler-realworld-test](https://github.com/Bortlesboat/aircraft-doppler-realworld-test) | Recording and evaluation harness around Hermes, including HLS clock evidence and four selected webcam jet passes. A constrained experiment, not a general locator. | 2026-11-02 | 2026-11-02 | Video and Hermes |
| [cbonitz/doppler-experiments](https://github.com/cbonitz/doppler-experiments) | First-principles waveform simulations and synthetic localization tests examining timing ambiguity, model mismatch and claims in the video. Numerical investigation rather than an application. | 2026-11-02 | 2026-11-02 | Video |
| [ss2098/aircraft_spectrograms](https://github.com/ss2098/aircraft_spectrograms) | Aircraft Doppler, visibility and multi-aircraft analysis for dense seismic nodal arrays. Research scripts with local-data assumptions; not unknown-microphone localization. | 2026-05-18 | 2026-08-06 | Independent; predates video |
| [seismo-netizen/Air_Traffic](https://github.com/seismo-netizen/Air_Traffic) | MATLAB spectrogram and Doppler-curve fitting for seismic aircraft events, using selected windows and external reference files. Focused analysis scripts. | 2021-09-02 | 2021-09-02 | Independent; predates video |
| [SarpHarbali/aircraft-audio-geolocation](https://github.com/SarpHarbali/aircraft-audio-geolocation) | Physics-first Python foundation: coordinates, trajectories, propagation delay, Doppler and synthetic/media ingestion. Explicitly lacks detector, matcher and end-to-end localization. | 2026-08-27 | 2026-08-27 | Independent; predates video |

## Supporting components and datasets

Ordered roughly by completeness within their own role. These are independently developed components, not aircraft-audio locator competitors.

| Project | What it does / completeness | Created | Updated | Origin |
|---|---|---|---|---|
| [wiedehopf/readsb](https://github.com/wiedehopf/readsb) | Established ADS-B decoder/receiver software and authoritative trace/altitude field documentation. | 2021-01-02 | 2026-11-02 | Independent; predates video |
| [dstl/Stone-Soup](https://github.com/dstl/Stone-Soup) | Established tracking and data-association framework, including global assignment with unmatched alternatives. | 2017-07-26 | 2026-11-03 | Independent; predates video |
| [OverLordGoldDragon/ssqueezepy](https://github.com/OverLordGoldDragon/ssqueezepy) | Established Python time-frequency transforms, synchrosqueezing and ridge extraction. | 2020-01-28 | 2025-08-22 | Independent; predates video |
| [sdr-enthusiasts/docker-planefence](https://github.com/sdr-enthusiasts/docker-planefence) | Deployable receiver-side flight/noise monitoring and reporting infrastructure. | 2021-02-05 | 2026-11-01 | Independent; predates video |
| [kx1t/docker-noisecapt](https://github.com/kx1t/docker-noisecapt) | Deployable Planefence add-on for noise levels and spectrograms; deliberately does not retain audio. | 2021-02-16 | 2025-10-05 | Independent; predates video |
| [aerosonicdb/AeroSonicDB-YPAD0523](https://github.com/aerosonicdb/AeroSonicDB-YPAD0523) | Published aircraft-audio dataset tooling, MFCC features and classification baselines; detection research rather than location validation. | 2023-06-07 | 2024-11-03 | Independent; predates video |
| [geo-ant/varpro](https://github.com/geo-ant/varpro) | Documented Rust library for separable nonlinear least squares and projected derivatives. | 2021-01-27 | 2025-11-13 | Independent; predates video |
| [sxs-collaboration/varpro](https://github.com/sxs-collaboration/varpro) | Compact Python weighted variable-projection solver with derivative and rank diagnostics. | 2022-03-11 | 2025-10-17 | Independent; predates video |
| [ProfLear/VarProPy](https://github.com/ProfLear/VarProPy) | Python variable-projection package with weighted fits, bounded coefficients, model helpers and tests. | 2026-09-11 | 2026-09-11 | Independent; predates video |

Sources: GitHub repository API fields `created_at` and `pushed_at`, retrieved on the review date; linked repository READMEs and reviewed implementations. Non-obvious origin evidence: Echolocate's [NOTICE](https://github.com/codyps/echolocate/blob/6f73d98dc466614e4e444043afebb36e9970255d/NOTICE.md), Echotrace's [method notes](https://github.com/Goprogabriel/echotrace/blob/4caf53227a0eb7ee3d386b5028b8ccdf98b4ae8b/docs/METHOD.md) (including [Paras Chopra's X post](https://x.com/paraschopra/status/2117561731065274562)), and Mearman's README challenge fixtures. “Unclear” does not mean independently originated.
