# IMT Dashboard

Permanent CIMT operational dashboard. GitHub Actions parses the NICC **IMSR** and **CIMT Assignments ledger** daily (~0800 MDT), commits `data/data.json` to `main`, and force-mirrors `main -> gh-pages`. GitHub Pages serves the `gh-pages` branch.

**Live:** https://dr-chris-long.github.io/imt-dashboard/

## Activate
- **Automatic:** daily cron (`.github/workflows/update.yml`, 1400 UTC).
- **On demand:** Actions tab -> `update-imt-data` -> **Run workflow**.

## Deployment mechanism (and why)
First attempt used `actions/configure-pages` with `enablement: true`; run #1 failed on the enablement API with the workflow token. Pivoted to the branch mechanism: creating a `gh-pages` branch via a user push auto-enables Pages from that branch — no settings click, no Pages API. `deploy-pages.yml` is retained as a disabled tombstone documenting the failure.

## Design decisions
- **Halt-on-anomaly:** parser exits non-zero on hollow/failed parse or stale edition -> no commit, no mirror -> dashboard keeps last-good data and shows an age banner. Never silently serves garbage.
- **Stable-URL lag defense:** `sitreprt.pdf` can lag a day (observed 2026-07-06). Parser reads the edition date inside the PDF and falls back to the dated archive path.
- **Team-less fire watch:** large, low-containment fires with no CIMT line are first-class output (pre-position/order candidates) — the Chelan Hills lesson.
- **Derived vs real:** glide paths (`min(est ctn, mob+14d)`) and relief predictions (NISRM Ch.20 heuristics) are labeled derivations; everything else traces to the source PDFs.

## Known limits
NW in-area rotation order and pre-position detail are FireNet-only. Type 3 status has no public feed. IMSR 0730 MDT figures lag same-day media.
