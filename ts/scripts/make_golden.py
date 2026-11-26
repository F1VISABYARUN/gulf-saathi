"""Write golden files from the Python code so the TypeScript port can be checked
against it. Run from the repo root: python3 ts/scripts/make_golden.py"""
import json, random, re, sys
sys.path.insert(0, ".")
from rapidfuzz import fuzz
from gulf_saathi import fees, matcher, offer

rnd = random.Random(20261126)
agents = matcher.LicensedList.load()
OUT = "ts/test/golden/"

words = sorted({w.lower() for a in agents.agents for w in re.findall(r"[A-Za-z]+", a.agency + " " + a.sign)})
TE = "".join(chr(c) for c in range(0x0C00, 0x0C80))
te_words = ["జగిత్యాల", "నిజామాబాద్", "సి ఎం ఆర్", "గగన్ మ్యాన్‌పవర్", "శ్రీ లక్ష్మి ట్రావెల్స్", "రమేష్", "కృష్ణ", "జ్ఞానం", "క్షేత్రం",
            "ఓవర్సీస్", "కన్సల్టెన్సీ", "మల్లేశం", "నర్సయ్య", "ౝ", "అమ్మ బాగుందా", "ఏజెంట్ పేరు రాజు, సిరిసిల్ల", "పది వేలు"]

def mutate(w):
    w = list(w)
    for _ in range(rnd.randint(0, 2)):
        if not w: break
        op, i = rnd.randint(0, 2), rnd.randrange(len(w))
        if op == 0: w.pop(i)
        elif op == 1: w.insert(i, rnd.choice("aeiouyhsnrt"))
        else: w[i] = rnd.choice("abcdefghijklmnopqrstuvwxyz")
    return "".join(w)

def phrase(n):
    return " ".join(mutate(rnd.choice(words)) if rnd.random() < .5 else rnd.choice(words) for _ in range(n))

# 1. fuzz scorers
pairs = [("", ""), ("a", ""), ("", "a"), ("abc", "abc"), ("manpower", "myanpavar"), ("a b", "b a"), ("x y z", "y z")]
for _ in range(3000):
    a, b = phrase(rnd.randint(0, 4)), phrase(rnd.randint(0, 4))
    if rnd.random() < .3: b = a + " " + phrase(rnd.randint(0, 2))
    pairs.append((a, b))
fz = [{"a": a, "b": b, "ratio": fuzz.ratio(a, b), "sort": fuzz.token_sort_ratio(a, b), "set": fuzz.token_set_ratio(a, b)} for a, b in pairs]

# 2. transliteration and token helpers
texts = te_words + [ "".join(rnd.choice(TE + "  abc") for _ in range(rnd.randint(1, 12))) for _ in range(800)]
texts += [phrase(rnd.randint(1, 5)) for _ in range(400)] + ["M/S. Gagan Man Power & Co Pvt Ltd", "si em ar overseas", "Café Rāmesh", "a b c travels"]
from indic_transliteration import sanscript
tr = [{"text": t, "itrans": sanscript.transliterate(t, sanscript.TELUGU, sanscript.ITRANS) if re.search(r"[ఀ-౿]", t) else None,
       "romanize": matcher.romanize(t), "tokens": matcher.tokens(t), "split_agency": list(matcher.split_agency(t)),
       "find_district": list(matcher.find_district(t)), "district_key": matcher.district_key(t)} for t in texts]
ph = [{"w": w, "phonetic": matcher.phonetic(w), "skeleton": matcher.skeleton(w), "generic": matcher._canonical_generic(w)}
      for w in words[:3000] + [mutate(rnd.choice(words)) for _ in range(1500)]]

# 3. matcher checks
dists = ["Jagtial", "Nizamabad", "Karimnagar", "Hyderabad", "Nirmal", "జగిత్యాల", "Mumbai", ""]
mq = []
for a in rnd.sample(agents.agents, 220):
    owner = a.sign.split(",")[0]
    for kw in [dict(agency=a.agency), dict(agency=mutate(a.agency)), dict(owner=owner), dict(owner=mutate(owner), district=rnd.choice(dists)),
               dict(agency=a.agency, owner=owner), dict(query=f"{a.agency} {a.district}"), dict(agency=" ".join(a.agency.split()[:1]), district=a.district),
               dict(licence_no=a.rc.split("/")[0]), dict(licence_no=a.raid)]:
        mq.append(kw)
mq += [dict(query=t) for t in te_words] + [dict(agency=phrase(2)) for _ in range(100)] + [dict(owner=phrase(2), district=rnd.choice(dists)) for _ in range(100)]
mres = [{"args": kw, "result": agents.check(**kw)} for kw in mq]

# 4. money text
mt = ["10000; 25000", "1.5 lakh", "80,000", "60 వేలు", "10000,25000", "9876543210", "5 L and 2k", "Rs 35400", "₹1,50,000 fee", "50 days", "1,2,3"]
mt += [f"{rnd.randint(0, 300000)}{rnd.choice(['', ' ', ','])}{rnd.choice(['', 'k', ' lakh', ' వేలు', ' thousand', 'l'])} {rnd.choice(['', 'and', ';', 'paid'])} {rnd.randint(0, 99999)}" for _ in range(600)]
money = []
for t in mt:
    row = {"text": t}
    for k, fn in (("parse_amounts", fees.parse_amounts), ("check_fee", fees.check_fee), ("parse_amount", offer.parse_amount)):
        try: row[k] = fn(t)
        except Exception as e: row[k] = {"error": type(e).__name__}
    an, flags = offer.analyze_text(t + " visit visa contract urgent upi fee")
    row["analyze"] = {"answers": vars(an), "flags": flags}
    money.append(row)

for name, data in (("fuzz", fz), ("translit", tr), ("phonetic", ph), ("matcher", mres), ("money", money)):
    with open(OUT + name + ".json", "w") as f:
        json.dump(data, f, ensure_ascii=False)
    print(name, len(data))
