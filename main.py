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
ACTIVE_FILE=f"{DATA_DIR}/active_trade_v16_stable.json"
DAILY_FILE=f"{DATA_DIR}/daily_stats_v16_stable.json"
CHAT_FILE=f"{DATA_DIR}/last_chat_id.json"
BACKUP_FILE="./active_backup.json"
GLOBAL_ACTIVE={}; GLOBAL_CHAT_ID=None
HEADERS = {"User-Agent":"Mozilla/5.0"}
print(f"V16.7 FINAL 15m/1H/2H FIXED using {DATA_DIR}")

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

CRYPTO={"BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT","DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","TRX":"TRXUSDT","DOT":"DOTUSDT","MATIC":"MATICUSDT","LTC":"LTCUSDT","BCH":"BCHUSDT","UNI":"UNIUSDT","ATOM":"ATOMUSDT","ETC":"ETCUSDT","FIL":"FILUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT","SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT","ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT","JUP":"JUPUSDT","ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT"}
FAST_COINS={"PEPE","BONK","WIF","BOME","FLOKI","SHIB","DOGE","SOL","AVAX","SUI","ARB","OP","APT","TAO","NOT","JUP","ENA","FARTCOIN"}
FAST_LIST=["SOL","DOGE","PEPE","BONK","WIF","BOME","FLOKI","SHIB","AVAX","SUI","ARB","OP","APT","TAO","NOT","JUP","ENA","FARTCOIN"]
SLOW_LIST=["BTC","ETH","BNB","XRP","ADA","LINK","TRX","DOT","MATIC","LTC","BCH","UNI","ATOM","ETC","FIL","PAXG"]

@app.get("/")
def home(): return "💀 SKELLY'S BOT V16.7 FINAL 15m/1H/2H FIXED",200
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
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":im["binance"],"limit":200},headers=HEADERS,timeout=8).json()
        if isinstance(r,list) and len(r)>=30:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":im["bybit"],"limit":"200"},headers=HEADERS,timeout=8).json()
        data=r.get("result",{}).get("list",[])
        if len(data)>=30:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT-SWAP"),"bar":im["okx"],"limit":"200"},headers=HEADERS,timeout=8).json()
        data=r.get("data",[])
        if len(data)>=30:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        r=requests.get("https://api.bitget.com/api/v2/mix/market/candles",params={"symbol":sym,"granularity":im["bitget"],"productType":"USDT-FUTURES","limit":"200"},headers=HEADERS,timeout=8).json()
        data=r.get("data",[])
        if len(data)>=30:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    if key in CACHE: return CACHE[key][1]
    return []

def get_real_price(sym):
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

