import sys,gzip,json,collections; sys.path.insert(0,'src')
from pathlib import Path
from norway_company_agent.identity_gate import target_from_envelope, assess_site, assess_item
from norway_company_agent.llm_experiments.capture import CaptureStore
st=CaptureStore(Path('out/v32/captures'))
V="measurements/v32-gemini-2026-11-04"
sets={"evalg250":(f"{V}/capture-evalg250/v31-evalg250.envelopes.jsonl.gz",f"{V}/datasets/evalg250.items.jsonl",f"{V}/audits/evalg250/labels.jsonl"),
      "eval200b":("measurements/v31-2026-11-01/replay/f2-eval200b/envelopes.jsonl.gz",f"{V}/datasets/eval200b.items.jsonl",None),
      "eval200":("measurements/v31-2026-11-01/replay/v31-eval200/envelopes.jsonl.gz",f"{V}/datasets/eval200.items.jsonl",None)}
for name,(path,ipath,lpath) in sets.items():
    E={json.loads(l)['organisation_number']:json.loads(l) for l in gzip.open(path)}
    items=[json.loads(l) for l in open(ipath)]
    if lpath:
        lab={json.loads(l)['item_id']:json.loads(l) for l in open(lpath)}
        for i in items: i['label']=lab[i['item_id']]['label']; i['label_note']=lab[i['item_id']]['note']
    P={json.loads(l)['item_id']:json.loads(l) for l in gzip.open(f"{V}/datasets/{name}.packets.jsonl.gz",'rt')}
    sites={}
    res=collections.Counter(); ex=[]
    for i in items:
        e=E.get(i['org']); p=P[i['item_id']]
        site=p['website']['url']
        if (i['org'],site) not in sites:
            page=st.page(site) if site else None
            t=target_from_envelope(e) if e else None
            sites[(i['org'],site)]=(t, assess_site(t,site,page.text) if (t and page) else None)
        t,s=sites[(i['org'],site)]
        if s is None: res[(i['label'],'no_site_assessment')]+=1; continue
        text="\n".join(filter(None,[p['item']['title'],p.get('source_text'),p.get('article_text')]))
        d=assess_item(t,s,text)
        res[(i['label'],d.decision,d.code if d.decision=='withhold' else '')]+=1
        if d.decision=='withhold' and i['label']=='correct': ex.append((i['company'][:25],i['title'][:60],d.code,d.other_entities[:2]))
    print("##",name)
    for k,v in sorted(res.items(),key=lambda kv:str(kv[0])): print("  ",k,v)
    for x in ex[:12]: print("   CORRECT WITHHELD:",x)
