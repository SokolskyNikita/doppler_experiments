"""Fetches raw files from their public sources on a job box, for `runs fetch-sources`.

    python3 tools/aws/box/fetch_sources.py <plan s3 url> <bucket>

The plan lists each file's path under the data root, its URL, its size and its SHA-256 (from
bench/manifest.json). Each file is downloaded to scratch, checked against both, and only then put at
s3://<bucket>/data/<path>; a file already there at its size is skipped, so a fetch never replaces a raw file
(and the bucket keeps any replaced version for 30 days). $RUN/fetched.json records every file's outcome.
Standard library and s5cmd only."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WORKERS = 8
ATTEMPTS = 3
CHUNK = 1 << 22


def download(url: str, dest: Path) -> tuple[int, str]:
    """Fetches url to dest with curl, resuming after a dropped connection (Zenodo cuts long downloads short),
    then returns the file's size and SHA-256."""
    subprocess.run(["curl", "-sSfL", "--retry", "20", "--retry-all-errors", "--retry-delay", "5", "-C", "-",
                    "-A", "dopplertrack-fetch/1", "-o", str(dest), url], check=True)
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return dest.stat().st_size, h.hexdigest()


def present(url: str, size: int) -> bool:
    r = subprocess.run(["s5cmd", "--log", "error", "ls", url], capture_output=True, text=True)
    return r.returncode == 0 and any(line.split()[2:3] == [str(size)] for line in r.stdout.splitlines())


def fetch(item: dict, scratch: Path, target: str, log) -> dict:
    dest = scratch / item["path"].replace("/", "__")
    out = {"path": item["path"], "url": item["url"], "bytes": item["bytes"], "sha256": item["sha256"]}
    if present(f"{target}/{item['path']}", item["bytes"]):
        log(f"already there: {item['path']}")
        return {**out, "state": "present", "attempts": 0}
    for attempt in range(1, ATTEMPTS + 1):
        t0 = time.time()
        try:
            n, digest = download(item["url"], dest)
            if (n, digest) != (item["bytes"], item["sha256"]):
                raise ValueError(f"got {n} bytes, sha256 {digest}")
            subprocess.run(["s5cmd", "--log", "error", "cp", str(dest), f"{target}/{item['path']}"], check=True)
            wall = time.time() - t0
            log(f"ok {item['path']} {n / 1e6:.0f} MB in {wall:.0f} s ({n / 1e6 / max(wall, 1e-3):.0f} MB/s)")
            return {**out, "state": "ok", "attempts": attempt, "wall_s": round(wall, 1)}
        except Exception as e:       # noqa: BLE001 - every failure is retried, then recorded
            log(f"attempt {attempt} failed for {item['path']}: {e}")
            out["error"] = str(e)[:300]
            time.sleep(10 * attempt)
        finally:
            dest.unlink(missing_ok=True)
    return {**out, "state": "failed", "attempts": ATTEMPTS}


def main(plan_url: str, bucket: str) -> int:
    run = Path(os.environ["RUN"])
    scratch = Path(os.environ.get("SCRATCH", "/scratch")) / "fetch"
    scratch.mkdir(parents=True, exist_ok=True)
    plan = json.loads(subprocess.run(["s5cmd", "--log", "error", "cat", plan_url], capture_output=True, text=True,
                                     check=True).stdout)
    total = sum(i["bytes"] for i in plan["files"])
    print(f"{len(plan['files'])} files, {total / 1e9:.1f} GB, {WORKERS} at a time", flush=True)

    def log(msg):
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(lambda i: fetch(i, scratch, f"s3://{bucket}/data", log), plan["files"]))
    wall = time.time() - t0
    ok = [r for r in results if r["state"] in ("ok", "present")]
    summary = {"plan": plan_url, "files": len(results), "ok": len(ok), "failed": len(results) - len(ok),
               "bytes_ok": sum(r["bytes"] for r in ok), "wall_s": round(wall, 1), "results": results}
    (run / "fetched.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"{len(ok)} of {len(results)} files, {summary['bytes_ok'] / 1e9:.1f} GB in {wall:.0f} s", flush=True)
    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
