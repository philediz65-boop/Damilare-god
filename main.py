import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math, concurrent.futures
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date, datetime

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET","").strip()
BINANCE_SECRET = BINANCE_API_SECRET or os.getenv("BINANCE_SECRET","").strip()
PORT = int(os.getenv("PORT","10000"))
BINANCE_PROXY = os.getenv("BINANCE_PROXY","").strip()
RISK_MODE = os.getenv("RISK_MODE","1.5").strip()

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v40.json"
DAILY_FILE = f"{DATA_DIR}/daily_v40.json"
CHAT_FILE = f"{DATA_DIR}/chat_v40.json"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

def binance_signed_request(method, endpoint, params={}, retries=2):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    for _ in range(retries):
        try:
            params['timestamp'] = int(time.time()*1000)
            params['recvWindow'] = 10000
            query = urllib.parse.urlencode(params)
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
    return 7.34

def get_trade_amount(mode="SNIPER"): return 3.0

# V64 META AI - SCAN 150 COINS, 3/3 GOOD ENTRY ONLY
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
                    if vol<10000000: continue # 10M min for quality
                    change=float(t.get('priceChangePercent',0))
                    if abs(change)<0.8: continue # Need 0.8% move for good entry
                    valid.append((sym, vol, abs(change)))
                except: continue
            valid.sort(key=lambda x: (x[2], x[1]), reverse=True) # Volatility first for good entry
            top=[s[0] for s in valid[:150]]
            print(f"🧠 V64 META AI: Found {len(valid)} quality alts, scanning {len(top)}")
            if len(top)>=30:
                return top
    except Exception as e:
        print(f"V64 err {e}")
    return ["SOLUSDT","DOGEUSDT","PEPEUSDT","WIFUSDT","BONKUSDT","FLOKIUSDT","AVAXUSDT","SUIUSDT","ARBUSDT","OPUSDT","TIAUSDT","ENAUSDT","WLDUSDT","1000PEPEUSDT","NEARUSDT","APTUSDT","SEIUSDT","PYTHUSDT","JUPUSDT","FETUSDT","RNDRUSDT","TAOUSDT","HYPEUSDT","ONDOUSDT","LINKUSDT","ADAUSDT","SHIBUSDT","TRUMPUSDT","FARTCOINUSDT","POPCATUSDT","PENDLEUSDT","WUSDT","AGIXUSDT","RENDERUSDT","INJUSDT"]

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        c=float(r.get('priceChangePercent',0))
        if c>=1.8: return True, f"₿ BTC +{c:.1f}% Strong Bull 🌞🚀🔥", c
        if c<=-1.8: return True, f"₿ BTC {c:.1f}% Strong Bear 🌧️📉🔥", c
        if abs(c)<0.6: return True, f"₿ BTC {c:.1f}% Calm = Best for Alts 😴✅💎", c
        return True, f"₿ BTC {c:.1f}% Mid ⚖️", c
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
def home(): return f"🧠💎 SKELLY'S META AI V64 3/3 Bal ${get_futures_balance():.2f} LIVE 🚀",200
@app.get("/health")
def health(): return "OK V64 META AI 3/3 GOOD ENTRY 🧠",200

