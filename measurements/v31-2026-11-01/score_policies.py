import sys, json, csv, glob, collections
sys.path.insert(0, "src")
from norway_company_agent.audit import arm_units, wilson
SP = "/tmp/claude-0/-home-user-signalpost-agent/3e43140a-eb25-5545-aa91-a0fabc1c685e/scratchpad"; M = SP + "/m"
labels = {}
for f in glob.glob("measurements/v3-2026-11-01/audits/*/items.labelled.csv") + [M + "/audit-diag80/items.labelled.csv", M + "/audit-eval120/items.labelled.csv", M + "/audit-eval200/items.labelled.csv"] + sys.argv[3:]:
    for r in csv.DictReader(open(f, encoding="utf-8")):
        if r.get("verdict"): labels[r["uid"]] = r["verdict"]
labels["916303122|social_profile|instagram.com/beredtinkludering"] = "incorrect"
env = lambda p: [json.loads(l) for l in open(p).read().split("\n") if l.strip()]
cat = sys.argv[1]; policies = sys.argv[2].split(",")
groups = {"tuned (smoke100+midsize40+fresh60+diag80)": ["smoke100", "midsize40", "fresh60", "diag80"], "fresh60b (consumed)": ["fresh60b"], "eval120 (consumed; diagnostic now)": ["eval120"], "eval200 (consumed after scoring 8223a37; development now)": ["eval200"]}
base = {s: arm_units(env(f"{M}/rbase-{s}/envelopes.jsonl")) for g in groups.values() for s in g}
print(f"category {cat}")
for g, sets in groups.items():
    print(f"== {g}")
    bc = sum(1 for s in sets for u in base[s] if u.split('|')[1] == cat and labels.get(u) == "correct")
    bi = sum(1 for s in sets for u in base[s] if u.split('|')[1] == cat and labels.get(u) == "incorrect")
    print(f"  {'baseline ff3b515':32} correct {bc:4} incorrect {bi:4} precision {bc/max(1,bc+bi):.3f}")
    for p in policies:
        c = collections.Counter(); kept_base_correct = 0
        for s in sets:
            units = arm_units(env(f"{M}/p-{p}-{s}/envelopes.jsonl"))
            for u in units:
                if u.split("|")[1] != cat: continue
                c[labels.get(u, "UNLABELLED")] += 1
                if u in base[s] and labels.get(u) == "correct": kept_base_correct += 1
        d = c["correct"] + c["incorrect"]; lo, hi = wilson(c["correct"], d) if d else (0, 0)
        rlo, rhi = wilson(kept_base_correct, bc) if bc else (0, 0)
        print(f"  {p:32} correct {c['correct']:4} incorrect {c['incorrect']:4} unsure {c['unsure']:3} unlabelled {c['UNLABELLED']:3} precision {c['correct']/max(1,d):.3f} ({lo:.3f}-{hi:.3f}) retention {kept_base_correct}/{bc}={kept_base_correct/max(1,bc):.3f} ({rlo:.3f}-{rhi:.3f})")
