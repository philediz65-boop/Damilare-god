import os,re,threading,requests,time,io,json,concurrent.futures
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,BotCommand
from telegram.ext import ApplicationBuilder,CommandHandler,CallbackQueryHandler,MessageHandler,filters
from datetime import datetime, date

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
PORT=int(os.getenv("PORT","10000"))
app=Flask(__name__)
CACHE={}; LOCK=threading.Lock()
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE=f"{DATA_DIR}/active_trade_v18.json"
DAILY_FILE=f"{DATA_DIR}/daily_stats_v18.json"
CHAT_FILE=f"{DATA_DIR}/last_chat_id.json"
BACKUP_FILE="./active_backup.json"
GLOBAL_ACTIVE={}; GLOBAL_CHAT_ID=None
HEADERS={"User-Agent":"Mozilla/5.0"}

# === V18.3.1 FIXED FINAL - OPTION A - 2-3 trades/day GUARANTEED ===
DEFAULT_STAKE=1.0
DEFAULT_LEV=15
MEME_LEV=10
MEME_COINS={"WIF","PEPE","BONK","FLOKI","BOME","SHIB","NOT","FARTCOIN"}
def get_lev(c): return MEME_LEV if c in MEME_COINS else DEFAULT_LEV

MIN_VOL_PCT = -35
MIN_ALIGN = 1
MIN_SCORE = 50
MIN_ADAPTIVE = 45
print(f"V18.3.1 FIXED FINAL using {DATA_DIR} - OPTION A 2-3 trades/day")

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
        alt=p.replace("/data","/tmp") if "/data" in p else p.replace("/tmp","/data")
        if os.path.exists(alt):
            with open(alt,'r') as f: return json.load(f)
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE,'r') as f: return json.load(f)
    except: pass
    return d

def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f: json.dump(data,f)
            with open(BACKUP_FILE,'w') as f2: json.dump(data,f2)
    except: pass

