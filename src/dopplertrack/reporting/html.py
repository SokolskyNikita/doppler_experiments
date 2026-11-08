"""The report (PLAN Phase 5): one static HTML page per result.json, with GeoJSON and KML of its candidates.

`render_report(result_json)` writes report.html, candidates.geojson and candidates.kml beside the record. The page
has no external assets and makes no network request: figures are inline PNGs, the exports are inline downloads too,
and terrain heights come only from tiles already in the cache. It reads the record, the hash written beside it and
the triples sidecar; it also reads the spectrogram and trace files named in the record's inputs when they are on
this machine (`data_root` maps another machine's paths), and says so wherever one is missing. Any record renders:
schema 1 or 2, an error record, a run that stopped early. A record that doesn't match its hash renders under a
warning, every section marked unverified: the report is for reading, and refusing a changed record is compare's job.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import html
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HASH_SUFFIX = ".sha256"
MAX_CANDIDATE_ROWS = 50


def _unavailable(v) -> bool:
    return isinstance(v, dict) and set(v) == {"unavailable"}


def _esc(v) -> str:
    return html.escape(str(v))


def _fmt(v, nd=3) -> str:
    """One value as page text: an unavailable field shows its reason, numbers a fixed precision."""
    if _unavailable(v):
        return f'<span class="na">n/a: {_esc(v["unavailable"])}</span>'
    if v is None:
        return '<span class="na">none</span>'
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}" if np.isfinite(v) else '<span class="na">not finite</span>'
    if isinstance(v, list) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return ", ".join(_fmt(x, nd) for x in v)
    if isinstance(v, (list, dict)):
        return f"<code>{_esc(json.dumps(v))}</code>"
    return _esc(v)


def _iso(t) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(t), datetime.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return "n/a"


def _table(rows: list[list], head: list[str] | None = None) -> str:
    out = ["<table>"]
    if head:
        out.append("<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _kv(d: dict) -> str:
    return _table([[_esc(k), _fmt(v)] for k, v in d.items()])


def _png(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f'<img alt="figure" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _local(path: str, data_root: Path | None) -> Path | None:
    """A recorded input path on this machine: as written, or its derived/ or raw/ part under data_root."""
    p = Path(path)
    if p.exists():
        return p
    if data_root is not None:
        for part in ("derived", "raw"):
            if part in p.parts:
                q = Path(data_root, *p.parts[p.parts.index(part):])
                if q.exists():
                    return q
    return None


class _Context:
    """What the page knows beyond the record: the hash check, the sidecar and the local input files."""

    def __init__(self, path: Path, record: dict, data_root, case_meta):
        self.path, self.record, self.meta = path, record, dict(case_meta or {})
        self.notes: list[str] = []
        data = path.read_bytes()
        side = path.with_name(path.name + HASH_SUFFIX)
        if not side.exists():
            self.hash_state = "no hash file beside the record"
        else:
            want = side.read_text().split()[0] if side.read_text().split() else ""
            self.hash_state = "ok" if hashlib.sha256(data).hexdigest() == want else "mismatch"
        self.unverified = self.hash_state == "mismatch"
        try:
            from dopplertrack.runtime.records import RecordError, validate
            validate(record)
            self.schema_problems: list[str] = []
        except RecordError as exc:
            self.schema_problems = exc.problems
        self.inputs = {}
        for e in record.get("provenance", {}).get("inputs", []) if isinstance(record.get("provenance"), dict) else []:
            self.inputs.setdefault(e.get("role"), []).append(_local(e.get("path", ""), data_root))
        self._sp, self._traces = None, None

    def triples(self):
        """The sidecar's best score per grid point, or why there is none."""
        tf = self.record.get("funnel", {}).get("triples_file") if isinstance(self.record.get("funnel"), dict) else None
        if _unavailable(tf):
            return None, tf["unavailable"]
        if not tf:
            if not self.record.get("candidates"):
                return None, "the search did not run, so there is nothing to map"
            return None, "the record has no triples sidecar (records before it, such as a16b700's, list candidates only)"
        p = self.path.parent / tf["path"]
        if not p.exists():
            return None, f"its triples sidecar {tf['path']} is not beside the record"
        if _sha256(p) != tf.get("sha256"):
            return None, f"its triples sidecar {tf['path']} doesn't match the hash in the record"
        with np.load(p) as z:
            stage = "scored" if "scored__score" in z.files else None
            if stage is None:
                return None, "the triples sidecar has no scored stage"
            x, y = ("east", "north") if "scored__east" in z.files else ("lat", "lon")
            lat, lon, score, g = (z[f"scored__{k}"] for k in (y, x, "score", "gidx"))
        if not len(g):
            return None, "no triple was scored"
        order = np.argsort(-score, kind="stable")
        _, first = np.unique(g[order], return_index=True)
        keep = order[first]
        return (lat[keep], lon[keep], score[keep]), None

    def spectrogram(self):
        if self._sp is None:
            paths = [p for p in self.inputs.get("spectrogram", []) if p is not None]
            if not paths:
                self._sp = False
            else:
                from dopplertrack.components.spectrogram import Spectrogram
                try:
                    self._sp = Spectrogram.load(paths[0])
                except (OSError, ValueError, KeyError):
                    self._sp = False
        return self._sp or None

    def traces(self):
        if self._traces is None:
            named = self.inputs.get("traces", [])
            if not named or any(p is None for p in named):
                self._traces = False
            else:
                from dopplertrack.data.day_seams import join_days
                self._traces = join_days(named)[0]
        return self._traces or None


