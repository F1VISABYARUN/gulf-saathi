"""Convert the 'Licensed Agents India' PDF (eMigrate active RA list) to CSV.

  python scripts/agents_pdf_to_csv.py Licensed_Agents_India.pdf -o data/licensed_agents.csv

Needs `pdftotext` (poppler-utils). Uses -layout mode: plain mode scrambles the
word order of justified lines. Each record in the PDF looks like:
  LICENSED AGENT: <agency> | RA ID <raid> | Licence <rc> | <district>, <state> | Owner: <owner> | Phone: <phone>
"""
import argparse
import csv
import re
import subprocess
import sys

RECORD = re.compile(
    r"^\s*(?P<agency>.+?)\s*\|\s*RA ID\s*(?P<raid>\S+)\s*\|\s*Licence\s*(?P<rc>.*?)\s*\|"
    r"\s*(?P<district>[^|]*?),\s*(?P<state>[^|,]*?)\s*\|\s*Owner:\s*(?P<sign>.*?)\s*\|\s*Phone:\s*(?P<phone>\S*)"
)
FIELDS = ["raid", "agency", "sign", "state", "district", "rc", "phone", "status"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="data/licensed_agents.csv")
    args = ap.parse_args()

    text = subprocess.run(["pdftotext", "-layout", args.pdf, "-"], capture_output=True, text=True, check=True).stdout
    expected = len(re.findall(r"LICENSED\s+AGENT:", text))
    records = re.split(r"LICENSED AGENT:", re.sub(r"\s+", " ", text))[1:]

    rows, bad = [], []
    for rec in records:
        m = RECORD.match(rec)
        if not m:
            bad.append(rec[:120])
            continue
        rows.append({**{k: v.strip() for k, v in m.groupdict().items()}, "status": "active"})

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} of {expected} agents written to {args.out}")
    for b in bad:
        print("UNPARSED:", b, file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
