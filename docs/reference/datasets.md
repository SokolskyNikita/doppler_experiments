# Datasets: what was searched, what was taken, what was left

The record of every search for data behind [PLAN.md](../../PLAN.md) section 5.6. What is on disk, with sources, licences and hashes, is in the data root's `MANIFEST.md` and in `bench/manifest.json`; this page keeps the searches, the verdicts and the leads, so the next search starts where the last one stopped. Section 5.6 keeps only the sources and their roles.

A source is only location truth if it meets 5.6's checklist: the microphone to about ±10 m, the start in UTC to the second, the original file, and adsb.lol coverage of the day. Anything else serves detection, physics or scouting.

## Searches so far

| Date | Search | Taken | Record |
|---|---|---|---|
| 2026-11-03 | xeno-canto API v3, remarks mentioning aircraft since 2023: 5,440 hits, 205 with coordinates, clock time and ≥2 min | 7 recordings | `MANIFEST.md`, xeno-canto section |
| 2026-11-03 | Eclipse Soundscapes: all 322 sites, prop passes within 12 km on 2024-04-07 counted with `tools/data/site_traffic.py` | 4 sites | `MANIFEST.md`; `raw/audio/eclipse/sites.csv` |
| 2026-11-03 | Zenodo and acoustic-observatory intake | Livermore, AeroSonicDB, DataSEC, DataSED, 3 A2O soundscapes | `runs/2026-11-03-dataset-intake/` |
| 2026-11-04 | Web search, plus the code, docs, issues and PRs of every repo in [related-projects.md](related-projects.md), our upstream and about 30 newer repos | the five below | `runs/2026-11-04-dataset-intake/` |

## Taken on 2026-11-04

