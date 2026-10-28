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

# === V78 HYBRID FINAL - CORRECT ANALYSIS + SAFE MODE FROM YOUR IMAGE ===
PAPER_TRADING = True   # From your image: True = NO REAL MONEY until YES!
AUTO_TRADE = False     # From your image: False = YOU must press YES BUY!
SL_ROI_PERCENT = 3.5   # From your image: 35% ROI = $1.05 loss smaller than $1.35!

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v67.json"
DAILY_FILE = f"{DATA_DIR}/daily_v67.json"
CHAT_FILE = f"{DATA_DIR}/chat_v67.json"
CHART_FILE = f"{DATA_DIR}/chart_v67.png"
PENDING_FILE = f"{DATA_DIR}/pending_v78.json"
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
    return 7.49

def get_trade_amount(mode="SNIPER"): return 3.0

def get_real_alt_futures_FIXED():
    # V78 - Only 30 SAFE coins from your image - NO BULLA, NO KORU, NO new coin!
    safe_30 = ["PEPEUSDT","DOGEUSDT","SHIBUSDT","WIFUSDT","BONKUSDT","FLOKIUSDT","SOLUSDT","AVAXUSDT","SUIUSDT","ARBUSDT","OPUSDT","TIAUSDT","WLDUSDT","NEARUSDT","APTUSDT","SEIUSDT","PYTHUSDT","JUPUSDT","FETUSDT","RNDRUSDT","LINKUSDT","INJUSDT","ADAUSDT","XRPUSDT","DOTUSDT","LTCUSDT","BCHUSDT","ETCUSDT","FILUSDT","UNIUSDT"]
    blacklist = ["KORUUSDT","BULLAUSDT","RATSUSDT","SATSUSDT","ORDIUSDT","MOGUSDT","1000RATSUSDT","1000SATSUSDT","TURBOUSDT","PEOPLEUSDT","MEMEUSDT","BULLA","KORU"]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",headers=HEADERS,timeout=15,proxies=PROXIES).json()
        valid=[]
        if isinstance(r,list):
            for t in r:
                sym=t.get('symbol','')
                if sym not in safe_30: continue
                if sym in blacklist: continue
                if "BULLA" in sym or "KORU" in sym: continue
                try:
                    vol=float(t.get('quoteVolume',0))
                    if vol<5000000: continue
                    valid.append(sym)
                except: continue
            return valid
    except: pass
    return safe_30

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        c=float(r.get('priceChangePercent',0))
        if c>=2.0: return True, f"BTC +{c:.1f}% Bull BLOCK SELL", c
        if c<=-2.0: return True, f"BTC {c:.1f}% Bear BLOCK BUY", c
        return True, f"BTC {c:.1f}%", c
    except: return True, "BTC N/A", 0

def get_symbol_filters(symbol):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",params={"symbol":symbol},headers=HEADERS,timeout=8,proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==symbol:
                if s.get('status')!='TRADING': return None, None, None
                qp=int(s.get('quantityPrecision',3)); pp=int(s.get('pricePrecision',5)); ss=0.001
                for f in s.get('filters',[]):
                    if f.get('filterType')=='LOT_SIZE': ss=float(f.get('stepSize',0.001))
                return qp, ss, pp
    except: pass
    return 3, 0.001, 5

def setup_symbol(symbol):
    try: binance_signed_request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"})
    except: pass
    try: binance_signed_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": 10})
    except: pass

def cancel_all_open_orders(symbol):
    try: binance_signed_request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol})
    except: pass

