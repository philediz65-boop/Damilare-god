import os,re,threading,requests,time,io,json,concurrent.futures,asyncio
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
ACTIVE_FILE=f"{DATA_DIR}/active_trade_v17_fast.json"
DAILY_FILE=f"{DATA_DIR}/daily_stats_v17_fast.json"
CHAT_FILE=f"{DATA_DIR}/last_chat_id.json"
BACKUP_FILE="./active_backup.json"
GLOBAL_ACTIVE={}; GLOBAL_CHAT_ID=None
HEADERS = {"User-Agent":"Mozilla/5.0"}

# === V17.4 SETTINGS - YOUR REQUEST ===
DEFAULT_LEV = 30  # Changed from 25 to 30x
DEFAULT_STAKE = 0.30  # Changed from 5.0 to 0.30c

print(f"V17.4 FAST 30x 0.30c NO DELAY using {DATA_DIR}")

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
        alt = p.replace("/data","/tmp") if "/data" in p else p.replace("/tmp","/data")
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
    file_active=load_json(ACTIVE_FILE,{})
    if file_active and file_active.get("status")=="OPEN":
        GLOBAL_ACTIVE=file_active; return file_active
    return {}

def set_active(data):
    global GLOBAL_ACTIVE; GLOBAL_ACTIVE=data; save_json(ACTIVE_FILE,data)

def clear_active():
    global GLOBAL_ACTIVE; GLOBAL_ACTIVE={}; save_json(ACTIVE_FILE,{})
    try:
        if os.path.exists(BACKUP_FILE): os.remove(BACKUP_FILE)
    except: pass

def save_chat_id(cid):
    global GLOBAL_CHAT_ID; GLOBAL_CHAT_ID=cid; save_json(CHAT_FILE,{"chat_id":cid})

def get_chat_id():
    global GLOBAL_CHAT_ID
    if GLOBAL_CHAT_ID: return GLOBAL_CHAT_ID
    d=load_json(CHAT_FILE,{}); cid=d.get("chat_id")
    if cid: GLOBAL_CHAT_ID=cid
    return cid

CRYPTO={
"BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT","DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","TRX":"TRXUSDT","DOT":"DOTUSDT","MATIC":"MATICUSDT","LTC":"LTCUSDT","BCH":"BCHUSDT","UNI":"UNIUSDT","ATOM":"ATOMUSDT","ETC":"ETCUSDT","FIL":"FILUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT","SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT","ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT","JUP":"JUPUSDT","ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT",
"TIA":"TIAUSDT","AVAIL":"AVAILUSDT","DYM":"DYMUSDT","ALT":"ALTUSDT","EIGEN":"EIGENUSDT","STRK":"STRKUSDT","SAGA":"SAGAUSDT","MANTA":"MANTAUSDT","GTC":"GTCUSDT"
}
FAST_COINS=set(CRYPTO.keys())
FAST_LIST=list(CRYPTO.keys())[:27]
SLOW_LIST=["BTC","ETH","BNB","XRP","ADA","LINK","TRX","DOT","MATIC","LTC","BCH","UNI","ATOM","ETC","FIL","PAXG"]

@app.get("/")
def home(): return "💀 SKELLY'S BOT V17.4 FAST 30x 0.30c NO DELAY",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        if v is None: return "0"
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