| Source | What it is | Truth | Proposed role |
|---|---|---|---|
| **Alaska seismic nodes**, Seppi, Tape & Fee 2025 ([Zenodo 16997158](https://zenodo.org/records/16997158), CC BY 4.0; code [uafgeotools/parkshwynodal](https://github.com/uafgeotools/parkshwynodal)) | 303 three-component nodes 1 km apart along the Parks Highway, 2019-02-11 to 03-26, 500 samples/s, GPS clocks, FDSN network `ZE` at EarthScope. The Zenodo record holds the node positions, 20,313 node crossings of 1,216 flights within 2 km (CPA time, distance, altitude, speed, heading, type; from Flightradar24), the authors' 1,987 fitted crossings (f0, CPA time, speed, sound speed) and a type table | Surveyed nodes and GPS time; trajectories only as the published CPA parameters | Phase 2 fits and tracks on real passes, independent of Livermore; their per-type tones as an f0 prior. A geophone, not a microphone, and Nyquist is 250 Hz |
| **Lorain Lighthouse cam**, YouTube `my6GvU6lG0U` | 2.6 h archive from 2026-06-15, fixed camera at West Breakwater Light (41.47757, -82.19056 per digitalis-p/doppler-locate) | Position from aerial imagery; the clock is YouTube's `release_timestamp`, which doppler-locate measured as 10.4 s off the audio (`NOTES.md`), so not to the second without our own check | a real livestream case for development. doppler-locate matched one TBM900 at 7.8 km; adsb.lol has 5 prop passes within 12 km during the archive and 2 within 6 km (a C82T at 3.5 km, an M20P at 5.6 km). The cam is 24/7, so recording it with HLS program-date-time is the better source |
| **Sussex/Gatwick sample** ([Zenodo 21072869](https://zenodo.org/records/21072869), CC BY 4.0) | 98 MP3 clips (48 kHz, 48 kbit/s) from 2026-07-03, file names giving the ICAO hex and start and end to the second, with full-day position and event CSVs; Isherwood & Newbury, Forum Acusticum 2026 | No microphone coordinates in the record; the paper names Penshurst Place (51.1771, 0.1862) | jet confusers with flight labels (E5). Ask g.isherwood@sussex.ac.uk for the coordinates and the clock source |
| **AeroLoop** ([Zenodo 17765718](https://zenodo.org/records/17765718), MIT) | Adelaide aircraft and negative clips in train/test zips, with labels; hex and local time to the minute in file names | none | extra detector labels; may overlap AeroSonicDB's sites |
| **EGM96 geoid grid** (`us_nga_egm96_15.tif`, PROJ CDN) | 15′ geoid heights | – | converting ellipsoidal ADS-B heights to the terrain's datum (D4) |

## Leads not taken yet

Take these when a phase needs them, not before.

- **Livestreams to record ourselves**, with HLS program-date-time as the clock:
  - Midway `67BCsiW-1Io` (owner-published 41.77844, -87.74278, ±30 m; jets; a 28 s stream delay read off the burned-in clock by Bodila51/colsto-leak-and-mask);
  - Brighton City Airport apron `mKRJrkz8H8k` (general aviation), Southampton ferry cam `QO-hO_kwwmY` (a TBM700 at 3 km), Miami `_GUsXnlVJmo` (±40 m), all from Bodila51/colsto-leak-and-mask;
  - kmkholm/overpass's 22 webcam sites (`data/streams*.csv`, 40–200 m), as a scouting list.
  - HDOnTap and EarthCam streams have no program-date-time tag, so they can't give a clock.
- **Pinned field recordings with a recordist's date and time**, listed in mojomast/hermes `docs/evaluation.md`: Freesound CC0 868926, 869798 (Manchester approach, jets), 802703, 843280, 807178, 839494; radio aporee locations 70347, 70334, 71095, 71173, 67216, 70927, 73201, 72394; Freesound 858688 (Cessna 172 at Kampina, NL, 2025-07-18, CC BY 4.0, from teamchong/doppler-geo). Pins are unverified. Each needs its day's flight data, and Freesound originals need a login.
- **More Eclipse Soundscapes sites**: 1337isnot1337/DOPPLERGEIST's `benchmarks/audio-candidate-index-20261103.csv` lists 20 sites with visible Doppler bands (706, 688, 656, 485, 281, 847, 696, 103, 756, 920, 962, 665, 762, 710, 443, 445, 439, 430, 923, 791) and a clock-setting column; ESID015 Hot Springs ([Zenodo 20817130](https://zenodo.org/records/20817130)) is 2 h continuous. Rank them with `site_traffic.py` on the 2024-04-07 tar already on disk before downloading 6–7 GB per site-day. DOPPLERGEIST's located-site runs failed by 12–36 km using publisher coordinates and file-name clocks.
- **Alaska, the other 18,300 node crossings**: about 3 GB of `DPZ` at ±150 s, fetched the same way.
- **Risoux** ([Zenodo 10701274](https://zenodo.org/records/10701274), CC BY-SA 4.0, 10.5 GB): 1,314 one-minute forest clips labelled plane or not, Jura 2018, mostly high jets. Only if the false-alarm curve needs more negatives.
- **Seattle home recorder**: the site has about 70 prop passes a day within 6 km (2026-11-01 and 11-02), mostly floatplanes, PC-12s and Cessnas. A band-limited recorder on a phone is being built in a separate project; its location stays in the data root, and recordings stay in `$DOPPLERTRACK_DATA/incoming/seattle-home/` and never in git. One site, so one group.

## Flight data and auxiliary sources

| Source | Cost | What it gives | Use |
|---|---|---|---|
| ADS-B Exchange samples (`samples.adsbexchange.com`) | free, the 1st of each month only, evaluation licence, no redistribution | a snapshot every 60 s from 2016, every 5 s from May 2020; per-aircraft traces from March 2020, 0.5 s high-resolution traces | an L2 cross-check against a second receiver network. No recording on disk falls on a 1st; record Seattle on 2026-12-01 to use it. 60 s is too coarse for 2019 Alaska truth |
| adsb.aero API (`adsb.aero/api/v1`, `llms.txt`) | free, keyless | adsb.lol trajectories from 2025-04-28, simplified to about 50 m and 100 ft | scouting a site's traffic before recording |
| adsb.lol per-aircraft traces and HTTP-range reads of release tars | free | one aircraft without the 3–4 GB day tar (echolocate `corpus/news-tracks/acquire.py`; unheard `evals/DATASETS.md`) | cheaper flight data for single-flyover cases |
| adsb.lol days with gaps | – | 2023-09-14 and 2024-04-17 have no tar parts; 2026-05-05 has no traces | avoid as recording days |
| OpenSky Trino | free for university researchers, government and aviation authorities; commercial licence, fee unpublished | history from 2016 | data before 2023 |
| Flightradar24 API | Explorer plan about $9/month per FR24's blog; higher plans unpriced here | historic positions, reportedly from 2016-05-11 | full Alaska tracks, if the CPA parameters in the crossings table turn out not to be enough |
| FlightAware AeroAPI | Standard plan $100/month minimum; a historical track costs $0.06 per 15 records | history from 2011 | the same, as an alternative |
| ADS-B Exchange enterprise | unpublished; annual subscription with a minimum, no one-off extracts | full archive | not worth it while the free samples cover L2 |
| Website history behind the tar1090 globes (ADS-B Exchange replay, adsb.fi, airplanes.live, theairtraffic): `globe_history/<date>/traces/<xx>/trace_full_<hex>.json` | – | per-aircraft days, as the replay view shows them | not used: a plain request returns 403 on all three tested (2026-11-04). Fine for checking one pass by hand in the replay view |
| tar1090-db `icao_aircraft_types`; teamchong/doppler-geo `prop-types.json` | free | ICAO type classes; 2,302 piston and turboprop designators | type tables |
| Copernicus GLO-30 (AWS), USGS 3DEP | free | 30 m terrain on EGM2008; US 10 m terrain | DEM alternatives |
| GFS 0.25° on AWS, Open-Meteo archive | free | winds aloft outside HRRR's US domain | propagation corrections abroad |

## Checked and rejected

| Source | Why not |
|---|---|
| TartanAviation (KAGC, KBTP) | its audio is ATC radio, not ambient sound |
| Silent Cities (OSF h285u) | 2020, one minute in ten, open clips are 10 s, coordinates only to the city |
| NPS Natural Sounds | no consolidated audio download |
| Worldwide Soundscapes inventory ([Zenodo 14216871](https://zenodo.org/records/14216871)) | 61 airborne collections run into 2023 or later, but almost all are on request; open leads are Taiwan's soundscape network and HIFI Lab Midwest on Arbimon |
| Orcasound hydrophones | CC BY-NC-SA, bucket listing denied, and sound enters water only near overhead |
| Eclipse Soundscapes 2023 annular eclipse | only observer notes are published, no audio |
| Gothenburg 2024 urban birds | occurrence records only |
| Anza 2014 (Mendeley kpftptxdj5), seismo-netizen/Air_Traffic | before ADS-B history |
| DLR RECORD139, NASA small-UAS flyovers, NASA STRIVES-5 | no geography or UTC, drones, or no download found |
| Vireo ([Zenodo 21246876](https://zenodo.org/records/21246876)) | 27.8 GB, DOPPLERGEIST found nothing in 107 of 108 clips |
| FSD50K | 272 Aircraft and 146 fixed-wing clips with per-clip licences inside about 30 GB; only if detection needs more labels |
| SONYC-UST, NoiseCapture | block-level positions, hourly times or level summaries |
| Moosehead Lake fly-in cam | almost no ADS-B within 5 km |
| Hugging Face `Mearman/doppler-adsb` | one day (2025-12-30) |
| Macaulay Library | audio by request |
