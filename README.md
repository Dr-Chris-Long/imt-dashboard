# IMT Dashboard

Permanent CIMT operational dashboard. GitHub Actions parses the NICC **IMSR** and **CIMT Assignments ledger** daily (~0800 MDT) and commits `data/data.json`; GitHub Pages serves `index.html`, which renders it.

## Activate
- **Automatic:** daily cron (`.github/workflows/update.yml`, 1400 UTC).
- **On demand:** Actions tab -> `update-imt-data` -> **Run workflow**. That is the activate button.

## One-time setup
Settings -> Pages -> Source: **Deploy from a branch** -> `main` / root. URL: `https://dr-chris-long.github.io/imt-dashboard/`.

## Design decisions
- **Halt-on-anomaly:** parser exits non-zero on hollow/failed parse or stale edition -> no commit -> dashboard keeps last-good data and shows an age banner. Never silently serves garbage.
- **Stable-URL lag defense:** `sitreprt.pdf` can lag a day (observed 2026-07-06). Parser reads the edition date inside the PDF and falls back to the dated archive path.
- **Team-less fire watch:** large, low-containment fires with no CIMT line are first-class output (pre-position/order candidates) — the Chelan Hills lesson.
- **Derived vs real:** glide paths (`min(est ctn, mob+14d)`) and relief predictions (NISRM Ch.20 heuristics: 2-assignment cap, in-area preference, complexity release) are labeled derivations. Everything else traces to the source PDFs.

## Known limits
NW in-area rotation order and pre-position detail are FireNet-only. Type 3 status has no public feed. IMSR 0730 MDT figures lag same-day media.