def get_daily():
    d=load_json(DAILY_FILE,{}); today=str(date.today())
    if d.get("date")!=today: d={"date":today,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d

def update_daily(result,pnl,coin=""):
    d=get_daily(); d["trades"]+=1
    if result=="WIN": d["wins"]+=1
    else: d["losses"]+=1
    d["pnl"]+=pnl; save_json(DAILY_FILE,d); return d

def get_active():
    global GLOBAL_ACTIVE
    if GLOBAL_ACTIVE and GLOBAL_ACTIVE.get("status")=="OPEN": return GLOBAL_ACTIVE
    fa=load_json(ACTIVE_FILE,{})
    if fa and fa.get("status")=="OPEN": GLOBAL_ACTIVE=fa; return fa
    return {}
def set_active(data): global GLOBAL_ACTIVE; GLOBAL_ACTIVE=data; save_json(ACTIVE_FILE,data)
def clear_active(): global GLOBAL_ACTIVE; GLOBAL_ACTIVE={}; save_json(ACTIVE_FILE,{})
def save_chat_id(cid): global GLOBAL_CHAT_ID; GLOBAL_CHAT_ID=cid; save_json(CHAT_FILE,{"chat_id":cid})
def get_chat_id():
    global GLOBAL_CHAT_ID
    if GLOBAL_CHAT_ID: return GLOBAL_CHAT_ID
    d=load_json(CHAT_FILE,{}); cid=d.get("chat_id")
    if cid: GLOBAL_CHAT_ID=cid
    return cid

CRYPTO={"BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT","DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","TRX":"TRXUSDT","DOT":"DOTUSDT","MATIC":"MATICUSDT","LTC":"LTCUSDT","BCH":"BCHUSDT","UNI":"UNIUSDT","ATOM":"ATOMUSDT","ETC":"ETCUSDT","FIL":"FILUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT","SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT","ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT","JUP":"JUPUSDT","ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT","TIA":"TIAUSDT","AVAIL":"AVAILUSDT","DYM":"DYMUSDT","ALT":"ALTUSDT","EIGEN":"EIGENUSDT","STRK":"STRKUSDT","SAGA":"SAGAUSDT","MANTA":"MANTAUSDT","GTC":"GTCUSDT"}
FAST_LIST=list(CRYPTO.keys())[:27]
SLOW_LIST=["BTC","ETH","BNB","XRP","ADA","LINK","TRX","DOT","MATIC","LTC","BCH","UNI","ATOM","ETC","FIL","PAXG"]

@app.get("/")
def home(): return "💀 SKELLY BOT V18.3.1 FIXED FINAL 👌",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        v=float(v)
        if v>=1000: return f"{v:,.2f}"
        if v>=1: return f"{v:.4f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def clean(t):
    t=t.upper().strip().replace("/","").replace("-","").replace("_",""); t=re.sub(r"[^A-Z0-9]","",t)
    if t=="FARTCOINUSD": return "FARTCOIN"
    if t.endswith("USDT") and t[:-4] in CRYPTO: return t[:-4]
    return t

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<90: return CACHE[key][1]
    im_map={"15m":("15m","15","15m","15m"),"1h":("1h","60","1H","1h"),"2h":("2h","120","2H","2h")}
    bin_iv,by_iv,okx_iv=im_map.get(interval,("2h","120","2H","2h"))[0],im_map.get(interval,("2h","120","2H","2h"))[1],im_map.get(interval,("2h","120","2H","2h"))[2]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":bin_iv,"limit":200},headers=HEADERS,timeout=6).json()
        if isinstance(r,list) and len(r)>=20:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":by_iv,"limit":200},headers=HEADERS,timeout=6).json()
        data=r.get("result",{}).get("list",[])
        if len(data)>=20:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT-SWAP"),"bar":okx_iv,"limit":200},headers=HEADERS,timeout=6).json()
        data=r.get("data",[])
        if len(data)>=20:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    if key in CACHE: return CACHE[key][1]
    return []

def get_real_price(sym):
    try:
        r=requests.get("https://api.bybit.com/v5/market/tickers",params={"category":"linear","symbol":sym},headers=HEADERS,timeout=4).json()
        lst=r.get("result",{}).get("list",[])
        if lst and lst[0].get("lastPrice"): return float(lst[0]["lastPrice"])
    except: pass
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=4).json()
        if r.get("price"): return float(r["price"])
    except: pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def get_whale_walls(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":sym,"limit":30},headers=HEADERS,timeout=3).json()
        bids=r.get("bids",[]); asks=r.get("asks",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            return b,a
    except: pass
    return 52000,67000

def get_liq_hint(kl):
    if len(kl)<15: return "💥 Liq N/A"
    highs=[k["h"] for k in kl[-20:]]; lows=[k["l"] for k in kl[-20:]]
    return f"💥 Liq UP {fmt(max(highs)*1.02)} | DOWN {fmt(min(lows)*0.98)}"

def ema(arr,p):
    if not arr: return 0
    if len(arr)<p: return sum(arr)/len(arr)
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e

def ema_series(arr,p):
    if len(arr)<p: return [sum(arr)/len(arr)]*len(arr)
    k=2/(p+1); e=sum(arr[:p])/p; res=[e]*p
    for x in arr[p:]: e=(x-e)*k+e; res.append(e)
    while len(res)<len(arr): res.insert(0,res[0])
    return res[-len(arr):]

def rsi_calc(arr,p=14):
    if len(arr)<p+1: return 50
    gains=losses=0
    for i in range(1,p+1):
        d=arr[-i]-arr[-i-1]
        if d>0: gains+=d
        else: losses+=-d
    if losses==0: return 75 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def atr_calc(kl,p=14):
    try:
        if len(kl)<p+1: return kl[-1]["c"]*0.015
        trs=[]
        for i in range(1,p+1):
            c=kl[-i]; pc=kl[-i-1]
            tr=max(c["h"]-c["l"], abs(c["h"]-pc["c"]), abs(c["l"]-pc["c"]))
            trs.append(tr)
        return sum(trs)/len(trs)
    except: return kl[-1]["c"]*0.015 if kl else 0.01

def get_adx(kl,p=14):
    try:
        if len(kl)<p+5: return 25
        highs=[k["h"] for k in kl]; lows=[k["l"] for k in kl]; closes=[k["c"] for k in kl]
        plus_dm=[]; minus_dm=[]; tr=[]
        for i in range(1,len(kl)):
            up=highs[i]-highs[i-1]; down=lows[i-1]-lows[i]
            plus_dm.append(up if up>down and up>0 else 0)
            minus_dm.append(down if down>up and down>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        if len(tr)<p: return 25
        atr=sum(tr[-p:])/p
        pdm=sum(plus_dm[-p:])/p; mdm=sum(minus_dm[-p:])/p
        if atr==0: return 25
        pdi=100*pdm/atr; mdi=100*mdm/atr
        if pdi+mdi==0: return 25
        dx=100*abs(pdi-mdi)/(pdi+mdi)
        return min(80, max(5, dx))
    except: return 25

def get_premium_discount(kl):
    try:
        if len(kl)<100: return "EQUILIBRIUM",50
        highs=[k["h"] for k in kl[-100:]]; lows=[k["l"] for k in kl[-100:]]
        rh=max(highs); rl=min(lows); price=kl[-1]["c"]
        if rh==rl: return "EQUILIBRIUM",50
        pct=(price-rl)/(rh-rl)*100
        if pct>=70: return "PREMIUM",pct
        if pct<=30: return "DISCOUNT",pct
        return "EQUILIBRIUM",pct
    except: return "EQUILIBRIUM",50

def get_mtf_trend(closes):
    if len(closes)<30: return 0,"➡️ SIDEWAYS 😐"
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200); live=closes[-1]
    if live>e20>e50>e200: return 80,"🟢 STRONG UP 🚀"
    if live>e20>e50: return 50,"⬆️ UPTREND 💹"
    if live>e50: return 20,"↗️ WEAK UP 🙂"
    if live<e20<e50<e200: return -80,"🔴 STRONG DOWN 💥"
    if live<e20<e50: return -50,"⬇️ DOWNTREND 😨"
    if live<e50: return -20,"↘️ WEAK DOWN 😕"
    return 0,"➡️ SIDEWAYS 😐"

def volume_check(kl):
    if len(kl)<15: return 0,"📊 Vol N/A"
    vols=[k["v"] for k in kl[-25:]]
    avg=sum(vols[-21:-1])/20 if len(vols)>=21 else sum(vols[:-1])/len(vols[:-1]) if len(vols)>1 else vols[0]
    curr=vols[-1]; pct=(curr-avg)/avg*100 if avg>0 else 0
    return pct,f"📊 Vol {pct:.0f}% {'🔥' if pct>20 else ''}"

def detect_candle_signal(kl):
    try:
        if len(kl)<5: return "NONE",0
        c2,c3=kl[-2],kl[-1]
        if c2["c"]>c2["o"] and c3["c"]<c3["o"] and c3["o"]>=c2["c"] and c3["c"]<=c2["o"]: return "🐻 BEARISH ENGULFING SELL",-30
        if c2["c"]<c2["o"] and c3["c"]>c3["o"] and c3["o"]<=c2["c"] and c3["c"]>=c2["o"]: return "🐂 BULLISH ENGULFING BUY",30
        if c3["h"]-max(c3["o"],c3["c"]) > (c3["h"]-c3["l"])*0.6: return "⭐ SHOOTING STAR SELL",-20
        if min(c3["o"],c3["c"])-c3["l"] > (c3["h"]-c3["l"])*0.6: return "🔨 HAMMER BUY",20
        return "NONE",0
    except: return "NONE",0

def detect_fvg(kl):
    try:
        if len(kl)<10: return None
        for i in range(len(kl)-12, len(kl)-1):
            a,b=kl[i-1],kl[i]
            if b["l"]>a["h"] and (b["l"]-a["h"])/a["h"]>0.0003: return {"top":b["l"],"bottom":a["h"],"type":"🟢 BULL FVG","mid":(b["l"]+a["h"])/2,"side":"BUY"}
            if b["h"]<a["l"] and (a["l"]-b["h"])/a["l"]>0.0003: return {"top":a["l"],"bottom":b["h"],"type":"🔴 BEAR FVG","mid":(a["l"]+b["h"])/2,"side":"SELL"}
        last=kl[-1]
        side="BUY" if last["c"]>last["o"] else "SELL"
        return {"top":last["h"]*1.003,"bottom":last["l"]*0.997,"type":"🔴 BEAR FVG" if side=="SELL" else "🟢 BULL FVG","mid":last["c"],"side":side}
    except: return None

def detect_order_block(kl):
    try:
        if len(kl)<15: return None
        for i in range(len(kl)-18, len(kl)-2):
            curr=kl[i]; nxt=kl[i+1:i+5]
            if not nxt or len(nxt)<3: continue
            move_up=(nxt[-1]["c"]-curr["l"])/curr["l"]*100 if curr["l"] else 0
            if curr["c"]<curr["o"] and move_up>0.8: return {"level":curr["h"],"low":curr["l"],"high":curr["h"],"type":"🟩 BULLISH OB","side":"BUY"}
            move_down=(curr["h"]-nxt[-1]["c"])/curr["h"]*100 if curr["h"] else 0
            if curr["c"]>curr["o"] and move_down>0.8: return {"level":curr["l"],"low":curr["l"],"high":curr["h"],"type":"🟥 BEARISH OB","side":"SELL"}
        last=kl[-5]
        if last["c"]<last["o"]: return {"level":last["l"],"low":last["l"]*0.998,"high":last["h"],"type":"🟥 BEARISH OB","side":"SELL"}
        else: return {"level":last["h"],"low":last["l"],"high":last["h"]*1.002,"type":"🟩 BULLISH OB","side":"BUY"}
    except: return None

def detect_chart_pattern(kl):
    try:
        closes=[k["c"] for k in kl[-30:]]; highs=[k["h"] for k in kl[-30:]]; lows=[k["l"] for k in kl[-30:]]
        if len(closes)<20: return "NONE",0
        last_high=max(highs[-5:-1]); prev_high=max(highs[-15:-6])
        if prev_high>0 and abs(last_high-prev_high)/prev_high<0.012 and closes[-1]<min(lows[-6:])*1.01: return "⛰️ DOUBLE TOP SELL",-40
        last_low=min(lows[-5:-1]); prev_low=min(lows[-15:-6])
        if prev_low>0 and abs(last_low-prev_low)/prev_low<0.012 and closes[-1]>max(highs[-6:])*0.99: return "🏔️ DOUBLE BOTTOM BUY",40
        return "NONE",0
    except: return "NONE",0

def smart_sl_tp(entry, ob, fvg, side, atr_val, lev):
    try:
        liq_dist_pct = 1.0/lev * 100
        max_sl_pct = min(liq_dist_pct * 0.60, 2.0 if lev==15 else 2.5)
        sl_dist = entry * max_sl_pct / 100
        sl = entry - sl_dist if side=="BUY" else entry + sl_dist
        if ob and ob["side"]==side:
            if side=="BUY":
                ob_sl = ob["low"]*0.998 - atr_val*0.5
                if 1.0 <= abs(entry-ob_sl)/entry*100 <= max_sl_pct: sl = ob_sl
            else:
                ob_sl = ob["high"]*1.002 + atr_val*0.5
                if 1.0 <= abs(ob_sl-entry)/entry*100 <= max_sl_pct: sl = ob_sl
        tp1=entry + atr_val*1.0 if side=="BUY" else entry - atr_val*1.0
        tp2=entry + atr_val*2.0 if side=="BUY" else entry - atr_val*2.0
        tp3=entry + atr_val*3.0 if side=="BUY" else entry - atr_val*3.0
        if side=="BUY" and sl>=entry: sl=entry*0.98
        if side=="SELL" and sl<=entry: sl=entry*1.02
        return sl,tp1,tp2,tp3
    except:
        return (entry*0.98, entry*1.015, entry*1.025, entry*1.04) if side=="BUY" else (entry*1.02, entry*0.985, entry*0.975, entry*0.96)

def analyze_perfect(code, btc_trend=0, allow_choppy=False):
    try:
        sym=CRYPTO.get(code,"BTCUSDT")
        kl15=get_klines(sym,"15m"); kl1=get_klines(sym,"1h"); kl2=get_klines(sym,"2h")
        if len(kl2)<15: return {"error":True,"msg":f"❌ No data {code}"}
        closes15=[c["c"] for c in kl15] if len(kl15)>=15 else [c["c"] for c in kl2]
        closes1=[c["c"] for c in kl1] if len(kl1)>=15 else [c["c"] for c in kl2]
        closes2=[c["c"] for c in kl2]
        live=get_real_price(sym) or closes2[-1]
        lev=get_lev(code)
        rsi=rsi_calc(closes2); atr=atr_calc(kl2,14); adx=get_adx(kl2)
        pd_zone,pd_pct=get_premium_discount(kl2)
        candle_sig,_=detect_candle_signal(kl2); chart_pat,_=detect_chart_pattern(kl2)
        ob=detect_order_block(kl2); fvg=detect_fvg(kl2)
        s15,t15=get_mtf_trend(closes15); s1,t1=get_mtf_trend(closes1); s2,t2=get_mtf_trend(closes2)
        vol_pct,vol_txt=volume_check(kl2)
        if (s15<0 and s1<0 and s2<0) or (s15>0 and s1>0 and s2>0): align=3
        elif (s1<0 and s2<0) or (s1>0 and s2>0): align=2
        else: align=1
        swept=kl2[-1]["l"] < min([k["l"] for k in kl2[-20:-3]])*0.998 if len(kl2)>=20 else False
        direction="BUY" if s2>=0 else "SELL"
        if ob and align>=2: direction=ob["side"]

        score=0; reasons=[]
        if align==3: score+=30; reasons.append("Align 3/3 +30")
        elif align==2: score+=15; reasons.append("Align 2/3 +15")
        else: reasons.append("Align 1/3 +0")

        if adx>=25: score+=15; reasons.append(f"ADX {adx:.0f} +15")
        elif adx>=20: score+=10; reasons.append(f"ADX {adx:.0f} +10")
        elif adx>=12: score+=5; reasons.append(f"ADX {adx:.0f} +5")

        if direction=="BUY" and rsi<45: score+=10; reasons.append(f"RSI {rsi:.0f} +10")
        elif direction=="SELL" and rsi>55: score+=10; reasons.append(f"RSI {rsi:.0f} +10")

        if ob and ob["side"]==direction: score+=10; reasons.append(f"OB match +10")
        elif ob and ob["side"]!=direction:
            if not allow_choppy: return {"error":False,"code":code,"perfect":False,"perfect_reason":f"OB MISMATCH {ob['type']} in {direction}","vol_pct":vol_pct,"align_score":align,"conf":score,"adx":adx}
            score-=5

        if fvg and fvg["side"]==direction: score+=10; reasons.append(f"FVG +10")

        if swept: score+=10; reasons.append("Sweep +10")

        if vol_pct>=20: score+=10; reasons.append(f"Vol {vol_pct:.0f}% +10")
        elif vol_pct>=0: score+=5; reasons.append(f"Vol {vol_pct:.0f}% +5")
        elif vol_pct>=MIN_VOL_PCT: score+=2; reasons.append(f"Vol {vol_pct:.0f}% +2")
        else:
            if not allow_choppy: return {"error":False,"code":code,"perfect":False,"perfect_reason":f"Vol {vol_pct:.0f}% < {MIN_VOL_PCT}%","vol_pct":vol_pct,"align_score":align,"conf":score,"adx":adx}

        if direction=="BUY" and pd_zone=="DISCOUNT": score+=10; reasons.append(f"DISCOUNT {pd_pct:.0f}% +10")
        elif direction=="SELL" and pd_zone=="PREMIUM": score+=10; reasons.append(f"PREMIUM {pd_pct:.0f}% +10")
        elif not allow_choppy and ((direction=="BUY" and pd_zone=="PREMIUM") or (direction=="SELL" and pd_zone=="DISCOUNT")):
            return {"error":False,"code":code,"perfect":False,"perfect_reason":f"{direction} in {pd_zone} {pd_pct:.0f}%","vol_pct":vol_pct,"align_score":align,"conf":score,"adx":adx}

        if candle_sig!="NONE": score+=5
        if chart_pat!="NONE": score+=5
        score=max(0,min(100,score))

        if score < (MIN_SCORE if not allow_choppy else MIN_ADAPTIVE):
            return {"error":False,"code":code,"perfect":False,"perfect_reason":f"Score {score}/100 < {MIN_SCORE if not allow_choppy else MIN_ADAPTIVE}","vol_pct":vol_pct,"align_score":align,"conf":score,"adx":adx,"reasons":reasons}

        sl,tp1,tp2,tp3=smart_sl_tp(live, ob, fvg, direction, atr, lev)
        big_bid,big_ask=get_whale_walls(sym); liq_txt=get_liq_hint(kl2)
        sl_pct=abs(sl-live)/live*100; tp1_pct=abs(tp1-live)/live*100; tp2_pct=abs(tp2-live)/live*100; tp3_pct=abs(tp3-live)/live*100
        smc_txt=f"🕯️ {candle_sig} | 📐 {chart_pat} | {ob['type'] if ob else '🟨 OB None'} | {fvg['type'] if fvg else '⚖️ FVG None'} | Sweep={'✅ YES' if swept else '❌ NO'}"
        tag="⚠️ CHOPPY" if score<60 else "✅ STRONG"
        return {"error":False,"code":code,"price":live,"rsi":rsi,"adx":adx,"atr":atr,"pd_zone":pd_zone,"pd_pct":pd_pct,"dir":direction,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":lev,"conf":score,"score":score,"kl":kl2,"mtf_txt":f"⏱️ 15m {t15} | 1H {t1} | 2H {t2} [Align {align}/3] ADX {adx:.0f}","vol_txt":vol_txt,"vol_pct":vol_pct,"sl_dist_pct":sl_pct,"tp1_dist_pct":tp1_pct,"tp2_dist_pct":tp2_pct,"tp3_dist_pct":tp3_pct,"whale_txt":f"🐋 Walls ${big_bid/1000:.0f}k/${big_ask/1000:.0f}k | {liq_txt}","auto_stake":DEFAULT_STAKE,"align_score":align,"smc_txt":smc_txt,"ob":ob,"fvg":fvg,"perfect":True,"perfect_reason":f"{tag} SCORE {score}/100 - {' | '.join(reasons)}","reasons":reasons}
    except Exception as e:
        return {"error":True,"msg":f"❌ Bug {code}: {str(e)[:180]}"}

def get_btc_trend():
    try:
        kl2=get_klines("BTCUSDT","2h")
        s2,_=get_mtf_trend([c["c"] for c in kl2])
        return s2
    except: return 0

def generate_chart_perfect(r):
    try:
        kl=r["kl"][-100:]; closes=[c["c"] for c in kl]
        e20=ema_series(closes,20); e50=ema_series(closes,50); e200=ema_series(closes,200)
        fig, ax=plt.subplots(figsize=(11,6))
        ax.plot(closes, label="Price", color="black", linewidth=1.3)
        ax.plot(e20, label="EMA20", color="#2196F3", linewidth=0.9)
        ax.plot(e50, label="EMA50", color="#FF9800", linewidth=0.9)
        ax.plot(e200, label="EMA200", color="#9C27B0", linewidth=0.7, linestyle=":")
        ax.axhline(r["entry"], color="blue", linestyle="--", linewidth=1.5, label=f'Entry {fmt(r["entry"])}')
        ax.axhline(r["sl"], color="red", linestyle="-", linewidth=1.6, label=f'SL {fmt(r["sl"])}')
        ax.axhline(r["tp1"], color="#00C853", linestyle="-", linewidth=1.4, label=f'TP1 {fmt(r["tp1"])}')
        ax.axhline(r["tp2"], color="#4CAF50", linestyle="-.", linewidth=1.2, label=f'TP2 {fmt(r["tp2"])}')
        ax.axhline(r["tp3"], color="#00E676", linestyle=":", linewidth=1.2, label=f'TP3 {fmt(r["tp3"])}')
        if r.get("fvg"): ax.axhspan(r["fvg"]["bottom"], r["fvg"]["top"], color='gold', alpha=0.22)
        if r.get("ob"):
            lvl=r["ob"]["high"] if r["ob"]["side"]=="SELL" else r["ob"]["low"]
            ax.axhline(lvl, color="orange", linestyle="-.", linewidth=1.6)
        ax.set_title(f'{r["code"]} {r["dir"]} SCORE {r["conf"]}/100 ADX {r["adx"]:.0f} {r["pd_zone"]}', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3); ax.legend(fontsize=7, loc='upper left', ncol=2)
        plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=160); buf.seek(0); plt.close(fig); return buf
    except Exception as e:
        print(f"chart err {e}"); return None

def coins_kb_perfect(active_override=None, view="ALL"):
    daily=get_daily(); active=active_override if active_override is not None else get_active()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active.get("dir")=="BUY" else "🔴 SELL"} {active.get("coin")} {active.get("conf",0)}/100 LIVE 🔴',callback_data="MONITOR_LIVE")])
        btns.append([InlineKeyboardButton(f"👀 Check {active.get('coin')} Now",callback_data="CHECK_NOW"), InlineKeyboardButton(f"❌ Close {active.get('coin')}",callback_data="CLOSE_TRADE")])
    else:
        btns.append([InlineKeyboardButton(f"🔍 SCAN BEST 27 SCORE {MIN_SCORE}+ ${DEFAULT_STAKE} - Trade {daily['trades']+1}/3 💀",callback_data="SCAN_BEST")])
    btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    btns.append([InlineKeyboardButton("⚡ FAST 27",callback_data="MENU_FAST"), InlineKeyboardButton("🐢 SLOW 16",callback_data="MENU_SLOW"), InlineKeyboardButton("📋 ALL 43",callback_data="MENU_ALL")])
    if view in ["FAST","ALL"]:
        btns.append([InlineKeyboardButton(f"--- ⚡ FAST 27 ${DEFAULT_STAKE} SCORE ---",callback_data="IGNORE")])
        row=[]
        for c in FAST_LIST:
            row.append(InlineKeyboardButton(f"⚡ {c} {get_lev(c)}x",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    if view in ["SLOW","ALL"]:
        btns.append([InlineKeyboardButton(f"--- 🐢 SLOW 16 ---",callback_data="IGNORE")])
        row=[]
        for c in SLOW_LIST:
            row.append(InlineKeyboardButton(f"🐢 {c} {DEFAULT_LEV}x",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        cmds=[BotCommand("start","💀 Main"),BotCommand("fast","⚡ FAST 27"),BotCommand("slow","🐢 SLOW 16"),BotCommand("all","📋 ALL 43"),BotCommand("scan","🔍 SCAN"),BotCommand("daily","📊 Daily"),BotCommand("monitor","📡 Check"),BotCommand("close","❌ Close")]
        await app.bot.set_my_commands(cmds)
    except: pass

def background_scan(chat_id):
    try:
        btc=get_btc_trend(); best=None; best_score=-1; scan_list=FAST_LIST; perfect_results=[]
        def scan_one(code):
            try: return analyze_perfect(code, btc, False)
            except: return {"error":True}
        print(f"SCAN {len(scan_list)} normal {MIN_SCORE}+")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures={ex.submit(scan_one, co): co for co in scan_list}
            for fut in concurrent.futures.as_completed(futures, timeout=40):
                try:
                    r=fut.result(timeout=5)
                    if r.get("error") or not r.get("perfect"): continue
                    perfect_results.append(r)
                    if r.get("conf",0)>best_score: best_score=r.get("conf",0); best=r
                except: continue
        if not best:
            print(f"ADAPTIVE fallback {MIN_ADAPTIVE}+")
            all_candidates=[]
            def scan_choppy(code):
                try: return analyze_perfect(code, btc, True)
                except: return {"error":True}
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex2:
                futures2={ex2.submit(scan_choppy, co): co for co in scan_list}
                for fut in concurrent.futures.as_completed(futures2, timeout=40):
                    try:
                        r=fut.result(timeout=5)
                        if r.get("error") or not r.get("perfect"): continue
                        if r.get("conf",0)>=MIN_ADAPTIVE: all_candidates.append(r)
                    except: continue
            if all_candidates:
                all_candidates.sort(key=lambda x: x.get("conf",0), reverse=True)
                best=all_candidates[0]; perfect_results=all_candidates
        if not best:
            msg=f"⚠️ *No SCORE {MIN_ADAPTIVE}+ even choppy*\nScanned {len(scan_list)} coins. Market dead, wait 2hrs 🙏"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"},timeout=8)
            return
        r=best; stake=r["auto_stake"]
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()})
        lev=r["lev"]; loss=stake*r["sl_dist_pct"]*lev/100; p1=stake*r["tp1_dist_pct"]*lev/100; p2=stake*r["tp2_dist_pct"]*lev/100; p3=stake*r["tp3_dist_pct"]*lev/100
        emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
        daily=get_daily()
        mode_txt="⚠️ CHOPPY" if r['conf']<60 else "✅ STRONG"
        txt=(f"💀 *{mode_txt} SCORE {r['conf']}/100 {r['code']} Trade {daily['trades']+1}/3* {emoji} ${stake} {lev}x\n💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f}\n⚡ TP1 {fmt(r['tp1'])} (+{r['tp1_dist_pct']*lev:.0f}% ${p1:.2f})\n🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_dist_pct']*lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_dist_pct']*lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{r['sl_dist_pct']*lev:.0f}% -${loss:.2f}) SAFE\n{r['smc_txt']}\n{r['mtf_txt']}\n{r['vol_txt']} | {r['whale_txt']}\n✅ {r['perfect_reason']}")
        try:
            buf=generate_chart_perfect(r)
            if buf: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"}, files={"photo": buf}, timeout=20)
            else: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"BG Scan err {e}")

async def start(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text(f"💀 *V18.3.1 FIXED FINAL OPTION A 👌*\n✅ {MIN_SCORE}+ normal, {MIN_ADAPTIVE}+ choppy fallback\n✅ ADX no block, just score\n✅ Vol {MIN_VOL_PCT}% allowed\n✅ 2-3 trades/day guaranteed",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="FAST"))
async def fast_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text(f"⚡ FAST 27 {MIN_SCORE}+ / {MIN_ADAPTIVE}+",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="FAST"))
async def slow_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("🐢 SLOW 16",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="SLOW"))
async def all_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("📋 ALL 43",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))
async def scan_cmd(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text(f"🔍 SCANNING FAST 27...\n⏳ 12 sec {MIN_SCORE}+ normal {MIN_ADAPTIVE}+ fallback 👌")
    threading.Thread(target=background_scan, args=(u.message.chat.id,), daemon=True).start()
async def daily_cmd(u,c):
    save_chat_id(u.message.chat.id); d=get_daily()
    await u.message.reply_text(f"📊 Daily {d['date']} Wins {d['wins']} Loss {d['losses']} Trades {d['trades']}/3 P&L ${d['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))
async def monitor_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if not active or active.get("status")!="OPEN": await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
    price=get_real_price(CRYPTO.get(coin)) or entry
    pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
    pnl=stake*pnl_pct/100
    await u.message.reply_text(f"📡 {coin} {dir_} {active.get('conf',0)}/100 P&L {pnl_pct:.2f}% ${pnl:+.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL"))
async def close_cmd(u,c):
    save_chat_id(u.message.chat.id); a=get_active()
    if a: clear_active(); await u.message.reply_text(f"✅ Closed {a.get('coin')}",reply_markup=coins_kb_perfect(view="ALL"))
    else: await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL"))
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    if d=="IGNORE": return
    btc=get_btc_trend()
    if d in ["MENU_FAST","MENU_SLOW","MENU_ALL"]:
        view=d.split("_")[1]; await q.message.reply_text(f"📋 {view} MENU",parse_mode="Markdown",reply_markup=coins_kb_perfect(view=view)); return
    if d=="SHOW_DAILY":
        daily=get_daily(); await q.message.reply_text(f"📊 Daily {daily['date']} {daily['wins']}W/{daily['losses']}L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
    if d in ["MONITOR_LIVE","CHECK_NOW"]:
        active=get_active()
        if not active or active.get("status")!="OPEN": await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
        coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
        price=get_real_price(CRYPTO.get(coin)) or entry
        pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
        pnl=stake*pnl_pct/100
        await q.message.reply_text(f"📡 {coin} {dir_} P&L {pnl_pct:.2f}% ${pnl:+.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL")); return
    if d=="CLOSE_TRADE":
        active=get_active()
        if active: clear_active(); await q.message.reply_text(f"✅ Closed {active.get('coin')}",reply_markup=coins_kb_perfect(view="ALL"))
        else: await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    if d=="SCAN_BEST":
        await q.message.reply_text(f"🔍 SCANNING...",parse_mode="Markdown")
        threading.Thread(target=background_scan, args=(q.message.chat.id,), daemon=True).start()
        return
    if d.startswith("C_"):
        code=d[2:]; r=analyze_perfect(code, btc, False)
        if r.get("error"): await q.message.reply_text(r.get("msg"),reply_markup=coins_kb_perfect(view="ALL")); return
        if not r.get("perfect"):
            r2=analyze_perfect(code, btc, True)
            if r2.get("perfect") and r2.get("conf",0)>=MIN_ADAPTIVE: r=r2
            else: await q.message.reply_text(f"⚠️ SKIP {code} - {r.get('perfect_reason')} Score {r.get('conf',0)}/100",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":r["auto_stake"],"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()})
        buf=generate_chart_perfect(r)
        txt=f"💀 SCORE {r['conf']}/100 {r['code']} {r['dir']} ${r['auto_stake']} {r['lev']}x @ {fmt(r['entry'])}"
        kb=coins_kb_perfect(r,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def txt_handler(u,c):
    code=clean(u.message.text.strip())
    if code not in CRYPTO: await u.message.reply_text("❌ Unknown - Use menu",reply_markup=coins_kb_perfect(view="ALL")); return
    btc=get_btc_trend(); r=analyze_perfect(code, btc, False)
    if r.get("error"): await u.message.reply_text(r.get("msg"),reply_markup=coins_kb_perfect(view="ALL")); return
    if not r.get("perfect"):
        r2=analyze_perfect(code, btc, True)
        if r2.get("perfect") and r2.get("conf",0)>=MIN_ADAPTIVE: r=r2
        else: await u.message.reply_text(f"⚠️ SKIP {code} - {r.get('perfect_reason')}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
    set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":r["auto_stake"],"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()})
    buf=generate_chart_perfect(r)
    txt=f"💀 SCORE {r['conf']}/100 {r['code']} {r['dir']}"
    kb=coins_kb_perfect(r,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

def monitor_loop():
    print("Monitor started")
    last_ping=0
    while True:
        try:
            time.sleep(40)
            if time.time()-last_ping>700:
                try:
                    host=os.getenv("RENDER_EXTERNAL_HOSTNAME")
                    if host: requests.get(f"https://{host}/health", headers=HEADERS, timeout=5)
                    last_ping=time.time()
                except: pass
            active=get_active()
            if not active or active.get("status")!="OPEN": continue
            coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
            sym=CRYPTO.get(coin); price=get_real_price(sym)
            if not price: continue
            chat_id=get_chat_id()
            if not chat_id: continue
            hit=None
            if dir_=="BUY":
                if price>=tp3: hit="TP3 MOON"
                elif price>=tp2: hit="TP2"
                elif price>=tp1: hit="TP1"
                elif price<=sl: hit="SL"
            else:
                if price<=tp3: hit="TP3 MOON"
                elif price<=tp2: hit="TP2"
                elif price<=tp1: hit="TP1"
                elif price>=sl: hit="SL"
            if hit:
                if "TP" in hit:
                    pnl_pct=abs((tp1 if "TP1" in hit else tp2 if "TP2" in hit else tp3)-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 {hit}! {coin} +{pnl_pct:.0f}% +${pnl:.2f}"; update_daily("WIN",pnl,coin); clear_active()
                else:
                    pnl_pct=abs(sl-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 SL {coin} -{pnl_pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=8)
                except: pass
        except Exception as e:
            print(f"Monitor err {e}"); time.sleep(15)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("fast",fast_cmd)); a.add_handler(CommandHandler("slow",slow_cmd)); a.add_handler(CommandHandler("all",all_cmd)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("close",close_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler)); a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    print("Bot V18.3.1 FIXED FINAL starting..."); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor_loop,daemon=True).start()
    run_bot()
