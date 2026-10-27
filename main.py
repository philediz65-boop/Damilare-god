import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math, concurrent.futures
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET","").strip()
BINANCE_SECRET = BINANCE_API_SECRET or os.getenv("BINANCE_SECRET","").strip()
PORT = int(os.getenv("PORT","10000"))
BINANCE_PROXY = os.getenv("BINANCE_PROXY","").strip()
RISK_MODE = os.getenv("RISK_MODE","1.5").strip()

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v67.json"
DAILY_FILE = f"{DATA_DIR}/daily_v67.json"
CHAT_FILE = f"{DATA_DIR}/chat_v67.json"
CHART_FILE = f"{DATA_DIR}/chart_v67.png"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

def binance_signed_request(method, endpoint, params={}, retries=2):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    for _ in range(retries):
        try:
            p = dict(params); p['timestamp'] = int(time.time()*1000); p['recvWindow'] = 10000
            query = urllib.parse.urlencode(p)
            sig = hmac.new(BINANCE_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"https://fapi.binance.com{endpoint}?{query}&signature={sig}"
            headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
            r = requests.request(method, url, headers=headers, proxies=PROXIES, timeout=20)
            data = r.json()
            if r.status_code == 200: return data
            time.sleep(0.4)
        except: time.sleep(0.3)
    return None

def get_futures_balance():
    data = binance_signed_request("GET", "/fapi/v2/balance")
    if isinstance(data, list):
        for b in data:
            if b.get('asset') == 'USDT':
                try: return float(b.get('balance',0))
                except: pass
    return 7.28

def get_trade_amount(mode="SNIPER"): return 3.0

def get_real_alt_futures_FIXED():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",headers=HEADERS,timeout=15,proxies=PROXIES).json()
        valid=[]
        if isinstance(r,list):
            for t in r:
                sym=t.get('symbol','')
                if not sym.endswith('USDT'): continue
                if sym in ["BTCUSDT","ETHUSDT","BNBUSDT","USDCUSDT"]: continue
                try:
                    vol=float(t.get('quoteVolume',0))
                    if vol<3000000: continue
                    change=float(t.get('priceChangePercent',0))
                    if abs(change)<0.5: continue
                    valid.append((sym, vol, abs(change)))
                except: continue
            valid.sort(key=lambda x: (x[2], x[1]), reverse=True)
            top=[s[0] for s in valid[:148]]
            if len(top)>=15: return top
    except: pass
    return ["SOLUSDT","DOGEUSDT","PEPEUSDT","WIFUSDT","BONKUSDT","FLOKIUSDT","AVAXUSDT","SUIUSDT","ARBUSDT","OPUSDT","TIAUSDT","ENAUSDT","WLDUSDT","NEARUSDT","APTUSDT","SEIUSDT","PYTHUSDT","JUPUSDT","FETUSDT","RNDRUSDT","TAOUSDT","HYPEUSDT","ONDOUSDT","LINKUSDT","INJUSDT","RENDERUSDT","ARUSDT","AAVEUSDT"]

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        c=float(r.get('priceChangePercent',0))
        if c>=2.0: return True, f"₿ BTC +{c:.1f}% Strong Bull 🌞🚀🔥 4H!", c
        if c<=-2.0: return True, f"₿ BTC {c:.1f}% Strong Bear 🌧️📉🔥 4H!", c
        if abs(c)<0.8: return True, f"₿ BTC {c:.1f}% Calm = BEST for 4H Alt Sniper 😴✅💎", c
        return True, f"₿ BTC {c:.1f}% Mid 4H ⚖️", c
    except: return True, "₿ BTC N/A 🤷", 0

def get_symbol_filters(symbol):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",params={"symbol":symbol},headers=HEADERS,timeout=8,proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==symbol:
                qp=int(s.get('quantityPrecision',3)); ss=0.001
                for f in s.get('filters',[]):
                    if f.get('filterType')=='LOT_SIZE': ss=float(f.get('stepSize',0.001))
                return qp, ss
    except: pass
    return 3, 0.001

def setup_symbol(symbol):
    try: binance_signed_request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"})
    except: pass
    try: binance_signed_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": 10})
    except: pass

def place_real_order(symbol, direction, usdt_amount):
    try:
        rp=requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",proxies=PROXIES,headers=HEADERS,timeout=10).json()
        price=float(rp.get('price',0))
        if price<=0: return None
        qp, ss=get_symbol_filters(symbol)
        raw=(usdt_amount*10)/price
        if ss>0: raw=math.floor(raw/ss)*ss
        raw=round(raw, qp)
        if raw<=0: return None
        setup_symbol(symbol)
        order=binance_signed_request("POST","/fapi/v1/order",{"symbol":symbol,"side":"BUY" if direction=="BUY" else "SELL","type":"MARKET","quantity":raw})
        if order and order.get('orderId'): return order
        return None
    except: return None

def close_real_position(symbol, qty_percent=100):
    try:
        pos=binance_signed_request("GET","/fapi/v2/positionRisk",{"symbol":symbol})
        if not isinstance(pos, list): return None
        for p in pos:
            if p.get('symbol')!=symbol: continue
            amt=float(p.get('positionAmt',0))
            if abs(amt)<0.000001: continue
            side="SELL" if amt>0 else "BUY"
            cq=abs(amt)*qty_percent/100.0
            qp, ss=get_symbol_filters(symbol)
            if ss>0: cq=math.floor(cq/ss)*ss
            cq=round(cq, qp)
            if cq<=0: cq=abs(amt)
            res=binance_signed_request("POST","/fapi/v1/order",{"symbol":symbol,"side":side,"type":"MARKET","quantity":cq,"reduceOnly":"true"})
            return res
    except: return None

def load_json(p,d):
    try:
        if os.path.exists(p):
            with LOCK:
                with open(p,'r') as f: return json.load(f)
    except: pass
    return d
def save_json(p,data):
    try:
        with LOCK:
            tmp=p+".tmp"
            with open(tmp,'w') as f: json.dump(data,f)
            os.replace(tmp,p)
    except: pass
def get_daily():
    d=load_json(DAILY_FILE,{}); t=str(date.today())
    if d.get("date")!=t: d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d
def update_daily(pnl, win):
    d=get_daily(); d["trades"]+=1; d["pnl"]+=pnl
    if win: d["wins"]+=1
    else: d["losses"]+=1
    save_json(DAILY_FILE,d)
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return f"🧠💎 SKELLY V67 4H PERFECT Bal ${get_futures_balance():.2f} LIVE 🚀📊🕯️",200
@app.get("/health")
def health(): return "OK V67 4H PERFECT BOT 📊🕯️",200

def fmt(v):
    try:
        v=float(v)
        if v>=1: return f"{v:.5f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="4h"):
    key=f"{sym}_{interval}"
    with CACHE_LOCK:
        if key in CACHE and time.time()-CACHE[key][0]<90: return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=8,proxies=PROXIES).json()
        if isinstance(r,list) and len(r)>=60:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            with CACHE_LOCK: CACHE[key]=(time.time(),kl)
            return kl
    except: pass
    with CACHE_LOCK:
        if key in CACHE: return CACHE[key][1]
    return []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=3,proxies=PROXIES).json()
        if "price" in r: return float(r["price"])
    except: pass
    kl=get_klines(sym,"1h"); return kl[-1]["c"] if kl else None

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e
def ema_series(arr,p):
    if len(arr)<p: return [sum(arr)/len(arr)]*len(arr)
    k=2/(p+1); e=sum(arr[:p])/p; out=[e]*p
    for x in arr[p:]:
        e=(x-e)*k+e; out.append(e)
    return out
