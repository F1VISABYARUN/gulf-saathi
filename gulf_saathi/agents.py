"""Recruiting-agent lookup against the licensed / flagged lists.

Speech recognition returns names in Telugu or Devanagari script, misspelt, or
half-heard over camp noise, so matching is fuzzy on a romanised, phonetically
flattened key. Urdu script isn't transliterated; add Urdu spellings as aliases.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from indic_transliteration import sanscript
from rapidfuzz import fuzz

CONFIDENT = 88
PROBABLE = 70

# Words that appear in most agency names and carry no identifying signal.
STOPWORDS = {
    "overseas", "manpower", "consultants", "consultancy", "consultant", "travels", "travel",
    "tours", "pvt", "private", "ltd", "limited", "agency", "agencies", "services", "service",
    "international", "intl", "recruiting", "recruitment", "recruiters", "enterprises", "and",
    "co", "company", "the", "demo", "agent", "placement", "placements", "solutions",
}

_TELUGU = re.compile(r"[\u0C00-\u0C7F]")
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_PHONETIC = [
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ph", "f"),
    ("sh", "s"), ("th", "t"), ("dh", "d"), ("kh", "k"), ("gh", "g"), ("bh", "b"),
    ("ch", "c"), ("w", "v"), ("z", "j"), ("q", "k"), ("y", "i"),
]


@dataclass
class Agent:
    name: str
    licence_no: str
    status: str  # "licensed" or "flagged"
    city: str = ""
    state: str = ""
    aliases: list[str] = field(default_factory=list)

    def spoken_name(self, lang: str) -> str:
        """The alias written in the caller's script, so the TTS voice can say it."""
        script = {"te": _TELUGU, "hi": _DEVANAGARI, "ur": _ARABIC}[lang]
        return next((a for a in self.aliases if script.search(a)), self.name)


@dataclass
class Match:
    agent: Agent | None
    score: float
    kind: str  # "confident", "probable" or "none"


def romanize(text: str) -> str:
    if _TELUGU.search(text):
        text = sanscript.transliterate(text, sanscript.TELUGU, sanscript.ITRANS)
    elif _DEVANAGARI.search(text):
        text = sanscript.transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
    return text


def name_key(text: str, drop_stopwords: bool = True) -> str:
    text = romanize(text).lower()
    # Keep Arabic-script letters: Urdu isn't romanised, it matches Urdu aliases.
    text = re.sub(r"[^a-z0-9\s\u0600-\u06FF]", " ", text)
    words = text.split()
    if drop_stopwords:
        core = [w for w in words if w not in STOPWORDS]
        words = core or words
    out = []
    for w in words:
        for a, b in _PHONETIC:
            w = w.replace(a, b)
        w = re.sub(r"(.)\1+", r"\1", w)
        out.append(w)
    return " ".join(out)


def _digits(text: str) -> str:
    return "".join(re.findall(r"\d", text))


class AgentRegistry:
    def __init__(self, agents: list[Agent]):
        self.agents = agents
        self._keys = [
            (a, name_key(n)) for a in agents for n in [a.name, *a.aliases] if n.strip()
        ]

    @classmethod
    def from_csv(cls, path: Path | str) -> "AgentRegistry":
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        agents = [
            Agent(
                name=r["name"].strip(),
                licence_no=r.get("licence_no", "").strip(),
                status=r["status"].strip().lower(),
                city=r.get("city", "").strip(),
                state=r.get("state", "").strip(),
                aliases=[x.strip() for x in r.get("aliases", "").split("|") if x.strip()],
            )
            for r in rows
            if r.get("name", "").strip()
        ]
        return cls(agents)

    def lookup(self, query: str) -> Match:
        query = query.strip()
        if not query:
            return Match(None, 0, "none")

        digits = _digits(query)
        if len(digits) >= 3:
            for a in self.agents:
                if a.licence_no and _digits(a.licence_no) == digits:
                    return Match(a, 100, "confident")

        q = name_key(query)
        if not q:
            return Match(None, 0, "none")
        best: dict[int, tuple[Agent, float]] = {}
        for agent, key in self._keys:
            score = fuzz.WRatio(q, key)
            if id(agent) not in best or score > best[id(agent)][1]:
                best[id(agent)] = (agent, score)
        ranked = sorted(best.values(), key=lambda x: x[1], reverse=True)
        if not ranked:
            return Match(None, 0, "none")

        agent, score = ranked[0]
        if score < PROBABLE:
            return Match(None, score, "none")
        # Two different agents scoring nearly the same: ask the caller to confirm.
        ambiguous = len(ranked) > 1 and ranked[1][1] >= score - 3
        kind = "confident" if score >= CONFIDENT and not ambiguous else "probable"
        return Match(agent, score, kind)
