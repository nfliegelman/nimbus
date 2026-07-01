#!/usr/bin/env python3
"""
Kalshi Weather Edge  -  GitHub-deployable edition
=================================================
Runs headless on GitHub Actions (twice daily). Each run:
  * RESOLVES past paper bets using Kalshi's OWN settled result + settled temp
    (authoritative win/loss and margin of victory, straight from Kalshi).
  * SCORES today's forecastable markets, sizes each play in UNITS
    (2u / 1.5u / 1u / no bet) from a confidence score, guards out realized and
    station-offset markets.
  * WRITES two dashboards into docs/ for GitHub Pages:
       docs/index.html    -> today's bets
       docs/results.html  -> performance tracker (charts + raw data)
  * Persists everything to weather_state.json (committed back by the Action).

Confidence -> units is fully tunable in UNIT knobs below; we adjust as the
scorecard calibrates. Stdlib only.
"""

import json, math, os, sys, time, webbrowser
import urllib.request, urllib.error, urllib.parse
import datetime as dt
from collections import defaultdict

# ------------------------------ knobs ------------------------------
BANKROLL      = 500.0
BASE_UNIT_USD = round(BANKROLL * 0.02, 2)     # 1u = 2% of bankroll ($10 at $500)
UNIT_MAP      = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.0}   # tier -> units (0 = no bet)
# Win-probability caps. A bet you rarely WIN is high-variance no matter how big
# the edge, so cap its size. A long price is already its own reward. p_win is the
# model prob the *position* wins (mp for YES, 1-mp for NO). Tunable.
WINPROB_CAP   = [(0.55, 2.0), (0.42, 1.5), (0.00, 1.0)]   # p_win >= x -> max units
MIN_OI        = 300
PLAY_NET_EDGE = 0.04
MAX_LEAD_DAYS = 4
BIAS_TOL      = 2.0
INTRADAY_HIGH_CUTOFF = 14
ENSEMBLE_MODELS = ["gfs025", "ecmwf_ifs025"]
# tier score thresholds (effective edge in cents); tune as we calibrate
TIER_CUTS = [("S", 0.12), ("A", 0.08), ("B", 0.05), ("C", 0.03)]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "docs")
STATE_PATH = os.path.join(HERE, "weather_state.json")
KBASE = "https://api.elections.kalshi.com/trade-api/v2"
# -------------------------------------------------------------------

CITIES = {
    "ATL":(33.6301,-84.4418,"America/New_York","Atlanta (ATL)"),
    "AUS":(30.1830,-97.6799,"America/Chicago","Austin (AUS)"),
    "BOS":(42.3606,-71.0097,"America/New_York","Boston (Logan)"),
    "CHI":(41.7868,-87.7522,"America/Chicago","Chicago (Midway)"),
    "DAL":(32.8975,-97.0203,"America/Chicago","Dallas (DFW)"),
    "DC":(38.8485,-77.0341,"America/New_York","Washington (DCA)"),
    "DEN":(39.8466,-104.6562,"America/Denver","Denver (DEN)"),
    "HOU":(29.9902,-95.3368,"America/Chicago","Houston (IAH)"),
    "LAX":(33.9416,-118.4085,"America/Los_Angeles","Los Angeles (LAX)"),
    "LV":(36.0719,-115.1633,"America/Los_Angeles","Las Vegas (LAS)"),
    "MIA":(25.7932,-80.2906,"America/New_York","Miami (MIA)"),
    "MIN":(44.8831,-93.2289,"America/Chicago","Minneapolis (MSP)"),
    "NOLA":(29.9934,-90.2581,"America/Chicago","New Orleans (MSY)"),
    "NYC":(40.7790,-73.9693,"America/New_York","New York (Central Park)"),
    "OKC":(35.3889,-97.6008,"America/Chicago","Oklahoma City (OKC)"),
    "PHIL":(39.8729,-75.2407,"America/New_York","Philadelphia (PHL)"),
    "PHX":(33.4277,-112.0037,"America/Phoenix","Phoenix (PHX)"),
    "SATX":(29.5337,-98.4698,"America/Chicago","San Antonio (SAT)"),
    "SEA":(47.4444,-122.3138,"America/Los_Angeles","Seattle (SEA)"),
    "SFO":(37.6189,-122.3750,"America/Los_Angeles","San Francisco (SFO)"),
}
MON={"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
TODAY=dt.date.today()
DOT="\u00b7"   # middot, kept out of f-string expressions for py3.11 safety

# ----------------------------- helpers -----------------------------
def fget(url, tries=3):
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"kw/3.0"})
            with urllib.request.urlopen(req,timeout=45) as r: return json.load(r)
        except Exception as e:
            if i==tries-1: print("   fetch failed:",str(e)[:90]); return None
            time.sleep(1.0)

def fnum(x,d=None):
    try: return float(x)
    except (TypeError,ValueError): return d

def parse_date_code(c):
    try: return dt.date(2000+int(c[:2]),MON[c[2:5]],int(c[5:7]))
    except Exception: return None

def round_nws(x): return int(math.floor(x+0.5))

def bucket_range(b):
    st=b["stype"]
    if st=="less":    return (-999, (b["cap"] or 999)-1)
    if st=="greater": return ((b["floor"] or -999)+1, 999)
    if st=="between": return (b["floor"], b["cap"])
    return (-999,999)

