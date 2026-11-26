"""pytest plugin: record the inputs and outputs of pure functions while the Python
tests run, so the TypeScript port can be checked against exactly the same cases.
Run from the repo root: python -m pytest -q -p ts.scripts.golden_plugin  (see make_golden.py)."""
import functools, inspect, json, os

REC = {}
OUT = os.environ.get("GOLDEN_OUT", "ts/test/golden/recorded.json")


def _wrap(mod, name, key=None, method_of=None):
    target = getattr(method_of or mod, name)
    sig = inspect.signature(target)

    @functools.wraps(target)
    def inner(*args, **kwargs):
        res = target(*args, **kwargs)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            a = dict(bound.arguments)
            a.pop("self", None)
            json.dumps(a); json.dumps(res, default=str)
            REC.setdefault(key or name, []).append({"args": a, "result": res})
        except Exception:
            pass
        return res
    setattr(method_of or mod, name, inner)


def pytest_configure(config):
    from gulf_saathi import calls, fees, matcher, offer
    _wrap(matcher, "check", key="matcher.check", method_of=matcher.LicensedList)
    _wrap(fees, "parse_amounts", key="fees.parse_amounts")
    _wrap(fees, "check_fee", key="fees.check_fee")
    _wrap(offer, "parse_amount", key="offer.parse_amount")
    _wrap(calls, "parse_call", key="calls.parse_call")


def pytest_sessionfinish(session, exitstatus):
    seen = {}
    for k, rows in REC.items():
        uniq, keys = [], set()
        for r in rows:
            s = json.dumps(r["args"], sort_keys=True, ensure_ascii=False)
            if s not in keys:
                keys.add(s); uniq.append(r)
        seen[k] = uniq
    with open(OUT, "w") as f:
        json.dump(seen, f, ensure_ascii=False, default=str)
