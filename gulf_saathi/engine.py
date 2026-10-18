"""The call flow as a plain state machine, independent of any telephony provider.

`handle(session, digits, speech)` takes the caller's last input and returns what
to say next and what kind of input to wait for. The Twilio layer and the text
simulator both drive this same code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import checkin, config
from .agents import AgentRegistry
from .offer import OfferAnswers, assess, parse_amount
from .prompts import LANGS, SPOKEN_DIGITS, say
from .store import Store

COUNTRIES = {"1": "UAE", "2": "Saudi Arabia", "3": "Other Gulf", "4": "Other"}


@dataclass
class Session:
    caller: str = ""
    lang: str = "te"
    step: str = "lang"
    data: dict = field(default_factory=dict)
    retries: int = 0


@dataclass
class Reply:
    say: list[tuple[str, str]]  # (text, lang)
    expect: str | None = "digit"  # "digit", "digits", "speech", or None to hang up
    hints: list[str] = field(default_factory=list)  # speech-recognition hints


def spoken_digit(speech: str | None) -> str | None:
    if not speech:
        return None
    # Split on spaces and punctuation, not \w: Indic vowel signs aren't \w.
    words = [w for w in re.split(r"[\s,.!?;:\"'।؟۔]+", speech.lower()) if w]
    for digit, forms in SPOKEN_DIGITS.items():
        if any(f.lower() in words for f in forms):
            return digit
    return None


def fmt_rupees(n: int) -> str:
    """Indian digit grouping: 150000 -> 1,50,000."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail])


def speak_digits(digits: str) -> str:
    return " ".join(digits)