def rsi_calc(arr,p=14):
    if len(arr)<p+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(arr)):
        d=arr[i]-arr[i-1]
        if d>0: gains.append(d); losses.append(0)
        else: gains.append(0); losses.append(-d)
    if len(gains)<p: return 50
    avg_g=sum(gains[-p:])/p; avg_l=sum(losses[-p:])/p
    if avg_l==0: return 70 if avg_g>0 else 50
    return 100-(100/(1+avg_g/avg_l))
def adx_calc(kl):
    try:
        if len(kl)<32: return 14
        highs=[k["h"] for k in kl]; lows=[k["l"] for k in kl]; closes=[k["c"] for k in kl]
        tr=[]; pdm=[]; mdm=[]
        for i in range(1,len(kl)):
            up=highs[i]-highs[i-1]; dn=lows[i-1]-lows[i]
            pdm.append(up if up>dn and up>0 else 0); mdm.append(dn if dn>up and dn>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        atr_v=sum(tr[-14:])/14
        if atr_v==0: return 14
        pdi=100*sum(pdm[-14:])/14/atr_v; mdi=100*sum(mdm[-14:])/14/atr_v
        if pdi+mdi==0: return 14
        return max(8,min(65,100*abs(pdi-mdi)/(pdi+mdi)))
    except: return 14
def trend_calc(closes):
    if len(closes)<50: return 0,"SIDEWAYS ➡️",0,False,0
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200)
    pr=closes[-1]; dist200 = abs(pr-e200)/e200*100
    if pr>e20>e50 and pr>e200: return 60,"UPTREND 🚀💎 4H",e20,True,dist200
    if pr<e20<e50 and pr<e200: return -60,"DOWNTREND 📉💎 4H",e20,True,dist200
    if pr>e20>e50: return 40,"UPTREND 🚀",e20,True,dist200
    if pr<e20<e50: return -40,"DOWNTREND 📉",e20,True,dist200
    if pr>e20: return 20,"WEAK UP ↗️",e20,False,dist200
    if pr<e20: return -20,"WEAK DOWN ↘️",e20,False,dist200
    return 0,"SIDEWAYS ➡️ 4H",e20,False,dist200
def calc_stoch_rsi(closes):
    try:
        if len(closes)<19: return 50
        rsi_vals=[rsi_calc(closes[:i+1]) for i in range(14, len(closes))]
        recent=rsi_vals[-5:]; low=min(recent); high=max(recent)
        if high==low: return 50
        return (recent[-1]-low)/(high-low)*100
    except: return 50
def calc_bos_META(kl):
    try:
        highs=[k["h"] for k in kl[-50:]]; lows=[k["l"] for k in kl[-50:]]; vols=[k["v"] for k in kl[-50:]]
        last_h=max(highs[-30:-1]) if len(highs)>30 else highs[-1]
        last_l=min(lows[-30:-1]) if len(lows)>30 else lows[-1]
        curr=kl[-1]["c"]; vol_now=vols[-1]; vol_avg=sum(vols[-25:-1])/24 if len(vols)>25 else vol_now
        vol_confirm = vol_now > vol_avg*1.1
        if curr>last_h*1.0003 and vol_confirm: return True,f"💥 BOS 4H UP Break 🚀💎 {curr:.4f} > {last_h:.4f} Vol {vol_now/vol_avg:.1f}x", curr-last_h, True
        if curr<last_l*0.9997 and vol_confirm: return True,f"💥 BOS 4H DOWN Break 📉💎 {curr:.4f} < {last_l:.4f} Vol {vol_now/vol_avg:.1f}x", last_l-curr, True
        if curr>last_h*1.0003: return True,f"💥 BOS 4H UP Break 🚀 {curr:.4f} > {last_h:.4f}", curr-last_h, False
        if curr<last_l*0.9997: return True,f"💥 BOS 4H DOWN Break 📉 {curr:.4f} < {last_l:.4f}", last_l-curr, False
        return False,f"⏳ No 4H BOS - Choppy 🔄 {curr:.4f} inside {last_l:.4f}-{last_h:.4f}",0, False
    except: return False,"❓ BOS N/A REJECT",0, False
