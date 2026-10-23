import os,sys,json
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,os.path.join(ROOT,"scripts")); sys.path.insert(0,os.path.join(ROOT,"creator"))
import fm_db_people, fm26_install
os.makedirs(os.path.join(ROOT,"work"),exist_ok=True)
db=fm_db_people.PeopleDB(fm26_install.db_dir(), cache=os.path.join(ROOT,"work","fm26_people.pkl"))
POS=["GK","DL","DC","DR","DM","ML","MC","MR","AML","AMC","AMR","ST","WBL","WBR"]
players=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pos_targets.json")))
def fmstring(r):
    rows=[("D",{"R":r["DR"],"L":r["DL"],"C":r["DC"]}),("WB",{"R":r["WBR"],"L":r["WBL"]}),("M",{"R":r["MR"],"L":r["ML"],"C":r["MC"]}),("AM",{"R":r["AMR"],"L":r["AML"],"C":r["AMC"]})]
    sided=[(name,"".join(s for s in "RLC" if v.get(s,0)>=18)) for name,v in rows]
    parts=[]
    if r["GK"]>=18: parts.append(("GK",""))
    # merge consecutive sided rows with the same sides; DM sits between WB and M
    groups=[]; 
    for name,sides in sided:
        if sides and groups and groups[-1][1]==sides and groups[-1][2]:
            groups[-1][0].append(name)
        else:
            groups.append([[name],sides,bool(sides)])
    out=[]
    dm_done=False
    for names,sides,ok in groups:
        if names[0] in ("M","AM") and not dm_done:
            if r["DM"]>=18: out.append(("DM",""))
            dm_done=True
        if ok: out.append(("/".join(names),sides))
    if not dm_done and r["DM"]>=18: out.append(("DM",""))
    if r["ST"]>=18: out.append(("ST",""))
    parts+=out
    return parts
def code(row,sides):
    if row=="GK": return 1
    if row=="DM": return 5
    if row=="ST": return 10
    first=row.split("/")[0]; s=sides[0]
    if first in ("D","WB"): return {"C":2,"R":3,"L":4}[s]
    if first=="M": return {"C":6,"R":8,"L":9}[s]
    return {"C":7,"R":8,"L":9}[s]
out={}
for name,dbid in players:
    if dbid not in db.prows: print(name,'NO RECORD'); continue
    s,e=db.prows[dbid]; rec=db.people[s:e]
    r={p:(rec[36+i] or 1) for i,p in enumerate(POS)}
    parts=fmstring(r)
    flag=""
    if not parts:
        best=max(v for k,v in r.items()); flag="none >=18, best %d"%best
        # positions at the best rating
        rr={k:(20 if v==best else 1) for k,v in r.items()}; parts=fmstring(rr)
    txt=", ".join((row+(" "+sides if sides else "")) for row,sides in parts)
    c1=code(*parts[0]); db_=c1 if len(parts)==1 else round(c1+code(*parts[1])/100,2)
    out[name]={"pos":txt,"db":db_,"ratings":{k:v for k,v in r.items() if v>1},"flag":flag}
    print("%-20s %-22s DB %-5s %s %s"%(name,txt,db_,{k:v for k,v in r.items() if v>1},flag))
json.dump(out,open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "positions.json"),"w"),ensure_ascii=False,indent=1)