def _elevation(lat: float, lon: float) -> tuple[float, str]:
    """Ground height at a point from the cached terrain tiles only; 0 m, said so, when its tile isn't cached."""
    from dopplertrack.data.terrain import Terrain

    class Offline(Terrain):
        def _download(self, x, y, force=False):
            if not self._path(x, y).exists():
                raise FileNotFoundError("tile not cached")

    try:
        h = float(Offline().elevation(np.array([lat]), np.array([lon]))[0])
        return (max(h, 0.0), "terrain from the cached tile") if np.isfinite(h) else (0.0, "terrain no-data: 0 m")
    except (OSError, ValueError):
        return 0.0, "no cached terrain tile: observer at 0 m"


# sections ------------------------------------------------------------------------------------------------------

def _header(ctx: _Context) -> str:
    rec = ctx.record
    case = rec.get("case") or {}
    v = rec.get("verdict")
    if isinstance(v, dict) and "outcome" in v:
        badge = (f'<span class="badge {v["outcome"]}">{_esc(v["outcome"])}</span> '
                 + " ".join(f'<code>{_esc(c)}</code>' for c in v.get("reason_codes", []))
                 + "<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in v.get("reasons", [])) + "</ul>")
    else:
        badge = f'<span class="badge none">no verdict</span> {_fmt(v)}'
    errors = (rec.get("execution") or {}).get("errors") or []
    code = (rec.get("provenance") or {}).get("code") or {}
    set_ = ctx.meta.get("set")
    rows = [["case", f"{_esc(case.get('id', '?'))} v{_esc(case.get('version', '?'))}"],
            ["set", _esc(set_) if set_ else '<span class="na">not a benchmark case, or not given</span>'],
            ["schema", _esc(rec.get("schema_version"))],
            ["record hash", f'<span class="{"bad" if ctx.unverified else ""}">{_esc(ctx.hash_state)}</span>'],
            ["created", _fmt((rec.get("provenance") or {}).get("created"))],
            ["code", f"{_fmt(code.get('git_commit'))}{' (uncommitted changes)' if code.get('git_dirty') is True else ''}"]]
    out = [f"<h1>{_esc(case.get('id', 'result'))}</h1>", badge, _table(rows)]
    if ctx.unverified:
        out.insert(0, '<div class="warn">This record does not match the hash written beside it: it changed after it was '
                      'written. Every number on this page is from an unverified record.</div>')
    if set_ == "evaluation":
        out.insert(0, '<div class="warn eval">Evaluation case: read it at a milestone only, never for tuning.</div>')
    if errors:
        out.append('<div class="warn">Execution errors: <ul>' + "".join(f"<li>{_esc(e)}</li>" for e in errors) + "</ul></div>")
    if ctx.schema_problems:
        out.append('<div class="note">The record does not validate against its schema: <ul>'
                   + "".join(f"<li>{_esc(p)}</li>" for p in ctx.schema_problems[:20]) + "</ul></div>")
    return "".join(out)


def _top(rec):
    c = rec.get("candidates") or []
    return c[0] if c else None


def _relative(rec: dict) -> bool:
    """A private case's record (bench/private.py): positions are offsets from its site, never coordinates."""
    return rec.get("frame") == "site-relative"


def _where(item: dict) -> str:
    if "offset_m" in item:
        o = item["offset_m"]
        return f"{o['east'] / 1000:+.3f} km east, {o['north'] / 1000:+.3f} km north of the site"
    return f"{item['lat']:.6f}, {item['lon']:.6f}"


def _answer(ctx: _Context) -> str:
    rec, top = ctx.record, _top(ctx.record)
    if top is None:
        return '<p class="na">No candidate: the search found none, or did not run.</p>'
    amu = top["clock"]["audio_minus_utc_s"]
    rows = [["top candidate", f"{_where(top)} ({' + '.join(map(_esc, top['flights']))})"]]
    ref = rec.get("refined")
    rows.append(["refined point", _where(ref) if isinstance(ref, dict) and ("lat" in ref or "offset_m" in ref)
                 else _fmt(ref)])
    sp = ctx.spectrogram()
    end = f" to {_iso(float(sp.t[-1]) - amu)}" if sp is not None else ""
    rows.append(["recording start (UTC)", f"{_iso(-amu)}{end}, from the top candidate's clock "
                                          f"(audio = UTC {amu:+.2f} s)"])
    c = rec["candidates"]
    if len(c) > 1 and c[1]["score"]:
        rows.append(["margin over #2", f"{100 * (c[0]['score'] - c[1]['score']) / c[1]['score']:.1f} %"])
    return _table(rows)


def _map_relative(ctx: _Context) -> str:
    """The site-relative map: east and north km from the site, no site marker, no latitude or longitude."""
    import matplotlib.pyplot as plt
    rec = ctx.record
    cands = rec.get("candidates") or []
    best, why = ctx.triples()
    fig, ax = plt.subplots(figsize=(7.5, 6))
    if best is not None:
        north, east, score = best
        sc = ax.scatter(east / 1000, north / 1000, c=score, s=4, cmap="viridis", linewidths=0)
        fig.colorbar(sc, ax=ax, label="best score per grid point")
    for c in cands[:10]:
        e, n = c["offset_m"]["east"] / 1000, c["offset_m"]["north"] / 1000
        ax.plot(e, n, "o", mfc="none", mec="red", ms=9)
        ax.annotate(str(c["rank"]), (e, n), xytext=(4, 4), textcoords="offset points", color="red", fontsize=9)
    ref = rec.get("refined")
    if isinstance(ref, dict) and "offset_m" in ref:
        ax.plot(ref["offset_m"]["east"] / 1000, ref["offset_m"]["north"] / 1000, "*", color="orange", ms=14, mec="k",
                label="refined")
        ax.legend(loc="upper right")
    box = ((rec.get("provenance") or {}).get("parameters") or {}).get("search", {}).get("bbox")
    if isinstance(box, dict) and "offset_box_m" in box:
        s_, n_, w_, e_ = (v / 1000 for v in box["offset_box_m"])
        ax.plot([w_, e_, e_, w_, w_], [s_, s_, n_, n_, s_], "k-", lw=1)
    ax.set_aspect(1)
    ax.grid(True, lw=0.4, alpha=0.6)
    ax.set_xlabel("east of the site (km)"); ax.set_ylabel("north of the site (km)")
    out = [_png(fig), "<p>A private case: positions are offsets from its site, which isn't drawn, and no latitude or "
                      "longitude is shown. Solid box: the search box. Red circles: candidates 1–10.</p>"]
    if why:
        out.append(f'<p class="na">No score map: {_esc(why)}. The candidates are drawn alone.</p>')
    rows = [[c["rank"], _esc(_where(c)), _esc(" + ".join(c["flights"])), _fmt(c["score"]), _fmt(c["event_scores"])]
            for c in cands[:MAX_CANDIDATE_ROWS]]
    if rows:
        out.append(_table(rows, ["rank", "position", "flights", "score", "event scores"]))
    return "".join(out)


def _map(ctx: _Context) -> str:
    if _relative(ctx.record):
        return _map_relative(ctx)
    import matplotlib.pyplot as plt
    rec = ctx.record
    cands = rec.get("candidates") or []
    params = (rec.get("provenance") or {}).get("parameters") or {}
    search = params.get("search") if isinstance(params.get("search"), dict) else {}
    box = search.get("bbox")
    if not box:
        flight = (rec.get("data_limitations") or {}).get("flight_data")
        box = None if not isinstance(flight, dict) else flight.get("search_box")
    best, why = ctx.triples()
    if not cands and best is None and not box:
        return f'<p class="na">Nothing to draw: no candidates{"; " + _esc(why) if why else ""}.</p>'
    fig, ax = plt.subplots(figsize=(7.5, 6))
    if best is not None:
        lat, lon, score = best
        sc = ax.scatter(lon, lat, c=score, s=4, cmap="viridis", linewidths=0)
        fig.colorbar(sc, ax=ax, label="best score per grid point")
    for c in cands[:10]:
        ax.plot(c["lon"], c["lat"], "o", mfc="none", mec="red", ms=9)
        ax.annotate(str(c["rank"]), (c["lon"], c["lat"]), xytext=(4, 4), textcoords="offset points", color="red", fontsize=9)
    ref = rec.get("refined")
    if isinstance(ref, dict) and "lat" in ref:
        ax.plot(ref["lon"], ref["lat"], "*", color="orange", ms=14, mec="k", label="refined")
        ax.legend(loc="upper right")
    lats = [c["lat"] for c in cands]
    if box:
        ax.plot([box[2], box[3], box[3], box[2], box[2]], [box[0], box[0], box[1], box[1], box[0]], "k-", lw=1)
        need = None
        flight = (rec.get("data_limitations") or {}).get("flight_data")
        if isinstance(flight, dict):
            need = flight.get("search_box_plus_range")
        if need:
            ax.plot([need[2], need[3], need[3], need[2], need[2]], [need[0], need[0], need[1], need[1], need[0]],
                    "k--", lw=0.8)
        lats += [box[0], box[1]]
    lat_mid = float(np.mean(lats)) if lats else 0.0
    ax.set_aspect(1 / np.cos(np.radians(lat_mid)))
    ax.grid(True, lw=0.4, alpha=0.6)
    ax.set_xlabel("longitude (°)"); ax.set_ylabel("latitude (°)")
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    km = 10 ** np.floor(np.log10(max((x1 - x0) * 111.32 * np.cos(np.radians(lat_mid)) / 4, 0.01)))
    dlon = km / (111.32 * np.cos(np.radians(lat_mid)))
    ax.plot([x0 + 0.05 * (x1 - x0), x0 + 0.05 * (x1 - x0) + dlon], [y0 + 0.05 * (y1 - y0)] * 2, "k-", lw=3)
    ax.annotate(f"{km:g} km", (x0 + 0.05 * (x1 - x0), y0 + 0.07 * (y1 - y0)), fontsize=8)
    out = [_png(fig), "<p>Solid box: the search box; dashed: the box plus the search range. Red circles: candidates "
                      "1–10. No basemap.</p>"]
    if why:
        out.append(f'<p class="na">No score map: {_esc(why)}. The candidates are drawn alone.</p>')
    rows = []
    for c in cands[:MAX_CANDIDATE_ROWS]:
        amu = c["clock"]["audio_minus_utc_s"]
        rows.append([c["rank"], f"{c['lat']:.6f}", f"{c['lon']:.6f}", _esc(" + ".join(c["flights"])), _fmt(c["score"]),
                     _fmt(c["event_scores"]), _fmt(amu, 2), _fmt(c["clock"].get("shift_s"), 2), _iso(-amu)])
    if rows:
        out.append(_table(rows, ["rank", "lat", "lon", "flights", "score", "event scores", "audio − UTC (s)", "shift (s)",
                                 "start (UTC)"]))
        if len(cands) > MAX_CANDIDATE_ROWS:
            out.append(f"<p>{len(cands) - MAX_CANDIDATE_ROWS} more candidates in the record.</p>")
    return "".join(out)


def _flight_names(ctx: _Context) -> dict:
    rec = ctx.record
    names = []
    for e in rec.get("events") or []:
        a = e.get("assignment")
        if isinstance(a, dict) and a.get("flight"):
            names.append(a["flight"])
    top = _top(rec)
    names += list(top["flights"]) if top else []
    ref = rec.get("refined")
    if isinstance(ref, dict):
        names += list(ref.get("extra_flights") or [])
    return dict.fromkeys(names)


def _flights(ctx: _Context) -> str:
    names = _flight_names(ctx)
    if not names:
        return '<p class="na">No flight was matched.</p>'
    traces = ctx.traces()
    info = {}
    if traces:
        for tr in traces:
            if tr.icao in names and tr.icao not in info:
                info[tr.icao] = (tr.reg, tr.typ, tr.desc, tr.t[0], tr.t[-1])
    rows = [[_esc(n)] + ([_fmt(info[n][0]), _fmt(info[n][1]), _fmt(info[n][2]), _iso(info[n][3]) + " – " + _iso(info[n][4])]
                         if n in info else ['<span class="na">trace not loaded</span>'] * 4) for n in names]
    out = _table(rows, ["ICAO", "registration", "type", "description", "trace span (UTC)"])
    if not traces:
        out += '<p class="na">The flight data named in the record is not on this machine, so only ICAO addresses are shown.</p>'
    return out


def _fit_obj(fit: dict, score):
    from dopplertrack.components.types import EventFit
    try:
        f = EventFit(fit["t_heard_cpa_audio_s"], fit["t_emission_cpa_audio_s"], fit["f0_hz"], fit["speed_m_s"],
                     fit["slant_range_m"], fit["window_s"][0], fit["window_s"][1], float(score),
                     fit["f_pre_hz"], fit["f_post_hz"])
    except (KeyError, TypeError, IndexError, ValueError):
        return None
    return f if all(np.isfinite([f.t_cpa, f.f0, f.v, f.d, f.f_pre, f.f_post])) else None


def _events(ctx: _Context) -> str:
    import matplotlib.pyplot as plt
    rec = ctx.record
    events = rec.get("events") or []
    if not events:
        return '<p class="na">No events: detection found none usable, or the run stopped before it.</p>'
    sp, traces, top = ctx.spectrogram(), ctx.traces(), _top(rec)
    ref = rec.get("refined")
    point = None if _relative(rec) else \
        ((ref["lat"], ref["lon"], "refined point") if isinstance(ref, dict) and "lat" in ref else
         ((top["lat"], top["lon"], "top candidate") if top else None))
    params = (rec.get("provenance") or {}).get("parameters") or {}
    c = (params.get("speed_of_sound") or {}).get("c_m_s") if isinstance(params.get("speed_of_sound"), dict) else None
    out = []
    obs, elev_note = None, ""
    if point is not None and traces:
        elev, elev_note = _elevation(point[0], point[1])
        obs = np.array([0.0, 0.0, elev])
    for e in events:
        fit = e.get("fit") or {}
        a = e.get("assignment")
        flight = a.get("flight") if isinstance(a, dict) else None
        out.append(f"<h3>{_esc(e.get('id'))} ({_esc(e.get('source'))}, {_esc(e.get('harmonics'))} harmonic(s))"
                   f"{' → ' + _esc(flight) if flight else ''}</h3>")
        out.append(_kv({k: v for k, v in fit.items()}))
        diag = e.get("diagnostics") or {}
        out.append(_kv({k: v for k, v in diag.items()}))
        f = _fit_obj(fit, diag.get("score", 0.0) if not _unavailable(diag.get("score")) else 0.0)
        if f is None:
            out.append('<p class="na">No finite fit to draw.</p>')
            continue
        if sp is None:
            out.append('<p class="na">The spectrogram named in the record is not on this machine: no overlay.</p>')
            continue
        if not (float(sp.t[0]) <= f.t_start and f.t_end <= float(sp.t[-1])):
            out.append(f'<p class="na">The fit\'s window {f.t_start:.0f}–{f.t_end:.0f} s is outside the spectrogram '
                       f'({float(sp.t[0]):.0f}–{float(sp.t[-1]):.0f} s): no overlay.</p>')
            continue
        try:
            out.append(_overlay(sp, f, e, flight, traces, top, point, obs, elev_note, c))
        except Exception as exc:      # one event's figure never hides the others
            plt.close("all")
            out.append(f'<p class="bad">This event\'s figure could not be drawn: {_esc(type(exc).__name__)}: '
                       f'{_esc(exc)}</p>')
    return "".join(out)


def _overlay(sp, f, e, flight, traces, top, point, obs, elev_note, c) -> str:
    """The event's two panels: the measured spectrogram with the ideal fit, and the matched flight's modelled curve."""
    import matplotlib.pyplot as plt

    from dopplertrack.reporting.plots import plot_event_fit, plot_modelled
    h = int(e.get("harmonics") or 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    plot_event_fit(sp, f, harmonics=h, ax=axes[0])
    drawn, caption = False, ""
    if flight and obs is not None and top is not None:
        from dopplertrack.components.search.segments import build_segments
        amu = top["clock"]["audio_minus_utc_s"]
        t_utc = f.t_cpa - amu
        segs = [s for s in build_segments([t for t in traces if t.icao == flight], point[0], point[1])
                if s.t[0] - 120 <= t_utc <= s.t[-1] + 120]
        if segs:
            caption = f"{flight} modelled at the {point[2]} ({elev_note})"
            plot_modelled(sp, f, segs[0], obs, amu, harmonics=h, ax=axes[1], c=c, label=caption)
            drawn = True
    for ax in axes:
        ax.title.set_fontsize(8)
    if not drawn:
        caption = "no modelled curve: " + ("a private case's record holds no absolute position" if point is None
                                           and flight else "no matched flight" if not flight else
                                           "flight data not on this machine" if traces is None else
                                           "no trace of the flight at that time")
        axes[1].axis("off")
        axes[1].text(0.5, 0.5, caption, ha="center", va="center", transform=axes[1].transAxes)
    return _png(fig) + f'<p class="note">Left: the measured spectrogram with the ideal fit. Right: {_esc(caption)}.</p>'


def _pair_rules(ctx: _Context) -> str:
    pr = ctx.record.get("pair_rules")
    if pr is None:
        return '<p class="na">Schema 1: no pair rules.</p>'
    if _unavailable(pr):
        return f"<p>{_fmt(pr)}</p>"
    return _table([[_esc(r["rule"]), _fmt(r["events"]), _fmt(r.get("top_flights")), _fmt(r.get("top_score")),
                    _fmt(r.get("margin_pct"), 1), _fmt(r["wall_s"], 1), "chosen" if r["chosen"] else ""] for r in pr],
                  ["rule", "events", "top flights", "top score", "margin (%)", "wall (s)", ""])


def _data_report(ctx: _Context) -> str:
    rec = ctx.record
    dl = rec.get("data_limitations") or {}
    out = []
    flight = dl.get("flight_data")
    out.append("<h3>Flight data</h3>" + (_kv(flight) if isinstance(flight, dict) else f"<p>{_fmt(flight)}</p>"))
    if isinstance(flight, dict) and flight.get("covered_utc"):
        cu = flight["covered_utc"]
        out.append(f"<p>Covered: {_iso(cu[0])} to {_iso(cu[1])}.</p>")
    alt = dl.get("altitude_sources")
    out.append("<h3>Altitude sources</h3>" + (_kv(alt) if isinstance(alt, dict) and not _unavailable(alt) else f"<p>{_fmt(alt)}</p>"))
    gaps = dl.get("candidate_gaps")
    if isinstance(gaps, list):
        rows = [[_fmt(g)] for g in gaps[:40]]
        out.append("<h3>Trace gaps near the candidates</h3>" + (_table(rows) if rows else "<p>none known</p>"))
    else:
        out.append(f"<h3>Trace gaps near the candidates</h3><p>{_fmt(gaps)}</p>")
    # clock consistency: each event's UTC time on the top clock, and what the refinement could place
    top = _top(rec)
    out.append("<h3>Clock consistency</h3>")
    if top is None:
        out.append('<p class="na">No clock: no candidate.</p>')
    else:
        rows = []
        for e in rec.get("events") or []:
            u = e.get("utc")
            a = e.get("assignment")
            rows.append([_esc(e.get("id")), _esc(a.get("flight")) if isinstance(a, dict) and not _unavailable(a) else _fmt(a),
                         _iso(u["t_heard_cpa"]) if isinstance(u, dict) and "t_heard_cpa" in u else _fmt(u)])
        out.append(_table(rows, ["event", "flight", "heard CPA (UTC, top clock)"]))
        ref = rec.get("refined")
        if isinstance(ref, dict) and "lat" in ref:
            out.append(f"<p>Top candidate's shift {_fmt(top['clock'].get('shift_s'), 2)} s; refined shift "
                       f"{_fmt(ref.get('shift_s'), 2)} s; extra flights the refinement placed: "
                       f"{_fmt(ref.get('extra_flights') or 'none')}; flyovers with no flight near, dropped (audio s): "
                       f"{_fmt(flight.get('extras_dropped', 'not recorded') if isinstance(flight, dict) else 'not recorded')}.</p>")
        out.append(f"<p>Clock drift: {_fmt(top['clock'].get('drift'))}</p>")
    out.append(f"<h3>Possible edits</h3><p>{_fmt(dl.get('possible_edits'))}</p>")
    params = (rec.get("provenance") or {}).get("parameters") or {}
    ss = params.get("speed_of_sound")
    out.append("<h3>Speed of sound</h3>" + (_kv(ss) if isinstance(ss, dict) else
                                           f"<p>{_fmt(params.get('c_m_s', ss))}</p>"))
    out.append(f"<p class=\"note\">{_esc(dl.get('ads_b', ''))}</p>")
    return "".join(out)


def _funnel(ctx: _Context) -> str:
    f = ctx.record.get("funnel")
    if not isinstance(f, dict):
        return f"<p>{_fmt(f)}</p>"
    rows = []
    for k, v in f.items():
        if isinstance(v, list):
            rows.append([_esc(k), f"{len(v)} flight pairs"])
        elif k == "triples_file" and isinstance(v, dict):
            rows.append([_esc(k), _esc(f"{v.get('path')}: " + ", ".join(f"{s} {n}" for s, n in (v.get("rows") or {}).items()))])
        else:
            rows.append([_esc(k), _fmt(v)])
    return _table(rows)


def _execution(ctx: _Context) -> str:
    ex = ctx.record.get("execution") or {}
    rows = [[_esc(s.get("name")), _fmt(s.get("wall_s"), 2), _fmt(s.get("cpu_s"), 2)] for s in ex.get("stages", [])]
    out = [_table(rows, ["stage", "wall (s)", "CPU (s)"]) if rows else "<p>no stages recorded</p>"]
    for k in ("errors", "warnings"):
        items = ex.get(k) or []
        out.append(f"<h3>{k}</h3>" + ("<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>" if items else "<p>none</p>"))
    return "".join(out)


def _provenance(ctx: _Context) -> str:
    pv = ctx.record.get("provenance") or {}
    out = [_kv({"created": pv.get("created"), **{f"code.{k}": v for k, v in (pv.get("code") or {}).items()}})]
    for key in ("inputs", "caches"):
        items = pv.get(key) or []
        rows = [[_esc(e.get("role")), _esc(e.get("path")), _fmt(e.get("bytes")), f"<code>{_esc(str(e.get('sha256', ''))[:16])}…</code>"]
                for e in items[:30]]
        out.append(f"<h3>{key}</h3>" + (_table(rows, ["role", "path", "bytes", "sha256"]) if rows else "<p>none</p>"))
        if len(items) > 30:
            out.append(f"<p>{len(items) - 30} more in the record.</p>")
    out.append("<details><summary>parameters</summary><pre>"
               + _esc(json.dumps(pv.get("parameters"), indent=1, default=str)) + "</pre></details>")
    return "".join(out)


# exports -------------------------------------------------------------------------------------------------------

def geojson(record: dict) -> dict:
    """The candidates, the refined point and the search box as a GeoJSON FeatureCollection (lon, lat order)."""
    feats = []
    for c in record.get("candidates") or []:
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                      "properties": {"kind": "candidate", "rank": c["rank"], "score": c["score"], "flights": c["flights"],
                                     "recording_start_utc": _iso(-c["clock"]["audio_minus_utc_s"])}})
    ref = record.get("refined")
    if isinstance(ref, dict) and "lat" in ref:
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [ref["lon"], ref["lat"]]},
                      "properties": {"kind": "refined", "score": ref.get("score")}})
    box = (((record.get("provenance") or {}).get("parameters") or {}).get("search") or {}).get("bbox") \
        if isinstance(((record.get("provenance") or {}).get("parameters") or {}).get("search"), dict) else None
    if box:
        ring = [[box[2], box[0]], [box[3], box[0]], [box[3], box[1]], [box[2], box[1]], [box[2], box[0]]]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                      "properties": {"kind": "search box"}})
    case = record.get("case") or {}
    return {"type": "FeatureCollection", "name": f"{case.get('id', 'result')} v{case.get('version', '?')}",
            "features": feats}