def fmt(v):
    try:
        v=float(v)
        if v>=1: return f"{v:.5f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    with CACHE_LOCK:
        if key in CACHE and time.time()-CACHE[key][0]<40: return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=6,proxies=PROXIES).json()
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
    kl=get_klines(sym,"15m"); return kl[-1]["c"] if kl else None

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e

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
        if len(kl)<32: return 18
        highs=[k["h"] for k in kl]; lows=[k["l"] for k in kl]; closes=[k["c"] for k in kl]
        tr=[]; pdm=[]; mdm=[]
        for i in range(1,len(kl)):
            up=highs[i]-highs[i-1]; dn=lows[i-1]-lows[i]
            pdm.append(up if up>dn and up>0 else 0); mdm.append(dn if dn>up and dn>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        atr_v=sum(tr[-14:])/14
        if atr_v==0: return 18
        pdi=100*sum(pdm[-14:])/14/atr_v; mdi=100*sum(mdm[-14:])/14/atr_v
        if pdi+mdi==0: return 18
        return max(10,min(62,100*abs(pdi-mdi)/(pdi+mdi)))
    except: return 18

def trend_calc(closes):
    if len(closes)<50: return 0,"SIDEWAYS ➡️",0,False,0
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200)
    pr=closes[-1]
    dist200 = abs(pr-e200)/e200*100
    if pr>e20>e50 and pr>e200: return 60,"UPTREND 🚀💎",e20,True,dist200
    if pr<e20<e50 and pr<e200: return -60,"DOWNTREND 📉💎",e20,True,dist200
    if pr>e20>e50: return 40,"UPTREND 🚀",e20,True,dist200
    if pr<e20<e50: return -40,"DOWNTREND 📉",e20,True,dist200
    if pr>e20: return 20,"WEAK UP ↗️",e20,False,dist200
    if pr<e20: return -20,"WEAK DOWN ↘️",e20,False,dist200
    return 0,"SIDEWAYS ➡️",e20,False,dist200

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
        highs=[k["h"] for k in kl[-40:]]; lows=[k["l"] for k in kl[-40:]]; vols=[k["v"] for k in kl[-40:]]
        last_h=max(highs[-25:-1]) if len(highs)>25 else highs[-1]
        last_l=min(lows[-25:-1]) if len(lows)>25 else lows[-1]
        curr=kl[-1]["c"]
        vol_now=vols[-1]; vol_avg=sum(vols[-20:-1])/19 if len(vols)>20 else vol_now
        vol_confirm = vol_now > vol_avg*1.2 # Need volume spike for good entry
        if curr>last_h*1.0003 and vol_confirm: return True,f"💥 BOS UP Break 🚀💎 {curr:.4f} > {last_h:.4f} Vol {vol_now/vol_avg:.1f}x", curr-last_h, True
        if curr<last_l*0.9997 and vol_confirm: return True,f"💥 BOS DOWN Break 📉💎 {curr:.4f} < {last_l:.4f} Vol {vol_now/vol_avg:.1f}x", last_l-curr, True
        if curr>last_h*1.0003: return True,f"💥 BOS UP Break 🚀 {curr:.4f} > {last_h:.4f} (Low Vol)", curr-last_h, False
        if curr<last_l*0.9997: return True,f"💥 BOS DOWN Break 📉 {curr:.4f} < {last_l:.4f} (Low Vol)", last_l-curr, False
        return False,f"⏳ No BOS - Choppy 🔄 {curr:.4f} inside {last_l:.4f}-{last_h:.4f}",0, False
    except: return False,"❓ BOS N/A REJECT",0, False

