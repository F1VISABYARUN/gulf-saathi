"""Talk to the line in a terminal, no phone needed.

  python -m gulf_saathi.simulate              # inbound call
  python -m gulf_saathi.simulate --checkin    # weekly check-in call to a test worker

Type a digit (or digits) to press keys, or any other text to "speak" it.
"""
from __future__ import annotations

import argparse

from . import config, notify
from .agents import AgentRegistry
from .engine import Engine, Session
from .store import Store


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkin", action="store_true", help="simulate the weekly outbound call")
    ap.add_argument("--lang", default="te", choices=["te", "hi", "ur"], help="language for --checkin")
    ap.add_argument("--caller", default="+919999900000")
    args = ap.parse_args()

    store = Store()
    engine = Engine(AgentRegistry.from_csv(config.AGENTS_CSV), store)
    s = Session(caller=args.caller)
    if args.checkin:
        wid = store.upsert_worker(args.caller, args.lang, "UAE", "+919888800000")
        reply = engine.start_checkin(s, wid)
    else:
        reply = engine.start_inbound(s)

    while True:
        for text, _ in reply.say:
            print(f"  🔊 {text}")
        if reply.expect is None:
            print("  [call ended]")
            break
        try:
            raw = input(f"[{reply.expect}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if raw.isdigit():
            reply = engine.handle(s, digits=raw)
        else:
            reply = engine.handle(s, speech=raw)

    for m in notify.sent:
        print(f"  [would send {m['kind']} to {m['to']}] {m.get('body', m.get('url'))}")
    for e in store.open_escalations():
        print(f"  [escalation #{e['id']}] {e['reason']}")


if __name__ == "__main__":
    main()
