"""What a benchmark run reads, for a box that starts with nothing but the repo at a pinned commit.

`bench inputs [--profile P] [case ...]` and `bench inputs --tier1` print three lists:
- data: files under $DOPPLERTRACK_DATA, each with its SHA-256 when the manifest records one: spectrograms,
  trace files and anything else a case or span reads. A box copies these; raw audio is listed only as a source
  of the derived files, which `bench build` could remake from it.
- repo: files the commit already has (labels, saved fits), listed so a wrapper can check them.
- cache: what lives under $DOPPLERTRACK_CACHE. The CPA tables are named one per case grid and flight data; a box
  without one builds it (a cold table is the long part of a run), so copying one in saves that time. The detection
  and window-fit caches are small, content-keyed folders, copied whole; terrarium holds the terrain tiles a DEM
  grid needs, downloaded on a cold box.
"""
from __future__ import annotations

from .cases import latest_case
from .runner import locate_cpa_cache

SMALL_CACHES = ({"path": "detections/", "role": "detection cache (content-keyed)"},
                {"path": "window_fits/", "role": "Tier 1 window-fit cache (content-keyed)"})


class _Lists:
    def __init__(self):
        self.data, self.repo, self.cache = {}, {}, {}

    def add(self, kind: str, path: str, role: str, who: str, sha256: str | None = None):
        bucket = getattr(self, kind)
        e = bucket.setdefault(path, {"path": path, "role": role, "used_by": []})
        if sha256:
            e["sha256"] = sha256
        if who not in e["used_by"]:
            e["used_by"].append(who)

    def doc(self, **head) -> dict:
        return {**head, **{k: sorted(getattr(self, k).values(), key=lambda e: e["path"]) for k in ("data", "repo", "cache")}}


def _case_files(out: _Lists, case: dict, profile: str, who: str, cpa: bool = True):
    sha = {d["path"]: d["sha256"] for d in case.get("derived", [])}
    out.add("data", case["spectrogram"], "spectrogram", who, sha.get(case["spectrogram"]))
    fd = case["flight_data"]
    key = "locate_traces" if profile == "locate" and "locate_traces" in fd else "traces"
    for p in [fd[key]] if isinstance(fd[key], str) else fd[key]:
        out.add("data", p, "flight data", who, sha.get(p))
    if profile == "saved-fit" and case["events"]["mode"] == "saved_fits":
        for p in case["events"]["files"]:
            out.add("repo", p, "saved fits", who)
    for f in case["source"]["raw"]:
        out.add("data", f["path"], "raw source (only to rebuild derived files)", who, f["sha256"])
    if cpa:
        name = case["search"]["cpa_cache"]
        out.add("cache", locate_cpa_cache(case, name) if profile == "locate" else name, "CPA table (built if absent)", who)
    if case["search"].get("dem"):
        out.add("cache", "terrarium/", "terrain tiles (downloaded if absent)", who)


def run_inputs(case_ids: list[str], profile: str) -> dict:
    out = _Lists()
    for cid in case_ids:
        _case_files(out, latest_case(cid), profile, cid)
        out.add("repo", "bench/cases.json", "cases and their labels", cid)
    for c in SMALL_CACHES[:1]:
        out.add("cache", c["path"], c["role"], "all")
    return out.doc(kind="bench run", profile=profile, cases=case_ids)


def tier1_inputs(sets=("development",)) -> dict:
    from .tier1 import load_tier1
    doc, out = load_tier1(), _Lists()
    spans = [s for s in doc["spans"] if s["set"] in sets]
    for s in spans:
        out.add("data", s["spectrogram"]["path"], "spectrogram", s["id"], s["spectrogram"].get("sha256"))
        out.add("repo", s["labels"], "span labels", s["id"])
        if s.get("reference_case"):
            case = latest_case(s["reference_case"])
            fd = case["flight_data"]
            sha = {d["path"]: d["sha256"] for d in case.get("derived", [])}
            for p in [fd["traces"]] if isinstance(fd["traces"], str) else fd["traces"]:
                out.add("data", p, "flight data for the trajectory reference", s["id"], sha.get(p))
    for cid in doc["known_point"]:
        # the known point searches a one-point grid, so it needs no CPA table
        _case_files(out, latest_case(cid), "saved-fit", f"known point {cid}", cpa=False)
    for c in SMALL_CACHES:
        out.add("cache", c["path"], c["role"], "all")
    out.add("repo", "bench/tier1.json", "spans", "all")
    return out.doc(kind="tier1", sets=list(sets), spans=[s["id"] for s in spans], known_point=doc["known_point"])