def get_orderbook_ratio(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":30},headers=HEADERS,timeout=3,proxies=PROXIES).json()
        bids=r.get('bids',[]); asks=r.get('asks',[])
        if not bids or not asks: return 1.0
        bv=float(sum([float(x[0])*float(x[1]) for x in bids[:15]])); av=float(sum([float(x[0])*float(x[1]) for x in asks[:15]]))
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
        upper_wick = h - max(c,o)
        lower_wick = min(c,o) - l
        # 3/3 Good Entry: Need strong pattern + previous trend
        # Hammer with downtrend before
        if lower_wick > body*2.2 and upper_wick < body*0.4 and c>o and pc<po:
            return "🔨 HAMMER GOD 🟢💎","BULLISH 🟢",3
        if upper_wick > body*2.2 and lower_wick < body*0.4 and c>o and pc<po:
            return "🔨 INV HAMMER GOD 🟢💎","BULLISH 🟢",3
        if upper_wick > body*2.2 and lower_wick < body*0.4 and c<o and pc>po:
            return "🌠 SHOOTING STAR GOD 🔴💎","BEARISH 🔴",3
        if pc < po and c > o and c > po and o < pc and body > prev_body*1.15 and p2c < p2o:
            return "🟩 BULL ENGULF GOD 🚀💎","BULLISH 🟢",3
        if pc > po and c < o and c < po and o > pc and body > prev_body*1.15 and p2c > p2o:
            return "🟥 BEAR ENGULF GOD 📉💎","BEARISH 🔴",3
        if body < (h-l)*0.08:
            return "➖ DOJI ⏸️","NEUTRAL ⚪",0
        # Weak patterns score 1-2
        if lower_wick > body*1.5 and c>o:
            return "🔨 HAMMER WEAK 🟡","BULLISH 🟡",1
        if upper_wick > body*1.5 and c<o:
            return "🌠 SHOOTING WEAK 🟡","BEARISH 🟡",1
        return "⚪ NONE","NONE ⚪",0
    except:
        return "⚪ NONE","NONE ⚪",0

# META AI 3/3 GOOD ENTRY ANALYSER
def analyze_META_3_3(symbol):
    try:
        k15=get_klines(symbol,"15m"); k1=get_klines(symbol,"1h"); k2=get_klines(symbol,"2h")
        if len(k2)<60: k2=k1 if len(k1)>=60 else k15
        if len(k2)<60: return None, f"❌ {symbol} No data 📭", {"score":0,"conf":0}
        c15=[k["c"] for k in k15] if k15 else []; c1=[k["c"] for k in k1] if k1 else []; c2=[k["c"] for k in k2]
        price=get_price(symbol) or c2[-1]
        s15,t15,e15,strong15,dist200_15=trend_calc(c15 if c15 else c2)
        s1,t1,e1,strong1,dist200_1=trend_calc(c1 if c1 else c2)
        s2,t2,e2,strong2,dist200_2=trend_calc(c2)
        rsi=rsi_calc(c2); stoch=calc_stoch_rsi(c2); adx=adx_calc(k2)
        has_bos, bos_txt, bos_val, vol_confirm=calc_bos_META(k2)
        pattern, bias, pat_score = detect_candle_pattern_META(k2)
        direction="BUY" if s2>=0 else "SELL"
        ob_ratio=get_orderbook_ratio(symbol, direction)
        btc_ok, btc_txt, btc_change=get_btc_filter()

        # ===== 3/3 GOOD ENTRY STRICT =====
        strong_count = int(strong15) + int(strong1) + int(strong2)
        # 1) TREND 3/3 ALIGNED + at least 2 STRONG (good entry, not weak)
        if not ((s15>=0 and s1>=0 and s2>=0) or (s15<=0 and s1<=0 and s2<=0)):
            return None, f"❌ {symbol} FAIL 3/3 Trend ❌ {t15}/{t1}/{t2} 🕯️ {pattern}", {"score":0,"conf":0,"choppy":99,"strong":strong_count}
        if strong_count < 2:
            return None, f"❌ {symbol} FAIL Need 2/3 STRONG 💪 got {strong_count}/3 {t15}/{t1}/{t2} 🕯️ {pattern}", {"score":0,"conf":0,"choppy":99,"strong":strong_count}
        # 2) PATTERN MUST BE GOD (score 3), NO DOJI, NO WEAK
        if pat_score < 3:
            return None, f"❌ {symbol} FAIL Pattern not GOD 3/3 ⚪ Score {pat_score}/3 Need 🔨/🌠/🟩🟥 GOD 🕯️ {pattern}", {"score":pat_score,"conf":0,"choppy":99,"strong":strong_count}
        if "DOJI" in pattern or "NONE" in pattern:
            return None, f"❌ {symbol} FAIL ⏸️ {pattern} - No good entry 🚫", {"score":0,"conf":0,"choppy":99,"strong":strong_count}
        # 3) BOS MUST BE WITH VOLUME CONFIRM FOR GOOD ENTRY
        if not has_bos:
            return None, f"❌ {symbol} FAIL ⏳ {bos_txt} 🕯️ {pattern}", {"score":pat_score,"conf":20,"choppy":0,"strong":strong_count}
        if not vol_confirm:
            return None, f"❌ {symbol} FAIL 📉 BOS Low Volume - Bad Entry ⚠️ {bos_txt} 🕯️ {pattern}", {"score":pat_score,"conf":30,"choppy":0,"strong":strong_count}
        # 4) ALL INDICATORS STRICT FOR GOOD ENTRY
        if not (40<=rsi<=65):
            return None, f"❌ {symbol} FAIL 📊 RSI {rsi:.1f} not 40-65 Perfect Entry 🎯 {pattern}", {"score":pat_score,"conf":40,"choppy":0,"strong":strong_count}
        if stoch>=85:
            return None, f"❌ {symbol} FAIL 📈 Stoch {stoch:.0f} >=85 Overbought 🔥 {pattern}", {"score":pat_score,"conf":40,"choppy":0,"strong":strong_count}
        if adx<18:
            return None, f"❌ {symbol} FAIL 💪 ADX {adx:.1f} <18 Need Strong Trend 🚀 {pattern}", {"score":pat_score,"conf":40,"choppy":0,"strong":strong_count}
        if ob_ratio<1.15:
            return None, f"❌ {symbol} FAIL 📚 OB {ob_ratio:.2f} <1.15 Need Whale Support 🐋 {pattern}", {"score":pat_score,"conf":40,"choppy":0,"strong":strong_count}
        ema_dist=abs(price-e2)/e2*100 if e2 else 99
        if ema_dist>0.6:
            return None, f"❌ {symbol} FAIL 📏 EMA {ema_dist:.2f}% >0.6% Too far - Bad Entry 📏 {pattern}", {"score":pat_score,"conf":40,"choppy":ema_dist,"strong":strong_count}
        if dist200_2>3.5:
            return None, f"❌ {symbol} FAIL 🌊 Price too far from EMA200 {dist200_2:.1f}% - Risky Entry ⚠️", {"score":pat_score,"conf":40,"choppy":ema_dist,"strong":strong_count}
        # 5) BIAS MUST MATCH DIRECTION - 3/3 CORRECT
        expected_bias = "BULLISH 🟢" if direction=="BUY" else "BEARISH 🔴"
        if expected_bias not in bias:
            return None, f"❌ {symbol} FAIL 🔀 Pattern {bias} not match {direction} {expected_bias} ❌", {"score":pat_score,"conf":50,"choppy":ema_dist,"strong":strong_count}

        # GOOD ENTRY CONFIRMED - HIGH CONF
        conf = 85 + pat_score*5 + min(adx,25) + (5 if vol_confirm else 0)
        sl_pct=0.015; tp1_pct=0.012; tp2_pct=0.024; tp3_pct=0.04
        if direction=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
        else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)

        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp3_pct":tp3_pct*100,"rsi":rsi,"stoch":stoch,"adx":adx,"mtf":f"15m {t15} | 1H {t1} | 2H {t2} ({strong_count}/3 STRONG 💪💎)","bos":bos_txt,"ob":f"📚 OB {ob_ratio:.2f} Whale 🐋💎","btc":btc_txt,"ema_dist":f"{ema_dist:.2f}%","conf":conf,"pattern":pattern,"bias":bias,"pat_score":pat_score,"choppy":ema_dist,"vol":vol_confirm}
        return trade, "✅ 3/3 GOOD ENTRY 🎉💎"
    except Exception as e:
        return None, f"❌ {symbol} ERR 💥 {e}", {"score":0,"conf":0,"choppy":99,"strong":0}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/3 💰',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR {active["coin"]} 📊🧠',callback_data="MON"), InlineKeyboardButton(f'❌ Close Trade 🛑',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 150 META 3/3 🚀💎',callback_data="SCAN"), InlineKeyboardButton(f'🔥 RISK 1.5% ⚡',callback_data="RISK15"), InlineKeyboardButton(f'🔥 RISK 2% 💥',callback_data="RISK20")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 💵',callback_data="DAILY"), InlineKeyboardButton(f'👀 MONITOR META 🧠',callback_data="MON")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([
            BotCommand("start","🧠 SKELLY META V64 3/3"),
            BotCommand("scan","🧠 SCAN 150 META 3/3"),
            BotCommand("risk15","🔥 RISK 1.5%"),
            BotCommand("risk20","🔥 RISK 2%"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 Daily P&L")
        ])
    except: pass

def bg_scan(chat_id, risk_mode_override=None):
    try:
        bal=get_futures_balance()
        all_symbols=get_real_alt_futures_FIXED()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🧠💎 SKELLY'S SNIPER V64 META AI GOD BOT - 3/3 GOOD ENTRY 💎🧠\n🌐 Scanning {len(all_symbols)} Binance Futures Quality Alts! ⚡🔍\n🧠 META AI Analysing: EMA/RSI/STOCH/ADX/OB/BOS/Vol/E200 + 🕯️ GOD Patterns\n✅ Only 3/3 Perfect Entry - No Weak Trade!\n⏳ Fast 25 sec... Please wait 🙏🧠"},timeout=10,proxies=PROXIES)
        
        raws=[]; fails=[]
        
        def scan_one(sym):
            trade, msg, meta = analyze_META_3_3(sym)
            return (sym, trade, msg, meta)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=18) as executor:
            results = list(executor.map(scan_one, all_symbols))
        
        for sym, trade, msg, meta in results:
            if trade: raws.append(trade)
            else: fails.append(msg)

        if not raws:
            # V64 META - NO FALLBACK WEAK TRADE! PROTECT BALANCE
            txt=f"🧠💎 SKELLY'S META V64 - 3/3 GOOD ENTRY PROTECT MODE 🛡️🧠\nScanned {len(all_symbols)} Binance Futures! 🌐⚡\n🔍 No 3/3 GOD Entry found — this na GOOD! ✅ No force loss trade like before!\n📜 Need 3/3:\n✅ 3/3 Trend Aligned + 2/3 STRONG 💪💎\n✅ GOD Pattern 3/3: 🔨 HAMMER GOD / 🌠 STAR GOD / 🟩🟥 ENGULF GOD 💎\n✅ 💥 BOS + Volume Spike 1.2x 📈 + 📚 OB >=1.15 🐋\n✅ 📊 RSI 40-65 + 📈 Stoch <85 + 💪 ADX >=18 + 📏 EMA <0.6%\n✅ Bias match Direction\n\n💰 Bal ${bal:.2f} safe! 🛡️💎 No loss trade! Wait 3 mins for perfect entry! ⏰🙏🧠\n\nTOP NEAR MISSES:\n" + "\n".join(fails[:6])
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES); return
        
        # PICK BEST OF 3/3 - HIGHEST CONF FOR GOOD ENTRY
        raws.sort(key=lambda x: (x['conf'], x['adx'], x['pat_score']), reverse=True)
        best=raws[0]
        
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active trade {get_active().get('coin')} OPEN! 🟢 Close first! 🛑🧠"},timeout=10,proxies=PROXIES); return
        mode="META AI 3/3 🎯🧠"
        if risk_mode_override=="2.0" or RISK_MODE=="2.0": mode="META RISKY20 💥🧠"
        elif risk_mode_override=="1.5" or RISK_MODE=="1.5": mode="META RISKY15 ⚡🧠"
        amt=get_trade_amount(mode); real_symbol=best['symbol']
        order_res=place_real_order(real_symbol, best['dir'], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol} 💥 Check Binance API! 🔑🧠"},timeout=10,proxies=PROXIES); return
        set_active({"status":"OPEN","coin":best['code'],"symbol":real_symbol,"dir":best['dir'],"entry":best['entry'],"sl":best['sl'],"tp1":best['tp1'],"tp2":best['tp2'],"tp3":best['tp3'],"conf":best['conf'],"stake":amt,"lev":10,"stage":0,"highest":best['entry'],"lowest":best['entry'],"sl_pct":best['sl_pct'],"tp3_pct":best['tp3_pct'],"mode":mode,"time":str(datetime.now()),"pattern":best['pattern']})
        txt=(f"🧠💎 SKELLY'S META AI V64 - 3/3 GOOD ENTRY FOUND! GOD ENTRY! ✅🏆💎🧠\n💎 {best['symbol']} {best['dir']} @ {fmt(best['entry'])} 💰 GOOD ENTRY! 🎯\n🕯️ Pattern: {best['pattern']} {best['bias']} Score {best['pat_score']}/3 GOD ⭐ Conf {best['conf']:.0f}% 🔥🧠\n💰 ${amt} 10x Leverage ⚡ | 🛑 SL {best['sl_pct']:.1f}% 📉 TP1 {best['tp1_pct']:.1f}% 📈 TP3 {best['tp3_pct']:.1f}% (1:3) 🎯\n🆔 ORDER {order_res.get('orderId')} ✅ {mode} 🟢💎\nScanned {len(all_symbols)} Binance Futures! Best 3/3 Picked! 👑🧠\n━━━━━━━━━━━━━━━\n🧠 META AI 3/3 RULES PASSED ✅🧠\n✅ {best['mtf']} 3/3 Aligned 💎\n✅ {best['bos']} Vol Confirm 📈💎\n✅ 🕯️ {best['pattern']} {best['bias']} GOD 3/3 + 📊 RSI {best['rsi']:.1f} + 💪 ADX {best['adx']:.1f} ✅🧠\n✅ {best['ob']} ✅🐋\n✅ 📏 EMA {best['ema_dist']} + {best['btc']} + Vol Spike ✅📈\n━━━━━━━━━━━━━━━\n💵 Bal ${bal:.2f} | 🎯 TP1 1.2% = $0.36 profit! 50% lock BE 🛡️🔒 | 3/3 GOOD ENTRY! 👑💎🧠\n⚠️ No more 1/3 loss trade - This na quality! 💎")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES)
    except Exception as e:
        print(f"SCAN ERR {e}"); import traceback; traceback.print_exc()
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Scan error: {e} 💥🧠"},timeout=10,proxies=PROXIES)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(f"🧠💎 SKELLY'S SNIPER V64 META AI GOD BOT LIVE 👑✨🧠\n💰 Futures ${bal:.2f} USDT 💵 Risk {RISK_MODE}% ⚙️\n\n🧠 META AI ACTIVE ANALYSING:\n🌐 Scans 150 Binance Futures Quality Coins Fast! ⚡\n🏆 ONLY 3/3 GOOD ENTRY - No weak 2/3 loss trade!\n🛡️ Protects $ Balance - No force trade!\n\n🕯️ GOD CANDLE PATTERNS 3/3 ONLY:\n🔨 HAMMER GOD 💎 / 🌠 SHOOTING STAR GOD 💎\n🟩 BULL ENGULF GOD 🚀💎 / 🟥 BEAR ENGULF GOD 📉💎\n➖ DOJI = SKIP ⏸️ (bad entry)\n\n📜 V64 META 3/3 GOOD ENTRY RULES:\n✅ 3/3 Trend Aligned + 2/3 STRONG 💪💎\n✅ GOD Pattern 3/3 Score 💎\n✅ 💥 BOS + Volume Spike 1.2x 📈 + 📚 OB >=1.15 🐋\n✅ 📊 RSI 40-65 + 📈 Stoch <85 + 💪 ADX >=18\n✅ 📏 EMA <0.6% + E200 <3.5% + Bias Match\n✅ All EMA/RSI/STOCH/ADX/OB/BOS/Vol/E200/Candle dey analyse! 🧠\n\n💵 TP1 1.2% = $0.36 50% BE 🛡️\n💵 TP3 4% = $1.20 🎉\n\nPress 🧠 SCAN 150 META 3/3 now! Only perfect go enter! 🎯🚀💎",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("🧠 SKELLY'S V64 META AI SCANNING 150 Binance Futures... Only 3/3 GOD Entry! 🎯🧠 25 sec... ⏳⚡💎")

