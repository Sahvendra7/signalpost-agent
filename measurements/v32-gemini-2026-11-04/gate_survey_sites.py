import sys,gzip,json,collections; sys.path.insert(0,'src')
from pathlib import Path
from norway_company_agent.identity_gate import target_from_envelope, assess_site
from norway_company_agent.llm_experiments.capture import CaptureStore
st=CaptureStore(Path('out/v32/captures'))
V="measurements/v32-gemini-2026-11-04"
sets={"evalg250":(f"{V}/capture-evalg250/v31-evalg250.envelopes.jsonl.gz",f"{V}/datasets/evalg250.items.jsonl",f"{V}/audits/evalg250/labels.jsonl"),
      "eval200b":("measurements/v31-2026-11-01/replay/f2-eval200b/envelopes.jsonl.gz",f"{V}/datasets/eval200b.items.jsonl",None),
      "eval200":("measurements/v31-2026-11-01/replay/v31-eval200/envelopes.jsonl.gz",f"{V}/datasets/eval200.items.jsonl",None)}
for name,(path,ipath,lpath) in sets.items():
    E=[json.loads(l) for l in gzip.open(path)]
    items=[json.loads(l) for l in open(ipath)]
    if lpath:
        lab={json.loads(l)['item_id']:json.loads(l)['label'] for l in open(lpath)}
        for i in items: i['label']=lab.get(i['item_id'])
    corr=collections.Counter(i['org'] for i in items if i['label']=='correct'); wrong=collections.Counter(i['org'] for i in items if i['label']=='incorrect')
    dist=collections.Counter(); rows=[]
    for e in E:
        site=next((c['value'] for c in e['claims'] if c['field']=='official_website' and c['availability']=='available'),None)
        if not site: continue
        page=st.page(site)
        if page is None: continue
        t=target_from_envelope(e); s=assess_site(t,site,page.text); dist[s.status]+=1
        o=e['organisation_number']
        if s.status not in ('target_operated','brand_only') or corr[o] or wrong[o]:
            rows.append((s.status,t.legal_name[:30],site[:36],corr[o],wrong[o],json.dumps(s.evidence,ensure_ascii=False)[:110]))
    print("##",name,dict(dist))
    for r in sorted(rows): 
        if r[3] or r[4] or r[0] not in ('target_operated','brand_only'): print("  %-15s %-30s %-36s correct=%-3s incorrect=%-3s %s"%r)