def in_bucket(val,b):
    lo,hi=bucket_range(b); v=round_nws(val); return lo<=v<=hi

def margin_deg(actual,b,won):
    lo,hi=bucket_range(b)
    lo_e,hi_e=lo-0.5,hi+0.5
    if lo<=round_nws(actual)<=hi:
        mag=min(actual-lo_e,hi_e-actual)
    else:
        mag=min(abs(actual-lo_e),abs(hi_e-actual))
    return round(mag if won else -mag,1)

def bucket_rep(b):
    if b["stype"]=="between" and b["floor"] is not None and b["cap"] is not None: return (b["floor"]+b["cap"])/2
    if b["stype"]=="less"    and b["cap"]   is not None: return b["cap"]-1.5
    if b["stype"]=="greater" and b["floor"] is not None: return b["floor"]+1.5
    return None

def bucket_id(b): return f'{b["stype"]}:{b["floor"]}:{b["cap"]}'
def fee(p): return max(round(0.07*p*(1-p),2),0.0)
def pstdev(xs):
    if len(xs)<2: return 0.0
    m=sum(xs)/len(xs); return math.sqrt(sum((x-m)**2 for x in xs)/len(xs))

# --------------------------- data fetch ----------------------------
def pull_weather_markets():
    evs,cur=[],None; print("Pulling Kalshi weather markets...")
    for _ in range(60):
        u=f"{KBASE}/events?limit=200&status=open&with_nested_markets=true"
        if cur: u+="&cursor="+cur
        d=fget(u)
        if not d: break
        evs+=d.get("events",[]); cur=d.get("cursor")
        if not cur: break
        time.sleep(0.15)
    out=[]
    for e in evs:
        ser=e.get("series_ticker") or ""
        if   ser.startswith("KXHIGHT"): kind,code="HIGH",ser[7:]
        elif ser.startswith("KXLOWT"):  kind,code="LOW",ser[6:]
        else: continue
        if code not in CITIES: continue
        et=e.get("event_ticker",""); parts=et.split("-")
        tdate=parse_date_code(parts[1]) if len(parts)>1 else None
        if not tdate: continue
        bks=[]
        for m in e.get("markets",[]):
            yb,ya=fnum(m.get("yes_bid_dollars")),fnum(m.get("yes_ask_dollars"))
            if yb is None or ya is None: continue
            bks.append({"ticker":m.get("ticker"),"floor":fnum(m.get("floor_strike")),
                        "cap":fnum(m.get("cap_strike")),"stype":m.get("strike_type"),
                        "sub":m.get("yes_sub_title") or "","yb":yb,"ya":ya,
                        "oi":fnum(m.get("open_interest_fp"),0) or 0})
        if bks: out.append({"code":code,"kind":kind,"date":tdate,"event_ticker":et,"buckets":bks})
    print(f"  found {len(out)} city/day ladders")
    return out

def fetch_members(lat,lon,tz):
    highs,lows,offset={},{},0
    for model in ENSEMBLE_MODELS:
        u=(f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m&models={model}&temperature_unit=fahrenheit"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=10")
        d=fget(u)
        if not d: continue
        offset=d.get("utc_offset_seconds",offset)
        h=d.get("hourly",{}); times=h.get("time",[])
        for k in [k for k in h if k.startswith("temperature_2m")]:
            dv={}
            for t,v in zip(times,h[k]):
                if v is not None: dv.setdefault(t[:10],[]).append(v)
            for day,vs in dv.items():
                if vs: highs.setdefault(day,[]).append(max(vs)); lows.setdefault(day,[]).append(min(vs))
        time.sleep(0.2)
    return highs,lows,offset

def fetch_settled_event(event_ticker):
    """Return {ticker: (result, exp_value)} for settled markets of an event."""
    d=fget(f"{KBASE}/markets?event_ticker={event_ticker}&status=settled&limit=100")
    out={}
    if d:
        for m in d.get("markets",[]):
            out[m.get("ticker")]=(m.get("result"), fnum(m.get("expiration_value")))
    return out

# ------------------------------ tiers ------------------------------
def city_skill(state):
    agg=defaultdict(lambda:{"bm":0.0,"bk":0.0,"nb":0})
    for r in state.get("resolved",[]):
        a=agg[(r["code"],r["kind"])]
        for b in r["buckets"]:
            a["bm"]+=(b["mp"]-b["hit"])**2; a["bk"]+=(b["mid"]-b["hit"])**2; a["nb"]+=1
    return {k:{"nb":a["nb"],"brier_edge":(a["bk"]-a["bm"])/a["nb"]} for k,a in agg.items() if a["nb"]>=20}

TIER_RANK={"S":0,"A":1,"B":2,"C":3}
def tier_for(net,lead,sd,skill):
    lead_w={0:1.0,1:1.0,2:0.8,3:0.6,4:0.45}.get(lead,0.4)
    sharp_w=1.0 if sd<=2 else 0.85 if sd<=3 else 0.7 if sd<=4 else 0.55
    proven=skill is not None
    hist_w=max(0.5,min(1.4,1.0+skill["brier_edge"]*8)) if proven else 1.0
    eff=net*lead_w*sharp_w*hist_w
    t=None
    for name,cut in TIER_CUTS:
        if eff>=cut: t=name; break
    if t=="S" and not proven: t="A"
    return t,eff,proven

def units_of(t): return UNIT_MAP.get(t,0.0)

