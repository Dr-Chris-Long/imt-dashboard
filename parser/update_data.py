#!/usr/bin/env python3
"""IMT dashboard data pipeline. Fetch NICC IMSR + CIMT Assignments ledger,
parse, validate, emit data/data.json. HALT (exit 1) on anomaly rather than
emit garbage -- the workflow then skips the commit and the dashboard keeps
last-good data with a client-side age banner.
Known trap engineered around: the stable sitreprt.pdf URL can lag a day
(observed 2026-07-06). We read the edition date INSIDE the PDF and fall back
to the dated archive path for today/yesterday if stale.
"""
import io, json, re, sys, datetime as dt
import requests, pdfplumber

UA = {"User-Agent": "Mozilla/5.0 (imt-dashboard bot)"}
STABLE = "https://www.nifc.gov/nicc-files/sitreprt.pdf"
ARCHIVE = ("https://www.nifc.gov/sites/default/files/NICC/1-Incident%20Information/"
           "IMSR/{y}/{mon}/IMSR_CY{yy}_{mdy}.pdf")
LEDGER = "https://www.nifc.gov/nicc-files/logistics/teams/cimt_assigns.pdf"
MONTHS = ["January","February","March","April","May","June","July","August",
          "September","October","November","December"]
GACCS = ["AICC","NWCC","ONCC","OSCC","NRCC","GBCC","SWCC","RMCC","EACC","SACC"]

def fetch_pdf_text(url):
    r = requests.get(url, headers=UA, timeout=60)
    if r.status_code != 200 or "pdf" not in r.headers.get("content-type",""):
        return None
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)

def imsr_date(text):
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})", text)
    if not m: return None
    return dt.date(int(m.group(3)), MONTHS.index(m.group(1)) + 1, int(m.group(2)))

def get_current_imsr(today):
    """Stable URL first; if its internal date is stale, try dated archive for
    today then yesterday. Returns (text, edition_date, source_url)."""
    candidates = [(STABLE, None)]
    for d in (today, today - dt.timedelta(days=1)):
        candidates.append((ARCHIVE.format(y=d.year, mon=MONTHS[d.month-1],
                           yy=str(d.year)[2:], mdy=d.strftime("%m%d%Y")), d))
    best = None
    for url, _ in candidates:
        t = fetch_pdf_text(url)
        if not t: continue
        ed = imsr_date(t)
        if ed and (best is None or ed > best[1]):
            best = (t, ed, url)
        if ed == today:
            break
    return best