def kml(record: dict) -> str:
    ns = "http://www.opengis.net/kml/2.2"       # the KML namespace name, not a fetched URL
    root = ET.Element("kml", xmlns=ns)
    doc = ET.SubElement(root, "Document")
    ET.SubElement(doc, "name").text = geojson(record)["name"]
    for f in geojson(record)["features"]:
        pm = ET.SubElement(doc, "Placemark")
        p = f["properties"]
        ET.SubElement(pm, "name").text = (f"#{p['rank']} {' + '.join(p['flights'])}" if p["kind"] == "candidate"
                                          else p["kind"])
        ET.SubElement(pm, "description").text = json.dumps(p)
        g = f["geometry"]
        if g["type"] == "Point":
            ET.SubElement(ET.SubElement(pm, "Point"), "coordinates").text = f"{g['coordinates'][0]},{g['coordinates'][1]},0"
        else:
            ring = ET.SubElement(ET.SubElement(ET.SubElement(pm, "Polygon"), "outerBoundaryIs"), "LinearRing")
            ET.SubElement(ring, "coordinates").text = " ".join(f"{x},{y},0" for x, y in g["coordinates"][0])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# the page --------------------------------------------------------------------------------------------------------

CSS = """
body{font:14px/1.45 -apple-system,Helvetica,Arial,sans-serif;max-width:1150px;margin:16px auto;padding:0 16px;
color:#1d1d1f;background:#fff}
h1{margin:.2em 0}h2{border-bottom:1px solid #ccc;margin-top:1.6em}table{border-collapse:collapse;margin:.4em 0}
td,th{border:1px solid #ddd;padding:2px 7px;text-align:left;vertical-align:top}th{background:#f3f3f3}
code{font-size:12px}.na{color:#777}.note{color:#555}.bad{color:#b00020;font-weight:bold}
.warn{background:#fde7e9;border:1px solid #b00020;padding:6px 10px;margin:8px 0}.eval{background:#fff4d6;border-color:#a06a00}
.badge{display:inline-block;padding:2px 10px;border-radius:10px;color:#fff;font-weight:bold;background:#666}
.badge.located{background:#1a7f37}.badge.ambiguous{background:#a06a00}.badge.insufficient_evidence{background:#b00020}
body.unverified section{border-left:4px solid #b00020;padding-left:10px}
body.unverified h2:after{content:" (unverified record)";color:#b00020;font-size:13px}
img{max-width:100%}pre{white-space:pre-wrap;font-size:12px}
"""

