"""A private case for one new session of the owner's home recorder, from the pilot's as a template.

usage: home_session_case.py SESSION_ID --traces PATH [--extraction-box S N W E] [--pod TEXT] [--box-km 4] [--write]

SESSION_ID names raw/seattle-home/<SESSION_ID>/ (session.json, timeline.jsonl and its FLACs, archived there read-only
like the pilot's). Writes two things, and refuses to overwrite either:
- private/cases/seattle-home-<SESSION_ID>.json: the spectrogram (40-450 Hz, the pipeline's) and, when the session
  stores more than 450 Hz, `spectrogram_wide` at the band test's edge: the stored passband's edge, capped at the
  pre-registered 1800 Hz (docs/experiments/2026-11-04-seattle-home-pilot.md), stated in the file; the audio, the flight
  data (--traces, data-root relative: a public cut such as `fetch-day --keep-jets` output under derived/, or a private
  one under private/) and its envelope, and the search box: a --box-km square around the site, the site 73 m east and
  131 m north of its centre so off the 200 m grid (the box series' placement).
- the case's public entry in bench/cases.json: the pilot's, with this session's id, start time (the first file's first
  sample from the timeline), date and CPA cache name, and nothing that places the site.
Without --write it prints both and writes nothing. The owner's per-file approval for the fleet is separate and comes
first: nothing here ships anything.
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import private as priv  # noqa: E402
from bench.cases import data_root, latest_case  # noqa: E402
from session_spectrogram import session_files  # noqa: E402

TEMPLATE = "seattle-home-20261104-ha-pilot-2"
SITE = "seattle-home"
WIDE_FMAX = 1800.0           # the pre-registered band test's upper edge
OFFSET_M = (73.0, 131.0)     # the box series' placement: the site off every 200 m node


def stored_edge(session: dict) -> float:
    """The stored band's upper edge, Hz: the filter's passband edge, else 0.45 of the stored rate."""
    edge = (session.get("filter") or {}).get("passband_edge_hz")
    return float(edge) if edge else 0.45 * float(session["stored"]["rate_hz"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_id"); ap.add_argument("--traces", required=True)
    ap.add_argument("--extraction-box", nargs=4, type=float, metavar=("S", "N", "W", "E"),
                    help="the traces' envelope, declared (needed when the file has no measured coverage_bbox)")
    ap.add_argument("--pod", default="fetch-day --keep-jets (adsb.lol globe_history)")
    ap.add_argument("--box-km", type=float, default=4.0); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    root = data_root()
    sdir = root / "raw" / "seattle-home" / a.session_id
    session = json.loads((sdir / "session.json").read_text())
    files, start = session_files(sdir)
    case_id = f"seattle-home-{a.session_id}"
    if not (root / a.traces).exists():
        sys.exit(f"{root / a.traces} does not exist")
    edge = stored_edge(session)
    wide = min(WIDE_FMAX, edge) if edge > 450.0 else None
    site = priv.load_site(SITE)
    cache = f"cpa/private/{case_id}_200m_dem.npz"
    derived = [{"path": f"private/derived/{case_id}/rec.npz", "sha256": None,
                "recipe": [["python", "-I", "{repo}/tools/data/session_spectrogram.py",
                            f"{{data}}/raw/seattle-home/{a.session_id}", "{out}"]],
                "note": "built on the fleet's private box or this Mac; the hash is filled when it is first built"}]
    private = {"spectrogram": derived[0]["path"], "derived": derived,
               "audio": {"path": f"raw/seattle-home/{a.session_id}", "of": f"raw/seattle-home/{a.session_id}",
                         "clip_offset_s": 0.0, "clip_offset_samples": 0, "sample_rate_hz": session["stored"]["rate_hz"]},
               "flight_data": {"traces": a.traces,
                               "extraction_note": f"{a.pod}; the envelope as declared on the command line"},
               "search": {"bbox": priv.site_box(site, a.box_km * 1000.0, OFFSET_M), "cpa_cache": cache},
               "box_note": f"a {a.box_km:g} km square, the site {OFFSET_M[0]:g} m east and {OFFSET_M[1]:g} m north of "
                           "its centre, off every 200 m node"}
    if a.extraction_box:
        private["flight_data"]["extraction_box"] = list(a.extraction_box)
    if wide:
        w = {"path": f"private/derived/{case_id}/rec-wide.npz", "sha256": None, "fmax_hz": wide,
             "recipe": [["python", "-I", "{repo}/tools/data/session_spectrogram.py",
                         f"{{data}}/raw/seattle-home/{a.session_id}", "{out}", "--fmax", f"{wide:g}"]],
             "note": f"the band test's spectrogram, 40-{wide:g} Hz (the stored band's edge {edge:g} Hz, capped at "
                     f"{WIDE_FMAX:g})"}
        private["spectrogram_wide"] = w["path"]
        private["derived"].append(w)
    entry = json.loads(json.dumps(latest_case(TEMPLATE)))
    hours = sum(1 for _ in files)
    ms = int(round(start * 1000))
    utc = datetime.datetime.fromtimestamp(ms // 1000, datetime.timezone.utc)
    entry.update(id=case_id, version=1, built_with=subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip(),
        description=f"the owner's home recorder, session {a.session_id} ({hours} file(s), stored to "
                    f"{edge:g} Hz); a private case: its audio, site, flight data and search box live in "
                    "$DOPPLERTRACK_DATA/private/ and never enter git, docs or records; the owner names each file "
                    "before it goes to the private bucket and fleet")
    entry["source"]["identifiers"] = {"session": a.session_id,
                                      "recorder": f"{session['recorder']['name']} {session['recorder']['version']}"}
    entry["start_time"]["utc"] = f"{utc:%Y-%m-%dT%H:%M:%S}.{ms % 1000:03d}Z"
    entry["flight_data"] = {"date": utc.date().isoformat(), "pod": a.pod, "archive_assets": []}
    entry["search"]["cpa_cache"] = cache
    for k in ("audio", "derived", "spectrogram", "spectrogram_wide"):
        entry.pop(k, None)
    print(json.dumps({"public entry": entry, "private case": "written only with --write (it places the site)"}, indent=1))
    if not a.write:
        return
    out = root / "private" / "cases" / f"{case_id}.json"
    if out.exists():
        sys.exit(f"{out} exists")
    cases_path = REPO / "bench" / "cases.json"
    doc = json.loads(cases_path.read_text())
    if any(c["id"] == case_id for c in doc["cases"]):
        sys.exit(f"{case_id} is already in bench/cases.json")
    out.write_text(json.dumps(private, indent=1) + "\n")
    doc["cases"].append(entry)
    cases_path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out} and the entry in {cases_path}; run `uv run python -m bench validate` before committing")


if __name__ == "__main__":
    main()