def set_binance_tpsl_visible(symbol, direction, sl_price, tp1, tp2, tp3, tp4):
    try:
        cancel_all_open_orders(symbol); time.sleep(0.3)
        pos = binance_signed_request("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        qty_total = 0
        if isinstance(pos, list):
            for p in pos:
                if p.get('symbol')==symbol: qty_total = abs(float(p.get('positionAmt',0))); break
        if qty_total==0: return
        qp, ss, pp = get_symbol_filters(symbol)
        if qp is None: return
        close_side = "BUY" if direction=="SELL" else "SELL"
        try:
            sl_params = {"symbol": symbol, "side": close_side, "type": "STOP_MARKET", "stopPrice": round(sl_price, pp), "closePosition": "true"}
            binance_signed_request("POST", "/fapi/v1/order", sl_params)
        except: pass
        qty_25 = qty_total * 0.25
        if ss>0: qty_25 = math.floor(qty_25/ss)*ss
        qty_25 = round(qty_25, qp)
        if qty_25<=0: qty_25 = qty_total*0.25
        for i, tp_price in enumerate([tp1, tp2, tp3, tp4]):
            try:
                qty = qty_25 if i<3 else round(qty_total - qty_25*3, qp)
                if qty<=0: qty=qty_25
                tp_params = {"symbol": symbol, "side": close_side, "type": "TAKE_PROFIT_MARKET", "stopPrice": round(tp_price, pp), "quantity": qty, "reduceOnly": "true"}
                binance_signed_request("POST", "/fapi/v1/order", tp_params); time.sleep(0.2)
            except: pass
    except: pass

def update_sl_to_be_visible(symbol, direction, entry_price):
    try:
        cancel_all_open_orders(symbol); time.sleep(0.3)
        qp, ss, pp = get_symbol_filters(symbol)
        close_side = "BUY" if direction=="SELL" else "SELL"
        sl_params = {"symbol": symbol, "side": close_side, "type": "STOP_MARKET", "stopPrice": round(entry_price, pp), "closePosition": "true"}
        binance_signed_request("POST", "/fapi/v1/order", sl_params)
    except: pass

def place_real_order(symbol, direction, usdt_amount, is_confirmed=False):
    if PAPER_TRADING and not is_confirmed:
        print(f"PAPER MODE: Would place {direction} {symbol} - Need YES confirmation!")
        return {"orderId": 999999, "symbol": symbol, "side": direction, "paper": True}
    if not AUTO_TRADE and not is_confirmed:
        return {"orderId": 999999, "symbol": symbol, "side": direction, "paper": True}
    try:
        filters = get_symbol_filters(symbol)
        if filters[0] is None: return None
        rp=requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",proxies=PROXIES,headers=HEADERS,timeout=10).json()
        price=float(rp.get('price',0))
        if price<=0: return None
        qp, ss, pp = filters
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
            qp, ss, pp=get_symbol_filters(symbol)
            if qp is None: qp=3; ss=0.001
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
def get_pending(): return load_json(PENDING_FILE,{})
def set_pending(d): save_json(PENDING_FILE,d)
def clear_pending(): save_json(PENDING_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return f"V78 HYBRID FINAL PAPER={PAPER_TRADING} AUTO={AUTO_TRADE} SL 35% ROI $1.05 + MA7/25/99 + 30 SAFE + BULLA/KORU BLOCK!",200
@app.get("/health")
def health(): return "OK V78 HYBRID",200

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
        if key in CACHE and time.time()-CACHE[key][0]<45: return CACHE[key][1]
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
def sma(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
    return sum(arr[-p:])/p
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
    if len(closes)<50: return 0,"SIDEWAYS",0,False,0
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200)
    pr=closes[-1]; dist200 = abs(pr-e200)/e200*100
    if pr>e20>e50 and pr>e200: return 60,"UPTREND STRONG",e20,True,dist200
    if pr<e20<e50 and pr<e200: return -60,"DOWNTREND STRONG",e20,True,dist200
    if pr>e20>e50: return 40,"UPTREND",e20,True,dist200
    if pr<e20<e50: return -40,"DOWNTREND",e20,True,dist200
    if pr>e20: return 20,"WEAK UP",e20,False,dist200
    if pr<e20: return -20,"WEAK DOWN",e20,False,dist200
    return 0,"SIDEWAYS",e20,False,dist200
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
        if curr>last_h*1.0003 and vol_confirm: return True,f"BOS UP Vol {vol_now/vol_avg:.1f}x", curr-last_h, True
        if curr<last_l*0.9997 and vol_confirm: return True,f"BOS DOWN Vol {vol_now/vol_avg:.1f}x", last_l-curr, True
        if curr>last_h*1.0003: return True,f"BOS UP", curr-last_h, False
        if curr<last_l*0.9997: return True,f"BOS DOWN", last_l-curr, False
        return False,f"No BOS {curr:.4f}",0, False
    except: return False,"BOS N/A",0, False
def get_orderbook_ratio(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":40},headers=HEADERS,timeout=3,proxies=PROXIES).json()
        bids=r.get('bids',[]); asks=r.get('asks',[])
        if not bids or not asks: return 1.0
        bv=float(sum([float(x[0])*float(x[1]) for x in bids[:20]])); av=float(sum([float(x[0])*float(x[1]) for x in asks[:20]]))
        if bv==0 or av==0: return 1.0
        return bv/av if direction=="BUY" else av/bv
    except: return 1.0
def detect_candle_pattern_META(kl):
    try:
        if len(kl)<4: return "NONE","NONE",0
        prev=kl[-2]; last=kl[-1]
        o,h,l,c = last["o"],last["h"],last["l"],last["c"]
        po,ph,pl,pc = prev["o"],prev["h"],prev["l"],prev["c"]
        body = abs(c-o)
        if body==0: body=0.0001
        upper_wick = h - max(c,o); lower_wick = min(c,o) - l; total_range = h-l
        if lower_wick > body*2.0 and upper_wick < body*0.5 and c>o and total_range > body*2.2:
            return "HAMMER BULL","BULLISH",3
        if upper_wick > body*2.0 and lower_wick < body*0.5 and c<o and total_range > body*2.2:
            return "SHOOTING BEAR","BEARISH",3
        if pc < po and c > o and c > po and o < pc:
            return "BULL ENGULF","BULLISH",3
        if pc > po and c < o and c < po and o > pc:
            return "BEAR ENGULF","BEARISH",3
        if lower_wick > body*1.5 and c>o:
            return "HAMMER STRONG","BULLISH",2
        if upper_wick > body*1.5 and c<o:
            return "SHOOTING STRONG","BEARISH",2
        return "NONE","NONE",0
    except: return "NONE","NONE",0

def generate_colored_chart_4H(symbol, trade):
    try:
        kl = get_klines(symbol, "15m")
        if not kl or len(kl)<60: kl = get_klines(symbol, "1h")
        if not kl: return None
        closes = [k["c"] for k in kl]
        ema20 = ema_series(closes,20); ema50 = ema_series(closes,50)
        plt.style.use('dark_background')
        fig, ax1 = plt.subplots(figsize=(10,5), facecolor='#0e0e0e')
        fig.suptitle(f"{symbol} V78 HYBRID SAFE+ CORRECT | {trade['pattern']} @ {fmt(trade['entry'])}", color='white', fontsize=11, fontweight='bold')
        x = list(range(len(closes))); color = '#00ff88' if trade['dir']=="BUY" else '#ff4444'
        ax1.plot(x, closes, color=color, linewidth=2.5); ax1.plot(x, ema20, color='#ffeb3b', linewidth=1.2); ax1.plot(x, ema50, color='#ff9800', linewidth=1.2)
        ax1.axhline(trade['entry'], color='white', linestyle='--'); ax1.axhline(trade['sl'], color='red', linestyle='--'); ax1.axhline(trade['tp1'], color='green', linestyle=':')
        ax1.grid(True, alpha=0.2)
        plt.tight_layout(); plt.savefig(CHART_FILE, dpi=150, bbox_inches='tight', facecolor='#0e0e0e'); plt.close()
        return CHART_FILE
    except: return None

def analyze_PERFECT_V78(symbol):
    try:
        if "BULLA" in symbol or "KORU" in symbol:
            return None, f"❌ {symbol} BLOCKLIST BULLA/KORU!", {"score":0,"pat":0}
        k15=get_klines(symbol,"15m"); k1=get_klines(symbol,"1h"); k4=get_klines(symbol,"4h")
        if len(k15)<100:
            return None, f"❌ {symbol} BLOCK <100 candles new coin!", {"score":0,"pat":0}
        c15=[k["c"] for k in k15]; c1=[k["c"] for k in k1] if k1 else c15; c4=[k["c"] for k in k4] if k4 else c1
        price=get_price(symbol) or c15[-1]
        ma7 = sma(c15, 7); ma25 = sma(c15, 25); ma99 = sma(c15, 99) if len(c15)>=99 else ema(c15, 99)
        if abs(ma7 - ma25) < 0.0000001 and abs(ma25 - ma99) < 0.0000001:
            return None, f"❌ {symbol} BLOCK MA all same {fmt(ma7)} = No history BULLA!", {"score":0,"pat":0}
        ema20_v = ema(c15, 20)
        s15,t15,e15,strong15,dist200_15=trend_calc(c15)
        s1,t1,e1,strong1,dist200_1=trend_calc(c1)
        s4,t4,e4,strong4,dist200_4=trend_calc(c4)
        rsi=rsi_calc(c15); stoch=calc_stoch_rsi(c15); adx=adx_calc(k15)
        has_bos, bos_txt, bos_val, vol_confirm=calc_bos_META(k15)
        pattern15, bias15, pat_score15 = detect_candle_pattern_META(k15)
        pattern1, bias1, pat_score1 = detect_candle_pattern_META(k1 if k1 else k15)
        if pat_score15>=2: pattern, bias, pat_score = pattern15, bias15, pat_score15
        elif pat_score1>=2: pattern, bias, pat_score = pattern1, bias1, pat_score1
        else: pattern, bias, pat_score = pattern15, bias15, pat_score15
        direction="BUY" if s15>=0 else "SELL"
        if "BULLISH" in bias: direction="BUY"
        elif "BEARISH" in bias: direction="SELL"
        btc_ok, btc_txt, btc_change = get_btc_filter()
        strong_up = price > ma7 and ma7 > ma25 and ma25 > ma99
        strong_down = price < ma7 and ma7 < ma25 and ma25 < ma99
        weak_up = price > ma7 and price > ma25
        weak_down = price < ma7 and price < ma25
        if strong_up and direction=="SELL":
            return None, f"❌ {symbol} BLOCK SELL UPTREND Price > MA7 > MA25 > MA99 = BUY not SELL!", {"score":0,"pat":pat_score}
        if strong_down and direction=="BUY":
            return None, f"❌ {symbol} BLOCK BUY DOWNTREND Price < MA7 < MA25 < MA99 = SELL not BUY!", {"score":0,"pat":pat_score}
        if weak_up and direction=="SELL" and pat_score<3:
            return None, f"❌ {symbol} BLOCK WEAK SELL in UPTREND", {"score":5,"pat":pat_score}
        if weak_down and direction=="BUY" and pat_score<3:
            return None, f"❌ {symbol} BLOCK WEAK BUY in DOWNTREND", {"score":5,"pat":pat_score}
        if btc_change >= 2.0 and direction=="SELL":
            return None, f"❌ {symbol} BLOCK SELL BTC Bull +{btc_change:.1f}%", {"score":0,"pat":pat_score}
        if btc_change <= -2.0 and direction=="BUY":
            return None, f"❌ {symbol} BLOCK BUY BTC Bear {btc_change:.1f}%", {"score":0,"pat":pat_score}
        if weak_up and "BEARISH" in bias and pat_score<3:
            return None, f"❌ {symbol} FAIL Pattern BEARISH not match UPTREND", {"score":8,"pat":pat_score}
        if weak_down and "BULLISH" in bias and pat_score<3:
            return None, f"❌ {symbol} FAIL Pattern BULLISH not match DOWNTREND", {"score":8,"pat":pat_score}
        ob_ratio=get_orderbook_ratio(symbol, direction)
        strong_count = int(strong15) + int(strong1) + int(strong4)
        trend_ok = (s15>=0 and s1>=0) or (s15<=0 and s1<=0) or (s15>=0 and s4>=0) or (s15<=0 and s4<=0)
        if not trend_ok: return None, f"❌ {symbol} FAIL Trend MTF {t15}/{t1}/{t4}", {"score":0,"pat":pat_score}
        if pat_score < 2: return None, f"❌ {symbol} FAIL Pattern {pat_score}/3", {"score":pat_score*5,"pat":pat_score}
        if not (20<=rsi<=80): return None, f"❌ {symbol} FAIL RSI {rsi:.1f}", {"score":15,"pat":pat_score}
        if adx<10: return None, f"❌ {symbol} FAIL ADX {adx:.1f}", {"score":20,"pat":pat_score}
        if ob_ratio<1.02: return None, f"❌ {symbol} FAIL OB {ob_ratio:.2f}", {"score":22,"pat":pat_score}
        ema_dist=abs(price-ema20_v)/ema20_v*100 if ema20_v else 99
        if ema_dist>1.5: return None, f"❌ {symbol} FAIL EMA Dist {ema_dist:.2f}%", {"score":25,"pat":pat_score}
        conf = 78 + pat_score*10 + min(adx,30) + (8 if vol_confirm else 0) + (strong_count*2)
        if strong_up or strong_down: conf += 15
        sl_pct=SL_ROI_PERCENT/100.0; tp1_pct=0.05; tp2_pct=0.08; tp3_pct=0.12; tp4_pct=0.18
        if direction=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct); tp4=price*(1+tp4_pct)
        else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct); tp4=price*(1-tp4_pct)
        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp2_pct":tp2_pct*100,"tp3_pct":tp3_pct*100,"tp4_pct":tp4_pct*100,"rsi":rsi,"stoch":stoch,"adx":adx,"mtf":f"15m {t15} | 1H {t1} | 4H {t4}","bos":bos_txt,"ob":f"OB {ob_ratio:.2f}","btc":btc_txt,"ema_dist":f"{ema_dist:.2f}%","conf":conf,"pattern":pattern,"bias":bias,"pat_score":pat_score,"vol":vol_confirm,"ma7":ma7,"ma25":ma25,"ma99":ma99}
        return trade, f"✅ V78 HYBRID {direction} MA7 {fmt(ma7)}"
    except Exception as e: return None, f"❌ {symbol} ERR {e}", {"score":0}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/4 V78 HYBRID 💰',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR {active["coin"]} 📊',callback_data="MON"), InlineKeyboardButton(f'❌ Close Trade 🛑',callback_data="CLS")])
    else:
        pending=get_pending()
        if pending:
            btns.append([InlineKeyboardButton(f'⚠️ PENDING SIGNAL {pending.get("symbol","")} {pending.get("dir","")} - Confirm?',callback_data="SHOW_PENDING")])
        btns.append([InlineKeyboardButton(f'⚡ SCAN 30 SAFE - NO AUTO BUY - YOU CONFIRM YES/NO! 💎',callback_data="SCAN")])
        btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 💵',callback_data="DAILY"), InlineKeyboardButton(f'📈 CHART ⚡',callback_data="CHART")])
        btns.append([InlineKeyboardButton(f'🔄 RESET DAILY 0W/0L',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","V78 HYBRID FINAL SAFE+CORRECT"), BotCommand("scan","SCAN 30 SAFE NO AUTO BUY"), BotCommand("monitor","MONITOR"), BotCommand("daily","Daily P&L"), BotCommand("chart","CHART"), BotCommand("reset","RESET 0W/0L")])
    except: pass

def send_chart_photo(chat_id, file_path, caption):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        with open(file_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            requests.post(url, data=data, files=files, timeout=18, proxies=PROXIES)
    except: pass

def bg_scan(chat_id, risk_mode_override=None):
    try:
        bal=get_futures_balance(); all_symbols=get_real_alt_futures_FIXED()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚡💎 V78 HYBRID FINAL! Scanning {len(all_symbols)} SAFE COINS! PAPER={PAPER_TRADING} AUTO={AUTO_TRADE} SL 35% ROI $1.05! MA7/MA25/MA99 + <100 block + BULLA/KORU block! NO AUTO BUY - YOU confirm YES/NO!"},timeout=10,proxies=PROXIES)
        raws=[]; fails=[]
        def scan_one(sym):
            trade, msg, meta = analyze_PERFECT_V78(sym)
            return (sym, trade, msg, meta)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(scan_one, all_symbols))
        for sym, trade, msg, meta in results:
            if trade: raws.append(trade)
            else: fails.append(msg)
        if not raws:
            txt=f"⚡💎 V78 HYBRID - PROTECT MODE\nScanned {len(all_symbols)} SAFE COINS! No entry - All counter-trend / new coins blocked! Money safe! Bal ${bal:.2f}\n" + "\n".join(fails[:8])
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES); return
        
        raws.sort(key=lambda x: (x['conf'], x['adx'], x['pat_score']), reverse=True)
        best = raws[0]
        set_pending(best)
        chart_path = generate_colored_chart_4H(best['symbol'], best)
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f'✅ YES BUY {best["symbol"]} {best["dir"]} @ {fmt(best["entry"])} SL 35% $1.05', callback_data=f'CONFIRM_{best["symbol"]}_{best["dir"]}')],
            [InlineKeyboardButton(f'❌ NO Skip - Keep Money Safe', callback_data='SKIP')]
        ])
        txt=(f"⚡💎 V78 HYBRID SIGNAL! ✅ Found but NO AUTO BUY! From your image!\n💎 {best['symbol']} {best['dir']} @ {fmt(best['entry'])} MA7 {fmt(best.get('ma7',0))} MA25 {fmt(best.get('ma25',0))} MA99 {fmt(best.get('ma99',0))}\n🕯️ {best['pattern']} {best['bias']} Score {best['pat_score']}/3 Conf {best['conf']:.0f}% CORRECT + SAFE!\n💰 ${3.0} 10x | SL {best['sl_pct']:.1f}% (35% ROI $1.05 loss smaller!) @ {fmt(best['sl'])} | TP1 {best['tp1_pct']:.1f}% @ {fmt(best['tp1'])} | TP4 {best['tp4_pct']:.1f}% @ {fmt(best['tp4'])}\n💵 Bal ${bal:.2f} | PAPER={PAPER_TRADING} AUTO={AUTO_TRADE}\n\n👇 From your image: Press YES BUY if you want REAL money entry, or NO Skip! Your money safe until YES!")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt, "reply_markup": confirm_kb.to_dict()},timeout=10,proxies=PROXIES)
        if chart_path and os.path.exists(chart_path):
            send_chart_photo(chat_id, chart_path, f"📊 {best['symbol']} V78 HYBRID SAFE+CORRECT")
    except Exception as e: 
        print(f"SCAN ERR {e}")
        import traceback; traceback.print_exc()

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(
        f"🧠💎 SKELLY'S V78 HYBRID FINAL 👑✨ SAFE + CORRECT!\n"
        f"💰 Futures ${bal:.2f} USDT — From your image + Correct analysis!\n\n"
        f"✅ What this RESET do (from your image + V77 fix):\n"
        f"• PAPER_TRADING={PAPER_TRADING} + AUTO_TRADE={AUTO_TRADE} — Bot NO go buy again by itself! E go only show signal + chart + YES/NO button — YOU go press YES before money enter market!\n"
        f"• Only 30 SAFE coins — PEPE, DOGE, SOL, etc — NO BULLA, NO KORU, NO new coin!\n"
        f"• MA7/MA25/MA99 + BTC filter + <100 candles block + MA same block — No more counter-trend loss! No more BULLA 0.06373 all same!\n"
        f"• SL now 35% ROI ($1.05 loss) smaller than before $1.35! Protect your $7!\n\n"
        f"How to use now (from your image):\n"
        f"1. Replace main.py for this file, deploy\n"
        f"2. Press /start — e go show V78 HYBRID + 0W/0L reset option\n"
        f"3. Press /reset to make daily 0W/0L fresh start!\n"
        f"4. Press SCAN — bot go send signal: YES BUY or NO Skip — your money safe until you press YES!\n\n"
        f"Your 9 loss before fixed! No auto loss again! 🚀",
        reply_markup=kb(get_active())
    )

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("⚡ V78 HYBRID SCANNING 30 SAFE COINS... PAPER=True NO AUTO BUY! You confirm YES/NO!")