def size_play(tier, p_win):
    """Tier sets the ceiling; win-probability caps it so low-prob bets stay small."""
    base=UNIT_MAP.get(tier,0.0)
    if base<=0: return 0.0, ""
    cap=WINPROB_CAP[-1][1]
    for thr,u in WINPROB_CAP:
        if p_win>=thr: cap=u; break
    units=min(base,cap)
    reason=("longshot cap: win prob %.0f%%"%(p_win*100)) if units<base else ""
    return units, reason

# ----------------------------- scoring -----------------------------
def score(state):
    ladders=pull_weather_markets()
    needed=sorted({l["code"] for l in ladders})
    print(f"Forecasts for {len(needed)} cities ({'+'.join(ENSEMBLE_MODELS)})...")
    fc,offs={},{}
    for code in needed:
        lat,lon,tz,label=CITIES[code]
        hi,lo,off=fetch_members(lat,lon,tz); fc[code]={"HIGH":hi,"LOW":lo}; offs[code]=off
    rows,plays=[],[]
    skill=city_skill(state); preds=state.setdefault("predictions",{})
    for L in ladders:
        code,kind,tdate=L["code"],L["kind"],L["date"]; lead=(tdate-TODAY).days
        if lead<0: continue
        lhr=(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)+dt.timedelta(seconds=offs.get(code,0))).hour
        realized=(lead==0 and kind=="LOW") or (lead==0 and kind=="HIGH" and lhr>=INTRADAY_HIGH_CUTOFF)
        members=fc[code][kind].get(tdate.isoformat(),[])
        if len(members)<10: continue
        n=len(members); sd=pstdev(members); mean=sum(members)/n
        ov=sum(b["ya"] for b in L["buckets"])-1.0
        wsum=sum((b["yb"]+b["ya"])/2 for b in L["buckets"])
        mkt_mean=(sum(((b["yb"]+b["ya"])/2)*(bucket_rep(b) or 0) for b in L["buckets"])/wsum) if wsum else mean
        offset=mean-mkt_mean; biased=abs(offset)>BIAS_TOL
        pbk,ppl=[],[]
        for b in L["buckets"]:
            mp=sum(1 for v in members if in_bucket(v,b))/n; mid=(b["yb"]+b["ya"])/2
            cost=(b["ya"]-b["yb"])/2+fee(mid)+0.01; edge=mp-mid
            if edge>0: side,entry,net="Buy YES",b["ya"],edge-cost
            else:      side,entry,net="Buy NO",round(1-b["yb"],2),(-edge)-cost
            base=((not biased) and (not realized) and net>=PLAY_NET_EDGE and b["oi"]>=MIN_OI
                  and lead<=MAX_LEAD_DAYS and 0.02<mid<0.98)
            tier=eff=None; units=0.0; p_win=None; size_reason=""
            if base:
                tier,eff,_=tier_for(net,lead,sd,skill.get((code,kind)))
                p_win = mp if side=="Buy YES" else 1-mp
                units, size_reason = size_play(tier, p_win)
            is_play=base and units>0
            rec={"code":code,"label":CITIES[code][3],"kind":kind,"date":tdate,"lead":lead,
                 "bucket":b["sub"],"ticker":b["ticker"],"mid":mid,"mp":mp,"edge":edge,"side":side,
                 "entry":entry,"net":net,"oi":b["oi"],"sd":sd,"mean":mean,"overround":ov,
                 "offset":offset,"biased":biased,"realized":realized,"tier":tier,"eff":eff,"p_win":p_win,"size_reason":size_reason,
                 "units":units,"stake":round(units*BASE_UNIT_USD,2) if units else None}
            rows.append(rec)
            if is_play: plays.append(rec)
            pbk.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"floor":b["floor"],
                        "cap":b["cap"],"stype":b["stype"],"mp":mp,"mid":mid,"yb":b["yb"],"ya":b["ya"],"oi":b["oi"]})
            if is_play:
                ppl.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"side":side,
                            "entry":entry,"net":net,"tier":tier,"units":units,
                            "stake":round(units*BASE_UNIT_USD,2),"p_win":p_win,"mp":mp,"mid":mid})
        if not realized:
            preds[f"{code}|{kind}|{tdate.isoformat()}"]={"code":code,"kind":kind,"target":tdate.isoformat(),
                "event_ticker":L["event_ticker"],"logged_at":dt.datetime.now().isoformat(timespec="minutes"),
                "lead":lead,"mean":mean,"sd":sd,"biased":biased,"offset":offset,"buckets":pbk,"plays":ppl}
    plays.sort(key=lambda r:(TIER_RANK.get(r.get("tier"),9),-r.get("eff",0)))
    return ladders,rows,plays