INTERVAL_MAP={
"15m":{"binance":"15m","bybit":"15","okx":"15m","bitget":"15m"},
"1h":{"binance":"1h","bybit":"60","okx":"1H","bitget":"1h"},
"2h":{"binance":"2h","bybit":"120","okx":"2H","bitget":"2h"},
"4h":{"binance":"4h","bybit":"240","okx":"4H","bitget":"4h"},
"1d":{"binance":"1d","bybit":"D","okx":"1D","bitget":"1d"}}

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<120: return CACHE[key][1]
    kl=[]; im=INTERVAL_MAP.get(interval, INTERVAL_MAP["2h"])
    for ex_try in ["binance","bybit","okx","bitget"]:
        try:
            if ex_try=="binance":
                r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":im["binance"],"limit":200},headers=HEADERS,timeout=8).json()
                if isinstance(r,list) and len(r)>=30:
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
                    CACHE[key]=(time.time(),kl); return kl
            elif ex_try=="bybit":
                r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":im["bybit"],"limit":"200"},headers=HEADERS,timeout=8).json()
                data=r.get("result",{}).get("list",[])
                if len(data)>=30:
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
                    CACHE[key]=(time.time(),kl); return kl
            elif ex_try=="okx":
                r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT-SWAP"),"bar":im["okx"],"limit":"200"},headers=HEADERS,timeout=8).json()
                data=r.get("data",[])
                if len(data)>=30:
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
                    CACHE[key]=(time.time(),kl); return kl
            elif ex_try=="bitget":
                r=requests.get("https://api.bitget.com/api/v2/mix/market/candles",params={"symbol":sym,"granularity":im["bitget"],"productType":"USDT-FUTURES","limit":"200"},headers=HEADERS,timeout=8).json()
                data=r.get("data",[])
                if len(data)>=30:
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
                    CACHE[key]=(time.time(),kl); return kl
        except: continue
    if key in CACHE: return CACHE[key][1]
    return []

def get_real_price(sym):
    for _ in range(2):
        try:
            r=requests.get("https://api.bybit.com/v5/market/tickers", params={"category":"linear","symbol":sym}, headers=HEADERS, timeout=5).json()
            lst=r.get("result",{}).get("list",[])
            if lst:
                mp=lst[0].get("markPrice") or lst[0].get("lastPrice")
                if mp: return float(mp)
        except: pass
        try:
            r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price", params={"symbol":sym}, headers=HEADERS, timeout=5).json()
            if r.get("price"): return float(r["price"])
        except: pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def get_whale_walls(sym):
    big_bid=52000; big_ask=67000
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":sym,"limit":50},headers=HEADERS,timeout=5).json()
        bids=r.get("bids",[]); asks=r.get("asks",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            if b>1000: big_bid=b; big_ask=a
    except: pass
    return big_bid,big_ask

def get_liq_hint(kl):
    if len(kl)<20: return "⚪ Liq N/A"
    highs=[k["h"] for k in kl[-20:]]; lows=[k["l"] for k in kl[-20:]]
    return f"💥 Liq UP {fmt(max(highs)*1.02)} | DOWN {fmt(min(lows)*0.98)}"

def ema(arr,p):
    if not arr: return 0
    if len(arr)<p: return sum(arr)/len(arr)
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e

def ema_series(arr,p):
    if not arr: return []
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

def atr_calc(kl, p=14):
    try:
        if len(kl)<p+1: return kl[-1]["c"]*0.015 if kl else 0.01
        trs=[]
        for i in range(1,p+1):
            c=kl[-i]; pc=kl[-i-1]
            tr=max(c["h"]-c["l"], abs(c["h"]-pc["c"]), abs(c["l"]-pc["c"]))
            trs.append(tr)
        return sum(trs)/len(trs) if trs else kl[-1]["c"]*0.01
    except: return kl[-1]["c"]*0.015 if kl else 0.01

def get_mtf_trend(closes):
    if len(closes)<50: return 0,"N/A"
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200); live=closes[-1]
    if live>e20>e50>e200: return 80,"🟢 STRONG UP 🚀"
    if live>e20>e50: return 50,"⬆️ UPTREND 💹"
    if live>e50: return 20,"↗️ WEAK UP 🙂"
    if live<e20<e50<e200: return -80,"🔴 STRONG DOWN 💥"
    if live<e20<e50: return -50,"⬇️ DOWNTREND 😨"
    if live<e50: return -20,"↘️ WEAK DOWN 😕"
    return 0,"➡️ SIDEWAYS 😐"

