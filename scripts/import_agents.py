"""Build data/agents.csv from saved eMigrate list pages.

eMigrate has no public API that I know of. Save the licensed-agent list page and
the illegal-agent list page from the browser (File > Save Page As, .html),
then run:

  python scripts/import_agents.py --licensed licensed.html --flagged flagged.html -o data/agents.csv

The importer reads every <table> on each page and guesses which columns hold the
name and the registration number from the header text. Check the output by
hand: the page layout may change, and a wrong "flagged" entry harms a real
business.
"""
from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser

NAME_HINTS = ("name of ra", "name of the ra", "agent name", "agency name", "name of agent", "name")
LICENCE_HINTS = ("registration", "licence", "license", "rc no", "reg no", "reg. no")
CITY_HINTS = ("city", "district", "place", "address")
STATE_HINTS = ("state",)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _col(header: list[str], hints) -> int | None:
    low = [h.lower() for h in header]
    for hint in hints:
        for i, h in enumerate(low):
            if hint in h:
                return i
    return None


def extract(path: str, status: str) -> list[dict]:
    p = TableParser()
    with open(path, encoding="utf-8", errors="replace") as f:
        p.feed(f.read())
    out = []
    for table in p.tables:
        if len(table) < 2:
            continue
        header = table[0]
        name_i = _col(header, NAME_HINTS)
        if name_i is None:
            continue
        lic_i, city_i, state_i = _col(header, LICENCE_HINTS), _col(header, CITY_HINTS), _col(header, STATE_HINTS)
        for row in table[1:]:
            get = lambda i: row[i].strip() if i is not None and i < len(row) else ""
            if get(name_i):
                out.append({
                    "name": get(name_i),
                    "licence_no": get(lic_i) if status == "licensed" else "",
                    "status": status,
                    "city": get(city_i),
                    "state": get(state_i),
                    "aliases": "",
                })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--licensed", nargs="*", default=[])
    ap.add_argument("--flagged", nargs="*", default=[])
    ap.add_argument("-o", "--out", default="data/agents.csv")
    args = ap.parse_args()

    rows = [r for f in args.licensed for r in extract(f, "licensed")]
    rows += [r for f in args.flagged for r in extract(f, "flagged")]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "licence_no", "status", "city", "state", "aliases"])
        w.writeheader()
        w.writerows(rows)
    n_l = sum(r["status"] == "licensed" for r in rows)
    print(f"wrote {len(rows)} agents ({n_l} licensed, {len(rows) - n_l} flagged) to {args.out}")


if __name__ == "__main__":
    main()