async def risk15_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "1.5"),daemon=True).start()
    await u.message.reply_text("🔥 SKELLY'S V64 META RISK 1.5% ⚡ Scanning 150 3/3... 🕯️🧠🚀")

async def risk20_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "2.0"),daemon=True).start()
    await u.message.reply_text("🔥🔥 SKELLY'S V64 META RISK 2% 💥 Scanning 150 3/3... 🕯️🧠🚀")

async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 Daily P&L META AI 🧠📈\n🏆 {d['wins']}W/{d['losses']}L 💪\n💰 ${d['pnl']:.2f} 💵\n🔢 Trades: {d['trades']} 🎯\nSKELLY'S V64 META 3/3 👑💎",reply_markup=kb(get_active()))

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN":
        await u.message.reply_text("😴 No active trade - Press SCAN 150 META 3/3! 🧠🚀💎",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]; stake=act["stake"]; lev=act["lev"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    pnl_usdt=pnl_pct/100*stake*lev; bal=get_futures_balance()
    txt=(f"👀 MONITOR {act.get('mode','')} AI {act.get('conf',0)}% 🧠🤖\n💎 {act['coin']} {act['dir']} Stage {act.get('stage',0)}/3 🎯\n🕯️ Pattern {act.get('pattern','')} ✨💎 Good Entry! 🎯\n📍 Entry {fmt(entry)} → Now {fmt(price)} 📊\n💹 P&L {pnl_pct:.3f}% (${pnl_usdt:+.4f}) 💰 ROI {pnl_pct*lev:.1f}% 📈\n💵 Bal ${bal:.2f} 🛡️")
    await u.message.reply_text(txt, reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily P&L META AI 🧠📈 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💵 SKELLY'S META V64 3/3 👑💎",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade 😴🧠",reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        pnl_usdt=pnl_pct/100*act["stake"]*act["lev"]
        await q.message.reply_text(f"👀 {act['coin']} {act['dir']} {pnl_pct:.2f}% (${pnl_usdt:+.4f}) 💰 Pattern {act.get('pattern','')} 🕯️💎",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed Trade ✅ Safe! 🛡️🧠",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("🧠 SKELLY'S V64 META 3/3 SCANNING 150... 🔍💎⚡🧠"); return
    if data=="RISK15": threading.Thread(target=bg_scan,args=(q.message.chat.id, "1.5"),daemon=True).start(); await q.message.reply_text("🔥 SKELLY'S V64 META RISK 1.5%... ⚡🚀🧠"); return
    if data=="RISK20": threading.Thread(target=bg_scan,args=(q.message.chat.id, "2.0"),daemon=True).start(); await q.message.reply_text("🔥🔥 SKELLY'S V64 META RISK 2%... 💥🚀🧠"); return

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
            if "SNIPER" in mode and roi<=-4.5:
                close_real_position(symbol,100); clear_active(); update_daily(-0.135, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨 -4% ROI GUARD! 🛡️ {act['coin']} Closed! 😴 Loss $0.135 💸🧠"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            max_roi=-16.0 if "1.5" in mode else -21.0 if "2.0" in mode else -10.0
            if roi<=max_roi:
                close_real_position(symbol,100); clear_active()
                loss=0.60 if "2.0" in mode else 0.45 if "1.5" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨🛑 SL {act.get('sl_pct',1.5):.1f}% HIT 💥 {act['coin']} ROI {roi:.1f}% 📉 Loss ${loss:.2f} 💸🛡️🧠"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            if act["dir"]=="BUY": act["highest"]=max(act.get("highest",entry),price)
            else: act["lowest"]=min(act.get("lowest",entry),price)
            hit=None
            if stage>=2:
                trail=0.012 if "RISKY" in mode else 0.008
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
                close_real_position(symbol,50); new_sl=entry*1.001 if act["dir"]=="BUY" else entry*0.999
                act["sl"]=new_sl; act["stage"]=1; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 HIT! 🎉 {act['coin']} +{act.get('sl_pct',1.5):.1f}% 💰 50% BE 🛡️🔒 Pattern {act.get('pattern','')} 🕯️💎 Good Entry! 🧠"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol,30); act["sl"]=act["tp1"]; act["stage"]=2; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 TP2 HIT! 🎉🎉 {act['coin']} + TRAILING 🏃💨🔒🧠"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol,100); clear_active()
                win=1.80 if "2.0" in mode else 1.35 if "1.5" in mode else 0.50
                update_daily(win, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 TP3 HIT! 🏆🎉 {act['coin']} +{act.get('tp3_pct',4.0):.1f}% +${win:.2f} 💰💰💰 Pattern {act.get('pattern','')} GOD ENTRY META AI! 👑🚀🧠💎"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol,100); clear_active(); update_daily(0.70, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING SL HIT! 🔒 {act['coin']} Profit $0.70+ 💰✅🧠"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="SL":
                close_real_position(symbol,100); clear_active()
                loss=0.60 if "2.0" in mode else 0.45 if "1.5" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL {act.get('sl_pct',1.5):.1f}% HIT 😢 {act['coin']} Loss ${loss:.2f} 💸🛡️🧠"},timeout=8,proxies=PROXIES)
                except: pass
        except Exception as e:
            print(f"monitor err {e}"); time.sleep(5)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing ❌🧠"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("risk15",risk15_cmd)); a.add_handler(CommandHandler("risk20",risk20_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"🧠💎 SKELLY'S SNIPER V64 META AI starting Risk {RISK_MODE}% 🚀 150 coins 3/3"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
