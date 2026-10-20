"""Check a spoken agent name against the MEA licensed recruiting-agent list.

The caller may give an agency name, an owner name, a district or a licence / RA
number, often misheard by speech recognition and written in Telugu script.

Safety rules (from the project rules):
- Only an RC/RA number match, or owner + agency, or a strong name + the right
  district, counts as "confirmed_in_list".
- Anything weaker comes back as up to 3 candidates for the caller to confirm.
- Nothing close enough is "not_found". The closest guess is never returned as
  confirmed.

  python -m gulf_saathi.matcher --owner "Seedi Kavitha"
  python -m gulf_saathi.matcher --agency "Gagan Manpower" --district Jagtial
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from indic_transliteration import sanscript
from rapidfuzz import fuzz

from . import config

LICENSED_CSV = Path(config.ROOT / "data" / "licensed_agents.csv")

CANDIDATE_MIN = 78  # below this a record isn't worth reading back to the caller
STRONG = 90  # one name this strong + the right district confirms
OWNER_OK = 85  # owner + agency both at least this good confirms
AGENCY_OK = 80

# Words in nearly every agency name. They can't identify an agency on their own.
GENERIC = [
    "overseas", "manpower", "consultants", "consultancy", "consultant", "travels", "travel",
    "tours", "tour", "international", "recruiting", "recruitment", "recruiters", "services",
    "service", "enterprises", "enterprise", "agency", "agencies", "placement", "placements",
    "solutions", "global", "resources", "human", "hr", "and", "the", "of", "india",
    "gulf", "dubai", "saudi", "arabia", "jobs", "job", "visa", "visas", "employment", "career",
    "careers", "world", "worldwide", "group", "associates", "management", "staffing",
]
LEGAL_NOISE = {"m", "s", "ms", "pvt", "private", "ltd", "limited", "llp", "p", "co", "company", "mr", "mrs", "smt", "sri", "shri", "dr"}

# Letters as spoken, after transliteration ("సి ఎం ఆర్" -> "si em ar" -> "cmr").
LETTER_NAMES = {
    "e": "a", "ey": "a", "bi": "b", "si": "c", "di": "d", "i": "e", "ef": "f", "ji": "g",
    "hec": "h", "ec": "h", "ai": "i", "je": "j", "ke": "k", "el": "l", "em": "m", "en": "n",
    "o": "o", "pi": "p", "kyu": "q", "ar": "r", "es": "s", "ti": "t", "yu": "u", "vi": "v",
    "eks": "x", "vai": "y", "jed": "z",
}

DISTRICTS = {
    "jagtial": ["jagtial", "jagityal", "jagityala", "jagitial", "jagithyal"],
    "nizamabad": ["nizamabad", "nijamabad", "indur", "induru"],
    "karimnagar": ["karimnagar", "karimnagaram"],
    "rajanna sircilla": ["sircilla", "sirisilla", "siricilla", "rajanna sircilla"],
    "nirmal": ["nirmal"],
    "kamareddy": ["kamareddy", "kamareddi", "kamaredi"],
    "hyderabad": ["hyderabad", "haidarabad", "hyd"],
    "ranga reddy": ["ranga reddy", "rangareddy", "rangareddi"],
    "medchal malkajgiri": ["medchal", "malkajgiri"],
}


def romanize(text: str) -> str:
    if re.search(r"[\u0C00-\u0C7F]", text):
        text = sanscript.transliterate(text, sanscript.TELUGU, sanscript.ITRANS)
        text = text.replace("M", "m")  # anusvara
    # Strip accents that ITRANS puts on e/o, and zero-width joiners.
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).replace("\u200c", "").replace("\u200d", "")


def phonetic(word: str) -> str:
    """Flatten spellings that Telugu speech-to-text and English records disagree on."""
    w = re.sub(r"c(?=[aoukrlt])", "k", word)  # hard c: "consultancy", "cargo"
    for a, b in [("tion", "san"), ("aiah", "aia"), ("ayya", "aia"), ("aya", "aia"), ("sh", "s"), ("ch", "s"), ("c", "s"),
                 ("th", "t"), ("dh", "t"), ("d", "t"), ("kh", "k"), ("gh", "g"), ("bh", "b"), ("ph", "f"),
                 ("w", "v"), ("z", "j"), ("q", "k"), ("y", "i"), ("ee", "i"), ("oo", "u")]:
        w = w.replace(a, b)
    w = re.sub(r"m(?=[kgsjtdpb])", "n", w)
    w = re.sub(r"(.)\1+", r"\1", w)
    return re.sub(r"(?<=[aeiou])h$", "", w)


def skeleton(word: str) -> str:
    """Consonants only. Telugu speech keeps an English word's consonants but changes
    its vowels: "manpower" -> "myanpavar", both "mnpvr"."""
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiou]", "", phonetic(word)))


_GENERIC_KEYS = [(g, phonetic(g), skeleton(g)) for g in GENERIC]


def _canonical_generic(token: str) -> str | None:
    """"myanpavar" (Telugu-spoken "manpower") -> "manpower"."""
    if token in GENERIC:
        return token
    if len(token) < 4:
        return None
    p, s = phonetic(token), skeleton(token)
    for g, gp, gs in _GENERIC_KEYS:
        if p[0] == gp[0] and (fuzz.ratio(p, gp) >= 80 or (len(gs) >= 3 and s == gs)):
            return g
    return None


def tokens(text: str) -> list[str]:
    text = romanize(text).lower().replace("man power", "manpower").replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    # Join runs of 2+ spoken letters into one acronym; a lone one stays a word.
    out, run = [], []
    for w in words + [""]:
        if w in LETTER_NAMES or (len(w) == 1 and w.isalpha()):
            run.append(w)
            continue
        if len(run) >= 2:
            out.append("".join(LETTER_NAMES.get(x, x) for x in run))
        else:
            out.extend(run)
        run = []
        if w:
            out.append(w)
    return [w for w in out if w not in LEGAL_NOISE]


def split_agency(text: str) -> tuple[str, str]:
    """(distinctive part, generic part), both as space-joined phonetic keys."""
    distinct, generic = [], []
    for t in tokens(text):
        g = _canonical_generic(t)
        (generic if g else distinct).append(g or phonetic(t))
    return " ".join(distinct), " ".join(generic)


def _person(text: str) -> tuple[str, str, list[str], list[str]]:
    """(plain key, phonetic key, plain tokens, phonetic tokens) for a person's name."""
    plain = tokens(text)
    flat = [phonetic(x) for x in plain]
    return " ".join(plain), " ".join(flat), plain, flat


