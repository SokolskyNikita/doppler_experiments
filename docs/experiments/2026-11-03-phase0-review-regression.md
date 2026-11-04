# Phase 0 review regression

## Question and changes

Do the review corrections preserve Oyster Bay's existing fit/detection checks while preventing
reception gaps from fragmenting otherwise usable flight geometry or supplying false curve evidence?

The readsb stale flag describes the reception gap before a new reliable fix. This is visible in
[readsb's position-acceptance code](https://github.com/wiedehopf/readsb/blob/dev/track.c): the flag is
computed against the previous reliable-position time before that time is updated and the new fix
is added. The fix remains usable.

The revised pipeline keeps its 90 s geometry segment bound for CPA proposals. Resampling carries a
separate evidence mask for gaps over 30 s, including through grid clipping, and curve derivatives and
scoring preserve that mask. Geometry can propose a CPA inside a 30–90 s hole, but the hole contributes
no acoustic evidence. Coverage diagnostics now share the segmentation validity/boundary rules and
report missing positions/heights and new-leg boundaries as well as time gaps. The unused inverse
retarded-time solver and the temporary status paragraph in PLAN.md were removed.

## Setup

Development recording: the existing Oyster Bay `derived/oyster_bay/rec.npz` and `traces_ny.npz`.
No new data was downloaded and no fit windows, thresholds or score normalisation were tuned.
These checks do not constitute independent evaluation or a blind location search.

Scripts: `tests/test_oyster_bay.py`, the offline regression tests and `tests/install_smoke.py`.

```bash
.venv/bin/python -m pytest -q
DOPPLERTRACK_OYSTER_BAY="$HOME/data/dopplertrack/derived/oyster_bay" \
    .venv/bin/python -m pytest -q tests/test_oyster_bay.py
```

The run started from `de6d542` with the review corrections uncommitted. Its `source.patch` captures
the changes and `run.json` records the command and environment.

## Results

- Offline suite: **66 passed, 3 skipped**, 73.01 s; it ran concurrently with the Oyster Bay check.
- Oyster Bay: **2 passed, 1 expected failure**, 102.59 s. The saved-fit/known-point and automatic
  detection checks pass; the strict expected failure for detector-fit search gates remains.
- Installed-wheel decode/detect smoke test outside the checkout: passed.
- Synthetic checks retain a stale-flagged fix after a 25 s reception gap and the CPA proposal within
  that gap. A separate 45 s hole straddling CPA keeps one geometry segment and the CPA within 1 s of
  truth, while its modelled frequency samples remain invalid and contribute no score. This holds
  with and without spatial clipping.
- Missing-height and new-leg boundaries now appear in candidate-local coverage diagnostics.

Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-03-phase0-review-regression/` (`run.json`, `source.patch`,
`pytest.log`). The raw-audio fit bias remains Phase 2 work.