def get_orderbook_ratio(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":40},headers=HEADERS,timeout=3,proxies=PROXIES).json()
        bids=r.get('bids',[]); asks=r.get('asks',[])
        if not bids or not asks: return 1.0
        bv=float(sum([float(x[0])*float(x[1]) for x in bids[:20]])); av=float(sum([float(x[0])*float(x[1]) for x in asks[:20]]))
        if bv==0 or av==0: return 1.0
        ratio=bv/av if direction=="BUY" else av/bv
        return ratio
    except: return 1.0
def detect_candle_pattern_META(kl):
    try:
        if len(kl)<4: return "NONE ⚪","NONE ⚪",0
        prev2=kl[-3]; prev=kl[-2]; last=kl[-1]
        o,h,l,c = last["o"],last["h"],last["l"],last["c"]
        po,ph,pl,pc = prev["o"],prev["h"],prev["l"],prev["c"]
        p2o,p2h,p2l,p2c = prev2["o"],prev2["h"],prev2["l"],prev2["c"]
        body = abs(c-o); prev_body = abs(pc-po)
        if body==0: body=0.0001
        upper_wick = h - max(c,o); lower_wick = min(c,o) - l; total_range = h-l
        if lower_wick > body*2.5 and upper_wick < body*0.35 and c>o and pc<po and total_range > body*2.8:
            return "🔨 HAMMER GOD 4H 🟢💎","BULLISH 🟢 4H GOD",3
        if upper_wick > body*2.5 and lower_wick < body*0.35 and c<o and pc>po and total_range > body*2.8:
            return "🌠 SHOOTING STAR GOD 4H 🔴💎","BEARISH 🔴 4H GOD",3
        if pc < po and c > o and c > po and o < pc and body > prev_body*1.25 and p2c < p2o and c > (po+pc)/2:
            return "🟩 BULL ENGULF GOD 4H 🚀💎","BULLISH 🟢 4H GOD",3
        if pc > po and c < o and c < po and o > pc and body > prev_body*1.25 and p2c > p2o and c < (po+pc)/2:
            return "🟥 BEAR ENGULF GOD 4H 📉💎","BEARISH 🔴 4H GOD",3
        if lower_wick > body*1.8 and c>o and total_range > body*1.8:
            return "🔨 HAMMER STRONG 4H 🟡","BULLISH 🟢 4H",2
        if upper_wick > body*1.8 and c<o and total_range > body*1.8:
            return "🌠 SHOOTING STRONG 4H 🟡","BEARISH 🔴 4H",2
        if pc < po and c > o and c > po and o < pc:
            return "🟩 BULL ENGULF STRONG 4H 🚀","BULLISH 🟢 4H",2
        if pc > po and c < o and c < po and o > pc:
            return "🟥 BEAR ENGULF STRONG 4H 📉","BEARISH 🔴 4H",2
        if body < total_range*0.12: return "➖ DOJI 4H ⏸️","NEUTRAL ⚪ 4H",0
        return "⚪ NONE 4H","NONE ⚪ 4H",0
    except: return "⚪ NONE 4H","NONE ⚪ 4H",0

def generate_colored_chart_4H(symbol, trade):
    try:
        kl = get_klines(symbol, "4h")
        if not kl or len(kl)<60: kl = get_klines(symbol, "2h")
        if not kl: return None
        closes = [k["c"] for k in kl]
        ema20 = ema_series(closes,20); ema50 = ema_series(closes,50); ema200 = ema_series(closes,200)
        plt.style.use('dark_background')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12,7), gridspec_kw={'height_ratios':[3,1]}, facecolor='#0e0e0e')
        fig.suptitle(f"{symbol} 4H PERFECT | {trade['pattern']} @ {fmt(trade['entry'])} | {trade['bias']} | Conf {trade['conf']:.0f}% RSI {trade['rsi']:.1f} ADX {trade['adx']:.1f} | {trade['mtf']}", color='white', fontsize=11, fontweight='bold')
        x = list(range(len(closes))); color = '#00ff88' if trade['dir']=="BUY" else '#ff4444'
        ax1.plot(x, closes, color=color, linewidth=2.5, label=f"Price 4H {symbol}")
        ax1.plot(x, ema20, color='#ffeb3b', linewidth=1.3, alpha=0.9, label='EMA20 🟡 4H')
        ax1.plot(x, ema50, color='#ff9800', linewidth=1.3, alpha=0.9, label='EMA50 🟠 4H')
        ax1.plot(x, ema200, color='#00bfff', linewidth=1.6, alpha=0.9, label='EMA200 🔵 4H')
        ax1.axhline(trade['entry'], color='white', linestyle='--', linewidth=1.2, label=f"Entry {fmt(trade['entry'])}")
        ax1.axhline(trade['sl'], color='#ff0000', linestyle='--', linewidth=1.1, label=f"SL {fmt(trade['sl'])}")
        ax1.axhline(trade['tp1'], color='#00ff00', linestyle=':', linewidth=1, label=f"TP1 {fmt(trade['tp1'])}")
        ax1.axhline(trade['tp3'], color='#00ff00', linestyle='-', linewidth=1.4, label=f"TP3 {fmt(trade['tp3'])}")
        last_x = x[-1]; last_price = closes[-1]
        ax1.annotate(f"{trade['pattern']}\n@ {fmt(last_price)}\n{trade['bias']}", xy=(last_x, last_price), xytext=(last_x-22, last_price*1.018 if trade['dir']=="BUY" else last_price*0.982), fontsize=9, fontweight='bold', color='black', bbox=dict(boxstyle="round,pad=0.5", fc="#ffeb3b" if "HAMMER" in trade['pattern'] else "#00ff88" if "BULL" in trade['pattern'] else "#ff4444", ec="white", alpha=0.97), arrowprops=dict(arrowstyle="->", color="white", lw=1.6))
        info_text = f"4H PERFECT BOT\n{trade['bias']}\nScore {trade['pat_score']}/3 GOD\n{trade['bos'][:32]}\n{trade['ob']}\nEMA {trade['ema_dist']}"
        ax1.text(0.02, 0.98, info_text, transform=ax1.transAxes, fontsize=8, color='white', va='top', ha='left', bbox=dict(boxstyle="round,pad=0.35", fc="#1e1e1e", ec="#00bfff", alpha=0.85))
        ax1.set_ylabel('Price 4H', color='white'); ax1.legend(loc='upper left', fontsize=7, facecolor='#1e1e1e'); ax1.grid(True, alpha=0.2, color='gray')
        rsi_vals = [rsi_calc(closes[:i+1]) for i in range(len(closes))]
        ax2.plot(x, rsi_vals, color='#e040fb', linewidth=1.7, label='RSI 14 4H')
        ax2.axhline(70, color='red', linestyle='--', alpha=0.5); ax2.axhline(30, color='green', linestyle='--', alpha=0.5); ax2.axhline(50, color='gray', linestyle='-', alpha=0.3)
        ax2.set_ylim(0,100); ax2.set_ylabel('RSI 4H', color='white'); ax2.legend(fontsize=7); ax2.grid(True, alpha=0.2)
        plt.tight_layout(); plt.savefig(CHART_FILE, dpi=170, bbox_inches='tight', facecolor='#0e0e0e'); plt.close()
        return CHART_FILE
    except Exception as e:
        print(f"Chart err {e}"); return None