# --------------------------- resolution ----------------------------
def resolve_pending(state):
    preds=state.get("predictions",{}); resolved=state.setdefault("resolved",[])
    due={k:p for k,p in preds.items() if dt.date.fromisoformat(p["target"])<=TODAY-dt.timedelta(days=1)}
    n=0
    for k,p in list(due.items()):
        settled=fetch_settled_event(p["event_ticker"]); time.sleep(0.1)
        if not settled: continue                      # not settled yet; retry next run
        exps=[v for _,v in settled.values() if v is not None]
        actual=exps[0] if exps else None
        rec={"code":p["code"],"kind":p["kind"],"target":p["target"],"lead":p["lead"],
             "actual":round_nws(actual) if actual is not None else None,
             "mean":p["mean"],"bias":(p["mean"]-actual) if actual is not None else None,
             "buckets":[],"plays":[]}
        ok=True
        for b in p["buckets"]:
            res=settled.get(b["ticker"])
            if not res or res[0] not in ("yes","no"): ok=False; continue
            hit=1 if res[0]=="yes" else 0
            rec["buckets"].append({"mp":b["mp"],"mid":b["mid"],"hit":hit})
        for pl in p.get("plays",[]):
            res=settled.get(pl["ticker"])
            if not res or res[0] not in ("yes","no"): continue
            won=(res[0]=="yes") if pl["side"]=="Buy YES" else (res[0]=="no")
            entry=pl["entry"]; contracts=int(pl["stake"]//entry) if entry>0 else 0
            pnl=contracts*((1-entry) if won else -entry)-contracts*fee(entry)
            bb=next((b for b in p["buckets"] if b["ticker"]==pl["ticker"]),None)
            mv=margin_deg(actual,bb,won) if (bb and actual is not None) else None
            rec["plays"].append({"code":p["code"],"kind":p["kind"],"target":p["target"],"sub":pl["sub"],
                                 "side":pl["side"],"entry":entry,"tier":pl["tier"],"units":pl["units"],
                                 "stake":pl["stake"],"contracts":contracts,"won":won,"pnl":round(pnl,2),
                                 "margin":mv,"actual":rec["actual"],"mp":pl["mp"],"mid":pl["mid"]})
        if ok and rec["buckets"]:
            resolved.append(rec); del preds[k]; n+=1
    print(f"Resolved {n} events from Kalshi settlement.")
    return n

# --------------------------- reporting -----------------------------
def compute_report(state):
    resolved=state.get("resolved",[])
    bk=[b for r in resolved for b in r["buckets"]]
    pls=[pl for r in resolved for pl in r["plays"]]
    rep={"n_events":len(resolved),"n_buckets":len(bk),"plays":pls}
    if bk:
        rep["brier_model"]=sum((b["mp"]-b["hit"])**2 for b in bk)/len(bk)
        rep["brier_market"]=sum((b["mid"]-b["hit"])**2 for b in bk)/len(bk)
    # calibration bins
    bins=[]
    for lo in [i/10 for i in range(10)]:
        sel=[b for b in bk if lo<=b["mp"]<lo+0.1]
        if sel: bins.append((lo,len(sel),sum(b["mp"] for b in sel)/len(sel),sum(b["hit"] for b in sel)/len(sel)))
    rep["bins"]=bins
    # per-city bias
    cb=defaultdict(list)
    for r in resolved:
        if r["bias"] is not None: cb[(r["code"],r["kind"])].append(r["bias"])
    rep["city_bias"]=sorted(((CITIES[c][3],k,sum(v)/len(v),len(v)) for (c,k),v in cb.items()),key=lambda x:-abs(x[2]))
    # play performance
    if pls:
        wins=sum(1 for p in pls if p["won"]); tot=len(pls); pnl=sum(p["pnl"] for p in pls)
        staked=sum(p["contracts"]*p["entry"] for p in pls)
        net_units=sum((p["units"] if p["won"] else -p["units"])*0+ (p["pnl"]/BASE_UNIT_USD) for p in pls)
        rep["pnl"]={"n":tot,"wins":wins,"winrate":wins/tot,"net":pnl,"staked":staked,
                    "roi":(pnl/staked if staked else 0),"net_units":pnl/BASE_UNIT_USD,
                    "avg_margin":sum(p["margin"] for p in pls if p["margin"] is not None)/max(1,sum(1 for p in pls if p["margin"] is not None))}
        # by city
        byc=defaultdict(lambda:{"n":0,"w":0,"pnl":0.0})
        for p in pls:
            a=byc[p["code"]]; a["n"]+=1; a["w"]+=1 if p["won"] else 0; a["pnl"]+=p["pnl"]
        rep["by_city"]=sorted(((CITIES[c][3],v["n"],v["w"],v["pnl"]) for c,v in byc.items()),key=lambda x:-x[3])
        # by unit
        byu=defaultdict(lambda:{"n":0,"w":0,"pnl":0.0})
        for p in pls:
            a=byu[p["units"]]; a["n"]+=1; a["w"]+=1 if p["won"] else 0; a["pnl"]+=p["pnl"]
        rep["by_unit"]=sorted(((u,v["n"],v["w"],v["pnl"]) for u,v in byu.items()),key=lambda x:-x[0])
        # cumulative series (in $), ordered by target date
        ser=[]; run=0.0
        for p in sorted(pls,key=lambda x:x["target"]):
            run+=p["pnl"]; ser.append(run)
        rep["cum"]=ser
        rep["recent"]=sorted(pls,key=lambda x:x["target"],reverse=True)
    return rep

# ----------------------------- render ------------------------------
CSS=open(os.path.join(HERE,"_style.css")).read() if os.path.exists(os.path.join(HERE,"_style.css")) else ""
if not CSS:
 CSS=""":root{--bg:#0d1014;--panel:#14181e;--line:#232a33;--tx:#e7ecf2;--mut:#8b97a6;--dim:#4d5765;--teal:#5ad1c8;--up:#46c08a;--dn:#e3a23c;--red:#e25a4d;--gold:#e8c468}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font-family:Inter,system-ui,sans-serif;font-size:14px;line-height:1.45}
header{position:sticky;top:0;z-index:5;background:var(--bg);padding:16px 16px 8px;border-bottom:1px solid var(--line)}
.hd,.wrap{max-width:1120px;margin:0 auto}.wrap{padding:0 16px 64px}
.brand{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.brand h1{font-size:18px;font-weight:600;margin:0}.brand .dot{color:var(--teal)}
.brand .sub{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mut)}
.nav{display:flex;gap:8px;margin-top:10px}.nav a{text-decoration:none;font-size:13px;padding:7px 13px;border-radius:8px;border:1px solid var(--line);color:var(--mut);background:var(--panel)}
.nav a.on{color:#0d1014;background:var(--teal);border-color:var(--teal);font-weight:600}
.strip{margin-top:9px;display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.chip{font-family:'IBM Plex Mono',monospace;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--panel)}.chip b{color:var(--tx)}
.chip.pos b{color:var(--up)}.chip.neg b{color:var(--red)}
.note{margin:12px 0;padding:11px 13px;border:1px solid var(--line);border-left:2px solid var(--teal);border-radius:8px;background:var(--panel);color:var(--mut);font-size:12.5px}.note b{color:var(--tx)}
h2.sec{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:20px 0 8px}
table{width:100%;border-collapse:collapse}th{text-align:left;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--dim);font-weight:500;padding:8px 10px;border-bottom:1px solid var(--line)}
th.n,td.n{text-align:right;font-family:'IBM Plex Mono',monospace}td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}tbody tr:hover{background:var(--panel)}
.mk .mt{font-weight:500}.mk .me{font-size:11.5px;color:var(--dim);margin-top:2px}td.model{color:var(--teal)}td.edge{color:var(--up);font-weight:600}
.pl{font-family:'IBM Plex Mono',monospace;font-size:12.5px;white-space:nowrap}.up{color:var(--up)}.dn{color:var(--dn)}.dim{color:var(--dim)}.red{color:var(--red)}
.unit{font-family:'IBM Plex Mono',monospace;font-weight:700;font-size:12px;padding:2px 9px;border-radius:6px;display:inline-block;min-width:44px;text-align:center}
.u2{background:var(--gold);color:#0d1014}.u15{background:rgba(70,192,138,.2);color:var(--up);border:1px solid rgba(70,192,138,.4)}.u1{background:rgba(227,162,60,.16);color:var(--dn)}.u0{background:rgba(125,139,156,.14);color:var(--mut)}
tr.play td{background:rgba(70,192,138,.05)}
.rating{display:flex;align-items:center;gap:14px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:8px 0}
.rating .big{font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:700;line-height:1;padding:8px 14px;border-radius:10px}.rating .txt{color:var(--mut);font-size:13px}.rating .txt b{color:var(--tx)}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.kbox{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:12px 16px;min-width:120px}
.kbox .v{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600}.kbox .l{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
.tag{font-family:'IBM Plex Mono',monospace;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:5px}.c-hi{background:rgba(70,192,138,.14);color:var(--up)}.c-md{background:rgba(227,162,60,.14);color:var(--dn)}.c-lo{background:rgba(125,139,156,.12);color:var(--mut)}
.block{margin:14px 0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}.bh{padding:10px 12px;font-weight:600;border-bottom:1px solid var(--line)}.bm{padding:6px 12px;font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--mut);border-bottom:1px solid var(--line)}.block td,.block th{padding:8px 12px}
.tabs{display:flex;gap:4px;overflow-x:auto;padding:6px 0}.tab{flex:0 0 auto;background:transparent;border:1px solid transparent;color:var(--mut);font:inherit;font-size:13px;padding:7px 12px;border-radius:8px;cursor:pointer;white-space:nowrap}.tab:hover{color:var(--tx);background:var(--panel)}.tab.active{color:var(--tx);background:var(--panel);border-color:var(--line)}.panel{display:none}.panel.active{display:block}
.empty{padding:20px;border:1px dashed var(--line);border-radius:10px;color:var(--mut);background:var(--panel)}.empty b{color:var(--tx)}
.pcard{border:1px solid var(--line);border-radius:12px;background:var(--panel);margin-top:10px;overflow:hidden}
.pcard.side-yes{border-left:4px solid var(--up)}.pcard.side-no{border-left:4px solid var(--red)}
.ptop{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px}
.pcity{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.prange{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:700;margin-top:3px;line-height:1.1}
.pside{font-family:'IBM Plex Mono',monospace;font-weight:800;font-size:24px;padding:8px 14px;border-radius:10px;min-width:78px;text-align:center;line-height:1}
.pside .psub{font-size:12px;font-weight:600;margin-top:3px;opacity:.85}
.sb-yes{background:var(--up);color:#07130d}.sb-no{background:var(--red);color:#1c0707}
.pbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:0 16px 8px}
.pmoney{font-family:'IBM Plex Mono',monospace;font-size:14px;font-weight:600}
.pwin{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--mut)}
.pflag{font-size:11.5px;font-weight:600;color:var(--dn);background:rgba(227,162,60,.14);padding:2px 8px;border-radius:6px}
.pdata{padding:8px 16px;font-size:11.5px;color:var(--dim);border-top:1px solid var(--line)}
svg{max-width:100%;height:auto}.card{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px 16px;margin:10px 0}"""

def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def pct(x): return "%.0f%%"%(x*100)
def fmt_oi(o): o=o or 0; return "%.0fk"%(o/1000) if o>=1000 else "%.0f"%o
def _lead(l): return {0:"resolves today",1:"tomorrow"}.get(l,"%d days out"%l)
def _edge(e):
    if e>0: return '<span class="up">+%s</span>'%pct(e)
    if e<0: return '<span class="dn">%s</span>'%pct(e)
    return '<span class="dim">0%</span>'
def unit_badge(u):
    if u>=2: return '<span class="unit u2">2u</span>'
    if u>=1.5: return '<span class="unit u15">1.5u</span>'
    if u>=1: return '<span class="unit u1">1u</span>'
    return '<span class="unit u0">no bet</span>'
def head(active,updated,extra=""):
    a=lambda p:'on' if active==p else ''
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Kalshi Weather Edge</title>"
      "<link rel='preconnect' href='https://fonts.googleapis.com'>"
      "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>"
      f"<style>{CSS}</style></head><body><header><div class='hd'>"
      "<div class='brand'><h1>Kalshi Weather Edge<span class='dot'> .</span></h1>"
      f"<span class='sub'>{updated} &middot; ensemble {'+'.join(ENSEMBLE_MODELS)} &middot; settled by Kalshi</span></div>"
      f"<div class='nav'><a class='{a('bets')}' href='index.html'>Today's bets</a>"
      f"<a class='{a('results')}' href='results.html'>Results tracker</a></div>{extra}</div></header><div class='wrap'>")