SECTIONS = (("Answer", _answer), ("Map", _map), ("Matched flights", _flights), ("Events", _events),
            ("Pair rules", _pair_rules), ("Data report", _data_report), ("Funnel", _funnel),
            ("Execution", _execution), ("Provenance", _provenance))


def _section(title: str, fn, ctx: _Context) -> str:
    try:
        body = fn(ctx)
    except Exception as exc:          # one section's failure never hides the rest of the page
        body = f'<p class="bad">This section could not be drawn: {_esc(type(exc).__name__)}: {_esc(exc)}</p>'
    return f"<section><h2>{_esc(title)}</h2>{body}</section>"


def render_report(result_json, out_dir=None, data_root=None, case_meta: dict | None = None) -> Path:
    """Write report.html, candidates.geojson and candidates.kml for one result.json; returns the page's path.
    case_meta: the benchmark case's own fields the record doesn't carry (its set); data_root: where this
    machine keeps raw/ and derived/, for records written elsewhere."""
    path = Path(result_json)
    out = Path(out_dir) if out_dir else path.parent
    out.mkdir(parents=True, exist_ok=True)
    record = json.loads(path.read_text())
    ctx = _Context(path, record, Path(data_root) if data_root else None, case_meta)
    if _relative(record):
        links = ("<p>Exports: none. GeoJSON and KML are absolute by nature, and this private case's record holds only "
                 "offsets from its site.</p>")
    else:
        gj = json.dumps(geojson(record), indent=1)
        km = kml(record)
        (out / "candidates.geojson").write_text(gj + "\n")
        (out / "candidates.kml").write_text(km)
        links = (f'<p>Exports: <a download="candidates.geojson" href="data:application/geo+json;base64,'
                 f'{base64.b64encode(gj.encode()).decode()}">GeoJSON</a> · <a download="candidates.kml" '
                 f'href="data:application/vnd.google-earth.kml+xml;base64,{base64.b64encode(km.encode()).decode()}">'
                 f"KML</a> (also written beside this page)</p>")
    title = _esc((record.get("case") or {}).get("id", "result"))
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{title}: dopplertrack report</title><style>{CSS}</style>'
            f'</head><body class="{"unverified" if ctx.unverified else ""}"><header>{_header(ctx)}{links}</header>'
            + "".join(_section(t, fn, ctx) for t, fn in SECTIONS) + "</body></html>\n")
    target = out / "report.html"
    target.write_text(page)
    return target


def render_index(run_dir, pages: list[dict], title: str | None = None) -> Path:
    """index.html for a folder of reports: one row per case, linking its page. pages: dicts of case, set, status,
    verdict, note and page (a path relative to run_dir)."""
    title = title or Path(run_dir).name
    rows = [[f'<a href="{_esc(p["page"])}">{_esc(p["case"])}</a>' if p.get("page") else _esc(p["case"]),
             _esc(p.get("set") or ""), _esc(p.get("status") or ""), _esc(p.get("verdict") or ""), _esc(p.get("note") or "")]
            for p in pages]
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_esc(title)}</title>'
            f'<style>{CSS}</style></head><body><h1>{_esc(title)}</h1>'
            + _table(rows, ["case", "set", "status", "verdict", "note"]) + "</body></html>\n")
    target = Path(run_dir) / "index.html"
    target.write_text(page)
    return target