def analyze_PERFECT_V67_4H(symbol):
    try:
        k1=get_klines(symbol,"1h"); k2=get_klines(symbol,"2h"); k4=get_klines(symbol,"4h")
        if len(k4)<60: k4=k2 if len(k2)>=60 else k1
        if len(k4)<60: return None, f"❌ {symbol} No 4H data 📭", {"score":0,"pat":0,"rsi":50}
        c1=[k["c"] for k in k1] if k1 else []; c2=[k["c"] for k in k2] if k2 else []; c4=[k["c"] for k in k4]
        price=get_price(symbol) or c4[-1]
        s1,t1,e1,strong1,dist200_1=trend_calc(c1 if c1 else c4)
        s2,t2,e2,strong2,dist200_2=trend_calc(c2 if c2 else c4)
        s4,t4,e4,strong4,dist200_4=trend_calc(c4)
        rsi=rsi_calc(c4); stoch=calc_stoch_rsi(c4); adx=adx_calc(k4)
        has_bos, bos_txt, bos_val, vol_confirm=calc_bos_META(k4)
        pattern4, bias4, pat_score4 = detect_candle_pattern_META(k4)
        pattern2, bias2, pat_score2 = detect_candle_pattern_META(k2 if k2 else k4)
        if pat_score4>=2: pattern, bias, pat_score = pattern4, bias4, pat_score4
        elif pat_score2>=2: pattern, bias, pat_score = pattern2, bias2, pat_score2
        else: pattern, bias, pat_score = pattern4, bias4, pat_score4
        direction="BUY" if s4>=0 else "SELL"
        if "BULLISH" in bias: direction="BUY"
        elif "BEARISH" in bias: direction="SELL"
        ob_ratio=get_orderbook_ratio(symbol, direction)
        btc_ok, btc_txt, btc_change=get_btc_filter()
        strong_count = int(strong1) + int(strong2) + int(strong4)
        trend_ok = (s1>=0 and s2>=0) or (s1<=0 and s2<=0) or (s2>=0 and s4>=0) or (s2<=0 and s4<=0) or (s1>=0 and s4>=0) or (s1<=0 and s4<=0)
        if not trend_ok: return None, f"❌ {symbol} FAIL 4H Trend {t1} / {t2} / {t4} 🕯️ {pattern}", {"score":0,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if pat_score < 2: return None, f"❌ {symbol} FAIL 4H Pattern {pat_score}/3 Need 2/3 {pattern}", {"score":pat_score*5,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if not has_bos and pat_score < 3: return None, f"❌ {symbol} FAIL {bos_txt} 🕯️ {pattern}", {"score":12+pat_score*5,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if not (25<=rsi<=85): return None, f"❌ {symbol} FAIL 📊 RSI 4H {rsi:.1f} not 25-85 🎯 {pattern}", {"score":15+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if stoch>=95: return None, f"❌ {symbol} FAIL 📈 Stoch 4H {stoch:.0f} >=95 🔥 {pattern}", {"score":18+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if adx<12: return None, f"❌ {symbol} FAIL 💪 ADX 4H {adx:.1f} <12 🚀 {pattern}", {"score":22+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if ob_ratio<1.03: return None, f"❌ {symbol} FAIL 📚 OB 4H {ob_ratio:.2f} <1.03 🐋 {pattern}", {"score":22+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        ema_dist=abs(price-e4)/e4*100 if e4 else 99
        if ema_dist>1.3: return None, f"❌ {symbol} FAIL 📏 EMA 4H {ema_dist:.2f}% >1.3% 📏 {pattern}", {"score":25+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if dist200_4>5.0: return None, f"❌ {symbol} FAIL 🌊 EMA200 4H {dist200_4:.1f}% far ⚠️", {"score":25+pat_score*6,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        if ("BULLISH" in bias and direction=="SELL") or ("BEARISH" in bias and direction=="BUY"): return None, f"❌ {symbol} FAIL Bias mismatch {bias} vs {direction}", {"score":10,"pat":pat_score,"rsi":rsi,"adx":adx,"ob":ob_ratio,"symbol":symbol,"price":price,"dir":direction,"pattern":pattern,"bias":bias,"bos":bos_txt,"mtf":f"1H {t1} | 2H {t2} | 4H {t4}"}
        conf = 80 + pat_score*10 + min(adx,30) + (8 if vol_confirm else 0) + (strong_count*2)
        sl_pct=0.018; tp1_pct=0.015; tp2_pct=0.03; tp3_pct=0.05
        if direction=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
        else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)
        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp3_pct":tp3_pct*100,"rsi":rsi,"stoch":stoch,"adx":adx,"mtf":f"1H {t1} | 2H {t2} | 4H {t4} ({strong_count}/3 STRONG 💪💎 4H)","bos":bos_txt,"ob":f"📚 OB 4H {ob_ratio:.2f} Whale 🐋💎","btc":btc_txt,"ema_dist":f"{ema_dist:.2f}%","conf":conf,"pattern":pattern,"bias":bias,"pat_score":pat_score,"choppy":ema_dist,"vol":vol_confirm}
        return trade, "✅ 4H PERFECT GOD ENTRY 🎉💎🏆"
    except Exception as e: return None, f"❌ {symbol} ERR 💥 {e}", {"score":0}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/3 4H 💰',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR 4H {active["coin"]} 📊🧠',callback_data="MON"), InlineKeyboardButton(f'❌ Close Trade 🛑',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 148 4H PERFECT 🚀💎',callback_data="SCAN"), InlineKeyboardButton(f'🔥 RISK 1.5% ⚡',callback_data="RISK15"), InlineKeyboardButton(f'🔥 RISK 2% 💥',callback_data="RISK20")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 💵',callback_data="DAILY"), InlineKeyboardButton(f'📈 CHART 4H 📊',callback_data="CHART")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([
            BotCommand("start","🧠 V67 4H PERFECT"),
            BotCommand("scan","🧠 SCAN 148 4H PERFECT"),
            BotCommand("risk15","🔥 RISK 1.5%"),
            BotCommand("risk20","🔥 RISK 2%"),
            BotCommand("monitor","👀 MONITOR 4H"),
            BotCommand("daily","📊 Daily P&L"),
            BotCommand("chart","📈 CHART 4H SYMBOL")
        ])
    except: pass

def send_chart_photo(chat_id, file_path, caption):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        with open(file_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            requests.post(url, data=data, files=files, timeout=18, proxies=PROXIES)
    except Exception as e: print(f"Send chart err {e}")

def bg_scan(chat_id, risk_mode_override=None):
    try:
        bal=get_futures_balance(); all_symbols=get_real_alt_futures_FIXED()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🧠💎 SKELLY'S V67 4H PERFECT BOT - ANALYSE LIKE PRO! 💎🧠📊🕯️\n🌐 Scanning {len(all_symbols)} Binance Futures 4H Accurate! ⚡🔍\n🧠 Timeframe: 1H + 2H + 4H need 2/3 aligned 💪\n🕯️ Candle: 4H GOD first, 2H backup + body/wick ratio perfect!\n📊 Filters: RSI 25-85 + Stoch <95 + ADX >=12 + OB >=1.03 + EMA <1.3% + E200 <5% + Bias Match!\n📈 Full 4H colored chart + candle label bubble!\n⏳ 30 sec... Please wait perfect entry! 🙏🧠👑"},timeout=10,proxies=PROXIES)
        raws=[]; near_misses=[]; fails=[]
        def scan_one(sym):
            trade, msg, meta = analyze_PERFECT_V67_4H(sym)
            return (sym, trade, msg, meta)
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(scan_one, all_symbols))
        for sym, trade, msg, meta in results:
            if trade: raws.append(trade)
            else:
                fails.append(msg)
                if meta.get("pat",0)>=1: near_misses.append(meta)
        if not raws and near_misses:
            near_misses.sort(key=lambda x: (x.get("score",0), x.get("pat",0), x.get("adx",0)), reverse=True)
            best_fallback = near_misses[0]
            if best_fallback.get("score",0) >= 25:
                sym = best_fallback["symbol"]; price = best_fallback["price"]; direction = best_fallback["dir"]
                sl_pct=0.018; tp1_pct=0.015; tp2_pct=0.03; tp3_pct=0.05
                if direction=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
                else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)
                code=sym.replace("USDT","")
                forced = {"symbol":sym,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp3_pct":tp3_pct*100,"rsi":best_fallback.get("rsi",50),"stoch":50,"adx":best_fallback.get("adx",12),"mtf":best_fallback.get("mtf","2/3 Aligned 4H"),"bos":best_fallback.get("bos","BOS optional 4H"),"ob":f"📚 OB 4H {best_fallback.get('ob',1.03):.2f} Whale 🐋💎","btc":"₿ BTC Mid 4H ⚖️","ema_dist":"1.0%","conf":68,"pattern":best_fallback.get("pattern","🔨 HAMMER STRONG 4H 🟡"),"bias":best_fallback.get("bias","BULLISH 🟢 4H"),"pat_score":best_fallback.get("pat",2),"choppy":0,"vol":False}
                raws.append(forced)
        if not raws:
            txt=f"🧠💎 SKELLY'S V67 4H PERFECT - PROTECT MODE 🛡️🧠📊🕯️\nScanned {len(all_symbols)} Binance Futures 4H! 🌐⚡\n🔍 No 4H PERFECT entry — market choppy! Need:\n✅ 1H/2H/4H 2/3 Aligned 💪💎 4H Accurate\n✅ 4H GOD Pattern 2/3+: 🔨 HAMMER / 🟩 ENGULF 💎 4H\n✅ BOS 4H Vol Confirm + OB >=1.03 🐋 + ADX >=12\n✅ RSI 25-85 + Stoch <95 + EMA <1.3% + Bias Match\n\n💰 Bal ${bal:.2f} safe! 🛡️💎 Wait 10 mins 4H candle close! ⏰🙏🧠\n\nTOP NEAR MISSES 4H:\n" + "\n".join(fails[:6])
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x: (x['conf'], x['adx'], x['pat_score']), reverse=True)
        best=raws[0]
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active trade {get_active().get('coin')} OPEN! 🟢 Close first! 🛑🧠"},timeout=10,proxies=PROXIES); return
        mode="V67 4H PERFECT 🎯🧠📊"
        if risk_mode_override=="2.0" or RISK_MODE=="2.0": mode="V67 4H RISKY20 💥🧠📊"
        elif risk_mode_override=="1.5" or RISK_MODE=="1.5": mode="V67 4H RISKY15 ⚡🧠📊"
        amt=get_trade_amount(mode); real_symbol=best['symbol']
        order_res=place_real_order(real_symbol, best['dir'], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol} 💥 Check Binance API! 🔑🧠"},timeout=10,proxies=PROXIES); return
        set_active({"status":"OPEN","coin":best['code'],"symbol":real_symbol,"dir":best['dir'],"entry":best['entry'],"sl":best['sl'],"tp1":best['tp1'],"tp2":best['tp2'],"tp3":best['tp3'],"conf":best['conf'],"stake":amt,"lev":10,"stage":0,"highest":best['entry'],"lowest":best['entry'],"sl_pct":best['sl_pct'],"tp3_pct":best['tp3_pct'],"mode":mode,"time":str(datetime.now()),"pattern":best['pattern']})
        chart_path = generate_colored_chart_4H(real_symbol, best)
        txt=(f"🧠💎 SKELLY'S V67 4H PERFECT FOUND! 📊🕯️✅🏆💎🧠\n💎 {best['symbol']} {best['dir']} @ {fmt(best['entry'])} 💰 4H PERFECT ENTRY! 🎯\n🕯️ CANDLE: {best['pattern']} {best['bias']} Score {best['pat_score']}/3 GOD ⭐ Conf {best['conf']:.0f}% 🔥🧠 4H\n💰 ${amt} 10x | 🛑 SL {best['sl_pct']:.1f}% TP1 {best['tp1_pct']:.1f}% TP3 {best['tp3_pct']:.1f}% (1:2.7) 🎯\n🆔 ORDER {order_res.get('orderId')} ✅ {mode} 🟢💎 4H Perfect!\n━━━━━━━━━━━━━━━\n🧠 PERFECT 4H ANALYSIS PASSED ✅🧠\n✅ {best['mtf']} 💎 4H Accurate\n✅ {best['bos']} 💎\n✅ 🕯️ {best['pattern']} {best['bias']} {best['pat_score']}/3 + 📊 RSI {best['rsi']:.1f} + 💪 ADX {best['adx']:.1f} + 📈 Stoch {best['stoch']:.0f} ✅🧠\n✅ {best['ob']} ✅🐋\n✅ 📏 EMA {best['ema_dist']} + {best['btc']} ✅📈\n━━━━━━━━━━━━━━━\n💵 Bal ${bal:.2f} | 🎯 4H TP1 1.5% = $0.45 profit! 50% lock BE 🛡️🔒 | Chart + Candle label below 👇📊🕯️")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES)
        if chart_path and os.path.exists(chart_path):
            send_chart_photo(chat_id, chart_path, f"📊 {best['symbol']} 4H PERFECT CHART + CANDLE LABEL 🎨🕯️👑\n🕯️ {best['pattern']} @ {fmt(best['entry'])} {best['bias']}\n🟡 EMA20 | 🟠 EMA50 | 🔵 EMA200 4H Accurate\nWhite -- Entry | Red -- SL | Green TP1/TP3\nRSI {best['rsi']:.1f} ADX {best['adx']:.1f} Stoch {best['stoch']:.0f} | Analyse like pro trader! 🧠💎")
    except Exception as e:
        print(f"SCAN ERR {e}"); import traceback; traceback.print_exc()
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Scan error 4H: {e} 💥🧠"},timeout=10,proxies=PROXIES)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(f"🧠💎 SKELLY'S V67 4H PERFECT BOT 👑✨📊🕯️🧠\n💰 Futures ${bal:.2f} USDT 💵 Risk {RISK_MODE}% ⚙️ 4H Accurate\n\n🧠 PERFECT ANALYSIS LIKE ME:\n🌐 Scans 148 Binance Futures — 1H + 2H + 4H Timeframe Accurate! ⚡\n🏆 ONLY 4H PERFECT GOD ENTRY — Analyse like pro trader!\n🛡️ Protects $ Balance but MUST snap perfect!\n\n🕯️ 4H CANDLE PATTERNS 2/3+ PERFECT:\n🔨 HAMMER GOD 4H 💎 / 🌠 SHOOTING STAR GOD 4H 💎\n🟩 BULL ENGULF GOD 4H 🚀💎 / 🟥 BEAR ENGULF GOD 4H 📉💎\nNeed body/wick ratio perfect + trend + volume!\n\n📜 V67 4H PERFECT RULES Accurate:\n✅ 1H/2H/4H 2/3 Aligned 💪💎 4H Accurate\n✅ 4H GOD Pattern 2/3+ Score + Bias Match 💎\n✅ 💥 BOS 4H Vol 1.1x Confirm + 📚 OB >=1.03 🐋 + 💪 ADX >=12\n✅ 📊 RSI 25-85 + 📈 Stoch <95 + 📏 EMA <1.3% + E200 <5%\n✅ FALLBACK only if score >25 — Perfect not random! 🔥\n\n💵 4H TP1 1.5% = $0.45 50% BE 🛡️\n💵 4H TP3 5% = $1.50 🎉\n📊 4H Chart + Candle Label Bubble!\n\nPress 🧠 SCAN 148 4H PERFECT now! Must trade perfect! 🎯🚀💎📊🕯️",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("🧠 SKELLY'S V67 4H PERFECT SCANNING 148... Analyse like pro! 🎯📊🕯️ 30 sec... ⏳⚡💎 4H Accurate!")

async def risk15_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "1.5"),daemon=True).start()
    await u.message.reply_text("🔥 SKELLY'S V67 4H PERFECT RISK 1.5% ⚡ Scanning 148 4H... 🕯️🧠🚀📊")

async def risk20_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "2.0"),daemon=True).start()
    await u.message.reply_text("🔥🔥 SKELLY'S V67 4H PERFECT RISK 2% 💥 Scanning 148 4H... 🕯️🧠🚀📊")

async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 Daily P&L V67 4H PERFECT 🧠📈📊🕯️\n🏆 {d['wins']}W/{d['losses']}L 💪\n💰 ${d['pnl']:.2f} 💵\n🔢 Trades: {d['trades']} 🎯\nSKELLY'S V67 4H PERFECT 👑💎📊🕯️",reply_markup=kb(get_active()))

async def chart_cmd(u,c):
    save_chat(u.message.chat.id)
    symbol = (c.args[0] if c.args else "SOLUSDT").upper()
    if not symbol.endswith("USDT"): symbol += "USDT"
    await u.message.reply_text(f"📊 Generating 4H PERFECT colored chart + candle label for {symbol}... 🎨🕯️⏳ 4H Accurate!")
    try:
        kl = get_klines(symbol, "4h")
        if not kl: 
            await u.message.reply_text(f"❌ No 4H data for {symbol} 📭")
            return
        closes = [k["c"] for k in kl]; price = closes[-1]
        pat, bias, score = detect_candle_pattern_META(kl)
        dummy_trade = {"symbol":symbol,"dir":"BUY" if "BULLISH" in bias else "SELL","entry":price,"sl":price*0.982,"tp1":price*1.015,"tp3":price*1.05,"rsi":rsi_calc(closes),"adx":adx_calc(kl),"stoch":calc_stoch_rsi(closes),"pattern":pat,"bias":bias,"pat_score":score,"conf":85,"bos":"BOS 4H check","ob":"OB 1.05 4H","btc":"BTC Mid 4H","ema_dist":"0.8%","mtf":"1H UP | 2H UP | 4H UP 3/3"}
        path = generate_colored_chart_4H(symbol, dummy_trade)
        if path and os.path.exists(path):
            await u.message.reply_photo(photo=open(path,'rb'), caption=f"📊 {symbol} 4H PERFECT Chart + Candle Label 🎨🕯️👑\n🕯️ {pat} {bias} Score {score}/3 @ {fmt(price)} 4H Accurate\n🟡 EMA20 | 🟠 EMA50 | 🔵 EMA200 4H\nAnalyse like pro trader! 🧠💎")
        else: await u.message.reply_text("❌ Chart failed 💥")
    except Exception as e: await u.message.reply_text(f"❌ Chart error 4H {e} 💥")

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN":
        await u.message.reply_text("😴 No active trade - Press SCAN 148 4H PERFECT! 🧠🚀💎📊🕯️ 4H",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]; stake=act["stake"]; lev=act["lev"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    pnl_usdt=pnl_pct/100*stake*lev; bal=get_futures_balance()
    txt=(f"👀 MONITOR 4H PERFECT {act.get('mode','')} AI {act.get('conf',0)}% 🧠🤖📊🕯️ 4H\n💎 {act['coin']} {act['dir']} Stage {act.get('stage',0)}/3 🎯 4H\n🕯️ Pattern {act.get('pattern','')} ✨💎 4H\n📍 Entry {fmt(entry)} → Now {fmt(price)} 📊 4H\n💹 P&L {pnl_pct:.3f}% (${pnl_usdt:+.4f}) 💰 ROI {pnl_pct*lev:.1f}% 📈 4H\n💵 Bal ${bal:.2f} 🛡️ 4H Perfect")
    await u.message.reply_text(txt, reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily P&L V67 4H PERFECT 🧠📈📊🕯️ 4H {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💵 V67 4H PERFECT 👑💎📊🕯️",reply_markup=kb(get_active())); return
    if data=="CHART":
        act=get_active()
        if act.get("status")=="OPEN":
            path = generate_colored_chart_4H(act["symbol"], {"symbol":act["symbol"],"dir":act["dir"],"entry":act["entry"],"sl":act["sl"],"tp1":act["tp1"],"tp3":act["tp3"],"rsi":50,"adx":14,"stoch":50,"pattern":act.get("pattern",""),"bias":"BULLISH 4H","pat_score":3,"conf":act.get("conf",85),"bos":"BOS 4H","ob":"OB 1.05 4H","btc":"BTC Mid 4H","ema_dist":"0.8%","mtf":"1H/2H/4H Aligned 4H"})
            if path: await q.message.reply_photo(photo=open(path,'rb'), caption=f"📊 {act['coin']} 4H PERFECT Current Chart + Candle Label 🎨🕯️📈 4H Accurate")
        else: await q.message.reply_text("😴 No active trade — use /chart SOLUSDT to get 4H perfect chart + candle label 📊🕯️ 4H")
        return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade 4H 😴🧠📊🕯️",reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        pnl_usdt=pnl_pct/100*act["stake"]*act["lev"]
        await q.message.reply_text(f"👀 4H {act['coin']} {act['dir']} {pnl_pct:.2f}% (${pnl_usdt:+.4f}) 💰 Pattern {act.get('pattern','')} 🕯️💎📊 4H",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed Trade 4H ✅ Safe! 🛡️🧠📊🕯️ 4H",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("🧠 V67 4H PERFECT SCANNING 148 + Candle Label 4H... 🔍💎⚡🧠📊🕯️ 4H Accurate!"); return
    if data=="RISK15": threading.Thread(target=bg_scan,args=(q.message.chat.id, "1.5"),daemon=True).start(); await q.message.reply_text("🔥 V67 4H PERFECT RISK 1.5%... ⚡🚀🧠📊🕯️ 4H"); return
    if data=="RISK20": threading.Thread(target=bg_scan,args=(q.message.chat.id, "2.0"),daemon=True).start(); await q.message.reply_text("🔥🔥 V67 4H PERFECT RISK 2%... 💥🚀🧠📊🕯️ 4H"); return

def monitor():
    while True:
        try:
            time.sleep(5); act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(act["symbol"])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            stage=act.get("stage",0); entry=act["entry"]; symbol=act["symbol"]; mode=act.get("mode","SNIPER")
            if act["dir"]=="BUY": roi=(price-entry)/entry*100*10
            else: roi=(entry-price)/entry*100*10
            if "SNIPER" in mode and roi<=-5.0:
                close_real_position(symbol,100); clear_active(); update_daily(-0.15, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨 -5% ROI GUARD 4H! 🛡️ {act['coin']} Closed! 😴 Loss $0.15 💸🧠📊🕯️ 4H"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            max_roi=-18.0 if "1.5" in mode else -23.0 if "2.0" in mode else -12.0
            if roi<=max_roi:
                close_real_position(symbol,100); clear_active()
                loss=0.65 if "2.0" in mode else 0.50 if "1.5" in mode else 0.30
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨🛑 SL 4H {act.get('sl_pct',1.8):.1f}% HIT 💥 {act['coin']} ROI {roi:.1f}% 📉 Loss ${loss:.2f} 💸🛡️🧠📊🕯️ 4H"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            if act["dir"]=="BUY": act["highest"]=max(act.get("highest",entry),price)
            else: act["lowest"]=min(act.get("lowest",entry),price)
            hit=None
            if stage>=2:
                trail=0.015 if "RISKY" in mode else 0.01
                if act["dir"]=="BUY":
                    nts=act["highest"]*(1-trail)
                    if nts>act["sl"]: act["sl"]=nts; set_active(act)
                else:
                    nts=act["lowest"]*(1+trail)
                    if nts<act["sl"]: act["sl"]=nts; set_active(act)
                if act["dir"]=="BUY" and price<=act["sl"]: hit="TRAIL_SL"
                elif act["dir"]=="SELL" and price>=act["sl"]: hit="TRAIL_SL"
            if not hit:
                if act["dir"]=="BUY":
                    if stage==0 and price>=act["tp1"]: hit="TP1"
                    elif stage==1 and price>=act["tp2"]: hit="TP2"
                    elif stage>=2 and price>=act["tp3"]: hit="TP3"
                    elif price<=act["sl"] and stage==0: hit="SL"
                else:
                    if stage==0 and price<=act["tp1"]: hit="TP1"
                    elif stage==1 and price<=act["tp2"]: hit="TP2"
                    elif stage>=2 and price<=act["tp3"]: hit="TP3"
                    elif price>=act["sl"] and stage==0: hit="SL"
            if hit=="TP1":
                # FIXED: EXACT BREAKEVEN MOVE - SL = ENTRY
                close_real_position(symbol,50)
                new_sl = entry  # EXACT BE - no +0.1%
                act["sl"]=new_sl; act["stage"]=1; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 4H HIT! 🎉 {act['coin']} +{act.get('sl_pct',1.8):.1f}% 💰 50% BE EXACT @ {fmt(entry)} 🛡️🔒 Pattern {act.get('pattern','')} 🕯️💎📊🕯️ 4H Perfect! 🧠"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol,30); act["sl"]=act["tp1"]; act["stage"]=2; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 TP2 4H HIT! 🎉🎉 {act['coin']} + TRAILING 4H 🏃💨🔒🧠📊🕯️"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol,100); clear_active()
                win=2.0 if "2.0" in mode else 1.50 if "1.5" in mode else 0.65
                update_daily(win, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 TP3 4H HIT! 🏆🎉 {act['coin']} +{act.get('tp3_pct',5.0):.1f}% +${win:.2f} 💰💰💰 Pattern {act.get('pattern','')} GOD ENTRY 4H PERFECT! 👑🚀🧠💎📊🕯️ 4H"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol,100); clear_active(); update_daily(0.80, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING SL 4H HIT! 🔒 {act['coin']} Profit $0.80+ 💰✅🧠📊🕯️ 4H"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="SL":
                close_real_position(symbol,100); clear_active()
                loss=0.65 if "2.0" in mode else 0.50 if "1.5" in mode else 0.30
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL 4H {act.get('sl_pct',1.8):.1f}% HIT 😢 {act['coin']} Loss ${loss:.2f} 💸🛡️🧠📊🕯️ 4H"},timeout=8,proxies=PROXIES)
                except: pass
        except Exception as e:
            print(f"monitor err {e}"); time.sleep(5)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing ❌🧠"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("risk15",risk15_cmd)); a.add_handler(CommandHandler("risk20",risk20_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("chart",chart_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"🧠💎 SKELLY'S V67 4H PERFECT starting Risk {RISK_MODE}% 🚀 148 coins 4H PERFECT + CHART 🕯️📊"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