def svg_line(vals,w=680,h=170,pad=26):
    if not vals: return ""
    lo=min(0,min(vals)); hi=max(0,max(vals)); rng=(hi-lo) or 1
    def X(i): return pad+(w-2*pad)*(i/max(1,len(vals)-1))
    def Y(v): return h-pad-(h-2*pad)*((v-lo)/rng)
    pts=" ".join(f"{X(i):.1f},{Y(v):.1f}" for i,v in enumerate(vals))
    zero=Y(0)
    return (f"<svg viewBox='0 0 {w} {h}'><line x1='{pad}' y1='{zero:.1f}' x2='{w-pad}' y2='{zero:.1f}' "
            f"stroke='#232a33'/><polyline points='{pts}' fill='none' stroke='#5ad1c8' stroke-width='2'/>"
            f"<text x='{pad}' y='14' fill='#8b97a6' font-size='11' font-family=monospace>cumulative $ P&amp;L</text></svg>")

def svg_bars(items,w=680,bar=26,gap=10,pad=90):
    if not items: return ""
    h=pad and len(items)*(bar+gap)+16
    mx=max(abs(v) for _,v in items) or 1
    out=[f"<svg viewBox='0 0 {w} {h}'>"]
    for i,(lab,v) in enumerate(items):
        y=8+i*(bar+gap); wpx=(w-pad-20)*(abs(v)/mx); col="#46c08a" if v>=0 else "#e25a4d"
        out.append(f"<text x='0' y='{y+bar/2+4:.0f}' fill='#e7ecf2' font-size='12'>{esc(lab)[:16]}</text>")
        out.append(f"<rect x='{pad}' y='{y}' width='{wpx:.0f}' height='{bar}' rx='4' fill='{col}'/>")
        out.append(f"<text x='{pad+wpx+6:.0f}' y='{y+bar/2+4:.0f}' fill='#8b97a6' font-size='11' font-family=monospace>{v:+.2f}</text>")
    out.append("</svg>"); return "".join(out)