class Engine:
    def __init__(self, registry: AgentRegistry, store: Store):
        self.registry = registry
        self.store = store

    # -- entry points -------------------------------------------------------
    def start_inbound(self, s: Session) -> Reply:
        s.step = "lang"
        return Reply([(say("welcome", l), l) for l in LANGS])

    def start_checkin(self, s: Session, worker_id: int) -> Reply:
        w = self.store.worker(worker_id)
        s.lang = w["lang"]
        s.data = {"worker_id": worker_id}
        s.step = "ci_paid"
        return self._r(s, "ci_hello", "ci_paid")

    def handle(self, s: Session, digits: str | None = None, speech: str | None = None) -> Reply:
        digits = (digits or "").strip() or None
        speech = (speech or "").strip() or None
        step = getattr(self, "_step_" + s.step)
        reply = step(s, digits, speech)
        if reply is None:  # input not understood
            s.retries += 1
            if s.retries >= config.MAX_RETRIES:
                return self._bye(s)
            return self._reprompt(s)
        s.retries = 0
        return reply

    # -- helpers ------------------------------------------------------------
    def _r(self, s: Session, *keys: str, expect: str = "digit", **kw) -> Reply:
        return Reply([(say(k, s.lang, **kw), s.lang) for k in keys], expect)

    def _bye(self, s: Session, *before: str, **kw) -> Reply:
        return Reply([(say(k, s.lang, **kw), s.lang) for k in (*before, "goodbye")], None)

    def _reprompt(self, s: Session) -> Reply:
        r = getattr(self, "_prompt_" + s.step)(s)
        r.say.insert(0, (say("invalid", s.lang), s.lang))
        return r

    def _choice(self, digits, speech) -> str | None:
        if digits:
            return digits[0]
        return spoken_digit(speech)

    def _menu(self, s: Session, *before: str) -> Reply:
        s.step = "menu"
        return self._r(s, *before, "menu")

    # -- prompts (used for first entry and for reprompts) ----------------------
    def _prompt_lang(self, s):
        return Reply([(say("welcome", l), l) for l in LANGS])

    def _prompt_menu(self, s):
        return self._r(s, "menu")

    def _prompt_agent_name(self, s):
        r = self._r(s, "ask_agent", expect="speech")
        r.hints = [a.name for a in self.registry.agents][:400]
        return r

    def _prompt_agent_confirm(self, s):
        return self._r(s, "agent_confirm", name=s.data["candidate"])

    def _prompt_agent_after(self, s):
        return self._r(s, "back_or_menu")

    _prompt_offer_after = _prompt_agent_after

    def _prompt_offer_contract(self, s):
        return self._r(s, "offer_contract")

    def _prompt_offer_visa(self, s):
        return self._r(s, "offer_visa")

    def _prompt_offer_fee(self, s):
        return self._r(s, "offer_fee", expect="digits")

    def _prompt_offer_region(self, s):
        return self._r(s, "offer_region")

    def _prompt_offer_passport(self, s):
        return self._r(s, "offer_passport")

    def _prompt_reg_country(self, s):
        return self._r(s, "reg_country")

    def _prompt_reg_family(self, s):
        return self._r(s, "reg_family", expect="digits")

    def _prompt_reg_confirm(self, s):
        return self._r(s, "reg_confirm", digits=speak_digits(s.data["family"]))

    def _prompt_fam_menu(self, s):
        return self._r(s, "fam_menu")

    def _prompt_fam_exgratia(self, s):
        return self._r(s, "fam_exgratia", amount=fmt_rupees(config.EX_GRATIA_INR))

    def _prompt_fam_pbby(self, s):
        return self._r(s, "fam_pbby", amount=fmt_rupees(config.PBBY_COVER_INR))

    def _prompt_ci_paid(self, s):
        return self._r(s, "ci_paid")

    def _prompt_ci_passport(self, s):
        return self._r(s, "ci_passport")

    def _prompt_ci_safe(self, s):
        return self._r(s, "ci_safe")

    # -- steps --------------------------------------------------------------
    def _step_lang(self, s, digits, speech):
        c = self._choice(digits, speech)
        if speech and not c:
            # Pick the language from the script the caller spoke in.
            if re.search(r"[\u0C00-\u0C7F]", speech):
                c = "1"
            elif re.search(r"[\u0600-\u06FF]", speech):
                c = "3"
            elif re.search(r"[\u0900-\u097F]", speech):
                c = "2"
        lang = {"1": "te", "2": "hi", "3": "ur"}.get(c)
        if not lang:
            return None
        s.lang = lang
        return self._menu(s)

    def _step_menu(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            s.step = "agent_name"
            return self._prompt_agent_name(s)
        if c == "2":
            s.data["offer"] = OfferAnswers()
            s.step = "offer_contract"
            return self._prompt_offer_contract(s)
        if c == "3":
            s.step = "reg_country"
            return self._prompt_reg_country(s)
        if c == "4":
            s.step = "fam_menu"
            return self._prompt_fam_menu(s)
        if c == "9":
            return self._menu(s)
        return None

    # 1. Agent check
    def _step_agent_name(self, s, digits, speech):
        query = speech or digits
        if not query:
            return None
        m = self.registry.lookup(query)
        self.store.log_lookup(s.caller, query, m.agent and m.agent.name, m.agent and m.agent.status, m.score)
        if m.kind == "probable":
            s.data["candidate"] = m.agent.spoken_name(s.lang)
            s.data["candidate_agent"] = m.agent
            s.step = "agent_confirm"
            return self._prompt_agent_confirm(s)
        return self._agent_result(s, m.agent if m.kind == "confident" else None)

    def _step_agent_confirm(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            return self._agent_result(s, s.data["candidate_agent"])
        if c == "2":
            s.step = "agent_name"
            return self._prompt_agent_name(s)
        return None

    def _agent_result(self, s, agent) -> Reply:
        s.step = "agent_after"
        if agent is None:
            keys, kw = ["agent_unknown"], {}
        elif agent.status == "flagged":
            keys, kw = ["agent_flagged"], {"name": agent.spoken_name(s.lang)}
        else:
            keys = ["agent_licensed"]
            kw = {"name": agent.spoken_name(s.lang), "licence": agent.licence_no, "max_fee": fmt_rupees(config.MAX_SERVICE_FEE_INR)}
        return self._r(s, *keys, "ecr_visit_warning", "back_or_menu", **kw)

    def _step_agent_after(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            s.step = "agent_name"
            return self._prompt_agent_name(s)
        if c == "0":
            return self._menu(s)
        return None

    # 2. Offer check
    def _step_offer_contract(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c not in ("1", "2"):
            return None
        s.data["offer"].has_contract = c == "1"
        s.step = "offer_visa"
        return self._prompt_offer_visa(s)

    def _step_offer_visa(self, s, digits, speech):
        c = self._choice(digits, speech)
        visa = {"1": "employment", "2": "visit", "3": "unknown"}.get(c)
        if not visa:
            return None
        s.data["offer"].visa = visa
        s.step = "offer_fee"
        return self._prompt_offer_fee(s)

    def _step_offer_fee(self, s, digits, speech):
        fee = int(digits) if digits and digits.isdigit() else parse_amount(speech or "")
        if fee is None and speech:
            # A bare spoken number like "80000" with no unit.
            nums = re.findall(r"\d+", speech.replace(",", ""))
            fee = int(nums[0]) if nums else None
        if fee is None:
            return None
        s.data["offer"].fee_inr = fee
        s.step = "offer_region"
        return self._prompt_offer_region(s)

    def _step_offer_region(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c not in ("1", "2"):
            return None
        s.data["offer"].region = "gulf" if c == "1" else "other"
        s.step = "offer_passport"
        return self._prompt_offer_passport(s)

    def _step_offer_passport(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c not in ("1", "2"):
            return None
        offer: OfferAnswers = s.data["offer"]
        offer.passport_kept = c == "1"
        flags = assess(offer)
        kw = {"n": len(flags), "max_fee": fmt_rupees(config.MAX_SERVICE_FEE_INR)}
        if offer.fee_inr is not None:
            kw["fee"] = fmt_rupees(offer.fee_inr)
        s.step = "offer_after"
        if flags:
            return self._r(s, "offer_bad", *flags, "back_or_menu", **kw)
        return self._r(s, "offer_ok", "back_or_menu", **kw)

    def _step_offer_after(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            s.data["offer"] = OfferAnswers()
            s.step = "offer_contract"
            return self._prompt_offer_contract(s)
        if c == "0":
            return self._menu(s)
        return None

    # 3. Check-in registration
    def _step_reg_country(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c not in COUNTRIES:
            return None
        s.data["country"] = COUNTRIES[c]
        s.step = "reg_family"
        return self._prompt_reg_family(s)

    def _step_reg_family(self, s, digits, speech):
        number = re.sub(r"\D", "", digits or speech or "")
        if len(number) != 10:
            return None
        s.data["family"] = number
        s.step = "reg_confirm"
        return self._prompt_reg_confirm(s)

    def _step_reg_confirm(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "2":
            s.step = "reg_family"
            return self._prompt_reg_family(s)
        if c != "1":
            return None
        self.store.upsert_worker(s.caller, s.lang, s.data["country"], "+91" + s.data["family"])
        return self._bye(s, "reg_done")

    # 4. Family help
    def _step_fam_menu(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            s.step, s.data["topic"] = "fam_exgratia", "ex_gratia"
            return self._prompt_fam_exgratia(s)
        if c == "2":
            s.step, s.data["topic"] = "fam_pbby", "pbby"
            return self._prompt_fam_pbby(s)
        if c == "0":
            return self._menu(s)
        return None

    def _step_fam_exgratia(self, s, digits, speech):
        c = self._choice(digits, speech)
        if c == "1":
            self.store.add_callback(s.caller, s.lang, s.data["topic"])
            return self._bye(s, "callback_logged")
        if c == "0":
            return self._menu(s)
        return None

    _step_fam_pbby = _step_fam_exgratia

    # Outbound weekly check-in
    def _yes_no(self, digits, speech) -> bool | None:
        c = self._choice(digits, speech)
        return {"1": True, "2": False}.get(c)

    def _step_ci_paid(self, s, digits, speech):
        v = self._yes_no(digits, speech)
        if v is None:
            return None
        s.data["paid"] = v
        s.step = "ci_passport"
        return self._prompt_ci_passport(s)

    def _step_ci_passport(self, s, digits, speech):
        v = self._yes_no(digits, speech)
        if v is None:
            return None
        s.data["passport"] = v
        s.step = "ci_safe"
        return self._prompt_ci_safe(s)

    def _step_ci_safe(self, s, digits, speech):
        v = self._yes_no(digits, speech)
        if v is None:
            return None
        wid, paid, passport = s.data["worker_id"], s.data["paid"], s.data["passport"]
        self.store.record_checkin(wid, paid, passport, v)
        problems = [r for r, ok in (("unpaid", paid), ("passport", passport), ("unsafe", v)) if not ok]
        if problems:
            checkin.escalate(self.store, wid, problems)
            return self._bye(s, "ci_escalated")
        return self._bye(s, "ci_ok")
