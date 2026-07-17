#!/usr/bin/env python3
"""
Nimbus  -  Kalshi weather edge, GitHub-deployable
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

import json, math, os, sys, time, webbrowser, hashlib
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
# Edge-band base sizing (net edge in probability, after spread+fee). Bigger edge
# earns more size UP TO A POINT: an edge past SUSPECT_EDGE is almost always the
# model being wrong or a thin market, not free money, so we size it DOWN and flag it.
SUSPECT_EDGE  = 0.20     # net edge above this is treated as noise, capped to 1u + flagged
EDGE_2U       = 0.14     # net edge for a 2u ceiling (also needs proven city + win prob >= .55)
EDGE_1_5U     = 0.08     # net edge for a 1.5u ceiling
# Stamp every logged bet so history survives model changes and tunes can be compared.
MODEL_VERSION = "2026-07-13.v13-nowcast-shadow"
# Exposure caps (audit batch 8). Measured before caps: 54.5u staked on a single
# target date against a $500 bankroll, and up to 5 plays stacked on one ladder
# (31 of 44 played events carried 2+), i.e. multiples of one settlement number.
# Cross-city error-sign concordance measured at 51% (effectively independent),
# so the binding correlation lives WITHIN an event and the binding risk is raw
# daily exposure: bootstrap median max drawdown was -$255 (p95 -$461) at the
# uncapped sizing. Best plays (by units, then p_win) fill first; the rest are
# never logged (their counterfactual stays reconstructible from the buckets).
DAILY_UNIT_CAP = 6.0   # total units per TARGET date (FUTURE section 2 guidance)
EVENT_UNIT_CAP = 2.0   # total units riding one ladder / one settlement number
# Pre-scoring integrity GATE (audit item 0.8, owner-approved in batch 7).
# A ladder or city that fails produces NO plays and NO logged prediction: a
# degraded forecast must reach neither the board nor the calibration history.
# Refinement vs the 0.8 draft, documented in HANDOFF v5.8: degraded-data
# records are excluded from LOGGING too, because bias/sigma learned from a
# 1-2 model forecast is not the statistic applied to healthy forecasts.
GATE_MIN_LADDERS = 25   # below this the Kalshi pull is truncated: abort the run
GATE_MIN_MEMBERS = 90   # three healthy models minimum is 92 pooled members
GATE_MIN_MODELS  = 3    # of the 4 ensemble models must have contributed
# Tail humility clamp (audit batch 4). Measured: buckets the model stated at
# 0-2% (avg 0.3%) realized ~6.8% (n=118, Wilson lower bound 3.5%; tail misses
# cluster within busted ladders, so treat the magnitude as directional).
# Gaussian kernel tails are too thin for temperature busts, and a fake NO edge
# on an ultra-thin tail passes the cost gate quietly. For EDGE and p_win the
# model prob is clamped into [TAIL_FLOOR, 1-TAIL_FLOOR]; the displayed and
# logged mp stays RAW so the calibration tables keep seeing the true model.
# Revisit the value at 500+ tail buckets (rule in FUTURE.md section 2b).
TAIL_FLOOR = 0.015
MIN_OI        = 300
PLAY_NET_EDGE = 0.04
MAX_LEAD_DAYS = 4
LEAD_CAP_DAYS = 3        # plays 3+ days out are capped at 1u; forecast skill decays fast
BIAS_TOL      = 2.0
INTRADAY_HIGH_CUTOFF = 14
NOWCAST_MIN_LHR = 9      # nowcast SHADOW snapshots collect no earlier than this local hour (FUTURE 5 stage 1); upper bound is INTRADAY_HIGH_CUTOFF
# Four independent global ensembles pooled: ~143 members (GFS 31, ECMWF 51, ICON 40, GEM 21).
# Multi-model diversity beats more members from one model.
ENSEMBLE_MODELS = ["gfs025", "ecmwf_ifs025", "icon_seamless", "gem_global"]
# Reference point forecasts logged alongside every prediction and NEVER scored:
# NBM is NOAA's station-calibrated National Blend of Models, HRRR the sharpest
# short-lead CONUS model. Their skill vs the pooled ensemble is judged from
# settled results before any blending decision (audit batches 4-5).
REF_MODELS = ["ncep_nbm_conus", "ncep_hrrr_conus"]
# Open-Meteo publishes per-model run metadata at
# api.open-meteo.com/data/{id}/static/meta.json; forecast responses themselves
# carry no run id. Ensemble-API model names map to different metadata ids.
META_IDS = {"gfs025":"ncep_gefs025","ecmwf_ifs025":"ecmwf_ifs025",
            "icon_seamless":"dwd_icon_eps","gem_global":"cmc_gem_geps",
            "ncep_nbm_conus":"ncep_nbm_conus","ncep_hrrr_conus":"ncep_hrrr_conus"}
# --- calibration (learned automatically from settled results) ---
# Kernel dressing: each member is smeared with a Gaussian so 1-degree bucket
# probabilities are smooth instead of noisy member counts. Width is learned per
# city/kind from realized errors (Wang-Bishop second-moment matching), clamped.
DRESS_SIGMA_DEFAULT = 1.1   # deg F, used until a city has enough settled history
DRESS_SIGMA_MIN     = 0.6
DRESS_SIGMA_MAX     = 3.0
# Rolling bias correction: shift members by the negative of the city's recent
# raw forecast bias vs Kalshi settlement, shrunk toward 0 when history is thin.
BIAS_MIN_N    = 5     # settled events needed before any correction applies
BIAS_LOOKBACK = 30    # only the most recent N settlements count (season drift)
BIAS_SHRINK_K = 5     # correction = -mean_bias * n/(n+K)
HICONF_PWIN   = 0.65  # plays with win prob >= this get the high-confidence tag
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
    "HOU":(29.6454,-95.2789,"America/Chicago","Houston (Hobby)"),
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
# ASOS/ICAO station ids for each city's Kalshi settlement station, derived
# from the rules-text CLI products verified 2026-07-04 (audit batch 1, e.g.
# CLIDFW -> KDFW, CLINYC -> KNYC Central Park, CLIHOU -> KHOU Hobby).
# INERT today: this is the prerequisite map for intraday observation
# truncation (nowcasting, FUTURE section 5) via api.weather.gov
# /stations/{id}/observations. Do not guess these; re-verify against
# rules_secondary if Kalshi changes a settlement source.
STATION_IDS={"ATL":"KATL","AUS":"KAUS","BOS":"KBOS","CHI":"KMDW","DAL":"KDFW",
             "DC":"KDCA","DEN":"KDEN","HOU":"KHOU","LAX":"KLAX","LV":"KLAS",
             "MIA":"KMIA","MIN":"KMSP","NOLA":"KMSY","NYC":"KNYC","OKC":"KOKC",
             "PHIL":"KPHL","PHX":"KPHX","SATX":"KSAT","SEA":"KSEA","SFO":"KSFO"}
# Legacy Kalshi series codes that differ from our CITIES keys (NYC's original
# high-temp series is KXHIGHNY, so the code after the prefix is "NY").
SERIES_ALIAS={"NY":"NYC"}
# NWS Climate Reports (the Kalshi settlement source) record the daily high/low in
# Local STANDARD Time year-round. During DST the settlement day therefore runs
# 1:00 AM to 12:59 AM local clock time, not midnight to midnight. We shift hourly
# forecast timestamps back to LST before picking each day's high/low so our "day"
# is the same day Kalshi settles. Standard UTC offsets are fixed per zone (hours):
STD_OFFSET_H={"America/New_York":-5,"America/Chicago":-6,"America/Denver":-7,
              "America/Phoenix":-7,"America/Los_Angeles":-8}

# Config fingerprint (audit batch 12). Every logged record carries an 8-hex
# hash of the behavior knobs, so a knob edited WITHOUT a MODEL_VERSION bump
# still splits cleanly in later analysis instead of silently blending eras.
_KNOB_NAMES=("BANKROLL","BASE_UNIT_USD","UNIT_MAP","WINPROB_CAP","SUSPECT_EDGE",
 "EDGE_2U","EDGE_1_5U","DAILY_UNIT_CAP","EVENT_UNIT_CAP","GATE_MIN_LADDERS",
 "GATE_MIN_MEMBERS","GATE_MIN_MODELS","TAIL_FLOOR","MIN_OI","PLAY_NET_EDGE",
 "MAX_LEAD_DAYS","LEAD_CAP_DAYS","BIAS_TOL","INTRADAY_HIGH_CUTOFF","NOWCAST_MIN_LHR",
 "DRESS_SIGMA_DEFAULT","DRESS_SIGMA_MIN","DRESS_SIGMA_MAX","BIAS_MIN_N",
 "BIAS_LOOKBACK","BIAS_SHRINK_K","HICONF_PWIN","TIER_CUTS","ENSEMBLE_MODELS","REF_MODELS")
CONFIG_HASH=hashlib.sha1(repr([(k,globals()[k]) for k in _KNOB_NAMES if k in globals()]).encode()).hexdigest()[:8]
MON={"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
TODAY=dt.date.today()
DOT="\u00b7"   # middot, kept out of f-string expressions for py3.11 safety
# Client-side staleness guard: the page carries its own build epoch and warns
# when it is more than 16h old. Catches failed scheduled runs AND failed GitHub
# Pages deploys (observed 2026-07-04: Pages served a board one run behind the
# repo, showing a profit that no longer existed). Plain string, not an f-string,
# because the JS braces would need doubling.
STALE_JS=("<div id='stale' style='display:none;background:#2a1a12;color:#e3a23c;"
 "padding:9px 16px;font-size:12.5px;border-bottom:1px solid #3a2a1a'></div>"
 "<script>(function(){var el=document.getElementById('stale');"
 "var h=(Date.now()/1000-%d)/3600.0;if(h>16){el.style.display='block';"
 "el.textContent='Stale board: last successful update was '+Math.round(h)+"
 "' hours ago. A scheduled run or the Pages deploy has not landed; check the repo Actions tab.';}})();</script>")

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
def fee(p):
    """Per-contract taker fee RATE under Kalshi's quadratic schedule
    (fee_type "quadratic", fee_multiplier 1, read live from the series API,
    audit batch 6): 0.07*p*(1-p) dollars. Unrounded here because the cost gate
    consumes it as a rate; the real charge rounds UP to the next cent per TRADE
    and is applied that way in resolve_pending. The old round(...,2) was wrong
    in both directions (undercharged ~0.5c/contract near 30c, overcharged near 50c)."""
    return max(0.07*p*(1-p),0.0)
def pstdev(xs):
    if len(xs)<2: return 0.0
    m=sum(xs)/len(xs); return math.sqrt(sum((x-m)**2 for x in xs)/len(xs))

# --------------------------- data fetch ----------------------------
def _ladder_contiguous(strikes):
    """Structural integrity of one ladder from ALL parsed strikes (before the
    quote filter drops unquoted buckets): exactly one 'less', one 'greater',
    a chained run of 'between's, no gaps or overlaps. Strictly stronger than
    the 0.8 draft's probability-sum test and immune to its false positive
    (an illiquid unquoted tail bucket). A False here means Kalshi changed the
    bucket structure or the parser broke: gate the ladder, touch the code."""
    less=[s for s in strikes if s[0]=="less"]; grt=[s for s in strikes if s[0]=="greater"]
    bet=sorted([s for s in strikes if s[0]=="between"],key=lambda s:(s[1] if s[1] is not None else -1e9))
    if len(less)!=1 or len(grt)!=1 or not bet: return False
    try:
        if less[0][2]!=bet[0][1]: return False              # less-than C meets between starting at C
        for a,b in zip(bet,bet[1:]):
            if b[1]!=a[2]+1: return False                   # betweens chain with step 1
        if grt[0][1]!=bet[-1][2]: return False              # greater-than F meets between ending at F
    except TypeError:
        return False
    return True

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
        # Two ticker generations coexist on Kalshi: newer cities use KXHIGHT/KXLOWT,
        # the original cities still use legacy KXHIGH/KXLOW (no T), and legacy NYC
        # is "NY". Matching only KXHIGHT* silently dropped 7 of 20 HIGH ladders
        # (AUS, CHI, DEN, LAX, MIA, NYC, PHIL), including the most liquid ones.
        # Non-weather KXHIGH* series fall out at the CITIES membership check.
        if   ser.startswith("KXHIGHT"): kind,code="HIGH",ser[7:]
        elif ser.startswith("KXLOWT"):  kind,code="LOW",ser[6:]
        elif ser.startswith("KXHIGH"):  kind,code="HIGH",ser[6:]
        elif ser.startswith("KXLOW"):   kind,code="LOW",ser[5:]
        else: continue
        code=SERIES_ALIAS.get(code,code)
        if code not in CITIES: continue
        et=e.get("event_ticker",""); parts=et.split("-")
        tdate=parse_date_code(parts[1]) if len(parts)>1 else None
        if not tdate: continue
        bks=[]; raw_strikes=[]
        for m in e.get("markets",[]):
            raw_strikes.append((m.get("strike_type"),fnum(m.get("floor_strike")),fnum(m.get("cap_strike"))))
            yb,ya=fnum(m.get("yes_bid_dollars")),fnum(m.get("yes_ask_dollars"))
            if yb is None or ya is None: continue
            bks.append({"ticker":m.get("ticker"),"floor":fnum(m.get("floor_strike")),
                        "cap":fnum(m.get("cap_strike")),"stype":m.get("strike_type"),
                        "sub":m.get("yes_sub_title") or "","yb":yb,"ya":ya,
                        "oi":fnum(m.get("open_interest_fp"),0) or 0})
        if bks: out.append({"code":code,"kind":kind,"date":tdate,"event_ticker":et,"buckets":bks,
                            "structure_ok":_ladder_contiguous(raw_strikes)})
    print(f"  found {len(out)} city/day ladders")
    if len(out)<GATE_MIN_LADDERS:
        print(f"FATAL (gate): only {len(out)} ladders returned, below GATE_MIN_LADDERS={GATE_MIN_LADDERS}."
              " A truncated or empty market universe must not publish as a quiet day.")
        sys.exit(2)
    return out

def fetch_members(lat,lon,tz):
    """Pool ensemble members across models. Daily highs/lows are taken over the
    NWS Climate Report day (Local Standard Time), not the local clock day, because
    that is the window Kalshi settles on. During DST that means shifting every
    timestamp back one hour before grouping by date."""
    highs,lows,offset={},{},0
    permodel={}
    std_off=STD_OFFSET_H.get(tz,0)*3600
    for model in ENSEMBLE_MODELS:
        u=(f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m&models={model}&temperature_unit=fahrenheit"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=10")
        d=fget(u)
        if not d: continue
        offset=d.get("utc_offset_seconds",offset)
        dst_shift=dt.timedelta(seconds=(offset-std_off))  # 1h during DST, 0 in winter
        h=d.get("hourly",{}); times=h.get("time",[])
        # precompute the LST date string for each timestamp once per model
        lst_days=[]
        for t in times:
            try:
                lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
            except ValueError:
                lst_days.append(t[:10])
        mh,ml={},{}
        for k in [k for k in h if k.startswith("temperature_2m")]:
            dv={}
            for day,v in zip(lst_days,h[k]):
                if v is not None: dv.setdefault(day,[]).append(v)
            for day,vs in dv.items():
                if vs:
                    hv,lv=max(vs),min(vs)
                    highs.setdefault(day,[]).append(hv); lows.setdefault(day,[]).append(lv)
                    mh.setdefault(day,[]).append(hv);   ml.setdefault(day,[]).append(lv)
        permodel[model]={"hi":mh,"lo":ml}
        time.sleep(0.2)
    return highs,lows,offset,permodel

def fetch_ref(lat,lon,tz):
    """Reference point forecasts (NBM + HRRR) as CLI-day max/min per target date,
    same LST windowing as the ensemble. Logged for skill comparison only; these
    values never touch scoring, sizing, or the guards."""
    u=(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       f"&hourly=temperature_2m&models={','.join(REF_MODELS)}"
       f"&temperature_unit=fahrenheit&timezone={urllib.parse.quote(tz)}&forecast_days=3")
    d=fget(u,tries=2)
    out={}
    if not d: return out
    std_off=STD_OFFSET_H.get(tz,0)*3600
    dst_shift=dt.timedelta(seconds=(d.get("utc_offset_seconds",0)-std_off))
    h=d.get("hourly",{}); times=h.get("time",[])
    lst_days=[]
    for t in times:
        try: lst_days.append((dt.datetime.fromisoformat(t)-dst_shift).date().isoformat())
        except ValueError: lst_days.append(t[:10])
    for m in REF_MODELS:
        k="temperature_2m_"+m
        if k not in h: k="temperature_2m" if len(REF_MODELS)==1 else None
        if not k or k not in h: continue
        dv={}
        for day,v in zip(lst_days,h[k]):
            if v is not None: dv.setdefault(day,[]).append(v)
        out[m]={day:{"hi":round(max(vs),1),"lo":round(min(vs),1),"nh":len(vs)} for day,vs in dv.items()}
    return out

def fetch_run_meta():
    """Init time of the newest model run Open-Meteo is serving, per model.
    This is the audit's forecast-provenance stamp: responses carry no run id,
    so the metadata endpoint is the only honest 'which run made this' record."""
    out={}
    for name,mid in META_IDS.items():
        d=fget(f"https://api.open-meteo.com/data/{mid}/static/meta.json",tries=1)
        t=(d or {}).get("last_run_initialisation_time")
        if t:
            out[name]=dt.datetime.fromtimestamp(t,dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return out

def _pm_summary(pm,kind,day):
    """Per-model member count/mean/sd of the RAW daily extreme for one city/kind/day.
    Food for the provider-weighting decision (audit batch 5); display-free."""
    key="hi" if kind=="HIGH" else "lo"
    out={}
    for m,d in (pm or {}).items():
        vs=(d.get(key) or {}).get(day) or []
        if vs: out[m]={"n":len(vs),"mean":round(sum(vs)/len(vs),2),"sd":round(pstdev(vs),2)}
    return out

def _ref_for(ref,kind,day):
    """NBM/HRRR value for this city/kind/day, only when hourly coverage is real."""
    out={}
    for m,days in (ref or {}).items():
        d=days.get(day)
        if d and d.get("nh",0)>=18:
            out["nbm" if "nbm" in m else "hrrr"]=d["hi"] if kind=="HIGH" else d["lo"]
    return out

def fetch_settled_event(event_ticker):
    """Return {ticker: (result, exp_value)} for settled markets of an event."""
    d=fget(f"{KBASE}/markets?event_ticker={event_ticker}&status=settled&limit=100")
    out={}
    if d:
        for m in d.get("markets",[]):
            out[m.get("ticker")]=(m.get("result"), fnum(m.get("expiration_value")))
    return out

# --------------------------- calibration ---------------------------
SQRT2=math.sqrt(2.0)
def _phi(z): return 0.5*(1.0+math.erf(z/SQRT2))

def _wilson(k,n,z=1.96):
    """Wilson 95% interval for a binomial proportion: the honest error bars for
    small-n calibration bins (audit batch 9; plain +-1/sqrt(n) lies at the edges)."""
    if n<=0: return (0.0,1.0)
    p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d; m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (max(0.0,c-m),min(1.0,c+m))

def _crps_gauss(y,mu,s):
    """Closed-form CRPS of N(mu, s^2) against outcome y. A Gaussian
    approximation of the full kernel mixture (exact mixture CRPS would need the
    143 members stored per record, rejected for bytes). Lower is better; it is
    a proper score, so it rewards the whole distribution, not just the mean.
    Logged per resolved event for the retune-checkpoint sigma experiments."""
    if y is None or mu is None or not s or s<=0: return None
    z=(y-mu)/s
    pdf=math.exp(-0.5*z*z)/math.sqrt(2*math.pi)
    return round(s*(z*(2.0*_phi(z)-1.0)+2.0*pdf-1.0/math.sqrt(math.pi)),3)

def dressed_prob(members,b,sigma):
    """Bucket probability from a Gaussian-kernel-dressed ensemble. Each member is
    smeared with N(member, sigma^2); the bucket prob is the average kernel mass
    inside the bucket's real-valued interval. NWS rounds half-up, so the integer
    bucket [lo,hi] covers real temperatures [lo-0.5, hi+0.5). This replaces raw
    member counting, whose 1-degree bucket probs are dominated by sampling noise."""
    lo,hi=bucket_range(b); lo_e,hi_e=lo-0.5,hi+0.5
    tot=0.0
    for m in members:
        tot+=_phi((hi_e-m)/sigma)-_phi((lo_e-m)/sigma)
    return tot/len(members)

# --------------------- nowcast SHADOW (FUTURE 5 stage 1) ---------------------
# Built at checkpoint 1 (2026-07-13). Today's high cannot settle below the max
# already observed at the settlement station, so between NOWCAST_MIN_LHR and
# INTRADAY_HIGH_CUTOFF local time we truncate every calibrated member at the
# running observed max and store a PAIRED truncated-vs-untruncated ladder
# snapshot on the pending record. PLAYS NEVER SEE THESE NUMBERS: the
# pre-registered gate (FUTURE 5) requires truncated CRPS AND RPS to beat
# untruncated over 30+ graded same-day HIGH events before any pricing change.
# Snapshots are WRITE-ONCE (first in-window snapshot wins) so later,
# better-informed observations can never cherry-pick the comparison.

def _parse_obs_max(js,start_iso):
    """Running max (deg F) from an api.weather.gov observations payload,
    counting only records timestamped at or after start_iso (UTC, lexicographic
    compare on the first 16 chars). Null and non-numeric temperatures are
    skipped defensively. Returns (max_f, n_obs) or None."""
    if not isinstance(js,dict): return None
    best=None; n=0
    for f in js.get("features") or []:
        pr=(f or {}).get("properties") or {}
        ts=pr.get("timestamp") or ""
        if ts[:16]<start_iso[:16]: continue
        v=fnum(((pr.get("temperature") or {}).get("value")))
        if v is None: continue
        fdeg=v*9.0/5.0+32.0; n+=1
        if best is None or fdeg>best: best=fdeg
    return (best,n) if n else None

def fetch_running_max(code,tz,target_iso):
    """Observed running max at the settlement station since 07:00 LST of the
    target day. NWS CLI computes the daily max from denser data than hourly
    METARs, so this is a LOWER BOUND on the settlement value: exactly what
    truncation needs, never more than the truth. Returns (max_f,n_obs) or None."""
    sid=STATION_IDS.get(code)
    if not sid: return None
    start=dt.datetime.fromisoformat(target_iso)+dt.timedelta(hours=7-STD_OFFSET_H.get(tz,0))
    js=fget(f"https://api.weather.gov/stations/{sid}/observations"
            f"?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=200")
    if not js: return None
    return _parse_obs_max(js,start.strftime("%Y-%m-%dT%H:%M"))

def _grade_nowcast(nc,settled,actual):
    """Grade a paired shadow snapshot against Kalshi's own per-bucket settlement,
    mirroring compute_report's RPS conventions exactly (rep-sorted, normalized,
    last cumulative step dropped, exactly one hit required) so the two ladders
    and the headline metric all speak the same units. CRPS uses each snapshot's
    own mean/psd. Returns the compact graded dict or None."""
    bs=[b for b in nc.get("buckets",[]) if b.get("rep") is not None]
    if len(bs)<3: return None
    bs=sorted(bs,key=lambda b:b["rep"])
    hits=[]
    for b in bs:
        res=settled.get(b["ticker"])
        if not res or res[0] not in ("yes","no"): return None
        hits.append(1 if res[0]=="yes" else 0)
    if sum(hits)!=1: return None
    def _rps(key):
        s=sum(b[key] for b in bs) or 1.0
        F=O=0.0; tot=0.0
        for b,h in zip(bs[:-1],hits[:-1]):
            F+=b[key]/s; O+=h; tot+=(F-O)**2
        return tot
    out={"asof":nc.get("asof"),"obs_max":nc.get("obs_max"),"n_obs":nc.get("n_obs"),
         "mean_u":nc.get("mean_u"),"mean_t":nc.get("mean_t"),
         "rps_u":round(_rps("mp_u"),4),"rps_t":round(_rps("mp_t"),4)}
    if actual is not None:
        out["crps_u"]=_crps_gauss(actual,nc.get("mean_u"),nc.get("psd_u"))
        out["crps_t"]=_crps_gauss(actual,nc.get("mean_t"),nc.get("psd_t"))
    return out

def shadow_pass(state):
    """Collect nowcast shadow snapshots onto eligible pending records: same-day
    HIGH markets whose city clock sits inside [NOWCAST_MIN_LHR,
    INTRADAY_HIGH_CUTOFF) and which do not already carry one. Touches ONLY the
    'nowcast' key on pending records; boards, plays, resolution, and every
    existing measurement are untouched by design."""
    preds=state.get("predictions",{})
    if not preds: return 0
    calib=calib_params(state); gsigma=calib.get("_gsigma",DRESS_SIGMA_DEFAULT)
    ladders=None; members_cache={}
    wrote=0
    for key,p in preds.items():
        if p.get("kind")!="HIGH" or p.get("gated") or p.get("nowcast"): continue
        code=p.get("code"); tgt=p.get("target")
        if code not in CITIES: continue
        lat,lon,tz,label=CITIES[code]
        off=STD_OFFSET_H.get(tz,0)*3600
        lnow=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)+dt.timedelta(seconds=off)
        if tgt!=lnow.date().isoformat(): continue
        if not (NOWCAST_MIN_LHR<=lnow.hour<INTRADAY_HIGH_CUTOFF): continue
        if ladders is None:
            ladders={(l["code"],l["kind"],l["date"].isoformat()):l for l in pull_weather_markets()}
        L=ladders.get((code,"HIGH",tgt))
        if not L or not L.get("structure_ok",True): continue
        if code not in members_cache:
            hi,_lo,_o,_pm=fetch_members(lat,lon,tz); members_cache[code]=hi or {}
        raw=members_cache[code].get(tgt,[])
        if len(raw)<GATE_MIN_MEMBERS: continue
        obs=fetch_running_max(code,tz,tgt)
        if not obs: continue
        runmax,n_obs=obs
        cp=calib.get((code,"HIGH")) or {}
        corr=cp.get("corr",0.0); sigma=cp.get("sigma") or gsigma
        mem_u=[v+corr for v in raw]
        mem_t=[max(v,runmax) for v in mem_u]
        def _mps(ms):
            n=len(ms); mu=sum(ms)/n; msd=pstdev(ms)
            return mu,math.sqrt(msd*msd+sigma*sigma)
        mu_u,psd_u=_mps(mem_u); mu_t,psd_t=_mps(mem_t)
        p["nowcast"]={"asof":dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                      "obs_max":round(runmax,1),"n_obs":n_obs,
                      "mean_u":round(mu_u,2),"psd_u":round(psd_u,3),
                      "mean_t":round(mu_t,2),"psd_t":round(psd_t,3),
                      "model_version":MODEL_VERSION,"cfg":CONFIG_HASH,
                      "buckets":[{"ticker":b["ticker"],"rep":bucket_rep(b),
                                  "mp_u":dressed_prob(mem_u,b,sigma),
                                  "mp_t":dressed_prob(mem_t,b,sigma)} for b in L["buckets"]]}
        wrote+=1
    if wrote: print(f"   nowcast shadow: {wrote} snapshot(s) collected")
    return wrote

def calib_params(state):
    """Learn per (city,kind) mean-bias correction and dressing sigma from settled
    results. Uses the RAW forecast bias (logged bias plus whatever correction was
    applied at log time) so the learning target is stable as corrections evolve.
    Correction is shrunk toward 0 when history is thin; sigma comes from
    second-moment matching (Wang-Bishop): predictive variance should equal the
    realized MSE of the bias-corrected mean, so kernel variance fills the gap
    between that and the raw member variance."""
    hist=defaultdict(list)
    for r in state.get("resolved",[]):
        if r.get("bias") is None or r.get("gated"): continue   # quarantined: degraded data never teaches the corrections
        # RAW forecast bias = logged (corrected) bias MINUS the correction that was
        # added to the members at log time: corrected_mean = raw_mean + corr, so
        # raw = (corrected_mean - actual) - corr. The pre-audit code ADDED corr,
        # which is a stable but WRONG feedback loop: it converges to only
        # s/(1+2s) of the needed correction (about a third at full shrink), so a
        # city with a 3 degree station offset would keep a ~2 degree error and
        # trip the bias guard forever. Verified by simulation, audit batch 3.
        # It never fired live because no city had reached BIAS_MIN_N settlements.
        raw=r["bias"]-(r.get("bias_corr") or 0.0)
        hist[(r["code"],r["kind"])].append({"raw":raw,"sd":r.get("sd"),"t":r.get("target","")})
    out={}
    pooled=[]
    for k,rows in hist.items():
        # window by TARGET DATE, not append order: multi-day settlement batches
        # can resolve out of order, and "most recent 30" must mean the calendar.
        rows=sorted(rows,key=lambda x:x.get("t",""))[-BIAS_LOOKBACK:]
        rb=[x["raw"] for x in rows]; n=len(rb)
        corr=-(sum(rb)/n)*(n/(n+BIAS_SHRINK_K)) if n>=BIAS_MIN_N else 0.0
        srows=[x for x in rows if x.get("sd") is not None]
        pooled+=srows
        sig=None
        if len(srows)>=8:
            sb=[x["raw"] for x in srows]; m=sum(sb)/len(sb)
            var_err=sum((x-m)**2 for x in sb)/len(sb)
            mean_s2=sum(x["sd"]**2 for x in srows)/len(srows)
            sig=math.sqrt(max(var_err-mean_s2,0.0))
        out[k]={"corr":round(corr,2),"sigma":sig,"n":n}
    gsig=None
    if len(pooled)>=15:
        gb=[x["raw"] for x in pooled]; m=sum(gb)/len(gb)
        var_err=sum((x-m)**2 for x in gb)/len(gb)
        mean_s2=sum(x["sd"]**2 for x in pooled)/len(pooled)
        gsig=math.sqrt(max(var_err-mean_s2,0.0))
    for k,v in out.items():
        s=v["sigma"] if v["sigma"] is not None else (gsig if gsig is not None else DRESS_SIGMA_DEFAULT)
        v["sigma"]=round(min(max(s,DRESS_SIGMA_MIN),DRESS_SIGMA_MAX),2)
    out["_gsigma"]=round(min(max(gsig,DRESS_SIGMA_MIN),DRESS_SIGMA_MAX),2) if gsig is not None else DRESS_SIGMA_DEFAULT
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

def size_play(net, p_win, proven, lead=0):
    """Size from edge magnitude, then cap by win-probability, plausibility, lead time, and city track record."""
    if net < PLAY_NET_EDGE: return 0.0, ""
    # plausibility: an outsized edge is a red flag, not a green light
    if net >= SUSPECT_EDGE:
        return 1.0, "edge %.0f%% is implausibly large (likely model error or thin market), sized down" % (net*100)
    base = 2.0 if net>=EDGE_2U else 1.5 if net>=EDGE_1_5U else 1.0
    # win-probability ceiling: a bet you rarely WIN is high-variance regardless of edge
    wpc=WINPROB_CAP[-1][1]
    for thr,u in WINPROB_CAP:
        if p_win>=thr: wpc=u; break
    units=min(base,wpc); reason=""
    if wpc<base: reason="win prob %.0f%%, trimmed"%(p_win*100)
    # forecast skill decays fast with lead; a 3-4 day edge is mostly model noise
    if lead>=LEAD_CAP_DAYS and units>1.0:
        units=1.0; reason=reason or ("%d days out, capped"%lead)
    # a city must prove itself before it can earn max size
    if units>=2.0 and not proven:
        units=1.5; reason=reason or "city not yet proven, 2u locked"
    return units, reason

# ----------------------------- scoring -----------------------------
def score(state):
    ladders=pull_weather_markets()
    needed=sorted({l["code"] for l in ladders})
    print(f"Forecasts for {len(needed)} cities ({'+'.join(ENSEMBLE_MODELS)})...")
    fc,offs,pms,refs={},{},{},{}
    fetch_failed=[]; gated=[]
    for code in needed:
        lat,lon,tz,label=CITIES[code]
        hi,lo,off,pm=fetch_members(lat,lon,tz); fc[code]={"HIGH":hi,"LOW":lo}; offs[code]=off; pms[code]=pm
        refs[code]=fetch_ref(lat,lon,tz)
        if not hi and not lo: fetch_failed.append(code)
    run_meta=fetch_run_meta()
    run_stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    frozen_now=set()   # keys whose plays froze during THIS invocation (cap pruning
                       # must never touch plays frozen by an earlier run; a timestamp
                       # comparison fails when two runs share a minute, unit-test proven)
    rows,plays=[],[]
    skill=city_skill(state); preds=state.setdefault("predictions",{})
    calib=calib_params(state); gsigma=calib.get("_gsigma",DRESS_SIGMA_DEFAULT)
    for L in ladders:
        code,kind,tdate=L["code"],L["kind"],L["date"]
        # Lead and local hour come from the CITY's clock, never the runner's.
        # GitHub runners are UTC: after 00:00 UTC the runner's date is tomorrow
        # in every US zone, so runner-date leads mislabel each market by a day
        # and the realized guard wrongly kills next-day logging on evening runs.
        off=offs.get(code) or STD_OFFSET_H.get(CITIES[code][2],0)*3600
        lnow=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)+dt.timedelta(seconds=off)
        lead=(tdate-lnow.date()).days
        if lead<0: continue
        lhr=lnow.hour
        realized=(lead==0 and kind=="LOW") or (lead==0 and kind=="HIGH" and lhr>=INTRADAY_HIGH_CUTOFF)
        raw_members=fc[code][kind].get(tdate.isoformat(),[])
        # ---- integrity GATE (0.8, approved; quarantine amendment, batch 8) ----
        # A gated ladder still LOGS its record, flagged "gated", so the exclusion
        # is auditable later (owner-directed: never destroy the evidence needed
        # to judge whether an exclusion rule was right). Gated records carry no
        # plays, are skipped by calibration learning, drift alarms, and every
        # report aggregate, and never overwrite a healthy record's frozen plays.
        pmsum=_pm_summary(pms.get(code),kind,tdate.isoformat())
        gate=None
        if not L.get("structure_ok",True): gate="ladder structure"
        elif len(raw_members)<GATE_MIN_MEMBERS: gate=f"{len(raw_members)} members"
        elif len(pmsum)<GATE_MIN_MODELS: gate=f"{len(pmsum)}/4 models"
        if gate:
            gated.append(f"{code}/{kind} {tdate.isoformat()[5:]}: {gate}")
            if len(raw_members)<2: continue   # nothing meaningful to quarantine
        # learned calibration for this city/kind: shift by bias correction, dress with sigma
        cp=calib.get((code,kind)) or {}
        corr=cp.get("corr",0.0); sigma=cp.get("sigma") or gsigma
        members=[v+corr for v in raw_members]
        n=len(members); msd=pstdev(members); mean=sum(members)/n
        sd=math.sqrt(msd*msd+sigma*sigma)   # predictive spread incl. dressing
        ov=sum(b["ya"] for b in L["buckets"])-1.0
        wsum=sum((b["yb"]+b["ya"])/2 for b in L["buckets"])
        mkt_mean=(sum(((b["yb"]+b["ya"])/2)*(bucket_rep(b) or 0) for b in L["buckets"])/wsum) if wsum else mean
        offset=mean-mkt_mean; biased=abs(offset)>BIAS_TOL
        pbk,ppl=[],[]
        for b in L["buckets"]:
            mp=dressed_prob(members,b,sigma); mid=(b["yb"]+b["ya"])/2
            # decisions use the clamped prob; displays and logs keep raw mp
            mp_e=min(max(mp,TAIL_FLOOR),1.0-TAIL_FLOOR)
            cost=(b["ya"]-b["yb"])/2+fee(mid)+0.01; edge=mp_e-mid
            if edge>0: side,entry,net="Buy YES",b["ya"],edge-cost
            else:      side,entry,net="Buy NO",round(1-b["yb"],2),(-edge)-cost
            base=((not gate) and (not biased) and (not realized) and net>=PLAY_NET_EDGE and b["oi"]>=MIN_OI
                  and lead<=MAX_LEAD_DAYS and 0.02<mid<0.98)
            tier=None; eff=net; units=0.0; p_win=None; size_reason=""; hiconf=False
            if base:
                p_win = mp_e if side=="Buy YES" else 1-mp_e
                proven = (code,kind) in skill
                units, size_reason = size_play(net, p_win, proven, lead)
                tier = "S" if units>=2 else "A" if units>=1.5 else "B" if units>=1 else None
                hiconf = units>0 and p_win>=HICONF_PWIN
            is_play=base and units>0
            rec={"code":code,"label":CITIES[code][3],"kind":kind,"date":tdate,"lead":lead,
                 "bucket":b["sub"],"ticker":b["ticker"],"mid":mid,"mp":mp,"edge":edge,"side":side,
                 "entry":entry,"net":net,"oi":b["oi"],"sd":sd,"mean":mean,"overround":ov,
                 "offset":offset,"biased":biased,"realized":realized,"tier":tier,"eff":eff,"p_win":p_win,
                 "size_reason":size_reason,"hiconf":hiconf,
                 "units":units,"stake":round(units*BASE_UNIT_USD,2) if units else None}
            if not gate: rows.append(rec)
            if is_play: plays.append(rec)
            pbk.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"floor":b["floor"],
                        "cap":b["cap"],"stype":b["stype"],"mp":mp,"mid":mid,"yb":b["yb"],"ya":b["ya"],"oi":b["oi"]})
            if is_play:
                ppl.append({"ticker":b["ticker"],"bid":bucket_id(b),"sub":b["sub"],"side":side,
                            "entry":entry,"net":net,"edge":edge,"tier":tier,"units":units,
                            "stake":round(units*BASE_UNIT_USD,2),"p_win":p_win,"mp":mp,"mid":mid})
        if not realized:
            key=f"{code}|{kind}|{tdate.isoformat()}"
            old=preds.get(key)
            if gate and old and old.get("plays"):
                pass   # degraded data must never overwrite a record holding frozen plays
            else:
                rec={"code":code,"kind":kind,"target":tdate.isoformat(),
                    "event_ticker":L["event_ticker"],"logged_at":run_stamp,
                    "first_logged":(old or {}).get("first_logged") or (old or {}).get("logged_at") or run_stamp,
                    "lead":lead,"mean":mean,"sd":msd,"psd":sd,"bias_corr":corr,"sigma":sigma,
                    "model_version":MODEL_VERSION,"biased":biased,"offset":offset,
                    "model_runs":run_meta,
                    "members_by_model":_pm_summary(pms.get(code),kind,tdate.isoformat()),
                    "ref":_ref_for(refs.get(code),kind,tdate.isoformat()),
                    "cfg":CONFIG_HASH,
                    "mean_hist":(((old or {}).get("mean_hist") or [])+[[run_stamp,round(mean,2)]])[-6:],
                    "buckets":pbk,"plays":ppl}
                if gate: rec["gated"]=gate
                if old and old.get("nowcast"): rec["nowcast"]=old["nowcast"]   # shadow snapshots survive refreshes (write-once)
                # FREEZE: once a run has published plays for this market, later runs must
                # not rewrite them; the tracker has to score the board the owner actually
                # saw. Buckets/mean/sigma keep refreshing (calibration wants the freshest
                # forecast); the plays list locks at its first NON-EMPTY log, so an edge
                # that only appears later can still be picked up once, then locks too.
                if old and old.get("plays"):
                    rec["plays"]=old["plays"]
                    rec["plays_lead"]=old.get("plays_lead",old.get("lead"))
                    rec["plays_logged_at"]=old.get("plays_logged_at",old.get("logged_at"))
                    rec["plays_model_version"]=old.get("plays_model_version",old.get("model_version",""))
                elif ppl:
                    rec["plays_lead"]=lead; rec["plays_logged_at"]=run_stamp
                    rec["plays_model_version"]=MODEL_VERSION
                    frozen_now.add(key)
                preds[key]=rec
    plays.sort(key=lambda r:(-r["units"],-(r.get("p_win") or 0),-r.get("net",0),r["ticker"]))
    # ---- exposure caps (audit batch 8; SEEDED v12): best plays fill first ----
    # The caps bound CUMULATIVE frozen exposure per target, so the ledger of
    # already-frozen plays (earlier runs today, or inherited pre-audit records:
    # deploy day proved a 37.5u legacy board can be inherited in one race)
    # consumes the budget BEFORE any new play may freeze. Without the seed,
    # every additional run on a volatile day could rotate a fresh 6u into the
    # frozen set as old edges fade and new ones appear.
    kept=[]; dropped=0
    per_day=defaultdict(float); per_ev=defaultdict(float)
    for key,rec in preds.items():
        if key in frozen_now or not rec.get("plays"): continue
        for pl in rec["plays"]:
            per_day[rec["target"]]+=pl["units"]
            per_ev[(rec["target"],rec["code"],rec["kind"])]+=pl["units"]
    for r in plays:
        dk=r["date"].isoformat(); ek=(dk,r["code"],r["kind"])
        if per_day[dk]+r["units"]>DAILY_UNIT_CAP+1e-9 or per_ev[ek]+r["units"]>EVENT_UNIT_CAP+1e-9:
            dropped+=1; continue
        per_day[dk]+=r["units"]; per_ev[ek]+=r["units"]; kept.append(r)
    plays=kept
    # prune ONLY plays frozen THIS run; earlier frozen history is untouchable
    kept_ids={(r["date"].isoformat(),r["ticker"],r["side"]) for r in plays}
    for key,rec in preds.items():
        if key in frozen_now and rec.get("plays"):
            pruned=[pl for pl in rec["plays"] if (rec["target"],pl["ticker"],pl["side"]) in kept_ids]
            if len(pruned)!=len(rec["plays"]):
                rec["plays"]=pruned
                if not pruned:
                    for f in ("plays_lead","plays_logged_at","plays_model_version"): rec.pop(f,None)
    new24=0
    now_utc=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for rec in preds.values():
        ts=rec.get("plays_logged_at")
        if ts and rec.get("plays"):
            try:
                try: tsd=dt.datetime.strptime(ts,"%Y-%m-%dT%H:%MZ")
                except ValueError: tsd=dt.datetime.strptime(ts,"%Y-%m-%dT%H:%M")  # inherited pre-audit stamps lack the Z
                if (now_utc-tsd).total_seconds()<=86400:
                    new24+=len(rec["plays"])
            except ValueError: pass
    health={"ladders":len(ladders),"cities":len(needed),"cities_failed":fetch_failed,
            "gated":gated,"capped":dropped,"new_24h":new24,
            "run_utc":dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    return rows,plays,health

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
             "sd":p.get("sd"),"psd":p.get("psd"),"bias_corr":p.get("bias_corr",0.0),"sigma":p.get("sigma"),
             "crps":_crps_gauss(actual,p["mean"],p.get("psd")),
             "model_version":p.get("model_version",""),"cfg":p.get("cfg"),
             "first_logged":p.get("first_logged",p.get("logged_at")),
             "model_runs":p.get("model_runs"),
             "members_by_model":p.get("members_by_model"),
             "ref":p.get("ref"),
             "buckets":[],"plays":[]}
        if p.get("mean_hist"): rec["mean_hist"]=p["mean_hist"]   # run-by-run forecast revision trail (audit batch 11)
        if p.get("gated"): rec["gated"]=p["gated"]   # quarantined record: kept for audit, excluded from learning and metrics
        ok=True
        for b in p["buckets"]:
            res=settled.get(b["ticker"])
            if not res or res[0] not in ("yes","no"): ok=False; continue
            hit=1 if res[0]=="yes" else 0
            rec["buckets"].append({"mp":b["mp"],"mid":b["mid"],"hit":hit,"rep":bucket_rep(b)})
        if p.get("nowcast"):
            g=_grade_nowcast(p["nowcast"],settled,actual)
            if g: rec["nowcast"]=g   # nowcast shadow, graded (FUTURE 5 gate instrument)
        for pl in p.get("plays",[]):
            res=settled.get(pl["ticker"])
            if not res or res[0] not in ("yes","no"): continue
            won=(res[0]=="yes") if pl["side"]=="Buy YES" else (res[0]=="no")
            entry=pl["entry"]; contracts=int(pl["stake"]//entry) if entry>0 else 0
            # Kalshi charges the quadratic taker fee per TRADE, rounded UP to the
            # next cent. Ceil can only overstate paper costs: conservative.
            fees=math.ceil(0.07*contracts*entry*(1-entry)*100)/100 if contracts else 0.0
            pnl=contracts*((1-entry) if won else -entry)-fees
            bb=next((b for b in p["buckets"] if b["ticker"]==pl["ticker"]),None)
            # CLV analog (audit batch 5): entry-time mid (frozen with the play) vs
            # the mid at this record's LAST refresh, i.e. the final actionable
            # board (HIGHs: the morning-of 12:17 board; LOWs: the prior-evening
            # 02:07 board). Positive = the market moved toward the position.
            # Mirrors RidgeSeeker's beat-the-close philosophy: edge shows here
            # long before win/loss variance can.
            cmid=bb.get("mid") if bb else None
            clv=None
            if cmid is not None and pl.get("mid") is not None:
                clv=round((cmid-pl["mid"]) if pl["side"]=="Buy YES" else (pl["mid"]-cmid),3)
            mv=margin_deg(actual,bb,won) if (bb and actual is not None) else None
            rec["plays"].append({"code":p["code"],"kind":p["kind"],"target":p["target"],"sub":pl["sub"],
                                 "side":pl["side"],"entry":entry,"tier":pl["tier"],"units":pl["units"],
                                 "stake":pl["stake"],"contracts":contracts,"won":won,"pnl":round(pnl,2),
                                 "margin":mv,"actual":rec["actual"],"mp":pl["mp"],"mid":pl["mid"],
                                 "edge":pl.get("edge"),"lead":p.get("plays_lead",p.get("lead")),
                                 "close_mid":cmid,"clv":clv,
                                 "model_version":p.get("plays_model_version") or p.get("model_version","")})
        if ok and rec["buckets"]:
            resolved.append(rec); del preds[k]; n+=1
    print(f"Resolved {n} events from Kalshi settlement.")
    return n

# --------------------------- reporting -----------------------------
def _era_label(mv):
    """Legacy iff the stamp is empty or a pre-audit stamp; every later
    MODEL_VERSION (v11, v12, v13, ...) is the audit build. The first draft
    matched substrings 'audit'/'capseed' and silently misfiled v13 plays under
    Legacy for three days (caught 2026-07-16): never enumerate the NEW-era
    stamps, enumerate the CLOSED legacy set."""
    return "Legacy (pre-audit)" if ((not mv) or "nimbus-calib" in mv) else "Audit build (v11+)"

def compute_report(state):
    resolved=[r for r in state.get("resolved",[]) if not r.get("gated")]   # quarantined records never enter any aggregate
    bk=[b for r in resolved for b in r["buckets"]]
    pls=[pl for r in resolved for pl in r["plays"]]
    rep={"n_events":len(resolved),"n_buckets":len(bk),"plays":pls}
    if bk:
        rep["brier_model"]=sum((b["mp"]-b["hit"])**2 for b in bk)/len(bk)
        rep["brier_market"]=sum((b["mid"]-b["hit"])**2 for b in bk)/len(bk)
    # RPS: the ordered-bucket proper score (audit batch 9 verdict: the right
    # headline for ladder markets, because missing by one bucket should score
    # better than missing by five, which per-bucket Brier cannot see). Only
    # records whose buckets carry rep (v6+) qualify. Market probabilities are
    # the normalized mids: a devig used for SCORING ONLY, never for pricing.
    rme,rmk=[],[]
    for r in resolved:
        bs=[b for b in r["buckets"] if b.get("rep") is not None]
        if len(bs)<3 or sum(b["hit"] for b in bs)!=1: continue
        bs=sorted(bs,key=lambda b:b["rep"])
        sm=sum(b["mp"] for b in bs) or 1.0; sk=sum(b["mid"] for b in bs) or 1.0
        Fm=Fk=O=0.0; sA=sB=0.0
        for b in bs[:-1]:
            Fm+=b["mp"]/sm; Fk+=b["mid"]/sk; O+=b["hit"]
            sA+=(Fm-O)**2; sB+=(Fk-O)**2
        rme.append(sA); rmk.append(sB)
    if rme:
        rep["rps_model"]=sum(rme)/len(rme); rep["rps_market"]=sum(rmk)/len(rmk); rep["rps_n"]=len(rme)
    # nowcast shadow tally (FUTURE 5 gate: truncated must beat untruncated on
    # CRPS AND RPS over 30+ graded same-day HIGH events before plays may use it)
    ncs=[r["nowcast"] for r in resolved if r.get("nowcast") and r["nowcast"].get("rps_u") is not None]
    if ncs:
        rep["nowcast"]={"n":len(ncs),
            "rps_u":sum(g["rps_u"] for g in ncs)/len(ncs),
            "rps_t":sum(g["rps_t"] for g in ncs)/len(ncs),
            "crps_u":sum(g.get("crps_u") or 0.0 for g in ncs)/len(ncs),
            "crps_t":sum(g.get("crps_t") or 0.0 for g in ncs)/len(ncs),
            "wins":sum(1 for g in ncs if g["rps_t"]<g["rps_u"])}
    # calibration bins
    bins=[]
    for lo in [i/10 for i in range(10)]:
        sel=[b for b in bk if lo<=b["mp"]<lo+0.1]
        if sel:
            n=len(sel); hits=sum(b["hit"] for b in sel)
            wlo,whi=_wilson(hits,n)
            bins.append((lo,n,sum(b["mp"] for b in sel)/n,hits/n,wlo,whi))
    rep["bins"]=bins
    # Forecast-source skill (audit batch 10 display; data from batches 2-5):
    # MAE of each raw model mean, NBM, HRRR, and the corrected pooled mean.
    src=defaultdict(lambda:[0.0,0])
    for r in resolved:
        a=r.get("actual")
        if a is None: continue
        if r.get("mean") is not None:
            src["Pooled ensemble (corrected)"][0]+=abs(r["mean"]-a); src["Pooled ensemble (corrected)"][1]+=1
        for m,d in (r.get("members_by_model") or {}).items():
            src[m][0]+=abs(d["mean"]-a); src[m][1]+=1
        for k,v in (r.get("ref") or {}).items():
            nm="NBM (station-calibrated)" if k=="nbm" else "HRRR (short-lead)"
            src[nm][0]+=abs(v-a); src[nm][1]+=1
    rep["sources"]=sorted(((k,s/n,n) for k,(s,n) in src.items() if n),key=lambda x:x[1])
    # Calibration engine series (owner request 2026-07-06): rolling MAE of the
    # UNCORRECTED forecast, the CORRECTED forecast, and the market-implied mean,
    # in resolution order. Raw-vs-corrected divergence IS the learning engine
    # visible; the market line is the bar both must clear. The rounded stored
    # actual adds identical noise to every line, so comparisons stay fair.
    W=30
    crows=[r for r in resolved if r.get("bias") is not None and r.get("actual") is not None]
    if len(crows)>=8:
        raw=[abs(r["bias"]-(r.get("bias_corr") or 0.0)) for r in crows]
        cor=[abs(r["bias"]) for r in crows]
        mkt=[]
        for r in crows:
            bs=[b for b in r.get("buckets",[]) if b.get("rep") is not None and b.get("mid")]
            sm=sum(b["mid"] for b in bs) if len(bs)>=3 else 0
            mkt.append(abs(sum(b["mid"]*b["rep"] for b in bs)/sm-r["actual"]) if sm else None)
        def _roll(xs,minn=8):
            out=[]
            for i in range(len(xs)):
                w=[x for x in xs[max(0,i-W+1):i+1] if x is not None]
                out.append(round(sum(w)/len(w),3) if len(w)>=minn else None)
            return out
        rep["calib_series"]={"raw":_roll(raw),"cor":_roll(cor),"mkt":_roll(mkt),
            "active":sum(1 for r in crows if abs(r.get("bias_corr") or 0.0)>0.01)}
        zs=[(r["bias"]/r["psd"]) if r.get("psd") else None for r in crows]
        dso=[]
        for i in range(len(zs)):
            w=[z for z in zs[max(0,i-W+1):i+1] if z is not None]
            if len(w)>=10:
                m=sum(w)/len(w); dso.append(round(math.sqrt(sum((z-m)**2 for z in w)/len(w)),3))
            else: dso.append(None)
        if any(v is not None for v in dso): rep["disp_series"]=dso
    # learned calibration currently in force (bias correction + dressing sigma)
    cal=calib_params(state)
    rep["calib"]=sorted(((CITIES[k[0]][3],k[1],v["corr"],v["sigma"],v["n"])
                         for k,v in cal.items() if isinstance(k,tuple)),
                        key=lambda x:-abs(x[2]))
    rep["gsigma"]=cal.get("_gsigma",DRESS_SIGMA_DEFAULT)
    # per-city bias
    cb=defaultdict(list)
    for r in resolved:
        if r["bias"] is not None: cb[(r["code"],r["kind"])].append(r["bias"])
    rep["city_bias"]=sorted(((CITIES[c][3],k,sum(v)/len(v),len(v)) for (c,k),v in cb.items()),key=lambda x:-abs(x[2]))
    # play performance
    if pls:
        wins=sum(1 for p in pls if p["won"]); tot=len(pls); pnl=sum(p["pnl"] for p in pls)
        staked=sum(p["contracts"]*p["entry"] for p in pls)
        rep["pnl"]={"n":tot,"wins":wins,"winrate":wins/tot,"net":pnl,"staked":staked,
                    "roi":(pnl/staked if staked else 0),"net_units":pnl/BASE_UNIT_USD,
                    "avg_margin":sum(p["margin"] for p in pls if p["margin"] is not None)/max(1,sum(1 for p in pls if p["margin"] is not None))}
        # Honesty tiles (audit batch 10): stated edge vs realized cents/contract,
        # and a block-bootstrap-by-target-date ROI interval (batch 9 verdict).
        # random is DETERMINISTICALLY seeded from the data so identical inputs
        # still reproduce identical output (batch 8 replay guarantee holds).
        ncon=sum(p["contracts"] for p in pls)
        if ncon:
            rep["edge_stated"]=sum((p.get("net") or 0)*p["contracts"] for p in pls if p.get("net") is not None)/ncon
            rep["edge_real"]=pnl/ncon
        days=defaultdict(list)
        for p in pls: days[p["target"]].append(p)
        dk=sorted(days)
        if len(dk)>=3:
            import random as _rnd
            rng=_rnd.Random(len(pls)*100003+len(dk))
            rois=[]
            for _ in range(800):
                sample=[p for _x in range(len(dk)) for p in days[rng.choice(dk)]]
                st=sum(p["contracts"]*p["entry"] for p in sample)
                if st: rois.append(sum(p["pnl"] for p in sample)/st)
            rois.sort()
            if rois: rep["roi_ci"]=(rois[int(0.05*len(rois))],rois[int(0.95*len(rois))],len(dk))
        cl=[p for p in pls if p.get("clv") is not None]
        live=[p for p in cl if abs(p["clv"])>1e-9 or p.get("close_mid")!=p.get("mid")]
        if cl:
            rep["clv"]={"n":len(cl),"beat":sum(1 for p in cl if p["clv"]>0),
                        "avg":sum(p["clv"] for p in cl)/len(cl),"live":len(live)}
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
        # time-windowed win rate, by target date
        def _win(days):
            cut=(TODAY-dt.timedelta(days=days)).isoformat()
            sel=[x for x in pls if x["target"]>=cut]
            if not sel: return None
            w=sum(1 for x in sel if x["won"])
            return {"n":len(sel),"w":w,"wr":w/len(sel),"u":sum(x["pnl"] for x in sel)/BASE_UNIT_USD}
        rep["windows"]={"day":_win(1),"week":_win(7),"all":_win(100000)}
        # win rate by edge magnitude (does a bigger edge actually win more?)
        EB=[(0.0,0.08,"under 8%"),(0.08,0.15,"8-15%"),(0.15,0.25,"15-25%"),(0.25,9.0,"25%+")]
        bye=[]
        for lo,hi,lab in EB:
            sel=[x for x in pls if x.get("edge") is not None and lo<=abs(x["edge"])<hi]
            if sel:
                w=sum(1 for x in sel if x["won"]); bye.append((lab,len(sel),w,sum(x["pnl"] for x in sel)))
        rep["by_edge"]=bye
        # win rate and P&L by the model's stated win probability at bet time.
        # This is the go/no-go table for a "bet only the high-confidence cards"
        # strategy: it shows whether 80%+ plays actually deliver ROI or just wins.
        PB=[(0.0,0.50,"under 50%"),(0.50,0.65,"50-65%"),(0.65,0.80,"65-80%"),(0.80,1.01,"80%+")]
        byp=[]
        for lo,hi,lab in PB:
            sel=[]
            for x in pls:
                if x.get("mp") is None: continue
                pw=x["mp"] if x.get("side")=="Buy YES" else 1-x["mp"]
                if lo<=pw<hi: sel.append((x,pw))
            if sel:
                w=sum(1 for x,_ in sel if x["won"])
                stk=sum(x["contracts"]*x["entry"] for x,_ in sel)
                pn=sum(x["pnl"] for x,_ in sel)
                avgp=sum(pw for _,pw in sel)/len(sel)
                byp.append((lab,len(sel),w,avgp,pn,(pn/stk if stk else 0.0)))
        rep["by_pwin"]=byp
        # cumulative series (in UNITS: owner directive 2026-07-06, the display is
        # bankroll-agnostic until a real unit is chosen), ordered by target date
        ser=[]; run=0.0
        for p in sorted(pls,key=lambda x:x["target"]):
            run+=p["pnl"]/BASE_UNIT_USD; ser.append(round(run,2))
        rep["cum"]=ser
        rep["recent"]=sorted(pls,key=lambda x:x["target"],reverse=True)
        # Era split in units: the honest instrument for "is the audit build
        # better", once its plays settle. Version stamps make this a query.
        eras=defaultdict(lambda:[0,0,0.0,0.0])
        for p in pls:
            mv=p.get("model_version") or ""
            lab=_era_label(mv)
            e=eras[lab]; e[0]+=1; e[1]+=1 if p["won"] else 0
            e[2]+=p["units"]; e[3]+=p["pnl"]/BASE_UNIT_USD
        rep["eras"]=sorted(((k,)+tuple(v) for k,v in eras.items()))
        # Core vs experimental split (docket 1, registered 2026-07-13): the
        # cheap-entry cell is an EXPERIMENT the paper ledger pays tuition on;
        # showing it separately keeps the core strategy readable in both
        # directions and shows the docket gate filling in public.
        audp=[p for p in pls if _era_label(p.get("model_version") or "")!="Legacy (pre-audit)"]
        _cell=lambda p: p["entry"]<=0.20 or ((p.get("p_win") or 1.0)<=0.30)
        rep["book_split"]={
            "core":{"n":len([p for p in audp if not _cell(p)]),
                    "w":sum(1 for p in audp if not _cell(p) and p["won"]),
                    "stake_u":sum(p["units"] for p in audp if not _cell(p)),
                    "net_u":sum(p["pnl"] for p in audp if not _cell(p))/BASE_UNIT_USD},
            "exp":{"n":len([p for p in audp if _cell(p)]),
                   "w":sum(1 for p in audp if _cell(p) and p["won"]),
                   "stake_u":sum(p["units"] for p in audp if _cell(p)),
                   "net_u":sum(p["pnl"] for p in audp if _cell(p))/BASE_UNIT_USD}}
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
      "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Nimbus</title>"
      "<link rel='preconnect' href='https://fonts.googleapis.com'>"
      "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>"
      f"<style>{CSS}</style></head><body>"+(STALE_JS%int(time.time()))+"<header><div class='hd'>"
      "<div class='brand'><h1>Nimbus<span class='dot'> .</span></h1>"
      f"<span class='sub'>{updated} &middot; {MODEL_VERSION} &middot; calibrated ensemble {'+'.join(ENSEMBLE_MODELS)} &middot; settled by Kalshi</span></div> {DOT} cfg {CONFIG_HASH}"
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
            f"<text x='{pad}' y='14' fill='#8b97a6' font-size='11' font-family=monospace>cumulative units P&amp;L</text></svg>")

def svg_multi(series,labels,colors,w=680,h=190,pad=26,ref=None):
    """Multi-line chart; None values break the line (data-gated segments)."""
    vals=[v for s in series for v in s if v is not None]
    if not vals: return ""
    lo=min(vals+([ref] if ref is not None else [])); hi=max(vals+([ref] if ref is not None else []))
    rng=(hi-lo) or 1; n=max(len(s) for s in series)
    X=lambda i: pad+(w-2*pad)*(i/max(1,n-1)); Y=lambda v: h-pad-(h-2*pad)*((v-lo)/rng)
    out=[f"<svg viewBox='0 0 {w} {h}'>"]
    if ref is not None:
        out.append(f"<line x1='{pad}' y1='{Y(ref):.1f}' x2='{w-pad}' y2='{Y(ref):.1f}' stroke='#232a33' stroke-dasharray='4 4'/>")
        out.append(f"<text x='{w-pad-8}' y='{Y(ref)-5:.1f}' fill='#8b97a6' font-size='10' font-family=monospace text-anchor='end'>{ref:g}</text>")
    for s,c in zip(series,colors):
        seg=[]
        for i,v in enumerate(s):
            if v is None:
                if len(seg)>1: out.append(f"<polyline points='{' '.join(seg)}' fill='none' stroke='{c}' stroke-width='2'/>")
                seg=[]
            else: seg.append(f"{X(i):.1f},{Y(v):.1f}")
        if len(seg)>1: out.append(f"<polyline points='{' '.join(seg)}' fill='none' stroke='{c}' stroke-width='2'/>")
    x=pad
    for lab,c,s in zip(labels,colors,series):
        if any(v is not None for v in s):
            out.append(f"<text x='{x}' y='14' fill='{c}' font-size='11' font-family=monospace>{esc(lab)}</text>")
            x+=len(lab)*7+18
    out.append("</svg>")
    return "".join(out)

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

def _health_strip(health,alerts=None):
    if not health and not alerts: return ""
    health=health or {}
    fails=health.get("cities_failed") or []
    okc=health.get("cities",0)-len(fails)
    s=("<div class='strip'><span class='chip'>ladders <b>%d</b></span>"
       "<span class='chip'>forecast cities <b>%d/%d</b></span>"
       %(health.get("ladders",0),okc,health.get("cities",0)))
    if fails: s+="<span class='chip neg'>fetch failed: <b>%s</b></span>"%esc(", ".join(fails))
    if health.get("capped"): s+="<span class='chip'>cap trimmed <b>%d</b> plays</span>"%health["capped"]
    if health.get("new_24h") is not None: s+="<span class='chip'>new plays 24h <b>%d</b></span>"%health["new_24h"]
    if health.get("state_kb"): s+="<span class='chip'>state <b>%d KB</b> / <b>%d</b> resolved</span>"%(health["state_kb"],health.get("resolved_n",0))
    for g in (health.get("gated") or []):
        s+="<span class='chip neg'>gated: <b>%s</b></span>"%esc(g)
    for a in (alerts or []):
        s+="<span class='chip neg'>%s</span>"%esc(a)
    return s+"</div>"

def render_bets(rows,plays,updated,health=None):
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
            if r.get("hiconf"): flag='<span class="tag c-hi">high confidence</span>'+flag
            ptab+=(f'<div class="pcard {sc}"><div class="ptop">'
                   f'<div><div class="pcity">{city} &middot; {mk} &middot; {r["date"].strftime("%b %d")}</div>'
                   f'<div class="prange">{esc(r["bucket"])}</div></div>'
                   f'<div class="pside {sb}">{word}<div class="psub">{r["entry"]*100:.0f}\u00a2</div></div></div>'
                   f'<div class="pbar">{unit_badge(r["units"])}'
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
    html=(head("bets",updated,_health_strip(health))+
      "<div class='note'><b>Confidence = size.</b> Probabilities come from a bias-corrected, kernel-dressed "
      "multi-model ensemble that learns each city's error from Kalshi settlements. Plays are sized 2u / 1.5u / 1u "
      "and listed highest win probability first within each size. A city cannot earn a 2u until it has proven it "
      "beats the market on the Results tab.</div>"
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

def render_results(rep,updated,health=None,alerts=None):
    if not rep.get("plays"):
        body=('<div class="empty"><b>No resolved bets yet.</b> This tracker fills in automatically once your '
              'logged plays settle on Kalshi. Every run pulls Kalshi\'s official result and settled temperature, '
              'marks each bet win/loss, and updates the charts, per-city and per-unit tables, and margins below. '
              'Give it a couple weeks of morning runs.</div>')
        html=head("results",updated,_health_strip(health,alerts))+"<h2 class='sec'>Results tracker</h2>"+body+"</div></body></html>"
        with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html); return
    p=rep["pnl"]; cls="up" if p["net"]>=0 else "red"
    kpis=("<div class='kpi'>"
      f"<div class='kbox'><div class='v {cls}'>{p['net_units']:+.1f}u</div><div class='l'>net units</div></div>"
      f"<div class='kbox'><div class='v'>{p['winrate']*100:.0f}%</div><div class='l'>win rate ({p['wins']}/{p['n']})</div></div>"
      f"<div class='kbox'><div class='v {cls}'>{p['roi']*100:+.1f}%</div><div class='l'>ROI</div></div>"
      f"<div class='kbox'><div class='v'>{p['avg_margin']:+.1f}\u00b0</div><div class='l'>avg margin</div></div>"
      f"<div class='kbox'><div class='v'>{rep['n_events']}</div><div class='l'>events</div></div></div>")
    honest=""
    if rep.get("edge_stated") is not None or rep.get("roi_ci") or rep.get("clv"):
        cells=""
        if rep.get("edge_stated") is not None:
            ec="up" if rep["edge_real"]>=rep["edge_stated"] else "red"
            cells+=(f"<div class='kbox'><div class='v'>{rep['edge_stated']*100:+.1f}\u00a2</div><div class='l'>stated edge /contract</div></div>"
                    f"<div class='kbox'><div class='v {ec}'>{rep['edge_real']*100:+.1f}\u00a2</div><div class='l'>realized /contract</div></div>")
        if rep.get("roi_ci"):
            lo,hi,nd=rep["roi_ci"]
            cells+=f"<div class='kbox'><div class='v'>{lo*100:+.0f}% .. {hi*100:+.0f}%</div><div class='l'>ROI 90% CI (block by day, {nd}d)</div></div>"
        if rep.get("clv"):
            c=rep["clv"]
            if c["live"]:
                cv="up" if c["avg"]>0 else "red"
                cells+=(f"<div class='kbox'><div class='v'>{c['beat']}/{c['n']}</div><div class='l'>beat the close</div></div>"
                        f"<div class='kbox'><div class='v {cv}'>{c['avg']*100:+.1f}\u00a2</div><div class='l'>avg CLV (edge shows here first)</div></div>")
            else:
                cells+=f"<div class='kbox'><div class='v dim'>{c['n']} logged</div><div class='l'>CLV pending multi-board settlements</div></div>"
        honest="<div class='kpi'>"+cells+"</div>"
    srct=""
    if rep.get("sources"):
        rowsS="".join(f"<tr><td>{esc(k)}</td><td class='n'>{mae:.2f}\u00b0</td><td class='n'>{n}</td></tr>"
                      for k,mae,n in rep["sources"])
        srct=("<h2 class='sec'>Forecast sources</h2>"
          "<div class='note'>Mean absolute error of each source's daily-extreme forecast against Kalshi settlements. "
          "NBM and HRRR are logged references that never touch pricing; promotion is decided here, on settled "
          "evidence (50+ rows per source), never on reputation. Raw model rows accrue only on records logged "
          "after the audit build deployed.</div>"
          "<table><thead><tr><th>Source</th><th class='n'>MAE</th><th class='n'>Settled</th></tr></thead><tbody>"+rowsS+"</tbody></table>")
    chart=f"<div class='card'>{svg_line(rep.get('cum',[]))}</div>"
    calsec=""
    if rep.get("calib_series"):
        cs=rep["calib_series"]
        c1=svg_multi([cs["raw"],cs["cor"],cs["mkt"]],
                     ["uncorrected model MAE","corrected model MAE","market-implied MAE"],
                     ["#8b97a6","#5ad1c8","#e2b34d"])
        note=("<div class='note'>Rolling 30-settlement mean absolute error of the daily-extreme forecast, in "
              "resolution order. The grey line is what the raw ensemble would have said; the teal line is what "
              "Nimbus actually said after per-city corrections. The gap between them is the calibration engine, "
              "visible. Corrections have touched <b>%d</b> of the settled records so far, so the lines separate "
              "from that point on: they will overlap over the pre-activation history, which is the honest "
              "baseline, not a bug. Amber is the market's own implied forecast (computable on new-format records "
              "only): the bar both lines have to clear.</div>"%cs["active"])
        disp=""
        if rep.get("disp_series"):
            d1=svg_multi([rep["disp_series"]],["rolling sd(z), 30-settlement window"],["#5ad1c8"],ref=1.0)
            disp=("<div class='card'>"+d1+"</div>"
              "<div class='note'>Spread honesty. z is the forecast miss divided by the stated uncertainty; a "
              "well-calibrated model keeps the rolling sd(z) near the dashed 1.0 line. Above 1.0 the model is "
              "overconfident (spreads too tight, tail bets poisoned); below it, underconfident (edges understated). "
              "This converging to 1.0 is the leading indicator that the probabilities, and therefore the stated "
              "edges, can be believed. It moves weeks before P&amp;L can.</div>")
        erat=""
        if rep.get("eras"):
            rowsE="".join(f"<tr><td>{esc(k)}</td><td class='n'>{n}</td><td class='n'>{w}/{n-w}</td>"
                          f"<td class='n'>{st:.1f}u</td><td class='n {'up' if pn>=0 else 'red'}'>{pn:+.1f}u</td></tr>"
                          for k,n,w,st,pn in rep["eras"])
            erat=("<h2 class='sec'>By model era</h2>"
              "<div class='note'>Every play is stamped with the model version that froze it, so old and new "
              "engines never blend. The audit-era row is the number that answers whether the rebuild worked; "
              "judge it only at the pre-registered checkpoints, not daily.</div>"
              "<table><thead><tr><th>Era</th><th class='n'>Plays</th><th class='n'>W/L</th>"
              "<th class='n'>Risked</th><th class='n'>Net</th></tr></thead><tbody>"+rowsE+"</tbody></table>")
            if rep.get("book_split"):
                bs=rep["book_split"]; c,e=bs["core"],bs["exp"]
                erat+=("<div class='note'>Within the audit era: <b>core book</b> (entries above 0.20, win prob above 30 percent) "
                  f"{c['w']}/{c['n']-c['w']} for <b>{c['net_u']:+.1f}u</b> on {c['stake_u']:.1f}u risked. "
                  f"<b>Experimental cheap-entry cell</b> (docket item 1, gate {e['n']}/40): {e['w']}/{e['n']-e['w']} for {e['net_u']:+.1f}u. "
                  "The cell keeps trading until its pre-registered gate reads; its cost is the price of a verdict that "
                  "cannot be argued with. If the gate condition holds, a MIN_ENTRY floor of 0.20 ships automatically.</div>")
        calsec=("<h2 class='sec'>Calibration engine</h2>"+note+"<div class='card'>"+c1+"</div>"+disp+erat)
    # time-windowed win rate row
    W=rep.get("windows",{})
    def _wk(lbl,d):
        if not d: return f"<div class='kbox'><div class='v dim'>-</div><div class='l'>{lbl}</div></div>"
        return f"<div class='kbox'><div class='v'>{d['wr']*100:.0f}%</div><div class='l'>{lbl} ({d['w']}/{d['n']})</div></div>"
    winrow=("<div class='kpi'>"+_wk("win% past day",W.get("day"))+_wk("win% past week",W.get("week"))
            +_wk("win% overall",W.get("all"))+"</div>")
    # by edge magnitude
    et="".join(f'<tr><td>{lab}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
               f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
               for lab,n,w,pn in rep.get("by_edge",[]))
    # by city
    ct="".join(f'<tr><td>{esc(l)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
               f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
               for l,n,w,pn in rep.get("by_city",[]))
    city_bars=svg_bars([(l,pn) for l,n,w,pn in rep.get("by_city",[])])
    # by unit
    ut="".join(f'<tr><td>{unit_str(u)}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
               f'<td class="n">{(w/n*100):.0f}%</td><td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td></tr>'
               for u,n,w,pn in rep.get("by_unit",[]))
    # brier
    brier=""
    if rep.get("brier_model") is not None:
        bm,bkk=rep["brier_model"],rep["brier_market"]; v="up" if bm<bkk else "red"
        brier=("<div class='kpi'>"
          f"<div class='kbox'><div class='v'>{bm:.3f}</div><div class='l'>Brier model</div></div>"
          f"<div class='kbox'><div class='v'>{bkk:.3f}</div><div class='l'>Brier market</div></div>"
          f"<div class='kbox'><div class='v {v}'>{(bkk-bm):+.3f}</div><div class='l'>edge (lower wins; benchmark is the FINAL pre-settlement board)</div></div></div>")
        if rep.get("rps_n"):
            rv="up" if rep["rps_model"]<rep["rps_market"] else "red"
            brier+=("<div class='kpi'>"
              f"<div class='kbox'><div class='v'>{rep['rps_model']:.3f}</div><div class='l'>RPS model</div></div>"
              f"<div class='kbox'><div class='v'>{rep['rps_market']:.3f}</div><div class='l'>RPS market</div></div>"
              f"<div class='kbox'><div class='v {rv}'>{(rep['rps_market']-rep['rps_model']):+.3f}</div><div class='l'>RPS edge, n={rep['rps_n']} (distance-aware; the ladder headline. The benchmark is the final board, which folds in intraday obs the model does not ingest yet: red here is a sharpness gap vs a better-informed close, not miscalibration. Calibration health lives in the table below, sd(z), and the MAE chart; edge at ENTRY prices shows in CLV.)</div></div></div>")
        if rep.get("nowcast"):
            nw=rep["nowcast"]
            brier+=(f"<div class='note'>Nowcast shadow (same-day highs, FUTURE 5 gate = truncated wins CRPS and RPS at 30+ events): "
              f"n={nw['n']}, RPS truncated {nw['rps_t']:.3f} vs untruncated {nw['rps_u']:.3f}, "
              f"CRPS {nw['crps_t']:.2f} vs {nw['crps_u']:.2f}, truncated wins {nw['wins']}/{nw['n']}. "
              f"Plays stay on untruncated pricing until the gate passes.</div>")
    # raw
    # calibration curve: does an X% forecast happen X% of the time?
    caltab=""
    if rep.get("bins"):
        bt="".join(f'<tr><td>{int(lo*100)}-{int(lo*100)+10}%</td><td class="n">{n}</td>'
                   f'<td class="n">{fp*100:.0f}%</td><td class="n">{hr*100:.0f}%</td>'
                   f'<td class="n">{wlo*100:.0f}-{whi*100:.0f}%</td>'
                   f'<td class="n {"up" if wlo<=fp<=whi else "red"}">{(hr-fp)*100:+.0f}%</td></tr>'
                   for lo,n,fp,hr,wlo,whi in rep["bins"])
        caltab=("<h2 class='sec'>Calibration</h2>"
          "<div class='note'>Every ladder bucket ever logged, grouped by the model's stated probability. "
          "A calibrated model's actual column matches its forecast column. Rows are flagged red only when the stated "
          "probability falls OUTSIDE the 95% range of what actually happened (Wilson interval): with thin rows, "
          "a big-looking gap is usually just small-sample noise, and this column says which is which.</div>"
          "<table><thead><tr><th>Model prob</th><th class='n'>Buckets</th><th class='n'>Forecast</th>"
          "<th class='n'>Actual</th><th class='n'>95% range</th><th class='n'>Gap</th></tr></thead><tbody>"+bt+"</tbody></table>")
    # learned corrections currently applied
    lct=""
    if rep.get("calib"):
        rowsL="".join(f'<tr><td>{esc(l)}</td><td>{k.title()}</td><td class="n">{c:+.1f}\u00b0</td>'
                      f'<td class="n">{s:.1f}\u00b0</td><td class="n">{n}</td></tr>'
                      for l,k,c,s,n in rep["calib"])
        lct=("<h2 class='sec'>Learned corrections</h2>"
          "<div class='note'>Applied automatically before scoring, from each city's settled history: shift is the "
          "bias correction added to every ensemble member (shrunk when history is thin), width is the kernel "
          "dressing sigma (how much realized error exceeds raw ensemble spread). A persistent large shift usually "
          f"means the city's coordinates do not match Kalshi's settlement station. Pooled sigma: {rep.get('gsigma',DRESS_SIGMA_DEFAULT):.1f}\u00b0.</div>"
          "<table><thead><tr><th>City</th><th>Mkt</th><th class='n'>Shift</th><th class='n'>Width</th>"
          "<th class='n'>Settled</th></tr></thead><tbody>"+rowsL+"</tbody></table>")
    # by stated win probability: the go/no-go readout for betting only high-confidence cards
    pwt=""
    if rep.get("by_pwin"):
        pr="".join(f'<tr><td>{lab}</td><td class="n">{n}</td><td class="n">{w}/{n}</td>'
                   f'<td class="n">{ap*100:.0f}%</td><td class="n">{(w/n*100):.0f}%</td>'
                   f'<td class="n {"up" if pn>=0 else "red"}">{pn/BASE_UNIT_USD:+.1f}u</td>'
                   f'<td class="n {"up" if roi>=0 else "red"}">{roi*100:+.1f}%</td></tr>'
                   for lab,n,w,ap,pn,roi in rep["by_pwin"])
        pwt=("<h2 class='sec'>By win probability</h2>"
          "<div class='note'>Each play grouped by the win probability the model stated when the bet was logged. "
          "Two things to check before betting only the high-confidence cards: does the actual column roughly match "
          "the stated column (calibration), and does the 80%+ row have positive ROI, not just a high win rate? "
          "High-probability plays win small and lose big, so a few points of overconfidence flips them negative "
          "while still feeling like winning.</div>"
          "<table><thead><tr><th>Stated</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Avg stated</th>"
          "<th class='n'>Actual</th><th class='n'>P&amp;L</th><th class='n'>ROI</th></tr></thead><tbody>"+pr+"</tbody></table>")
    raw="".join(f'<tr><td>{esc(CITIES[r["code"]][3])}</td><td>{"H" if r["kind"]=="HIGH" else "L"} {r["target"][5:]}</td>'
                f'<td>{esc(r["sub"])}</td><td>{unit_str(r["units"])}</td><td class="pl">{r["side"]}@{r["entry"]*100:.0f}\u00a2</td>'
                f'<td class="n">{r["actual"]}\u00b0</td><td>{"WON" if r["won"] else "LOST"}</td>'
                f'<td class="n">{("%+.1f"%r["margin"]) if r["margin"] is not None else DOT}\u00b0</td>'
                f'<td class="n {"up" if r["pnl"]>=0 else "red"}">{r["pnl"]/BASE_UNIT_USD:+.1f}u</td></tr>'
                for r in rep.get("recent",[])[:60])
    html=(head("results",updated,_health_strip(health,alerts))+
      "<h2 class='sec'>Performance</h2>"+kpis+winrow+honest+chart+brier+calsec+
      "<h2 class='sec'>By city</h2><div class='card'>"+city_bars+"</div>"
      "<table><thead><tr><th>City</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+ct+"</tbody></table>"
      "<h2 class='sec'>By unit size</h2>"
      "<table><thead><tr><th>Size</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+ut+"</tbody></table>"
      "<h2 class='sec'>By edge size</h2>"
      "<div class='note'>The calibration check that matters most: a bigger edge should win more often. "
      "If the 25%+ row wins less than the 8-15% row, those fat edges are the model being wrong, not free money.</div>"
      "<table><thead><tr><th>Edge</th><th class='n'>Bets</th><th class='n'>W/L</th><th class='n'>Win%</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+et+"</tbody></table>"
      +pwt+caltab+lct+srct+
      "<h2 class='sec'>Every resolved bet</h2>"
      "<table><thead><tr><th>City</th><th>Mkt</th><th>Bucket</th><th>Size</th><th>Bet</th><th class='n'>Actual</th><th>Result</th><th class='n'>Margin</th><th class='n'>P&amp;L</th></tr></thead><tbody>"+raw+"</tbody></table>"
      "</div></body></html>")
    with open(os.path.join(OUT_DIR,"results.html"),"w",encoding="utf-8") as fp: fp.write(html)

# ------------------------------ main ------------------------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH,encoding="utf-8") as f: s=json.load(f)
        except Exception as e:
            # Never fall back to an empty state: on GitHub the workflow would
            # commit it and silently wipe the visible track record. Fail loudly;
            # a red run leaves the last good commit untouched.
            print("FATAL: weather_state.json is unreadable:",str(e)[:120])
            print("Refusing to start with a blank state. Restore weather_state.json from git history, then rerun.")
            sys.exit(3)
        if not (isinstance(s,dict) and isinstance(s.get("predictions"),dict) and isinstance(s.get("resolved"),list)):
            print("FATAL: weather_state.json schema is wrong (need a predictions dict and a resolved list).")
            print("Restore weather_state.json from git history, then rerun.")
            sys.exit(3)
        return s
    return {"predictions":{},"resolved":[]}

def save_state(s):
    tmp=STATE_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(s,f,indent=1,default=str)
    os.replace(tmp,STATE_PATH)

def notify_telegram(plays,health,alerts,rep):
    """Phone ping after each run (FUTURE item 4, shipped audit batch 10).
    Fires ONLY when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID exist in the
    environment (GitHub Actions secrets); otherwise a silent no-op. A
    notification failure must never fail the run."""
    tok=os.environ.get("TELEGRAM_BOT_TOKEN"); chat=os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat: return
    try:
        top=plays[0] if plays else None
        lines=["Nimbus "+dt.datetime.now(dt.timezone.utc).strftime("%b %d %H:%MZ"),
               f"{len(plays)} plays on the board, {health.get('new_24h',0)} new in 24h"]
        if top:
            lines.append(f"Top: {top['label']} {top['kind']} {top['bucket']} {top['side']} {top['units']}u @ {int(round(top['entry']*100))}c (p_win {int(round((top.get('p_win') or 0)*100))}%)")
        if rep.get("pnl"):
            p=rep["pnl"]; lines.append(f"Record {p['wins']}/{p['n']}  {p['net_units']:+.1f}u")
        if health.get("gated"): lines.append("Gated: "+", ".join(health["gated"][:3]))
        if alerts: lines.append("ALERT: "+alerts[0])
        url=os.environ.get("NIMBUS_PAGE_URL")
        if url: lines.append(url)
        body=json.dumps({"chat_id":chat,"text":chr(10).join(lines),"disable_web_page_preview":True}).encode()
        req=urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",data=body,
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=20) as r: r.read()
        print("Telegram: sent")
    except Exception as e:
        print("Telegram notify failed (non-fatal):",str(e)[:80])

def drift_alerts(state):
    """Display-only drift alarms (audit batch 7). These NEVER change behavior:
    they name a failure mode on the results header so the owner investigates
    before any knob moves. Auto-retuning beyond the existing bias/sigma
    learners stays forbidden; knob changes happen in owner sessions with a
    MODEL_VERSION bump (governance verdict, AUDIT_TODO section 11)."""
    al=[]
    res=[r for r in state.get("resolved",[]) if r.get("buckets") and not r.get("gated")]
    bk=[(b["mp"],b["hit"]) for r in res for b in r["buckets"] if b.get("mp") is not None]
    mk=[(b["mid"],b["hit"]) for r in res for b in r["buckets"] if b.get("mid") is not None]
    if len(bk)>=180 and len(mk)>=180:
        bm=lambda xs: sum((p-h)**2 for p,h in xs)/len(xs)
        gap_all=bm(bk)-bm(mk); gap_rec=bm(bk[-120:])-bm(mk[-120:])
        if gap_rec-gap_all>0.05:
            al.append("drift: recent Brier gap to market widened %+.2f"%(gap_rec-gap_all))
    bins=defaultdict(lambda:[0,0])
    for p,h in bk:
        i=min(9,int(p*10)); bins[i][0]+=1; bins[i][1]+=h
    for i in sorted(bins):
        n,k=bins[i]
        if n>=25 and abs(k/n-(i+0.5)/10)>0.20:
            al.append("calibration: %d-%d%% bin realizing %.0f%% (n=%d)"%(i*10,(i+1)*10,100*k/n,n))
    zs=[r["bias"]/r["psd"] for r in res[-60:] if r.get("bias") is not None and r.get("psd")]
    if len(zs)>=40:
        m=sum(zs)/len(zs); sdz=math.sqrt(sum((z-m)**2 for z in zs)/len(zs))
        if sdz>1.4: al.append("dispersion: sd(z)=%.2f, spreads too tight (overconfident)"%sdz)
        elif sdz<0.7: al.append("dispersion: sd(z)=%.2f, spreads too wide (underconfident)"%sdz)
    cal=calib_params(state); snap=state.get("calib_snapshot") or {}
    newsnap={}
    for k,v in cal.items():
        if isinstance(k,tuple):
            kk="%s|%s"%k; newsnap[kk]=round(v.get("corr",0.0),2)
            if kk in snap and v.get("n",0)>=8 and abs(newsnap[kk]-snap[kk])>1.0:
                al.append("correction jump: %s moved %+.1f -> %+.1f"%(kk,snap[kk],newsnap[kk]))
    state["calib_snapshot"]=newsnap
    return al

def main():
    os.makedirs(OUT_DIR,exist_ok=True)
    print("="*56); print("Nimbus  -",dt.datetime.now().strftime("%Y-%m-%d %H:%M")); print("="*56)
    state=load_state()
    if os.environ.get("NIMBUS_SHADOW_RUN")=="1":
        # Midday SHADOW run (checkpoint 1 build, FUTURE 5 stage 1): collect
        # paired nowcast snapshots and stop. No resolving, no board refresh,
        # no plays, no render, no Telegram: trading behavior and every
        # existing measurement (final-snapshot semantics, CLV close) are
        # untouched. Worst case this pass fails and nothing else notices.
        shadow_pass(state); save_state(state)
        print("\nShadow run complete."); return
    resolve_pending(state)
    shadow_pass(state)   # normal runs also collect when a city sits in the window (eastern cities hit it on the morning cron)
    rows,plays,health=score(state)
    alerts=drift_alerts(state)
    rep=compute_report(state)
    save_state(state)
    updated=dt.datetime.now().astimezone().strftime("%b %d %Y, %I:%M %p %Z")
    try:
        health["state_kb"]=os.path.getsize(STATE_PATH)//1024
        health["resolved_n"]=len(state.get("resolved",[]))
    except OSError: pass
    render_bets(rows,plays,updated,health); render_results(rep,updated,health,alerts)
    notify_telegram(plays,health,alerts,rep)
    print(f"\nPlays today: {len(plays)} | resolved: {rep.get('n_events',0)}")
    if rep.get("pnl"): print(f"Paper P&L: {rep['pnl']['net_units']:+.1f}u ({rep['pnl']['wins']}/{rep['pnl']['n']})")
    print("Dashboards ->",OUT_DIR)
    if os.environ.get("CI")!="true":
        try: webbrowser.open("file://"+os.path.join(OUT_DIR,"index.html"))
        except Exception: pass

if __name__=="__main__":
    try: main()
    except Exception as e:
        import traceback; traceback.print_exc(); print("ERROR:",e)
        # On GitHub a swallowed crash exits 0, the commit step runs, and a broken
        # run publishes as if it were healthy. Red runs are the honest signal.
        if os.environ.get("CI")=="true": sys.exit(1)
    if os.environ.get("CI")!="true" and sys.stdin.isatty():
        try: input("\nPress Enter to close...")
        except EOFError: pass