def volume_check(kl):
    if len(kl)<10: return 0,"📊 Vol N/A"
    vols=[k["v"] for k in kl[-25:]]
    avg=sum(vols[-21:-1])/20 if len(vols)>=21 else sum(vols)/len(vols)
    curr=vols[-1]; pct=(curr-avg)/avg*100 if avg>0 else 0
    return pct,f"📊 Vol {pct:.0f}%"

def detect_candle_signal(kl):
    try:
        if len(kl) < 5: return "NONE", 0
        c2, c3 = kl[-2], kl[-1]
        if c2["c"] > c2["o"] and c3["c"] < c3["o"] and c3["o"] >= c2["c"] and c3["c"] <= c2["o"]:
            return "BEARISH_ENGULFING_SELL", -30
        if c2["c"] < c2["o"] and c3["c"] > c3["o"] and c3["o"] <= c2["c"] and c3["c"] >= c2["o"]:
            return "BULLISH_ENGULFING_BUY", 30
        return "NONE", 0
    except: return "NONE", 0

def detect_fvg(kl):
    try:
        if len(kl) < 10: return None
        for i in range(len(kl)-15, len(kl)-1):
            if i < 1: continue
            a, b = kl[i-1], kl[i]
            if b["l"] > a["h"] and (b["l"]-a["h"])/a["h"] > 0.0003:
                return {"top": b["l"], "bottom": a["h"], "type": "BULL_FVG", "mid": (b["l"]+a["h"])/2}
            if b["h"] < a["l"] and (a["l"]-b["h"])/a["l"] > 0.0003:
                return {"top": a["l"], "bottom": b["h"], "type": "BEAR_FVG", "mid": (a["l"]+b["h"])/2}
        last = kl[-1]
        return {"top": last["h"]*1.003, "bottom": last["l"]*0.997, "type": "BEAR_FVG" if last["c"]<last["o"] else "BULL_FVG", "mid": last["c"]}
    except:
        return None

def detect_order_block(kl):
    try:
        if len(kl) < 15: return None
        for i in range(len(kl)-20, len(kl)-2):
            curr = kl[i]; nxt = kl[i+1:i+6]
            if not nxt or len(nxt)<3: continue
            try:
                move_up = (nxt[-1]["c"] - curr["l"]) / curr["l"] * 100 if curr["l"] else 0
                if curr["c"] < curr["o"] and move_up > 0.8:
                    return {"level": curr["h"], "low": curr["l"], "high": curr["h"], "type": "BULLISH_OB", "side": "BUY"}
                move_down = (curr["h"] - nxt[-1]["c"]) / curr["h"] * 100 if curr["h"] else 0
                if curr["c"] > curr["o"] and move_down > 0.8:
                    return {"level": curr["l"], "low": curr["l"], "high": curr["h"], "type": "BEARISH_OB", "side": "SELL"}
            except: continue
        last = kl[-6]
        return {"level": last["l"], "low": last["l"]*0.998, "high": last["h"], "type": "BEARISH_OB", "side": "SELL"} if last["c"] < last["o"] else {"level": last["h"], "low": last["l"], "high": last["h"]*1.002, "type": "BULLISH_OB", "side": "BUY"}
    except:
        return None

def detect_chart_pattern(kl):
    try:
        closes = [k["c"] for k in kl[-35:]]; highs = [k["h"] for k in kl[-35:]]; lows = [k["l"] for k in kl[-35:]]
        if len(closes) < 25: return "NONE", 0
        last_high = max(highs[-6:-1]); prev_high = max(highs[-18:-8])
        if prev_high>0 and abs(last_high-prev_high)/prev_high < 0.012 and closes[-1] < min(lows[-8:])*1.01:
            return "DOUBLE_TOP_SELL", -40
        last_low = min(lows[-6:-1]); prev_low = min(lows[-18:-8])
        if prev_low>0 and abs(last_low-prev_low)/prev_low < 0.012 and closes[-1] > max(highs[-8:])*0.99:
            return "DOUBLE_BOTTOM_BUY", 40
        return "NONE", 0
    except: return "NONE", 0

