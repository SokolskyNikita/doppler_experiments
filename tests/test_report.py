"""The Phase 5 report: every committed fixture record renders, offline, with its exports (src/dopplertrack/report.py)."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from dopplertrack import adsb, audio, report
from dopplertrack.geo import enu_to_lla
import dopplertrack.data.region_loading as region_loading

FIXTURES = Path(__file__).parent / "fixtures" / "records"
CASES = sorted(p.name for p in FIXTURES.iterdir() if (p / "result.json").exists())
SECTIONS = ("Answer", "Map", "Matched flights", "Events", "Pair rules", "Data report", "Funnel", "Execution", "Provenance")


def _render(name, tmp_path, **kw):
    page = report.render_report(FIXTURES / name / "result.json", out_dir=tmp_path / name, **kw)
    return page, page.read_text()


@pytest.mark.parametrize("name", CASES)
def test_every_fixture_renders_every_section_offline(name, tmp_path):
    page, text = _render(name, tmp_path)
    for title in SECTIONS:
        assert f"<h2>{title}</h2>" in text
    assert "could not be drawn" not in text                 # no section fell over
    assert "http://" not in text and "https://" not in text  # no external asset or request
    gj = json.loads((page.parent / "candidates.geojson").read_text())
    rec = json.loads((FIXTURES / name / "result.json").read_text())
    assert sum(f["properties"]["kind"] == "candidate" for f in gj["features"]) == len(rec["candidates"])
    root = ET.fromstring((page.parent / "candidates.kml").read_text().split("\n", 1)[1])
    assert len(root.findall(".//{http://www.opengis.net/kml/2.2}Placemark")) == len(gj["features"])
    v = rec.get("verdict")
    if isinstance(v, dict) and "outcome" in v:
        assert v["outcome"] in text and all(c in text for c in v["reason_codes"])


def test_a_changed_record_renders_marked_unverified(tmp_path):
    _, text = _render("v1-hash-mismatch", tmp_path)
    assert '<body class="unverified">' in text and "unverified record" in text
    _, text = _render("v1-saved-fit", tmp_path)
    assert '<body class="">' in text and "Every number on this page" not in text


def test_an_evaluation_case_carries_its_reminder(tmp_path):
    _, text = _render("v1-saved-fit", tmp_path, case_meta={"set": "evaluation"})
    assert "never for tuning" in text
    _, text = _render("v1-saved-fit", tmp_path, case_meta={"set": "development"})
    assert "never for tuning" not in text


def test_without_its_sidecar_the_map_says_so_and_draws_the_candidates(tmp_path):
    _, text = _render("v1-no-sidecar", tmp_path)
    assert "No score map" in text and "a16b700" in text and "<img" in text
    _, text = _render("v1-saved-fit", tmp_path)
    assert "No score map" not in text


def test_an_early_exit_says_the_search_did_not_run(tmp_path):
    _, text = _render("v2-flight-data-missing-box", tmp_path)
    assert "the search did not run" in text and "No candidate" in text


def test_an_error_record_leads_with_its_errors(tmp_path):
    _, text = _render("runner-error", tmp_path)
    head = text[:text.index("<section>")]
    assert "Execution errors" in head and "synthetic failure" in head


def _straight_pass(tmp_path, lat0, lon0, t_cpa_unix):
    """A trace flying east at 60 m/s, 1,500 m north of the point at 800 m, its CPA at t_cpa_unix."""
    t = np.arange(t_cpa_unix - 300, t_cpa_unix + 300, 2.0)
    e = 60.0 * (t - t_cpa_unix)
    lat, lon, _ = enu_to_lla(e, np.full_like(e, 1500.0), np.zeros_like(e), lat0, lon0)
    tr = adsb.Trace("abc123", "N123AB", "C172", "CESSNA 172", t, lat, lon, np.full_like(t, 800.0),
                    np.full_like(t, 60.0), np.zeros(len(t), bool))
    region_loading.save_traces([tr], tmp_path / "derived" / "traces.npz", metadata={"coverage_bbox": [39, 42, -75, -72]})


def test_the_overlay_and_the_flight_names_come_from_local_files_mapped_by_data_root(tmp_path):
    rec = json.loads((FIXTURES / "v2-locate-ambiguous" / "result.json").read_text())
    (tmp_path / "derived").mkdir()
    sp = audio.Spectrogram(np.arange(0, 600, 0.5), np.arange(40, 251, 1.0), np.zeros((211, 1200), np.float32))
    sp.save(tmp_path / "derived" / "rec.npz")
    lat0, lon0 = rec["refined"]["lat"], rec["refined"]["lon"]
    amu = -1788898650.72
    rec["candidates"][0]["clock"]["audio_minus_utc_s"] = amu
    _straight_pass(tmp_path, lat0, lon0, 300.0 - amu)
    e = rec["events"][0]
    e["fit"].update(t_heard_cpa_audio_s=300.0, t_emission_cpa_audio_s=295.0, window_s=[250.0, 350.0])
    e["assignment"] = {"flight": "abc123", "basis": "top candidate"}
    # the record was written on another machine: its paths only share the derived/ part with this one
    rec["provenance"]["inputs"] = [{"role": "spectrogram", "path": "/elsewhere/data/derived/rec.npz", "bytes": 1,
                                    "sha256": "0" * 64},
                                   {"role": "traces", "path": "/elsewhere/data/derived/traces.npz", "bytes": 1,
                                    "sha256": "0" * 64}]
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "result.json").write_text(json.dumps(rec))
    text = report.render_report(tmp_path / "rec" / "result.json", data_root=tmp_path).read_text()
    assert "abc123 modelled at the refined point" in text
    assert "N123AB" in text and "C172" in text
    assert "no hash file beside the record" in text
    text = report.render_report(tmp_path / "rec" / "result.json").read_text()      # without the mapping
    assert "not on this machine" in text and "N123AB" not in text


def test_the_index_links_each_page(tmp_path):
    pages = [{"case": "a", "page": "a/report.html", "status": "scored", "verdict": "ambiguous", "set": "development"},
             {"case": "b", "status": "error", "note": "report failed: X"}]
    text = report.render_index(tmp_path, pages, title="run").read_text()
    assert '<a href="a/report.html">a</a>' in text and "report failed: X" in text


def test_a_site_relative_record_renders_with_no_coordinate_and_no_export(tmp_path):
    rec = json.loads((FIXTURES / "v2-locate-ambiguous" / "result.json").read_text())
    for c in rec["candidates"]:
        c["offset_m"] = {"east": round((c.pop("lon") + 73.525) * 84000, 1), "north": round((c.pop("lat") - 40.8765) * 111000, 1)}
    rec["refined"]["offset_m"] = {"east": 30.0, "north": -40.0}
    del rec["refined"]["lat"], rec["refined"]["lon"]
    rec["provenance"]["parameters"]["search"]["bbox"] = {"offset_box_m": [-50000.0, 48000.0, -76000.0, 75000.0]}
    rec["frame"], rec["site"] = "site-relative", "home"
    rec["funnel"]["triples_file"] = report.unavailable("not in this fixture") if hasattr(report, "unavailable") else \
        {"unavailable": "not in this fixture"}
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "result.json").write_text(json.dumps(rec))
    page = report.render_report(tmp_path / "rec" / "result.json")
    text = page.read_text()
    assert "could not be drawn" not in text and "offsets from its site" in text and "km north of the site" in text
    assert not (page.parent / "candidates.geojson").exists() and "absolute by nature" in text
    assert "40.87" not in text and "-73.5" not in text