RATING_TXT={"2u":"an exceptional day. A proven-city edge worth your max size.",
            "1.5u":"a strong day. Solid, higher-probability edges.",
            "1u":"a decent day. Real but modest, or capped longshots.",
            "NO BET":"a sit-out day. Nothing clears the bar; the right move is no bet."}
RATING={"S":("2u","an exceptional day. A proven-city edge worth your max size."),
        "A":("1.5u","a strong day. Solid edges, good conditions."),
        "B":("1u","a decent day. Real but modest edges."),
        None:("NO BET","a sit-out day. Nothing clears the bar; the right move is no bet.")}

def render_bets(rows,plays,updated):
    best_u=max((p["units"] for p in plays),default=0)
    rlab="2u" if best_u>=2 else "1.5u" if best_u>=1.5 else "1u" if best_u>=1 else "NO BET"
    rtxt=RATING_TXT[rlab]
    ucls={"2u":"u2","1.5u":"u15","1u":"u1","NO BET":"u0"}[rlab]
    counts=defaultdict(int)
    for p in plays: counts[p["units"]]+=1
    cstr=", ".join(f'{counts[u]}x {unit_str(u)}' for u in sorted(counts,reverse=True)) or "none"
    if plays:
        ptab=""
        for r in plays[:30]:
            yes=r["side"]=="Buy YES"
            sc="side-yes" if yes else "side-no"; sb="sb-yes" if yes else "sb-no"; word="YES" if yes else "NO"
            city=esc(r["label"].split(" (")[0]); mk="Highest temp" if r["kind"]=="HIGH" else "Lowest temp"
            pw=("win prob %.0f%%"%(r["p_win"]*100)) if r.get("p_win") is not None else ""
            flag=(f'<span class="pflag">{esc(r["size_reason"])}</span>') if r.get("size_reason") else ""
            ptab+=(f'<div class="pcard {sc}"><div class="ptop">'
                   f'<div><div class="pcity">{city} &middot; {mk} &middot; {r["date"].strftime("%b %d")}</div>'
                   f'<div class="prange">{esc(r["bucket"])}</div></div>'
                   f'<div class="pside {sb}">{word}<div class="psub">{r["entry"]*100:.0f}\u00a2</div></div></div>'
                   f'<div class="pbar">{unit_badge(r["units"])}<span class="pmoney">${r["stake"]:.0f} stake</span>'
                   f'<span class="pwin">{pw}</span>{flag}</div>'
                   f'<div class="pdata">model {pct(r["mp"])} &middot; market {pct(r["mid"])} &middot; '
                   f'edge +{pct(abs(r["edge"]))} &middot; net +{r["net"]*100:.0f}\u00a2 &middot; OI {fmt_oi(r["oi"])}</div></div>')
    else:
        ptab=('<div class="empty"><b>No bets today.</b> Run in the morning; same-day lows are already '
              'realized and same-day highs after ~2pm too. Realized / offset ladders under By city are '
              'shown to illustrate the comparison, not to bet.</div>')
    # by city
    bycity=defaultdict(list)
    for r in rows: bycity[r["code"]].append(r)
    order=sorted(bycity,key=lambda c:-max((x["net"] for x in bycity[c]),default=0))
    ctabs=cpan=""
    for code in order:
        cid="c"+code; np=sum(1 for r in bycity[code] if r.get("stake"))
        ctabs+=f'<button class="tab" data-t="{cid}">{esc(CITIES[code][3])}{(" ("+str(np)+")") if np else ""}</button>'
        sub=defaultdict(list)
        for r in bycity[code]: sub[(r["kind"],r["date"])].append(r)
        blocks=""
        for (kind,d),rs in sorted(sub.items(),key=lambda kv:(kv[0][1],kv[0][0])):
            r0=rs[0]
            rt=('<span class="tag c-lo">realized</span>' if r0["realized"] else
                (f'<span class="tag c-md">offset {r0["offset"]:+.1f}\u00b0</span>' if r0["biased"] else
                 '<span class="tag c-hi">live</span>'))
            hd=f'{"High" if kind=="HIGH" else "Low"} &middot; {d.strftime("%a %b %d")} {rt}'
            mt=f'forecast {r0["mean"]:.0f}\u00b0 \u00b1{r0["sd"]:.1f}\u00b0 &middot; {_lead(r0["lead"])} &middot; model\u2212mkt {r0["offset"]:+.1f}\u00b0'
            tr=""
            for r in sorted(rs,key=lambda x:-x["mp"]):
                pcell=(f'{unit_badge(r["units"])} {r["side"]} @ {r["entry"]*100:.0f}\u00a2' if r.get("stake") else '<span class="dim">\u00b7</span>')
                tr+=(f'<tr><td>{esc(r["bucket"])}</td><td class="n">{pct(r["mid"])}</td><td class="n model">{pct(r["mp"])}</td>'
                     f'<td class="n">{_edge(r["edge"])}</td><td class="n">{fmt_oi(r["oi"])}</td><td class="pl">{pcell}</td></tr>')
            blocks+=(f'<div class="block"><div class="bh">{hd}</div><div class="bm">{mt}</div>'
                     f'<table><thead><tr><th>Bucket</th><th class="n">Mkt</th><th class="n">Model</th>'
                     f'<th class="n">Edge</th><th class="n">OI</th><th>Play</th></tr></thead><tbody>{tr}</tbody></table></div>')
        cpan+=f'<div class="panel" id="{cid}">{blocks}</div>'
    html=(head("bets",updated)+
      "<div class='note'><b>Confidence = size.</b> Each play is sized 2u / 1.5u / 1u from a score that blends "
      "net edge, forecast lead, ensemble tightness, and that city's track record. You cannot get a 2u until a "
      "city has proven it beats the market on the Results tab. Sizes are tunable as we calibrate.</div>"
      f"<h2 class='sec'>Today</h2><div class='rating'><div class='big unit {ucls}'>{rlab}</div>"
      f"<div class='txt'>Today is <b>{rtxt}</b><br>Plays: {cstr}.</div></div>"+ptab+
      "<h2 class='sec'>By city</h2><div class='tabs'>"+ctabs+"</div>"+cpan+
      "<script>document.querySelectorAll('.tab').forEach(function(b){b.onclick=function(){"
      "document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));"
      "document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));"
      "b.classList.add('active');document.getElementById(b.dataset.t).classList.add('active');};});"
      "var f=document.querySelector('.tab');if(f){f.classList.add('active');document.getElementById(f.dataset.t).classList.add('active');}</script>"
      "</div></body></html>")
    with open(os.path.join(OUT_DIR,"index.html"),"w",encoding="utf-8") as fp: fp.write(html)