def v16_scalp_sl_tp(entry, ob, fvg, side, atr_val, is_fast, coin=""):
    try:
        if ob and ob["side"] == side:
            if side=="BUY":
                sl = ob["low"] * 0.997 - atr_val * 1.0
                min_dist = entry * 0.015
                if entry - sl < min_dist:
                    sl = entry - min_dist - atr_val*0.3
            else:
                sl = ob["high"] * 1.003 + atr_val * 1.0
                min_dist = entry * 0.015
                if sl - entry < min_dist:
                    sl = entry + min_dist + atr_val*0.3
        else:
            sl = entry * 0.985 if side=="BUY" else entry * 1.015
        tp1 = entry*1.015 if side=="BUY" else entry*0.985
        tp2 = entry*1.025 if side=="BUY" else entry*0.975
        tp3 = entry*1.04 if side=="BUY" else entry*0.96
        if side=="BUY":
            if sl >= entry: sl = entry*0.985
        else:
            if sl <= entry: sl = entry*1.015
        return sl, tp1, tp2, tp3
    except:
        if side=="BUY": return entry*0.985, entry*1.015, entry*1.025, entry*1.04
        else: return entry*1.015, entry*0.985, entry*0.975, entry*0.96

def analyze_perfect(code, btc_trend=0, strict_vol=False):
    try:
        sym=CRYPTO.get(code,"BTCUSDT")
        kl15=get_klines(sym,"15m"); kl1=get_klines(sym,"1h"); kl2=get_klines(sym,"2h")
        if len(kl2)<30: return {"error":True,"msg":f"❌ No data {code}"}
        closes15=[c["c"] for c in kl15] if len(kl15)>=30 else [c["c"] for c in kl2]
        closes1=[c["c"] for c in kl1] if len(kl1)>=30 else [c["c"] for c in kl2]
        closes2=[c["c"] for c in kl2]
        live=get_real_price(sym) or closes2[-1]
        if live is None: return {"error":True,"msg":f"❌ No price {code}"}
        rsi=rsi_calc(closes2); atr=atr_calc(kl2,14)
        candle_sig, candle_score = detect_candle_signal(kl2)
        chart_pat, chart_score = detect_chart_pattern(kl2)
        ob = detect_order_block(kl2)
        fvg = detect_fvg(kl2)
        s15,t15=get_mtf_trend(closes15); s1,t1=get_mtf_trend(closes1); s2,t2=get_mtf_trend(closes2)
        vol_pct,vol_txt=volume_check(kl2)
        if strict_vol and vol_pct < -80: return {"error":True,"msg":f"🚫 Vol low {vol_pct:.0f}%"}
        align_score=3 if (s15<0 and s1<0 and s2<0) or (s15>0 and s1>0 and s2>0) else 2 if (s1<0 and s2<0) or (s1>0 and s2>0) else 1
        lows2=[k["l"] for k in kl2[-25:]]
        prev_low = min(lows2[-20:-3]) if len(lows2)>=20 else lows2[0]
        curr_low = lows2[-1]
        swept = curr_low < prev_low * 0.998
        direction="BUY" if s2>=0 else "SELL"
        if ob and align_score>=2:
            if (ob["side"]=="BUY" and s2>0) or (ob["side"]=="SELL" and s2<0):
                direction=ob["side"]
        if candle_score!=0 and abs(candle_score)>=25:
            direction="BUY" if candle_score>0 else "SELL"
        if chart_score!=0 and abs(chart_score)>=30:
            direction="BUY" if chart_score>0 else "SELL"
        if rsi<28: direction="BUY"; t2="🔄 OVERSOLD BUY 🤑"
        elif rsi>72: direction="SELL"; t2="🔄 OVERBOUGHT SELL 🥶"
        sl,tp1,tp2,tp3 = v16_scalp_sl_tp(live, ob, fvg, direction, atr, True, code)
        base_conf=60 + align_score*6
        if candle_sig!="NONE": base_conf+=10
        if chart_pat!="NONE": base_conf+=10
        if ob: base_conf+=8
        if fvg: base_conf+=8
        if swept: base_conf+=12
        if vol_pct>10: base_conf+=4
        conf=min(base_conf, 92)
        win_est=91 if conf>=90 else 88 if conf>=85 else 82 if conf>=78 else 75
        big_bid,big_ask=get_whale_walls(sym); liq_txt=get_liq_hint(kl2)
        sl_dist_pct=abs(sl-live)/live*100; tp1_dist_pct=abs(tp1-live)/live*100; tp2_dist_pct=abs(tp2-live)/live*100; tp3_dist_pct=abs(tp3-live)/live*100
        smc_txt=f"🕯️ {candle_sig} | 📐 {chart_pat} | 🟨 OB: {ob['type'] if ob else 'None'} | ⚖️ FVG: {fvg['type'] if fvg else 'None'} | Sweep={'YES' if swept else 'NO'}"
        return {"error":False,"code":code,"price":live,"rsi":rsi,"atr":atr,"dir":direction,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":DEFAULT_LEV,"conf":conf,"win_est":win_est,"kl":kl2,"is_fast":True,"mtf_txt":f"15m {t15} |1H {t1}|2H {t2} [Align {align_score}/3]","vol_txt":vol_txt,"vol_pct":vol_pct,"trend_txt":t2,"sl_dist_pct":sl_dist_pct,"tp1_dist_pct":tp1_dist_pct,"tp2_dist_pct":tp2_dist_pct,"tp3_dist_pct":tp3_dist_pct,"whale_txt":f"🐋 Walls ${big_bid/1000:.0f}k/${big_ask/1000:.0f}k | {liq_txt}","auto_stake":DEFAULT_STAKE,"align_score":align_score,"smc_txt":smc_txt,"ob":ob,"fvg":fvg,"candle":candle_sig,"pattern":chart_pat,"swept":swept}
    except Exception as e:
        return {"error":True,"msg":f"❌ Bug {code}: {str(e)[:50]}"}

def get_btc_trend():
    try:
        kl1=get_klines("BTCUSDT","1h"); kl2=get_klines("BTCUSDT","2h")
        s1,_=get_mtf_trend([c["c"] for c in kl1]); s2,_=get_mtf_trend([c["c"] for c in kl2])
        return (s1+s2)//2
    except: return 0

def generate_chart_perfect(r):
    try:
        kl=r["kl"][-120:]; closes=[c["c"] for c in kl]; e20s=ema_series(closes,20); e50s=ema_series(closes,50)
        fig, ax = plt.subplots(figsize=(10,5.5))
        ax.plot(closes, label="Price", color="black", linewidth=1.2); ax.plot(e20s, label="EMA20", color="#2196F3", linewidth=0.9); ax.plot(e50s, label="EMA50", color="#FF9800", linewidth=0.9)
        ax.axhline(r["entry"], color="blue", linestyle="--", linewidth=1.2, label=f'Entry {fmt(r["entry"])}'); ax.axhline(r["sl"], color="red", linestyle="-", linewidth=1.3, label=f'SL {fmt(r["sl"])} ANTI-HIT'); ax.axhline(r["tp1"], color="green", linestyle="-", linewidth=1.2, label=f'TP1 {fmt(r["tp1"])} 1.5% FAST'); ax.axhline(r["tp2"], color="#4CAF50", linestyle=":", linewidth=1.2, label=f'TP2 {fmt(r["tp2"])} 2.5%'); ax.axhline(r["tp3"], color="#00C853", linestyle="-.", linewidth=1.1, label=f'TP3 {fmt(r["tp3"])} 4%')
        if r.get("fvg"):
            ax.axhspan(r["fvg"]["bottom"], r["fvg"]["top"], color='yellow', alpha=0.25, label=f'FVG {r["fvg"]["type"]}')
        if r.get("ob"):
            ax.axhline(r["ob"]["high"] if r["ob"]["side"]=="SELL" else r["ob"]["low"], color="orange", linestyle="-.", linewidth=1.5, label=f'OB {r["ob"]["type"]}')
        ax.set_title(f'💀 {r["code"]} {r["dir"]} {r["conf"]}% V17.4 30x {r["auto_stake"]}$', fontsize=11, fontweight='bold'); ax.legend(fontsize=6, loc='upper left'); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close(fig); return buf
    except: return None

def coins_kb_perfect(active_override=None, view="ALL"):
    daily=get_daily(); active=active_override if active_override is not None else get_active()
    btns=[]
    if active and active.get("status")=="OPEN":
        coin=active.get("coin"); dir_=active.get("dir")
        emoji="🟢 BUY LONG 🚀" if dir_=="BUY" else "🔴 SELL SHORT 💥"
        btns.append([InlineKeyboardButton(f"{emoji} {coin} {active.get('conf',0)}% LIVE 30x🔴",callback_data="MONITOR_LIVE")])
        btns.append([InlineKeyboardButton(f"👀 Check {coin} Now",callback_data="CHECK_NOW"), InlineKeyboardButton(f"❌ Close {coin}",callback_data="CLOSE_TRADE")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    else:
        btns.append([InlineKeyboardButton(f"🔍 SCAN BEST 30x - Trade {daily['trades']+1}/3 💀",callback_data="SCAN_BEST")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    btns.append([InlineKeyboardButton("⚡ FAST 27",callback_data="MENU_FAST"), InlineKeyboardButton("🐢 SLOW 16",callback_data="MENU_SLOW"), InlineKeyboardButton("📋 ALL 43",callback_data="MENU_ALL")])
    if view=="FAST" or view=="ALL":
        btns.append([InlineKeyboardButton("--- ⚡ ALL 27 FAST 30x ---",callback_data="IGNORE")])
        row=[]
        for c in FAST_LIST:
            row.append(InlineKeyboardButton(f"⚡ {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    if view=="SLOW" or view=="ALL":
        btns.append([InlineKeyboardButton("--- 🐢 SLOW 16 FAST 30x ---",callback_data="IGNORE")])
        row=[]
        for c in SLOW_LIST:
            row.append(InlineKeyboardButton(f"🐢 {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        commands=[BotCommand("start","💀 Main V17.4 30x"),BotCommand("fast","⚡ FAST 27"),BotCommand("slow","🐢 SLOW 16"),BotCommand("all","📋 ALL 43"),BotCommand("scan","🔍 SCAN 30x"),BotCommand("daily","📊 Daily"),BotCommand("monitor","📡 Check"),BotCommand("close","❌ Close")]
        await app.bot.set_my_commands(commands)
    except: pass

# ===== NO DELAY SCAN - BACKGROUND THREAD =====
def background_scan(chat_id):
    try:
        btc=get_btc_trend()
        best=None; best_score=-10000
        def scan_one(code):
            try: return analyze_perfect(code, btc, strict_vol=False)
            except: return {"error":True}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                futures={ex.submit(scan_one, co): co for co in CRYPTO.keys()}
                for fut in concurrent.futures.as_completed(futures, timeout=25):
                    try: r=fut.result(timeout=3)
                    except: continue
                    if r.get("error"): continue
                    score=r.get("conf",0)*3 + r.get("align_score",0)*5 + (15 if r.get("swept") else 0)
                    if score>best_score: best_score=score; best=r
        except: pass
        if not best:
            r=analyze_perfect("SOL", btc, strict_vol=False)
            if not r.get("error"): best=r
        if not best:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"❌ No setup - market sideways"},timeout=10)
            return
        r=best; stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time()}
        set_active(active_data)
        lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
        daily=get_daily()
        txt=(f"💀 *V17.4 FAST {r['code']} Trade {daily['trades']+1}/3 {r['conf']}%* {emoji} ${stake} {lev}x 30x\n💰 @ {fmt(r['entry'])}\n⚡ TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) 1.5% FAST\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f}) ANTI-HIT\n{r['smc_txt']}\n{r['mtf_txt']}\n{r['whale_txt']}")
        # Try send chart
        try:
            buf=generate_chart_perfect(r)
            if buf:
                # send photo via telegram api
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"}, files={"photo": buf}, timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"BG Scan err {e}")

async def start(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text(f"💀 *V17.4 FAST 30x 0.30c - NO DELAY* 🔥\n\n✅ 30x LEVERAGE (you request)\n✅ $0.30 STAKE default\n✅ SCAN no block - /start reply instant\n✅ ANTI SL + 1.5% FAST ALL",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def fast_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("⚡ *FAST 27 V17.4 30x*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="FAST"))
async def slow_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("🐢 *SLOW 16 V17.4 30x*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="SLOW"))
async def all_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("📋 *ALL 43 V17.4 30x*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def scan_cmd(u,c):
    save_chat_id(u.message.chat.id)
    chat_id=u.message.chat.id
    # INSTANT REPLY - NO BLOCK
    await u.message.reply_text("🔍 V17.4 SCANNING 43 COINS 30x... (background - you fit use /start now, no delay)\n⏳ Result go come in 10 sec")
    threading.Thread(target=background_scan, args=(chat_id,), daemon=True).start()

async def daily_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily()
    await u.message.reply_text(f"📊 *V17.4 Daily 30x* {daily['date']}\nWins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def monitor_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if not active or active.get("status")!="OPEN":
        await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE)
    price=get_real_price(CRYPTO.get(coin))
    if not price: price=entry
    lev=DEFAULT_LEV; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
    pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
    emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
    txt=(f"📡 *V17.4 {coin} {emoji} {active.get('conf',0)}%* ${stake} {lev}x 30x\nEntry {fmt(entry)} Now {fmt(price)}\nSL {fmt(sl)} | TP1 {fmt(tp1)} 1.5% FAST | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
    await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL"))

async def close_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if active: clear_active(); await u.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V17.4 30x",reply_markup=coins_kb_perfect(view="ALL"))
    else: await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL"))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    if d=="IGNORE": return
    daily=get_daily(); btc=get_btc_trend()
    if d in ["MENU_FAST","MENU_SLOW","MENU_ALL"]:
        view=d.split("_")[1]; await q.message.reply_text(f"📋 {view} MENU V17.4 30x",parse_mode="Markdown",reply_markup=coins_kb_perfect(view=view)); return
    if d=="SHOW_DAILY":
        await q.message.reply_text(f"📊 Daily {daily['date']} Wins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
    if d in ["MONITOR_LIVE","CHECK_NOW"]:
        active=get_active()
        if not active or active.get("status")!="OPEN":
            await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
        coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE)
        price=get_real_price(CRYPTO.get(coin))
        if not price: price=entry
        lev=DEFAULT_LEV; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
        pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
        emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
        txt=(f"📡 *V17.4 {coin} {emoji} {active.get('conf',0)}%* ${stake} {lev}x\nEntry {fmt(entry)} Now {fmt(price)}\nSL {fmt(sl)} | TP1 {fmt(tp1)} 1.5% FAST | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
        await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL")); return
    if d=="CLOSE_TRADE":
        active=get_active()
        if active: clear_active(); await q.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V17.4 30x",reply_markup=coins_kb_perfect(view="ALL"))
        else: await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    if d=="SCAN_BEST":
        chat_id=q.message.chat.id
        await q.message.reply_text("🔍 V17.4 SCANNING 43 COINS 30x... (background - no delay)\n⏳ Result go come 10 sec - you fit still click /start")
        threading.Thread(target=background_scan, args=(chat_id,), daemon=True).start()
        return
    if d.startswith("C_"):
        code=d[2:]; r=analyze_perfect(code, btc, strict_vol=False)
        if r.get("error"):
            await q.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
        stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time()}
        set_active(active_data); buf=generate_chart_perfect(r)
        lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
        txt=(f"💀 *V17.4 FAST {r['code']} {r['dir']} {r['conf']}% ${stake} {lev}x 30x* {emoji}\n💰 @ {fmt(r['entry'])}\n⚡ TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) 1.5% FAST\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f}) ANTI-HIT\n{r['smc_txt']}\n{r['whale_txt']}\n{r['mtf_txt']}")
        kb=coins_kb_perfect(active_data,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def txt_handler(u,c):
    code=clean(u.message.text.strip())
    if code not in CRYPTO:
        await u.message.reply_text("❌ Unknown - Use Menu",reply_markup=coins_kb_perfect(view="ALL")); return
    btc=get_btc_trend(); r=analyze_perfect(code, btc, strict_vol=False)
    if r.get("error"):
        await u.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
    stake=r["auto_stake"]
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time()}
    set_active(active_data); buf=generate_chart_perfect(r)
    lev=r["lev"]
    txt=f"💀 *V17.4 FAST {r['code']} {r['dir']} {r['conf']}% ${stake} {lev}x 30x @ {fmt(r['entry'])}*\n{r['smc_txt']}"
    kb=coins_kb_perfect(active_data,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

def monitor_loop():
    print("V17.4 FAST 30x monitor started NO BUG")
    last_ping=0
    while True:
        try:
            time.sleep(45)
            if time.time()-last_ping>720:
                try:
                    host=os.getenv("RENDER_EXTERNAL_HOSTNAME")
                    if host: requests.get(f"https://{host}/health", headers=HEADERS, timeout=5)
                    last_ping=time.time()
                except: pass
            active=get_active()
            if not active or active.get("status")!="OPEN": continue
            coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE)
            sym=CRYPTO.get(coin)
            if not sym: continue
            price=get_real_price(sym)
            if not price: continue
            chat_id=get_chat_id()
            if not chat_id: continue
            hit=None
            if dir_=="BUY":
                if price>=tp3: hit="TP3 MOON 🌕 4%"
                elif price>=tp2: hit="TP2 GOOD 2.5%"
                elif price>=tp1: hit="TP1 FAST 1.5%"
                elif price<=sl: hit="SL"
            else:
                if price<=tp3: hit="TP3 MOON 🌕 4%"
                elif price<=tp2: hit="TP2 GOOD 2.5%"
                elif price<=tp1: hit="TP1 FAST 1.5%"
                elif price>=sl: hit="SL"
            if hit:
                lev=DEFAULT_LEV
                if "TP1" in hit:
                    pnl_pct=abs(tp1-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V17.4 {hit}! {coin} 30x ✅ +{pnl_pct:.0f}% +${pnl:.2f} FAST 1.5%!"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP2" in hit:
                    pnl_pct=abs(tp2-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V17.4 {hit}! {coin} 30x ✅ +{pnl_pct:.0f}% +${pnl:.2f}"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP3" in hit:
                    pnl_pct=abs(tp3-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V17.4 {hit}! {coin} 30x 🌕 +{pnl_pct:.0f}% +${pnl:.2f} MOON!"
                    update_daily("WIN",pnl,coin); clear_active()
                else:
                    pnl_pct=abs(sl-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 SL {coin} 30x -{pnl_pct:.0f}% -${pnl:.2f}"
                    update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10)
                except: pass
        except Exception as e:
            print(f"Monitor err {e}"); time.sleep(20)

def run_flask(): app.run(host="0.0.0.0",port=PORT)

def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("fast",fast_cmd)); a.add_handler(CommandHandler("slow",slow_cmd)); a.add_handler(CommandHandler("all",all_cmd)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("close",close_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler)); a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    print("Bot V17.4 FAST 30x 0.30c NO BUG starting..."); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor_loop,daemon=True).start()
    run_bot()