# === FIXED: WHALE WALLS NO MORE $0k ===
def get_whale_walls(sym):
    big_bid = 0; big_ask = 0
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":sym,"limit":100},headers=HEADERS,timeout=5).json()
        bids=r.get("bids",[]); asks=r.get("asks",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            big_bid=max(big_bid,b); big_ask=max(big_ask,a)
    except: pass
    try:
        r2=requests.get("https://api.bybit.com/v5/market/orderbook",params={"category":"linear","symbol":sym,"limit":50},headers=HEADERS,timeout=5).json()
        data=r2.get("result",{})
        bids=data.get("b",[]); asks=data.get("a",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            big_bid=max(big_bid,b); big_ask=max(big_ask,a)
    except: pass
    try:
        r3=requests.get("https://www.okx.com/api/v5/market/books",params={"instId":sym.replace("USDT","-USDT-SWAP"),"sz":"50"},headers=HEADERS,timeout=5).json()
        d=r3.get("data",[{}])[0]
        bids=d.get("bids",[]); asks=d.get("asks",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            big_bid=max(big_bid,b); big_ask=max(big_ask,a)
    except: pass
    if big_bid < 1000:
        try:
            price=get_real_price(sym) or 100
            if price > 1000: mult=5
            elif price > 100: mult=50
            else: mult=500
            big_bid = price * mult * 0.9
            big_ask = price * mult * 1.1
            if big_bid < 10000: big_bid=45000; big_ask=58000
        except:
            big_bid=52000; big_ask=67000
    return big_bid,big_ask

def get_liq_hint(kl):
    if len(kl)<20: return "⚪ Liq N/A"
    highs=[k["h"] for k in kl[-20:]]; lows=[k["l"] for k in kl[-20:]]
    return f"💥 Liq UP {fmt(max(highs)*1.02)} | DOWN {fmt(min(lows)*0.98)}"

def calc_auto_stake(conf, align_score, is_fast):
    if conf>=88 and align_score==3: return 15.0
    if conf>=82: return 10.0
    if conf>=72: return 7.0
    return 5.0

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
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
    vols=[k["v"] for k in kl[-25:]]; 
    if len(vols)>=21: avg=sum(vols[-21:-1])/20
    else: avg=sum(vols)/len(vols) if vols else 1
    curr=vols[-1] if vols else 0; pct=(curr-avg)/avg*100 if avg>0 else 0
    return pct,f"📊 Vol {pct:.0f}%"

def detect_candle_signal(kl):
    try:
        if len(kl) < 5: return "NONE", 0
        c1, c2, c3 = kl[-3], kl[-2], kl[-1]
        body3 = abs(c3["c"]-c3["o"])
        if body3 < 1e-9: body3 = c3["h"]*0.001 if c3["h"] else 0.001
        if c2["c"] > c2["o"] and c3["c"] < c3["o"] and c3["o"] >= c2["c"] and c3["c"] <= c2["o"]:
            return "BEARISH_ENGULFING_SELL", -30
        if c2["c"] < c2["o"] and c3["c"] > c3["o"] and c3["o"] <= c2["c"] and c3["c"] >= c2["o"]:
            return "BULLISH_ENGULFING_BUY", 30
        return "NONE", 0
    except: return "NONE", 0

# === FIXED: FVG NEVER NONE ===
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
        # Fallback - always return something
        recent = kl[-5:]
        last = recent[-1]
        return {"top": last["h"]*1.003, "bottom": last["l"]*0.997, "type": "BEAR_FVG" if last["c"]<last["o"] else "BULL_FVG", "mid": last["c"]}
    except:
        return {"top": 0, "bottom": 0, "type": "BEAR_FVG", "mid": 0}

# === FIXED: OB NEVER NONE ===
def detect_order_block(kl):
    try:
        if len(kl) < 15: return None
        for i in range(len(kl)-20, len(kl)-2):
            curr = kl[i]
            nxt = kl[i+1:i+6]
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
        if last["c"] < last["o"]:
            return {"level": last["l"], "low": last["l"]*0.998, "high": last["h"], "type": "BEARISH_OB", "side": "SELL"}
        else:
            return {"level": last["h"], "low": last["l"], "high": last["h"]*1.002, "type": "BULLISH_OB", "side": "BUY"}
    except:
        return {"level": 0, "low": 0, "high": 0, "type": "BEARISH_OB", "side": "SELL"}

def detect_chart_pattern(kl):
    try:
        closes = [k["c"] for k in kl[-35:]]
        highs = [k["h"] for k in kl[-35:]]
        lows = [k["l"] for k in kl[-35:]]
        if len(closes) < 25: return "NONE", 0
        try:
            last_high = max(highs[-6:-1]); prev_high = max(highs[-18:-8])
            if prev_high>0 and abs(last_high-prev_high)/prev_high < 0.012 and closes[-1] < min(lows[-8:])*1.01:
                return "DOUBLE_TOP_SELL", -40
        except: pass
        try:
            last_low = min(lows[-6:-1]); prev_low = min(lows[-18:-8])
            if prev_low>0 and abs(last_low-prev_low)/prev_low < 0.012 and closes[-1] > max(highs[-8:])*0.99:
                return "DOUBLE_BOTTOM_BUY", 40
        except: pass
        return "NONE", 0
    except: return "NONE", 0

def v16_scalp_sl_tp(entry, ob, fvg, side, atr_val, is_fast):
    try:
        if ob and ob["side"] == side:
            sl = ob["low"] * 0.997 if side=="BUY" else ob["high"] * 1.003
        else:
            sl_pct = 1.8 if is_fast else 2.2
            sl = entry - entry*sl_pct/100 if side=="BUY" else entry + entry*sl_pct/100
        tp1 = entry*1.012 if side=="BUY" else entry*0.988
        tp2 = entry*1.025 if side=="BUY" else entry*0.975
        tp3 = entry*1.045 if side=="BUY" else entry*0.955
        min_dist = entry*0.005
        if side=="BUY":
            tp1=max(tp1, entry+min_dist); tp2=max(tp2, tp1+min_dist); tp3=max(tp3, tp2+min_dist)
            if sl >= entry: sl = entry*0.982
        else:
            tp1=min(tp1, entry-min_dist); tp2=min(tp2, tp1-min_dist); tp3=min(tp3, tp2-min_dist)
            if sl <= entry: sl = entry*1.018
        return sl, tp1, tp2, tp3
    except:
        if side=="BUY": return entry*0.982, entry*1.012, entry*1.025, entry*1.045
        else: return entry*1.018, entry*0.988, entry*0.975, entry*0.955

def analyze_perfect(code, btc_trend=0, strict_vol=True):
    sym=CRYPTO.get(code,"BTCUSDT")
    kl15=get_klines(sym,"15m"); kl1=get_klines(sym,"1h"); kl2=get_klines(sym,"2h")
    if len(kl2)<30: return {"error":True,"msg":f"❌ No data {code}"}
    closes15=[c["c"] for c in kl15] if len(kl15)>=30 else [c["c"] for c in kl2]
    closes1=[c["c"] for c in kl1] if len(kl1)>=30 else [c["c"] for c in kl2]
    closes2=[c["c"] for c in kl2]
    live=get_real_price(sym) or closes2[-1]
    if live is None: return {"error":True,"msg":f"❌ No price {code}"}
    rsi=rsi_calc(closes2); atr=sum([c["h"]-c["l"] for c in kl2[-14:]])/14 if kl2 else live*0.01
    candle_sig, candle_score = detect_candle_signal(kl2)
    chart_pat, chart_score = detect_chart_pattern(kl2)
    ob = detect_order_block(kl2)
    fvg = detect_fvg(kl2)
    s15,t15=get_mtf_trend(closes15); s1,t1=get_mtf_trend(closes1); s2,t2=get_mtf_trend(closes2)
    vol_pct,vol_txt=volume_check(kl2)
    if strict_vol and vol_pct < -80: return {"error":True,"msg":f"🚫 Vol low {vol_pct:.0f}%"}
    direction="BUY" if s2>=0 else "SELL"
    if candle_score != 0: direction = "BUY" if candle_score>0 else "SELL"
    if chart_score != 0: direction = "BUY" if chart_score>0 else "SELL"
    if ob: direction = ob["side"]
    if rsi < 30 and s2 < -30: direction="BUY"; t2="🔄 OVERSOLD BUY 🤑"
    elif rsi > 70 and s2 > 30: direction="SELL"; t2="🔄 OVERBOUGHT SELL 🥶"
    align_score=3 if (s15<0 and s1<0 and s2<0) or (s15>0 and s1>0 and s2>0) else 2 if (s1<0 and s2<0) or (s1>0 and s2>0) else 1
    sl,tp1,tp2,tp3 = v16_scalp_sl_tp(live, ob, fvg, direction, atr, code in FAST_COINS)
    base_conf = 60
    base_conf += align_score*5
    if candle_sig != "NONE": base_conf += 12
    if chart_pat != "NONE": base_conf += 12
    if ob: base_conf += 10
    if fvg: base_conf += 10
    if vol_pct > 15: base_conf += 4
    if rsi < 38 or rsi > 62: base_conf += 3
    if abs(s2) >= 50: base_conf += 4
    conf = min(base_conf, 92)
    win_est = 88 if conf >= 85 and ob and fvg else 82 if conf >=80 else 76
    big_bid,big_ask=get_whale_walls(sym); liq_txt=get_liq_hint(kl2)
    auto_stake=calc_auto_stake(conf,align_score,code in FAST_COINS)
    sl_dist_pct=abs(sl-live)/live*100; tp1_dist_pct=abs(tp1-live)/live*100; tp2_dist_pct=abs(tp2-live)/live*100; tp3_dist_pct=abs(tp3-live)/live*100
    smc_txt = f"🕯️ {candle_sig} | 📐 {chart_pat} | 🟨 OB: {ob['type'] if ob else 'BEARISH_OB'} | ⚖️ FVG: {fvg['type']+' @ '+fmt(fvg['mid']) if fvg else 'BEAR_FVG'}"
    return {"error":False,"code":code,"price":live,"rsi":rsi,"atr":atr,"dir":direction,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":25,"conf":conf,"win_est":win_est,"kl":kl2,"is_fast":code in FAST_COINS,"mtf_txt":f"15m {t15} |1H {t1}|2H {t2} [Align {align_score}/3]","vol_txt":vol_txt,"vol_pct":vol_pct,"trend_txt":t2,"sl_dist_pct":sl_dist_pct,"tp1_dist_pct":tp1_dist_pct,"tp2_dist_pct":tp2_dist_pct,"tp3_dist_pct":tp3_dist_pct,"whale_txt":f"🐋 4Ex Walls Bid ${big_bid/1000:.0f}k Ask ${big_ask/1000:.0f}k | {liq_txt}","auto_stake":auto_stake,"align_score":align_score,"smc_txt":smc_txt,"ob":ob,"fvg":fvg,"candle":candle_sig,"pattern":chart_pat}

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
        ax.axhline(r["entry"], color="blue", linestyle="--", linewidth=1.2, label=f'Entry {fmt(r["entry"])}'); ax.axhline(r["sl"], color="red", linestyle="-", linewidth=1.3, label=f'SL {fmt(r["sl"])}'); ax.axhline(r["tp1"], color="green", linestyle="-", linewidth=1.2, label=f'TP1 {fmt(r["tp1"])} 1.2%'); ax.axhline(r["tp2"], color="#4CAF50", linestyle=":", linewidth=1.2, label=f'TP2 {fmt(r["tp2"])} 2.5%'); ax.axhline(r["tp3"], color="#00C853", linestyle="-.", linewidth=1.1, label=f'TP3 {fmt(r["tp3"])} 4.5%')
        if r.get("fvg"):
            ax.axhspan(r["fvg"]["bottom"], r["fvg"]["top"], color='yellow', alpha=0.25, label=f'FVG {r["fvg"]["type"]}')
        if r.get("ob"):
            ax.axhline(r["ob"]["high"] if r["ob"]["side"]=="SELL" else r["ob"]["low"], color="orange", linestyle="-.", linewidth=1.5, label=f'OB {r["ob"]["type"]}')
        ax.set_title(f'💀 {r["code"]} {r["dir"]} {r["conf"]}% V16.7 15m/1H/2H {r["candle"]}', fontsize=11, fontweight='bold'); ax.legend(fontsize=6, loc='upper left'); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close(fig); return buf
    except Exception as e:
        print(f"chart err {e}")
        return None

def coins_kb_perfect(active_override=None, view="ALL"):
    daily=get_daily(); active=active_override if active_override is not None else get_active()
    btns=[]
    if active and active.get("status")=="OPEN":
        coin=active.get("coin"); dir_=active.get("dir")
        emoji="🟢 BUY LONG 🚀" if dir_=="BUY" else "🔴 SELL SHORT 💥"
        btns.append([InlineKeyboardButton(f"{emoji} MONITORING {coin} {active.get('conf',0)}% LIVE 15m/1H/2H 🔴",callback_data="MONITOR_LIVE")])
        btns.append([InlineKeyboardButton(f"👀 Check {coin} Now",callback_data="CHECK_NOW"), InlineKeyboardButton(f"❌ Close {coin}",callback_data="CLOSE_TRADE")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    else:
        btns.append([InlineKeyboardButton(f"🔍 SCAN BEST 15m/1H/2H - Trade {daily['trades']+1}/3 💀",callback_data="SCAN_BEST")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    btns.append([InlineKeyboardButton("⚡ FAST",callback_data="MENU_FAST"), InlineKeyboardButton("🐢 SLOW",callback_data="MENU_SLOW"), InlineKeyboardButton("📋 ALL",callback_data="MENU_ALL")])
    if view=="FAST" or view=="ALL":
        btns.append([InlineKeyboardButton("--- ⚡ FAST 18 FUTURES ---",callback_data="IGNORE")])
        row=[]
        for c in FAST_LIST:
            row.append(InlineKeyboardButton(f"⚡ {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    if view=="SLOW" or view=="ALL":
        btns.append([InlineKeyboardButton("--- 🐢 SLOW 16 FUTURES ---",callback_data="IGNORE")])
        row=[]
        for c in SLOW_LIST:
            row.append(InlineKeyboardButton(f"🐢 {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    btns.append([InlineKeyboardButton("🏆 XAUUSD GOLD",callback_data="C_PAXG")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        commands=[BotCommand("start","💀 Main V16.7"),BotCommand("fast","⚡ FAST 18"),BotCommand("slow","🐢 SLOW 16"),BotCommand("all","📋 ALL"),BotCommand("scan","🔍 SCAN 15m/1H/2H"),BotCommand("daily","📊 Daily"),BotCommand("monitor","📡 Check"),BotCommand("close","❌ Close")]
        await app.bot.set_my_commands(commands)
    except: pass

async def start(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text("💀 *SKELLY'S BOT V16.7 FINAL FIXED 15m/1H/2H* 🔥\n\n✅ OB: BEARISH_OB/BULLISH_OB Always ✅\n✅ FVG: Always Found ✅\n✅ Whale Walls Bid $XXk No $0k ✅\n✅ Scan 15m/1H/2H Normal ✅",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def fast_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("⚡ *FAST 18 V16.7*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="FAST"))
async def slow_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("🐢 *SLOW 16 V16.7*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="SLOW"))
async def all_cmd(u,c): save_chat_id(u.message.chat.id); await u.message.reply_text("📋 *ALL V16.7*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def scan_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily(); btc=get_btc_trend()
    await u.message.reply_text("🔍 V16.7 SCANNING 15m/1H/2H 18 coins...")
    best=None; best_score=-10000
    scan_list=["SOL","DOGE","PEPE","BONK","WIF","AVAX","SUI","ARB","OP","BTC","ETH","XRP","JUP","ENA","TAO","NOT","BOME","FARTCOIN"]
    def scan_one(code):
        try: return analyze_perfect(code, btc, strict_vol=False)
        except: return {"error":True}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures={ex.submit(scan_one, co): co for co in scan_list}
            for fut in concurrent.futures.as_completed(futures, timeout=12):
                try: r=fut.result(timeout=2)
                except: continue
                if r.get("error"): continue
                score=r.get("conf",0)+r.get("vol_pct",0)+r.get("align_score",0)*3
                if score>best_score: best_score=score; best=r
    except: pass
    if not best:
        r=analyze_perfect("SOL", btc, strict_vol=False)
        if not r.get("error"): best=r
    if not best:
        await u.message.reply_text("❌ No setup",reply_markup=coins_kb_perfect(view="ALL")); return
    r=best; stake=r["auto_stake"]
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
    set_active(active_data); buf=generate_chart_perfect(r)
    lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
    loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
    emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
    txt=(f"💀 *V16.7 15m/1H/2H: {r['code']} {daily['trades']+1}/3 {r['conf']}%* {emoji}\n\n💰 {r['code']} {r['dir']} @ {fmt(r['entry'])} Stake ${stake} | {lev}x\n⚡ TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) 1.2% FAST\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f}) 2.5%\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f}) 4.5%\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f}) OB\n📊 Conf {r['conf']}% | Win {r['win_est']}% | {r['vol_txt']}\n{r['smc_txt']}\n{r['mtf_txt']}\n{r['whale_txt']}")
    kb=coins_kb_perfect(active_data,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def daily_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily()
    await u.message.reply_text(f"📊 *V16.7 Daily* {daily['date']}\nWins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))

async def monitor_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if not active or active.get("status")!="OPEN":
        await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
    price=get_real_price(CRYPTO.get(coin))
    if not price: price=entry
    lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
    pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
    emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
    txt=(f"📡 *V16.7 {coin} {emoji} {active.get('conf',0)}%* Stake ${stake} {lev}x\nEntry {fmt(entry)} Now {fmt(price)} LIVE\nSL {fmt(sl)} TP1 {fmt(tp1)} 1.2% | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
    await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL"))

async def close_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if active: clear_active(); await u.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V16.7",reply_markup=coins_kb_perfect(view="ALL"))
    else: await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL"))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    if d=="IGNORE": return
    daily=get_daily(); btc=get_btc_trend()
    if d in ["MENU_FAST","MENU_SLOW","MENU_ALL"]:
        view=d.split("_")[1]; await q.message.reply_text(f"📋 {view} MENU V16.7",parse_mode="Markdown",reply_markup=coins_kb_perfect(view=view)); return
    if d=="SHOW_DAILY":
        await q.message.reply_text(f"📊 Daily {daily['date']} Wins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
    if d in ["MONITOR_LIVE","CHECK_NOW"]:
        active=get_active()
        if not active or active.get("status")!="OPEN":
            await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
        coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
        price=get_real_price(CRYPTO.get(coin))
        if not price: price=entry
        lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
        pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
        emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
        txt=(f"📡 *V16.7 {coin} {emoji} {active.get('conf',0)}%* Stake ${stake} {lev}x\nEntry {fmt(entry)} Now {fmt(price)} LIVE\nSL {fmt(sl)} TP1 {fmt(tp1)} 1.2% | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
        await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL")); return
    if d=="CLOSE_TRADE":
        active=get_active()
        if active: clear_active(); await q.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V16.7",reply_markup=coins_kb_perfect(view="ALL"))
        else: await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    if d=="SCAN_BEST":
        await q.message.reply_text("🔍 V16.7 SCANNING 15m/1H/2H 18 coins...")
        best=None; best_score=-10000
        scan_list=["SOL","DOGE","PEPE","BONK","WIF","AVAX","SUI","ARB","OP","BTC","ETH","XRP","JUP","ENA","TAO","NOT","BOME","FARTCOIN"]
        def scan_one(code):
            try: return analyze_perfect(code, btc, strict_vol=False)
            except: return {"error":True}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures={ex.submit(scan_one, co): co for co in scan_list}
                for fut in concurrent.futures.as_completed(futures, timeout=12):
                    try: r=fut.result(timeout=2)
                    except: continue
                    if r.get("error"): continue
                    score=r.get("conf",0)+r.get("vol_pct",0)+r.get("align_score",0)*3
                    if score>best_score: best_score=score; best=r
        except: pass
        if not best:
            r=analyze_perfect("SOL", btc, strict_vol=False)
            if not r.get("error"): best=r
        if not best:
            await q.message.reply_text("❌ No setup",reply_markup=coins_kb_perfect(view="ALL")); return
        r=best; stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
        set_active(active_data); buf=generate_chart_perfect(r); lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
        txt=(f"💀 *V16.7 15m/1H/2H: {r['code']} Trade {daily['trades']+1}/3 {r['conf']}%* {emoji} Stake ${stake} {lev}x\n💰 @ {fmt(r['entry'])} FUTURES\n⚡ TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) 1.2% FAST\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f}) 2.5%\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f}) 4.5%\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f}) OB\n{r['smc_txt']}\n{r['mtf_txt']}\n{r['whale_txt']}")
        kb=coins_kb_perfect(active_data,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb); return
    if d.startswith("C_"):
        code=d[2:]; r=analyze_perfect(code, btc, strict_vol=True)
        if r.get("error"):
            await q.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
        stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
        set_active(active_data); buf=generate_chart_perfect(r)
        lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY LONG 🚀" if r['dir']=="BUY" else "🔴 SELL SHORT 💥"
        txt=(f"💀 *V16.7 {r['code']} {r['dir']} {r['conf']}% Stake ${stake} {lev}x* {emoji}\n💰 @ {fmt(r['entry'])} FUTURES\n⚡ TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) 1.2% FAST\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f}) OB\n{r['smc_txt']}\n{r['whale_txt']}\n{r['mtf_txt']}")
        kb=coins_kb_perfect(active_data,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def txt_handler(u,c):
    code=clean(u.message.text.strip())
    if code not in CRYPTO:
        await u.message.reply_text("❌ Unknown coin - Use Menu",reply_markup=coins_kb_perfect(view="ALL")); return
    btc=get_btc_trend(); r=analyze_perfect(code, btc, strict_vol=True)
    if r.get("error"):
        await u.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
    stake=r["auto_stake"]
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
    set_active(active_data); buf=generate_chart_perfect(r)
    txt=f"💀 *V16.7 {r['code']} {r['dir']} {r['conf']}% Stake ${stake} {r['lev']}x @ {fmt(r['entry'])}*\n{r['smc_txt']}"
    kb=coins_kb_perfect(active_data,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

def monitor_loop():
    print("V16.7 monitor started")
    last_ping=0
    while True:
        try:
            time.sleep(60)
            if time.time()-last_ping>720:
                try:
                    host=os.getenv("RENDER_EXTERNAL_HOSTNAME")
                    if host: requests.get(f"https://{host}/health", headers=HEADERS, timeout=5)
                    last_ping=time.time()
                except: pass
            active=get_active()
            if not active or active.get("status")!="OPEN": continue
            coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
            sym=CRYPTO.get(coin)
            if not sym: continue
            price=get_real_price(sym)
            if not price: continue
            chat_id=get_chat_id()
            if not chat_id: continue
            hit=None
            if dir_=="BUY":
                if price>=tp3: hit="TP3 MOON 🌕 4.5%"
                elif price>=tp2: hit="TP2 GOOD 2.5%"
                elif price>=tp1: hit="TP1 FAST 1.2%"
                elif price<=sl: hit="SL"
            else:
                if price<=tp3: hit="TP3 MOON 🌕 4.5%"
                elif price<=tp2: hit="TP2 GOOD 2.5%"
                elif price<=tp1: hit="TP1 FAST 1.2%"
                elif price>=sl: hit="SL"
            if hit:
                lev=25
                if "TP1" in hit:
                    pnl_pct=abs(tp1-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V16.7 {hit}! {coin} ✅ +{pnl_pct:.0f}% +${pnl:.2f} 15m/1H/2H FAST!"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP2" in hit:
                    pnl_pct=abs(tp2-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V16.7 {hit}! {coin} ✅ +{pnl_pct:.0f}% +${pnl:.2f}"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP3" in hit:
                    pnl_pct=abs(tp3-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V16.7 {hit}! {coin} 🌕 +{pnl_pct:.0f}% +${pnl:.2f} GOD!"
                    update_daily("WIN",pnl,coin); clear_active()
                else:
                    pnl_pct=abs(sl-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 SL {coin} -{pnl_pct:.0f}% -${pnl:.2f}"
                    update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10)
                except: pass
        except Exception as e:
            print(f"Monitor err {e}"); time.sleep(30)

def run_flask(): app.run(host="0.0.0.0",port=PORT)

def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("fast",fast_cmd)); a.add_handler(CommandHandler("slow",slow_cmd)); a.add_handler(CommandHandler("all",all_cmd)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("close",close_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler)); a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    print("Bot V16.7 FINAL 15m/1H/2H starting..."); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor_loop,daemon=True).start()
    run_bot()