def unit_str(u): return "2u" if u>=2 else "1.5u" if u>=1.5 else "1u" if u>=1 else "0u"

def render_results(rep,updated):
    if not rep.get("plays"):
        body=('<div class="empty"><b>No resolved bets yet.</b> This tracker fills in automatically once your '
              'logged plays settle on Kalshi. Every run pulls Kalshi\'s official result and settled temperature, '
              'marks each bet win/loss, and updates the charts, per-city and per-unit tables, and margins below. '
              'Give it a couple weeks of morning runs.</div>')
        html=head("results",updated)+"<h2 class='sec'>Results tracker</h2>"+body+"</div></body></html>"
        with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html); return
    p=rep["pnl"]; cls="up" if p["net"]>=0 else "red"
    kpis=("<div class='kpi'>"
      f"<div class='kbox'><div class='v {cls}'>{p['net_units']:+.1f}u</div><div class='l'>net units</div></div>"
      f"<div class='kbox'><div class='v {cls}'>${p['net']:+.2f}</div><div class='l'>net $</div></div>"
      f"<div class='kbox'><div class='v'>{p['winrate']*100:.0f}%</div><div class='l'>win rate ({p['wins']}/{p['n']})</div></div>"
      f"<div class='kbox'><div class='v {cls}'>{p['roi']*100:+.1f}%</div><div class='l'>ROI</div></div>"
      f"<div class='kbox'><div class='v'>{p['avg_margin']:+.1f}\u00b0</div><div class='l'>avg margin</div></div>"
      f"<div class='kbox'><div class='v'>{rep['n_events']}</div><div class='l'>events</div></div></div>")
    chart=f"<div class='card'>{svg_line(rep.get('cum',[]))}</div>"
    # by city
    ct="".join(f'<tr><td>{esc(l)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
               f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">${pn:+.2f}</td></tr>'
               for l,n,w,pn in rep.get("by_city",[]))
    city_bars=svg_bars([(l,pn) for l,n,w,pn in rep.get("by_city",[])])
    # by unit
    ut="".join(f'<tr><td>{unit_str(u)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
               f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">${pn:+.2f}</td></tr>'
               for u,n,w,pn in rep.get("by_unit",[]))
    # brier
    brier=""
    if rep.get("brier_model") is not None:
        bm,bkk=rep["brier_model"],rep["brier_market"]; v="up" if bm<bkk else "red"
        brier=("<div class='kpi'>"
          f"<div class='kbox'><div class='v'>{bm:.3f}</div><div class='l'>Brier model</div></div>"
          f"<div class='kbox'><div class='v'>{bkk:.3f}</div><div class='l'>Brier market</div></div>"
          f"<div class='kbox'><div class='v {v}'>{(bkk-bm):+.3f}</div><div class='l'>edge (lower wins)</div></div></div>")
    # raw
    raw="".join(f'<tr><td>{esc(CITIES[r["code"]][3])}</td><td>{"H" if r["kind"]=="HIGH" else "L"} {r["target"][5:]}</td>'
                f'<td>{esc(r["sub"])}</td><td>{unit_str(r["units"])}</td><td class="pl">{r["side"]}@{r["entry"]*100:.0f}\u00a2</td>'
                f'<td class="n">{r["actual"]}\u00b0</td><td>{"WON" if r["won"] else "LOST"}</td>'
                f'<td class="n">{("%+.1f"%r["margin"]) if r["margin"] is not None else DOT}\u00b0</td>'
                f'<td class="n {"up" if r["pnl"]>=0 else "red"}">${r["pnl"]:+.2f}</td></tr>'
                for r in rep.get("recent",[])[:60])
    html=(head("results",updated)+
      "<h2 class='sec'>Performance</h2>"+kpis+chart+brier+
      "<h2 class='sec'>By city</h2><div class='card'>"+city_bars+"</div>"
      "<table><thead><tr><th>City</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+ct+"</tbody></table>"
      "<h2 class='sec'>By unit size</h2>"
      "<table><thead><tr><th>Size</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+ut+"</tbody></table>"
      "<h2 class='sec'>Every resolved bet</h2>"
      "<table><thead><tr><th>City</th><th>Mkt</th><th>Bucket</th><th>Size</th><th>Bet</th><th class='n'>Actual</th><th>Result</th><th class='n'>Margin</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+raw+"</tbody></table>"
      "</div></body></html>")
    with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html)