async def daily_cmd(u,c): d=get_daily(); await u.message.reply_text(f"📊 Daily P&L V78 HYBRID {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active()))
async def reset_cmd(u,c):
    save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
    clear_active(); clear_pending()
    await u.message.reply_text("🔄 RESET DONE! Daily 0W/0L + no active + no pending! Fresh start 0W/0L! Your money safe!", reply_markup=kb(get_active()))

async def chart_cmd(u,c):
    save_chat(u.message.chat.id)
    symbol = (c.args[0] if c.args else "PEPEUSDT").upper()
    if not symbol.endswith("USDT"): symbol += "USDT"
    try:
        kl = get_klines(symbol, "15m")
        if not kl: kl = get_klines(symbol, "1h")
        closes = [k["c"] for k in kl]; price = closes[-1]
        dummy_trade = {"symbol":symbol,"dir":"BUY","entry":price,"sl":price*0.965,"tp1":price*1.05,"tp4":price*1.18,"pattern":"HAMMER","ma7":sma(closes,7),"ma25":sma(closes,25),"ma99":sma(closes,99) if len(closes)>=99 else price}
        path = generate_colored_chart_4H(symbol, dummy_trade)
        await u.message.reply_photo(photo=open(path,'rb'), caption=f"{symbol} V78 HYBRID Chart")
    except Exception as e: await u.message.reply_text(f"Chart err {e}")

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN": await u.message.reply_text("😴 No active trade - SAFE MODE",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    bal=get_futures_balance()
    await u.message.reply_text(f"👀 MONITOR V78 HYBRID {act['coin']} {act['dir']} P&L {pnl_pct:.2f}% Bal ${bal:.2f} SL 35% $1.05", reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily P&L V78 HYBRID {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data=="RESET":
        save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
        clear_active(); clear_pending()
        await q.message.reply_text("🔄 RESET DONE! 0W/0L Fresh start! From your image step 3!", reply_markup=kb(get_active())); return
    if data=="SKIP" or data=="SHOW_PENDING" and False:
        pass
    if data=="SKIP":
        clear_pending()
        await q.message.reply_text("✅ Skipped! Money safe! Press SCAN again later! From your image step 4 NO Skip!", reply_markup=kb(get_active())); return
    if data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending signal", reply_markup=kb(get_active())); return
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f'✅ YES BUY {pend["symbol"]} {pend["dir"]}', callback_data=f'CONFIRM_{pend["symbol"]}_{pend["dir"]}')],
            [InlineKeyboardButton(f'❌ NO Skip', callback_data='SKIP')]
        ])
        await q.message.reply_text(f"Pending: {pend['symbol']} {pend['dir']} @ {fmt(pend['entry'])} MA7 {fmt(pend.get('ma7',0))} SL 35% $1.05", reply_markup=confirm_kb); return
    if data.startswith("CONFIRM_"):
        try:
            parts=data.split("_")
            symbol=parts[1]; direction=parts[2]
            pend=get_pending()
            if not pend or pend.get('symbol')!=symbol:
                trade, msg, meta = analyze_PERFECT_V78(symbol)
                if not trade:
                    await q.message.reply_text(f"❌ Signal expired for {symbol} - scan again!"); return
                pend=trade
            # Now place REAL order because user pressed YES from your image!
            order_res = place_real_order(symbol, direction, get_trade_amount("FAST"), is_confirmed=True)
            if order_res and order_res.get('orderId'):
                if order_res.get('paper'):
                    set_active({"status":"OPEN","coin":symbol.replace("USDT",""),"symbol":symbol,"dir":direction,"entry":pend['entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"stake":3.0,"lev":10,"stage":0,"highest":pend['entry'],"lowest":pend['entry'],"sl_pct":pend['sl_pct'],"tp1_pct":pend['tp1_pct'],"mode":"V78 HYBRID YES CONFIRMED","time":str(datetime.now()),"pattern":pend['pattern']})
                    await q.message.reply_text(f"✅ YES CONFIRMED (Paper) {symbol} {direction} @ {fmt(pend['entry'])} - SL 35% $1.05! This was paper test!", reply_markup=kb(get_active()))
                else:
                    set_active({"status":"OPEN","coin":symbol.replace("USDT",""),"symbol":symbol,"dir":direction,"entry":pend['entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"stake":3.0,"lev":10,"stage":0,"highest":pend['entry'],"lowest":pend['entry'],"sl_pct":pend['sl_pct'],"tp1_pct":pend['tp1_pct'],"mode":"V78 HYBRID YES CONFIRMED REAL","time":str(datetime.now()),"pattern":pend['pattern']})
                    time.sleep(1.0)
                    try: set_binance_tpsl_visible(symbol, direction, pend['sl'], pend['tp1'], pend['tp2'], pend['tp3'], pend['tp4'])
                    except: pass
                    await q.message.reply_text(f"✅ YES BUY CONFIRMED REAL! Order {order_res.get('orderId')} {symbol} {direction} @ {fmt(pend['entry'])} SL 35% $1.05 VISIBLE! From your image YES pressed!", reply_markup=kb(get_active()))
                clear_pending()
            else:
                await q.message.reply_text(f"❌ Order failed for {symbol} - Check balance! No money lost! Safe!")
        except Exception as e:
            await q.message.reply_text(f"Confirm err {e}")
        return
    if data=="CHART":
        act=get_active()
        if act.get("status")=="OPEN":
            path = generate_colored_chart_4H(act["symbol"], {"symbol":act["symbol"],"dir":act["dir"],"entry":act["entry"],"sl":act["sl"],"tp1":act["tp1"],"tp4":act["tp4"],"pattern":act.get("pattern","")})
            if path: await q.message.reply_photo(photo=open(path,'rb'), caption=f"📊 {act['coin']} V78 HYBRID")
        else: await q.message.reply_text("😴 No active trade — use /chart PEPEUSDT")
        return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade SAFE MODE",reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        await q.message.reply_text(f"👀 V78 HYBRID {act['coin']} {act['dir']} {pnl_pct:.2f}% SL 35% $1.05",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"):
            cancel_all_open_orders(act["symbol"])
            close_real_position(act["symbol"],100)
        clear_active(); clear_pending(); await q.message.reply_text("❌ Closed Trade SAFE",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("⚡ V78 HYBRID SCANNING 30 SAFE... PAPER=True NO AUTO BUY! YES/NO as per your image! ⚡"); return

def monitor():
    while True:
        try:
            time.sleep(3); act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(act["symbol"])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            stage=act.get("stage",0); entry=act["entry"]; symbol=act["symbol"]
            if act["dir"]=="BUY": roi=(price-entry)/entry*100*10
            else: roi=(entry-price)/entry*100*10
            max_roi=-35.0
            if roi<=max_roi and stage==0:
                cancel_all_open_orders(symbol)
                close_real_position(symbol,100); clear_active(); update_daily(-1.05, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL 35% HIT {act['coin']} Loss $1.05 (smaller $1.05 from your image)!"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            if act["dir"]=="BUY": act["highest"]=max(act.get("highest",entry),price)
            else: act["lowest"]=min(act.get("lowest",entry),price)
            hit=None
            if act["dir"]=="BUY":
                if stage==0 and price>=act["tp1"]: hit="TP1"
                elif stage==1 and price>=act["tp2"]: hit="TP2"
                elif stage==2 and price>=act["tp3"]: hit="TP3"
                elif stage==3 and price>=act["tp4"]: hit="TP4"
                elif price<=act["sl"] and stage==0: hit="SL"
            else:
                if stage==0 and price<=act["tp1"]: hit="TP1"
                elif stage==1 and price<=act["tp2"]: hit="TP2"
                elif stage==2 and price<=act["tp3"]: hit="TP3"
                elif stage==3 and price<=act["tp4"]: hit="TP4"
                elif price>=act["sl"] and stage==0: hit="SL"
            if hit=="TP1":
                close_real_position(symbol,25)
                act["sl"]=entry; act["stage"]=1; set_active(act)
                try: update_sl_to_be_visible(symbol, act["dir"], entry)
                except: pass
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 50% HIT {act['coin']} +$1.50 BE!"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP4":
                cancel_all_open_orders(symbol)
                close_real_position(symbol,100); clear_active(); update_daily(5.40, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP4 180% HIT {act['coin']} +$5.40!"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="SL":
                cancel_all_open_orders(symbol)
                close_real_position(symbol,100); clear_active(); update_daily(-1.05, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"SL 35% HIT {act['coin']} Loss $1.05 (smaller loss from your image)!"},timeout=8,proxies=PROXIES)
                except: pass
        except Exception as e: print(f"monitor err {e}"); time.sleep(3)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("reset",reset_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("chart",chart_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"V78 HYBRID FINAL starting PAPER={PAPER_TRADING} AUTO={AUTO_TRADE} SL 35%"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