def owner_score(said: tuple, owners: list[tuple]) -> float:
    """Best match against any of the owners. Plain spelling first; phonetic flattening
    is a slightly weaker fallback. A partial name ("Mallesham") scores lower than
    the full name ("Chella Mallesham")."""
    s_plain, s_flat, s_pt, s_ft = said
    if not s_pt:
        return 0
    best = 0.0
    for o_plain, o_flat, o_pt, o_ft in owners:
        if not o_pt:
            continue
        full = max(fuzz.token_sort_ratio(s_plain, o_plain), fuzz.token_sort_ratio(s_flat, o_flat) - 3)
        per = [max(max(fuzz.ratio(sp, op), fuzz.ratio(sf, of) - 3) for op, of in zip(o_pt, o_ft))
               for sp, sf in zip(s_pt, s_ft)]
        coverage = min(1.0, len(s_pt) / len(o_pt))
        partial = sum(per) / len(per) * (0.75 + 0.25 * coverage) if min(per) >= 75 else 0
        best = max(best, full, partial)
    return best


def agency_score(said: tuple[str, str], agency: tuple[str, str]) -> float:
    s_d, s_g = said
    a_d, a_g = agency
    if not a_d:
        # A name made only of common words ("GULF OVERSEAS CONSULTANCY") must be said almost exactly.
        return fuzz.token_sort_ratio(s_g, a_g) if not s_d and fuzz.token_sort_ratio(s_g, a_g) >= 95 else 0
    if not s_d:
        return 0  # "overseas" alone identifies nobody
    distinct = fuzz.token_sort_ratio(s_d, a_d)
    if distinct < 80:
        return distinct * 0.8
    # Generic words count a little: "Vision Tours and Travels" vs "Vision Overseas".
    if s_g and a_g:
        generic = fuzz.token_set_ratio(s_g, a_g)
    elif s_g or a_g:
        generic = 70
    else:
        generic = 100
    return 0.85 * distinct + 0.15 * generic


def district_key(said: str) -> str:
    """Canonical district for what the caller said ("జగిత్యాల" -> "jagtial")."""
    found, _ = find_district(said)
    return phonetic(found or " ".join(tokens(said)))


def find_district(text: str) -> tuple[str | None, str]:
    """Pull a district name out of free text: (district, the text without it)."""
    words = tokens(text)
    for canon, names in DISTRICTS.items():
        for n in names:
            pn = phonetic(n)
            hits = [w for w in words if fuzz.ratio(phonetic(w), pn) >= 85]
            if hits:
                return canon, " ".join(w for w in words if w not in hits)
    return None, text


