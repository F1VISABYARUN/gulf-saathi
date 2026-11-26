"""Export the fixed text of the web pages (CSS, step lists, labels) from the Python modules to
ts/src/tables/pages.json, so the TypeScript pages use exactly the same words and styles.

    python ts/scripts/export_page_text.py
"""
import json
from pathlib import Path

from gulf_saathi import dashboard, site

out = {}
for name, mod in (("site", site), ("dashboard", dashboard)):
    consts = {}
    for k, v in vars(mod).items():
        if k.isupper() and not k.startswith("_"):
            try:
                json.dumps(v)
            except TypeError:
                continue
            consts[k] = v
    out[name] = consts
path = Path(__file__).resolve().parents[1] / "src" / "tables" / "pages.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(path, {k: sorted(v) for k, v in out.items()})