def parse_imsr(text):
    out = {}
    m = re.search(r"National Preparedness Level (\d)", text)
    out["national_pl"] = int(m.group(1)) if m else None
    # GACC summary rows: GACC PL Incidents Acres Crews Engines Helis Personnel Chg
    pls = []
    for ln in text.split("\n"):
        mm = re.match(r"\s*(" + "|".join(GACCS) + r")\s+(\d)\s+(\d+)\s+([\d,]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d,]+)", ln)
        if mm:
            pls.append({"gacc": mm.group(1), "pl": int(mm.group(2)),
                        "incidents": int(mm.group(3)),
                        "acres": int(mm.group(4).replace(",","")),
                        "personnel": int(mm.group(8).replace(",",""))})
    out["gacc_pl"] = pls
    m = re.search(r"CIMTs committed:\s*(\d+)", text)
    out["cimts_committed"] = int(m.group(1)) if m else None
    # team narrative lines
    teams = []
    for ln in text.split("\n"):
        for mm in re.finditer(r"CIMT \(([A-Z]{2}) Team (\d+)\)(\s*mobilizing)?", ln):
            teams.append({"team": f"{mm.group(1)} {mm.group(2)}",
                          "incident": ln.split(",")[0].lstrip("* ").strip(),
                          "status": "mobilizing" if mm.group(3) else "committed"})
    out["teams"] = teams
    # large-incident table rows
    fires = []
    for ln in text.split("\n"):
        mm = re.match(r"\s*\*?\s*([A-Za-z0-9 .'\-/]+?)\s+([A-Z]{2}-[A-Z0-9]{3,4})\s+([\d,]+)\s+([\d,\-]+|---)\s+(\d+)\s+\w+\s+(\d{1,2}/\d{1,2}|UNK)\b.*?\b(ST|BLM|USFS|FS|BIA|FWS|NPS|PRI|CNTY|DOD|ST/OT)\s*$", ln)
        if mm:
            name = mm.group(1).strip()
            fires.append({"name": name, "unit": mm.group(2),
                          "acres": int(mm.group(3).replace(",","")),
                          "ctn": int(mm.group(5)), "est": mm.group(6),
                          "own": mm.group(7),
                          "team": next((t["team"] for t in teams if t["incident"].lower().startswith(name.lower()[:8])), None)})
    out["fires"] = fires
    # predictive discussion
    m = re.search(r"Predictive Services Discussion:\s*(.*?)\s*National Predictive", text, re.S)
    out["discussion"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return out

def parse_ledger(text):
    out = {"teams": [], "log": []}
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+2026 CIMT Assignments", text)
    out["as_of"] = m.group(1) if m else None
    m = re.search(r"Totals?\s+(\d+)\s+(\d+)", text)
    if m: out["total_assigns"], out["total_days"] = int(m.group(1)), int(m.group(2))
    for ln in text.split("\n"):
        mm = re.match(r"\s*(AK|CA|EA|GB|NR|NW|RM|SA|SW)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", re.sub(r"\s+", " ", ln).strip())
        if mm:
            out["teams"].append({"team": f"{mm.group(1)} {mm.group(2)}",
                                 "assigns": int(mm.group(3)), "days": int(mm.group(4))})
        lg = re.match(r"\s*(\d{1,2}/\d{1,2})\s+([A-Z]{2})\s?(\d+)\s+([A-Z]{2})\s+(.+)", ln)
        if lg:
            rest = lg.group(5).strip()
            rel = re.search(r"(\d{1,2}/\d{1,2})\s+(\*|\d+)\s+(\d+)?\s*$", rest)
            out["log"].append({"mob": lg.group(1), "team": f"{lg.group(2)} {lg.group(3)}",
                               "ga": lg.group(4),
                               "incident": re.sub(r"\s*\d{1,2}/\d{1,2}\s+(\*|\d+)\s*\d*\s*$", "", rest).strip(),
                               "released": rel.group(1) if rel else None,
                               "days": int(rel.group(3)) if rel and rel.group(3) else None})
    return out

def main():
    today = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-6))).date()  # MDT
    imsr = get_current_imsr(today)
    if not imsr:
        sys.exit("HALT: no IMSR retrievable")
    text, edition, src = imsr
    if (today - edition).days > 2:
        sys.exit(f"HALT: freshest IMSR edition {edition} is >2 days old")
    data = parse_imsr(text)
    # anomaly gates -- refuse to publish a hollow parse
    if not data["gacc_pl"] or len(data["gacc_pl"]) < 8:
        sys.exit("HALT: GACC PL table parse failure")
    if data["national_pl"] is None:
        sys.exit("HALT: national PL parse failure")
    if data["cimts_committed"] and not data["teams"]:
        sys.exit("HALT: committed>0 but zero team lines parsed")
    ltext = fetch_pdf_text(LEDGER)
    ledger = parse_ledger(ltext) if ltext else {"error": "ledger unavailable"}
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "imsr_edition": edition.isoformat(), "imsr_source": src,
        "stable_url_lagged": src != STABLE,
        "imsr": data, "ledger": ledger,
        "notes": {
            "teamless_watch": "fires[] entries with team==null and ctn<50 are order/transition candidates (Chelan lesson)",
            "preposition": "GA prepositions appear in ledger log with no incident release; prepo >=4 days counts as an assignment (NISRM Ch.20)"
        }
    }
    with open("data/data.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"OK edition={edition} teams={len(data['teams'])} fires={len(data['fires'])} ledger_as_of={ledger.get('as_of')}")

if __name__ == "__main__":
    main()