def _norm_id(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", romanize(s).upper())


@dataclass
class Agent:
    raid: str
    agency: str
    sign: str
    state: str
    district: str
    rc: str
    phone: str

    def public(self) -> dict:
        return {"agency": self.agency, "owner": self.sign, "district": self.district,
                "state": self.state, "licence_no": self.rc, "ra_id": self.raid}


class LicensedList:
    def __init__(self, agents: list[Agent]):
        self.agents = agents
        # Name keys are computed once here, not on every lookup.
        self._keys = [
            (split_agency(a.agency), [_person(o) for o in a.sign.split(",")], phonetic(" ".join(tokens(a.district))))
            for a in agents
        ]
        self._by_id = {}
        for a in agents:
            self._by_id[_norm_id(a.raid)] = a
            self._by_id[_norm_id(a.raid).removeprefix("RA")] = a
            self._by_id[_norm_id(a.rc)] = a

    @classmethod
    def load(cls, path: Path | str = LICENSED_CSV) -> "LicensedList":
        with open(path, newline="", encoding="utf-8") as f:
            return cls([Agent(**{k: r[k] for k in Agent.__dataclass_fields__}) for r in csv.DictReader(f)])

    def by_number(self, number: str) -> Agent | None:
        n = _norm_id(number)
        if len(n) < 4:
            return None
        if n in self._by_id:
            return self._by_id[n]
        # "B 1293" style: the first part of the licence number.
        m = re.fullmatch(r"B0*(\d+)", n)
        if m:
            hits = [a for a in self.agents if re.match(rf"B-0*{m.group(1)}/", a.rc)]
            if len(hits) == 1:
                return hits[0]
        return None

    def check(self, agency: str = "", owner: str = "", district: str = "", licence_no: str = "", query: str = "") -> dict:
        """Main entry point. `query` is free text when the caller's words weren't split up."""
        if licence_no:
            a = self.by_number(licence_no)
            if a:
                return _result("confirmed_in_list", [(a, 100)], "licence number matched")
        if query:
            found, rest = find_district(query)
            district = district or found or ""
            agency = agency or rest
            owner = owner or rest
        if not (agency or owner):
            return _result("not_found", [], "no name given")

        said_agency = split_agency(agency) if agency else None
        said_owner = _person(owner) if owner else None
        want_district = district_key(district) if district else ""
        scored = []
        for a, (a_key, o_keys, a_district) in zip(self.agents, self._keys):
            o = owner_score(said_owner, o_keys) if owner else 0
            g = agency_score(said_agency, a_key) if agency else 0
            if owner and agency and not query:
                score = max((o + g) / 2, max(o, g) - 8)
            else:
                score = max(o, g)
            d_ok = bool(want_district) and fuzz.ratio(want_district, a_district) >= 90
            if district:
                score += 4 if d_ok else -8
            scored.append((a, score, o, g, d_ok))
        scored.sort(key=lambda x: x[1], reverse=True)

        top = [x for x in scored if x[1] >= CANDIDATE_MIN][:3]
        if not top:
            return _result("not_found", [], "no name close enough in the licensed list")

        a, score, o, g, d_ok = top[0]
        runner_up = top[1][1] if len(top) > 1 else 0
        clear_winner = score - runner_up >= 5
        both = owner and agency and not query and o >= OWNER_OK and g >= AGENCY_OK
        one_plus_district = d_ok and max(o, g) >= STRONG
        if clear_winner and (both or one_plus_district):
            return _result("confirmed_in_list", [(a, score)], "name and owner/district matched")
        return _result("needs_confirmation", [(x[0], x[1]) for x in top], "ask the caller which one, if any")


def _result(match: str, cands: list[tuple[Agent, float]], reason: str) -> dict:
    say = {
        "confirmed_in_list": "This name appears in the government's licensed list. Other checks are still needed.",
        "needs_confirmation": "Read the candidates back (agency, owner, district) and ask which one, if any, is the caller's agent.",
        "not_found": "Not found in the licensed list. Ask for the exact agency name, owner name, district or licence number.",
    }[match]
    return {
        "match": match,
        "candidates": [{**a.public(), "score": round(s, 1)} for a, s in cands],
        "reason": reason,
        "instruction": say,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--agency", default="")
    ap.add_argument("--owner", default="")
    ap.add_argument("--district", default="")
    ap.add_argument("--licence", default="")
    a = ap.parse_args()
    res = LicensedList.load().check(a.agency, a.owner, a.district, a.licence, a.query)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