# ------------------------------ main ------------------------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH,encoding="utf-8") as f: return json.load(f)
        except Exception:
            try: os.rename(STATE_PATH,STATE_PATH+".bak")
            except Exception: pass
    return {"predictions":{},"resolved":[]}

def save_state(s):
    tmp=STATE_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(s,f,indent=1,default=str)
    os.replace(tmp,STATE_PATH)

def main():
    os.makedirs(OUT_DIR,exist_ok=True)
    print("="*56); print("Kalshi Weather Edge  -",dt.datetime.now().strftime("%Y-%m-%d %H:%M")); print("="*56)
    state=load_state()
    resolve_pending(state)
    ladders,rows,plays=score(state)
    rep=compute_report(state)
    save_state(state)
    updated=dt.datetime.now().astimezone().strftime("%b %d %Y, %I:%M %p")
    render_bets(rows,plays,updated); render_results(rep,updated)
    print(f"\nPlays today: {len(plays)} | resolved: {rep.get('n_events',0)}")
    if rep.get("pnl"): print(f"Paper P&L: ${rep['pnl']['net']:+.2f} ({rep['pnl']['net_units']:+.1f}u, {rep['pnl']['wins']}/{rep['pnl']['n']})")
    print("Dashboards ->",OUT_DIR)
    if os.environ.get("CI")!="true":
        try: webbrowser.open("file://"+os.path.join(OUT_DIR,"index.html"))
        except Exception: pass

if __name__=="__main__":
    try: main()
    except Exception as e:
        import traceback; traceback.print_exc(); print("ERROR:",e)
    if os.environ.get("CI")!="true" and sys.stdin.isatty():
        try: input("\nPress Enter to close...")
        except EOFError: pass
