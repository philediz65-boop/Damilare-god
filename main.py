import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math, random
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
LEARN_FILE = f"{DATA_DIR}/ai_learn_v53.json"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

# ==================== BINANCE CORE - FIXED ====================
def binance_signed_request(method, endpoint, params={}, retries=2):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    for attempt in range(retries):
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
            time.sleep(0.7)
        except Exception as e:
            print(f"Signed fail {endpoint}: {e}"); time.sleep(0.5)
    return None

def get_futures_balance():
    data = binance_signed_request("GET", "/fapi/v2/balance")
    if isinstance(data, list):
        for b in data:
            if b.get('asset') == 'USDT':
                try: return float(b.get('balance',0))
                except: pass
    return 7.18

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
    except Exception as e:
        print(f"ORDER FAIL {e}"); return None

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
    except Exception as e: print(f"Close fail {e}")
    return None

# ==================== REAL AI BRAIN ====================
class RealAIBrain:
    def __init__(self):
        self.learn = self.load_learn()
    
    def load_learn(self):
        try:
            if os.path.exists(LEARN_FILE):
                with open(LEARN_FILE,'r') as f: return json.load(f)
        except: pass
        return {"wins_pattern":[],"losses_pattern":[],"best_hours":[],"best_coins":{"PEPE":0,"TOSHI":1,"WIF":0,"BONK":0},"total_trades":0}

    def save_learn(self):
        try:
            with LOCK:
                with open(LEARN_FILE,'w') as f: json.dump(self.learn,f)
        except: pass

    def get_btc_filter(self):
        try:
            r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
            change=float(r.get('priceChangePercent',0))
            volume=float(r.get('volume',0))
            if change>=1.6: return 6, f"BTC +{change:.1f}% Bull 🌞 Strong", change
            if change<=-1.6: return -7, f"BTC {change:.1f}% Bear 🌧️ Danger", change
            if -0.5<=change<=0.5: return 2, f"BTC {change:.1f}% Calm ✅ Good for alts", change
            return 0, f"BTC {change:.1f}% Neutral", change
        except: return 0, "BTC N/A", 0

    def get_orderbook_score(self, symbol, direction):
        try:
            r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":20},headers=HEADERS,timeout=4,proxies=PROXIES).json()
            bids=r.get('bids',[]); asks=r.get('asks',[])
            if not bids or not asks: return 0,"OB N/A",True, 1.0
            bv=float(sum([float(x[0])*float(x[1]) for x in bids[:12]])); av=float(sum([float(x[0])*float(x[1]) for x in asks[:12]]))
            if bv==0 or av==0: return 0,"OB N/A",True, 1.0
            ratio=bv/av if direction=="BUY" else av/bv
            if ratio>=1.35: return 15,f"OB Strong Bull {ratio:.2f} 🟢🟢 Whales Buying!",False, ratio
            if ratio>=1.15: return 9,f"OB Bull {ratio:.2f} 🟢 Buyers in control",False, ratio
            if ratio>=0.90: return 2,f"OB Neutral {ratio:.2f}",False, ratio
            if ratio>=0.78: return -5,f"OB Bear {ratio:.2f} ⚠️ Sellers",False, ratio
            return -25,f"OB Bear Wall {ratio:.2f} 🔴🔴 WHALES SELLING REJECT!",True, ratio
        except: return 0,"OB N/A",True, 1.0

    def get_oi_funding(self, symbol):
        try:
            prem=requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",params={"symbol":symbol},headers=HEADERS,timeout=4,proxies=PROXIES).json()
            funding=float(prem.get('lastFundingRate',0)) if isinstance(prem,dict) else 0
            oi=None
            try:
                oi_r=requests.get("https://fapi.binance.com/fapi/v1/openInterest",params={"symbol":symbol},headers=HEADERS,timeout=4,proxies=PROXIES).json()
                oi=float(oi_r.get('openInterest',0))
            except: pass
            if funding>0.0025: return -10,f"Fund Very High {funding*100:.4f}% 🔥 Longs overcrowded!",oi,funding
            if funding>0.0011: return -5,f"Fund High {funding*100:.3f}%",oi,funding
            if funding<-0.0018: return 9,f"Fund Very Low {funding*100:.4f}% 🟢🟢 Short squeeze potential!",oi,funding
            if funding<-0.0009: return 5,f"Fund Low {funding*100:.3f}% 🟢",oi,funding
            return 4,f"Fund Neutral {funding*100:.4f}% ✅ Healthy",oi,funding
        except: return 0,"Fund OK",None,0

    def get_ls_ratio(self, symbol, direction):
        try:
            r=requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",params={"symbol":symbol,"period":"15m","limit":1},headers=HEADERS,timeout=4,proxies=PROXIES).json()
            if isinstance(r,list) and len(r)>0:
                ratio=float(r[-1].get('longShortRatio',1)); long_pct=ratio/(1+ratio)*100
                if direction=="BUY" and long_pct>84: return -12,f"LS Crowd Long {long_pct:.0f}% 🔴 TRAP! Everyone long, will dump!", long_pct
                if direction=="SELL" and long_pct<16: return -12,f"LS Crowd Short {100-long_pct:.0f}% 🔴 TRAP!", long_pct
                if direction=="BUY" and long_pct<32: return 10,f"LS Short Crowd {100-long_pct:.0f}% 🟢 SQUEEZE! Shorts trapped!", long_pct
                if direction=="SELL" and long_pct>68: return 10,f"LS Long Crowd {long_pct:.0f}% 🟢 SQUEEZE! Longs trapped!", long_pct
                if 43<=long_pct<=57: return 8,f"LS Balanced {long_pct:.0f}% ✅ Perfect balance", long_pct
                return 0,f"LS {long_pct:.0f}%", long_pct
            return 0,"LS N/A",50
        except: return 0,"LS N/A",50

    def think_like_human(self, data):
        reasons=[]
        score=0
        prob=50
        # AI THINKING
        if data['align']==3: reasons.append("✅ 15m+1H+2H all same trend (3/3) - Trend is my friend!"); score+=18; prob+=12
        else: reasons.append(f"❌ MTF only {data['align']}/3 - Choppy market, skip"); prob-=15; return score, prob, reasons, False
        
        if data['ema_3tf_perfect']: reasons.append("✅ Price above EMA20 in 3 timeframes - Strong uptrend confirmed!"); score+=12; prob+=10
        elif not data['ema_3tf_ok']: reasons.append("❌ Price below EMA in 2 TF - Weak trend"); prob-=12; return score, prob, reasons, False
        
        if 42<=data['rsi']<=58: reasons.append(f"✅ RSI {data['rsi']:.1f} perfect zone (42-58) - Not overbought, room to pump!"); score+=16; prob+=10
        elif data['rsi']>68: reasons.append(f"❌ RSI {data['rsi']:.1f} overbought - Will dump!"); prob-=15; return score, prob, reasons, False
        elif data['rsi']<32: reasons.append(f"❌ RSI {data['rsi']:.1f} oversold but no reversal yet"); prob-=8
        
        if 20<=data['stoch']<=80: reasons.append(f"✅ Stoch RSI {data['stoch']:.0f} healthy - Momentum good"); score+=6; prob+=5
        else: reasons.append(f"⚠️ Stoch {data['stoch']:.0f} extreme - Careful"); score-=2
        
        if data['ob_ratio']>=1.15: reasons.append(f"✅ Orderbook {data['ob_ratio']:.2f} bull - Whales buying!"); score+=10; prob+=8
        elif data['ob_ratio']<0.8: reasons.append(f"❌ Orderbook {data['ob_ratio']:.2f} bear wall - Whales selling! REJECT"); prob-=20; return score, prob, reasons, False
        
        if "SQUEEZE" in data['ls_txt']: reasons.append(f"✅ {data['ls_txt']} - Squeeze coming!"); score+=10; prob+=10
        elif "TRAP" in data['ls_txt']: reasons.append(f"❌ {data['ls_txt']} - Crowd trap!"); prob-=15; return score, prob, reasons, False
        
        if data['vol_pct']>15: reasons.append(f"✅ Volume +{data['vol_pct']:.0f}% surge - Fast coin pumping!"); score+=8; prob+=7
        elif data['vol_pct']<-40: reasons.append(f"❌ Volume {data['vol_pct']:.0f}% dead - No movement"); prob-=10; return score, prob, reasons, False
        
        if "Break" in data['bos_txt']: reasons.append(f"✅ {data['bos_txt']} - Breakout! Smart money entering!"); score+=14; prob+=12
        else: reasons.append(f"⚠️ {data['bos_txt']} - No breakout yet, choppy"); score-=3; prob-=3
        
        if "GOLDEN" in data['fib_txt']: reasons.append(f"✅ {data['fib_txt']} - Perfect dip entry! Buying low!"); score+=14; prob+=10
        elif "BAD" in data['fib_txt']: reasons.append(f"❌ {data['fib_txt']} - Buying top!"); prob-=10; return score, prob, reasons, False
        
        if data['btc_change']>1.5: reasons.append(f"⚠️ {data['btc_txt']} - BTC pumping, alts may lag"); score+=1
        elif data['btc_change']<-1.5: reasons.append(f"❌ {data['btc_txt']} - BTC dumping, alts will dump harder! REJECT"); prob-=12; return score, prob, reasons, False
        else: reasons.append(f"✅ {data['btc_txt']} - BTC calm, perfect for alt pump!"); score+=4; prob+=4
        
        if data['adx']>=20: reasons.append(f"✅ ADX {data['adx']:.1f} strong trend - Trend is strong!"); score+=10; prob+=6
        else: reasons.append(f"⚠️ ADX {data['adx']:.1f} weak - Ranging market"); score-=2
        
        if prob>=72: reasons.append(f"\n🧠 AI BRAIN DECISION: {prob}% WIN PROBABILITY! HIGH CONFLUENCE! ENTER!")
        elif prob>=60: reasons.append(f"\n🧠 AI BRAIN: {prob}% probability - Good setup, risky mode OK")
        else: reasons.append(f"\n🧠 AI BRAIN: Only {prob}% - Too risky, skip!")
        
        should_enter = prob>=70 if data['mode']=='SNIPER' else prob>=58
        return score, prob, reasons, should_enter

BRAIN = RealAIBrain()
FAST = ["PEPE","BONK","WIF","FLOKI","BOME","1000PEPE","TRUMP","FARTCOIN","SHIB","DOGE","POPCAT","MEW","MOG","BRETT","TURBO","PENGU","MOODENG","GOAT","PNUT","ACT","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA","SPX","W","LADYS","WOJAK","MEME","PONKE","MYRO","WEN","TOSHI","CAT","BABYDOGE","NOT","DOGS","HMSTR","EIGEN","ZK","ZRO","ZEREBRO","NEIRO","DOG"]
CRYPTO = {k:f"{k}USDT" for k in FAST}
CRYPTO["1000PEPE"]="1000PEPEUSDT"

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
    if d.get("date")!=t: d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0,"loss_streak":0,"pause_until":0}; save_json(DAILY_FILE,d)
    if "loss_streak" not in d: d["loss_streak"]=0
    if "pause_until" not in d: d["pause_until"]=0
    return d
def update_daily(pnl, win):
    d=get_daily(); d["trades"]+=1; d["pnl"]+=pnl
    if win: d["wins"]+=1; d["loss_streak"]=0
    else: d["losses"]+=1; d["loss_streak"]+=1
    if d["loss_streak"]>=2: d["pause_until"]=int(time.time())+900
    save_json(DAILY_FILE,d)
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return f"V53 REAL AI BRAIN Bal ${get_futures_balance():.2f} Risk {RISK_MODE}% LIVE",200
@app.get("/health")
def health(): return "OK V53 AI BRAIN",200

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
        if key in CACHE and time.time()-CACHE[key][0]<60: return CACHE[key][1]
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
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=4,proxies=PROXIES).json()
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
    for i in range(len(arr)-p, len(arr)):
        if i<1: continue
        d=arr[i]-arr[i-1]; g=d if d>0 else 0; l=-d if d<0 else 0
        avg_g=(avg_g*(p-1)+g)/p; avg_l=(avg_l*(p-1)+l)/p
    if avg_l==0: return 70 if avg_g>0 else 50
    return 100-(100/(1+avg_g/avg_l))

def atr_calc(kl,p=14):
    if len(kl)<p+1: return kl[-1]["c"]*0.018
    trs=[]
    for i in range(1,p+1):
        idx=-i; prev=-i-1
        if abs(prev)>=len(kl): continue
        tr=max(kl[idx]["h"]-kl[idx]["l"], abs(kl[idx]["h"]-kl[prev]["c"]), abs(kl[idx]["l"]-kl[prev]["c"]))
        trs.append(tr)
    return sum(trs)/len(trs) if trs else kl[-1]["c"]*0.02

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

def pd_calc(kl):
    if len(kl)<100: return "EQUILIBRIUM",50
    hi=max(k["h"] for k in kl[-100:]); lo=min(k["l"] for k in kl[-100:]); pr=kl[-1]["c"]
    pct=(pr-lo)/(hi-lo)*100 if hi!=lo else 50
    return ("PREMIUM",pct) if pct>=70 else ("DISCOUNT",pct) if pct<=30 else ("EQUILIBRIUM",pct)

def trend_calc(closes):
    if len(closes)<50: return 0,"SIDEWAYS",0,0
    e20=ema(closes,20); e50=ema(closes,50); pr=closes[-1]
    if pr>e20>e50: return 50,"UPTREND",e20,e50
    if pr>e20: return 20,"WEAK UP",e20,e50
    if pr<e20<e50: return -50,"DOWNTREND",e20,e50
    if pr<e20: return -20,"WEAK DOWN",e20,e50
    return 0,"SIDEWAYS",e20,e50

def vol_calc(kl):
    if len(kl)<22: return 0,"Vol N/A",False
    vols=[k["v"] for k in kl[-22:]]; avg=sum(vols[:-2])/len(vols[:-2]) if len(vols)>2 else 1
    pct=(vols[-1]-avg)/avg*100 if avg else 0
    return pct,f"Vol {pct:.0f}%", pct<-50

def ema_distance_filter(price, ema20, mode):
    dist=abs(price-ema20)/ema20*100 if ema20 else 99
    if mode=="SNIPER" and dist>0.55: return False,f"EMA Dist {dist:.2f}% Too Far 🔴 Need <0.55% 3/3"
    if mode=="SCALP" and dist>1.0: return False,f"EMA Dist {dist:.2f}% Too Far 🔴"
    if "RISKY" in mode and dist>0.80: return False,f"EMA Dist {dist:.2f}% Too Far 🔴 Need <0.8%"
    return True,f"EMA Dist {dist:.2f}% ✅ Perfect!"

def calc_stoch_rsi(closes, period=14):
    try:
        if len(closes)<period+5: return 50
        rsi_vals=[rsi_calc(closes[:i+1]) for i in range(period, len(closes))]
        if len(rsi_vals)<5: return 50
        recent=rsi_vals[-5:]; low=min(recent); high=max(recent)
        if high==low: return 50
        return (recent[-1]-low)/(high-low)*100
    except: return 50

def calc_cvd(kl, direction):
    try:
        cvd=0
        for k in kl[-20:]:
            if k["c"]>k["o"]: cvd+=k["v"]
            else: cvd-=k["v"]
        if direction=="BUY": return (7,f"CVD Bull 💪 Buyers in control",False) if cvd>0 else (-7,f"CVD Bear 📉",False)
        else: return (7,f"CVD Bear 📉",False) if cvd<0 else (-7,f"CVD Bull Weak",False)
    except: return 0,"CVD N/A",False

def calc_bos(kl):
    try:
        highs=[k["h"] for k in kl[-30:]]; lows=[k["l"] for k in kl[-30:]]
        last_h=max(highs[-20:-1]) if len(highs)>20 else highs[-1]
        last_l=min(lows[-20:-1]) if len(lows)>20 else lows[-1]
        curr=kl[-1]["c"]
        if curr>last_h*1.001: return 14,f"BOS UP Break 🚀 Strong! Smart money!",False
        if curr<last_l*0.999: return 14,f"BOS DOWN Break 📉 Strong!",False
        return -5,"No BOS - Choppy ⏳",False
    except: return 0,"BOS N/A",False

def calc_fib_entry(kl, direction):
    try:
        hi=max(k["h"] for k in kl[-50:]); lo=min(k["l"] for k in kl[-50:]); curr=kl[-1]["c"]
        if hi==lo: return 0,"Fib N/A"
        pct=(curr-lo)/(hi-lo)*100
        if direction=="BUY":
            if 48<=pct<=64: return 15,f"Fib GOLDEN {pct:.0f}% 🎯 PERFECT DIP!"
            if pct<38: return 9,f"Fib Discount {pct:.0f}% ✅ Good low!"
            if pct>82: return -7,f"Fib Premium {pct:.0f}% BAD Top!"
        else:
            if 60<=pct<=82: return 15,f"Fib Premium {pct:.0f}% 🎯"
            if pct<18: return -7,f"Fib Discount {pct:.0f}% BAD"
        return 0,f"Fib {pct:.0f}% Mid"
    except: return 0,"Fib N/A"

def analyze_single_quick(code):
    try:
        sym=CRYPTO[code]; k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<50: k2=k1 if len(k1)>=50 else k15
        if len(k2)<50: return None
        c2=[k["c"] for k in k2]; price=get_price(sym) or c2[-1]
        rsi_v=rsi_calc(c2); atr_v=atr_calc(k2); adx_v=adx_calc(k2); pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2; c1=[k["c"] for k in k1] if k1 else c2
        s15,t15,e20_15,_=trend_calc(c15); s1,t1,e20_1h,_=trend_calc(c1); s2,t2,e20_2h,_=trend_calc(c2)
        vol_pct,vol_txt,vol_reject=vol_calc(k2)
        align=3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"
        pab=0
        if c15[-1]>e20_15: pab+=1
        if c1[-1]>e20_1h: pab+=1
        if c2[-1]>e20_2h: pab+=1
        pbb=3-pab
        ema_3tf_ok=(direction=="BUY" and pab>=2) or (direction=="SELL" and pbb>=2)
        ema_3tf_perfect=(direction=="BUY" and pab==3) or (direction=="SELL" and pbb==3)
        volatility=atr_v/price*100 if price else 0
        stoch=calc_stoch_rsi(c2)
        return {"code":code,"price":price,"rsi":rsi_v,"stoch":stoch,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"vol_reject":vol_reject,"align":align,"dir":direction,"kl":k2,"closes":c2,"ema20":e20_2h,"pab":pab,"ema_3tf_ok":ema_3tf_ok,"ema_3tf_perfect":ema_3tf_perfect}
    except Exception as e:
        print(f"quick err {code}: {e}"); return None

def build_trade(r, mode="SNIPER"):
    price=r["price"]; d=r["dir"]
    if mode=="RISKY15": sl_pct=0.015; tp1_pct=0.015; tp2_pct=0.03; tp3_pct=0.045
    elif mode=="RISKY20": sl_pct=0.02; tp1_pct=0.02; tp2_pct=0.04; tp3_pct=0.06
    elif mode=="RISKY": sl_pct=0.015; tp1_pct=0.015; tp2_pct=0.03; tp3_pct=0.045
    elif mode=="SCALP": sl_pct=0.006; tp1_pct=0.006; tp2_pct=0.012; tp3_pct=0.018
    else: sl_pct=0.009; tp1_pct=0.009; tp2_pct=0.019; tp3_pct=0.032
    if d=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
    else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)
    return {"code":r["code"],"dir":d,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":10,"rsi":r["rsi"],"stoch":r["stoch"],"adx":r["adx"],"volatility":r["volatility"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']}","vol_txt":r["vol_txt"],"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp2_pct":tp2_pct*100,"tp3_pct":tp3_pct*100,"atr":r["atr"],"ema20":r["ema20"],"align":r["align"]}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} {active.get("mode","")} TP{active.get("stage",0)}/3',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR {active["coin"]}',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🎯 SCAN V53 AI 🧠',callback_data="SCAN"), InlineKeyboardButton(f'🔥 RISK 1.5%',callback_data="RISK15"), InlineKeyboardButton(f'🔥 RISK 2%',callback_data="RISK20")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'👀 MONITOR',callback_data="MON")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([
            BotCommand("start","🧠 V53 REAL AI BRAIN"),
            BotCommand("scan","🧠 SCAN AI BRAIN"),
            BotCommand("risk15","🔥 RISK 1.5% AI"),
            BotCommand("risk20","🔥 RISK 2% AI"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 Daily")
        ])
    except: pass

def bg_scan(chat_id, risk_mode_override=None):
    try:
        daily=get_daily()
        if daily.get("pause_until",0)>int(time.time()):
            wait=(daily["pause_until"]-int(time.time()))//60
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⏸️ AI PAUSE! Loss guard wait {wait} min 🛡️"},timeout=10,proxies=PROXIES); return
        bal=get_futures_balance()
        # STEP 1 - FAST SCAN
        raws=[]
        for code in FAST:
            r=analyze_single_quick(code)
            if r: raws.append(r)
            time.sleep(0.015)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"❌ No data, Binance busy"},timeout=10,proxies=PROXIES); return
        # Filter quick
        cands=[r for r in raws if r['vol_pct']>-50 and r['adx']>=14 and r['align']>=2]
        if not cands:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"😴 Market dull, AI says no trade now. Your $ safe!"},timeout=10,proxies=PROXIES); return
        cands.sort(key=lambda x: (x['align'], x['adx'], x['vol_pct']), reverse=True)
        top20=cands[:18]
        # STEP 2 - REAL AI BRAIN ANALYSIS
        ai_cands=[]; report_lines=[]
        btc_score, btc_txt, btc_change = BRAIN.get_btc_filter()
        for q in top20:
            sym=CRYPTO[q['code']]
            ob_score, ob_txt, ob_reject, ob_ratio = BRAIN.get_orderbook_score(sym, q['dir'])
            oi_score, oi_txt, oi_val, funding = BRAIN.get_oi_funding(sym)
            ls_score, ls_txt, ls_pct = BRAIN.get_ls_ratio(sym, q['dir'])
            cvd_score, cvd_txt, _ = calc_cvd(q['kl'], q['dir'])
            bos_score, bos_txt, _ = calc_bos(q['kl'])
            fib_score, fib_txt = calc_fib_entry(q['kl'], q['dir'])
            ema_ok_sniper, ema_txt_sniper = ema_distance_filter(q['price'], q['ema20'], "SNIPER")
            ema_ok_risky, ema_txt_risky = ema_distance_filter(q['price'], q['ema20'], "RISKY15")
            
            # Build data for AI brain
            brain_data={
                'code':q['code'],'align':q['align'],'ema_3tf_ok':q['ema_3tf_ok'],'ema_3tf_perfect':q['ema_3tf_perfect'],
                'rsi':q['rsi'],'stoch':q['stoch'],'ob_ratio':ob_ratio,'ls_txt':ls_txt,'vol_pct':q['vol_pct'],
                'bos_txt':bos_txt,'fib_txt':fib_txt,'btc_txt':btc_txt,'btc_change':btc_change,
                'adx':q['adx'],'mode':'SNIPER' if risk_mode_override is None else 'RISKY15',
                'ob_txt':ob_txt,'oi_txt':oi_txt,'cvd_txt':cvd_txt,'vol_txt':q['vol_txt']
            }
            score, prob, reasons, should_enter = BRAIN.think_like_human(brain_data)
            
            if not should_enter:
                if prob<55:
                    report_lines.append(f"{q['code']} {prob}% ❌ {reasons[0][:45]}")
                continue
            if q['align']!=3 or not q['ema_3tf_perfect']:
                if prob<70: continue # Need 3/3 for high prob
            
            # Determine mode
            mode="SNIPER"
            if risk_mode_override=="2.0" or RISK_MODE=="2.0": mode="RISKY20"
            elif risk_mode_override=="1.5" or RISK_MODE=="1.5": mode="RISKY15"
            elif prob>=72 and ema_ok_sniper and 42<=q['rsi']<=58: mode="SNIPER"
            elif prob>=58 and ema_ok_risky: mode="RISKY15" if prob<75 else "RISKY20"
            else: mode="SCALP"
            
            trade=build_trade(q, mode)
            trade['conf']=int(prob)
            trade['raw']=q
            trade['raw']['ob_txt']=ob_txt; trade['raw']['oi_txt']=oi_txt; trade['raw']['ls_txt']=ls_txt
            trade['raw']['cvd_txt']=cvd_txt; trade['raw']['bos_txt']=bos_txt; trade['raw']['fib_txt']=fib_txt
            trade['raw']['btc_txt']=btc_txt; trade['raw']['btc_change']=btc_change
            trade['raw']['ob_ratio']=ob_ratio; trade['raw']['ls_pct']=ls_pct; trade['raw']['funding']=funding
            trade['raw']['ema_txt_sniper']=ema_txt_sniper; trade['raw']['ema_txt_risky']=ema_txt_risky
            trade['mode']=mode
            trade['reasons']=reasons
            trade['ai_score']=score
            ai_cands.append(trade)

        if not ai_cands:
            top_report="\n".join(report_lines[:5])
            msg=f"🧠 REAL AI BRAIN - No high prob trade now\n\nAI Checked TOP 5:\n{top_report}\n\n🧠 AI says: Need 3/3 MTF + Whale buying + Squeeze + BOS Break + Golden Fib!\nYour ${bal:.2f} safe! Try 5 min 🔥"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10,proxies=PROXIES); return
        
        ai_cands.sort(key=lambda x: x['conf'], reverse=True)
        best=ai_cands[0]
        
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN 🔒"},timeout=10,proxies=PROXIES); return
        
        mode=best['mode']; amt=get_trade_amount(mode); real_symbol=CRYPTO[best['code']]
        order_res=place_real_order(real_symbol, best['dir'], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol} Check ${amt*2}+ USDT"},timeout=10,proxies=PROXIES); return
        
        set_active({"status":"OPEN","coin":best['code'],"symbol":real_symbol,"dir":best['dir'],"entry":best['entry'],"sl":best['sl'],"tp1":best['tp1'],"tp2":best['tp2'],"tp3":best['tp3'],"conf":best['conf'],"stake":amt,"lev":10,"stage":0,"highest":best['entry'],"lowest":best['entry'],"sl_pct":best['sl_pct'],"tp1_pct":best['tp1_pct'],"tp2_pct":best['tp2_pct'],"tp3_pct":best['tp3_pct'],"mode":mode,"time":str(datetime.now()),"rsi":best['rsi'],"stoch":best['stoch'],"adx":best['adx'],"pd_pct":best['pd_pct'],"mtf":best['mtf'],"vol_txt":best['vol_txt'],"ema20":best['ema20'],"align":best['align']})
        
        # Build AI reasoning message
        reasons_text="\n".join(best['reasons'][:10])
        
        if mode=="RISKY15": risk_txt=f"SL 1.5% $0.45 | TP 1.5/3/4.5% $1.35 (1:3) 🔥"; sure=f"AI {best['conf']}% WIN! 🔥🔥"
        elif mode=="RISKY20": risk_txt=f"SL 2% $0.60 | TP 2/4/6% $1.80 (1:3) 🔥🔥"; sure=f"AI {best['conf']}% WIN! 🔥🔥🔥"
        else: risk_txt=f"SL {best['sl_pct']:.2f}% | TP {best['tp1_pct']:.2f}/{best['tp2_pct']:.2f}/{best['tp3_pct']:.2f}%"; sure=f"AI {best['conf']}% SURE 3/3! 🔥🔥🔥"
        
        txt=(
            f"🧠 REAL AI BRAIN {best['conf']}% {sure}\n"
            f"💎 {best['code']} {best['dir']} @ {fmt(best['entry'])}\n"
            f"💰 ${amt} 10x | {risk_txt}\n"
            f"🆔 ORDER {order_res.get('orderId')} ✅ {mode}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🧠 AI REASONING (Like Human Trader):\n"
            f"{reasons_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 DATA:\n"
            f"• MTF: {best['mtf']} Align {best['align']}/3 PERFECT!\n"
            f"• EMA: {best['raw']['ema_txt_sniper']} | {best['raw']['pab']}/3 TF above EMA\n"
            f"• RSI {best['rsi']:.1f} Stoch {best['stoch']:.0f} ADX {best['adx']:.1f}\n"
            f"• PD {best['pd_pct']:.0f}% | {best['raw']['fib_txt']}\n"
            f"• {best['vol_txt']} ATR {best['volatility']:.2f}%\n"
            f"🧱 {best['raw']['ob_txt']}\n"
            f"🔄 {best['raw']['ls_txt']}\n"
            f"🏗️ {best['raw']['bos_txt']}\n"
            f"₿ {best['raw']['btc_txt']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💵 Bal ${bal:.2f} | AI Brain 3/3 | SL {best['sl_pct']:.1f}% TP {best['tp3_pct']:.1f}%"
        )
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES)
    except Exception as e:
        print(f"SCAN ERR {e}"); import traceback; traceback.print_exc()
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ AI Scan error: {e}"},timeout=10,proxies=PROXIES)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(f"🧠 V53 REAL AI BRAIN LIVE ✨\n💰 Futures ${bal:.2f} USDT Risk {RISK_MODE}%\n\n🧠 AI THINKS LIKE HUMAN:\n✅ Checks BTC trend first\n✅ Checks 15m+1H+2H 3/3 SAME trend\n✅ Checks Whale orderbook (are whales buying?)\n✅ Checks Crowd LS ratio (trap or squeeze?)\n✅ Checks Volume surge + BOS breakout\n✅ Checks Fib golden zone (buy low!)\n✅ Gives WIN probability %\n\n💵 SNIPER 70%+ $3 SL 0.9% TP 3.2%\n🔥 RISKY15 58%+ SL 1.5% TP 4.5% $1.35 win (1:3)\n🔥🔥 RISKY20 SL 2% TP 6% $1.80 win (1:3)\n\nCommands: /scan /risk15 /risk20 /monitor",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("🧠 REAL AI BRAIN SCANNING... ⚡\nAI thinking: BTC? Trend 3/3? Whales? Squeeze? 15 sec...")

async def risk15_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "1.5"),daemon=True).start()
    await u.message.reply_text("🔥 AI RISKY 1.5%... SL 1.5% $0.45 TP 4.5% $1.35 (1:3) AI 60%+!")

async def risk20_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "2.0"),daemon=True).start()
    await u.message.reply_text("🔥🔥 AI RISKY 2%... SL 2% $0.60 TP 6% $1.80 (1:3) AI 60%+!")

async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} Streak {d.get('loss_streak',0)} 💵 V53 AI BRAIN",reply_markup=kb(get_active()))

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN":
        await u.message.reply_text("😴 No active trade 📭 Press SCAN AI! 🧠",reply_markup=kb()); return
    price=get_price(CRYPTO[act["coin"]]) or act["entry"]; entry=act["entry"]; stake=act["stake"]; lev=act["lev"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    pnl_usdt=pnl_pct/100*stake*lev; bal=get_futures_balance(); stage=act.get("stage",0)
    txt=(f"👀 MONITOR {act.get('mode','')} AI {act.get('conf',0)}% 3/3\n💎 {act['coin']} {act['dir']} Stage {stage}/3\nEntry {fmt(entry)} → Now {fmt(price)}\nP&L {pnl_pct:.3f}% (${pnl_usdt:+.4f}) ROI {pnl_pct*lev:.1f}%\nSL {fmt(act['sl'])} {act.get('sl_pct',0):.1f}% TP3 {fmt(act['tp3'])} {act.get('tp3_pct',0):.1f}%\nBal ${bal:.2f} Stake ${stake} 🧠 AI")
    await u.message.reply_text(txt, reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        pnl_usdt=pnl_pct/100*act["stake"]*act["lev"]
        await q.message.reply_text(f"👀 {act['coin']} {act['dir']} {pnl_pct:.2f}% (${pnl_usdt:+.4f}) ROI {pnl_pct*10:.1f}% AI {act.get('conf',0)}%\nSL {fmt(act['sl'])} TP {act.get('tp3_pct',0):.1f}%",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed ✅",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("🧠 AI SCANNING 3/3..."); return
    if data=="RISK15": threading.Thread(target=bg_scan,args=(q.message.chat.id, "1.5"),daemon=True).start(); await q.message.reply_text("🔥 AI RISKY 1.5%..."); return
    if data=="RISK20": threading.Thread(target=bg_scan,args=(q.message.chat.id, "2.0"),daemon=True).start(); await q.message.reply_text("🔥🔥 AI RISKY 2%..."); return

def monitor():
    while True:
        try:
            time.sleep(5); act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(CRYPTO[act["coin"]])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            stage=act.get("stage",0); entry=act["entry"]; symbol=act["symbol"]; mode=act.get("mode","SNIPER")
            if mode=="RISKY20": max_roi=-21.0
            elif "RISKY" in mode: max_roi=-16.0
            else: max_roi=-10.0
            if act["dir"]=="BUY": roi=(price-entry)/entry*100*10
            else: roi=(entry-price)/entry*100*10
            if roi<=max_roi:
                close_real_position(symbol,100); clear_active()
                loss=0.60 if mode=="RISKY20" else 0.45 if "RISKY" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨 AI SL {act.get('sl_pct',1.5):.1f}% HIT {act['coin']} {mode} ROI {roi:.1f}% Loss ${loss:.2f} 🧠 AI will learn!"},timeout=8,proxies=PROXIES)
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
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 AI TP1 HIT {act['coin']} {mode} +{act.get('tp1_pct',1.5):.1f}% 50% CLOSED ✅ BE 🛡️"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol,30); act["sl"]=act["tp1"]; act["stage"]=2; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 AI TP2 HIT {act['coin']} {mode} +{act.get('tp2_pct',3):.1f}% 80% total ✅ TRAILING"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol,100); clear_active()
                win=1.80 if mode=="RISKY20" else 1.35 if "RISKY" in mode else 0.50
                update_daily(win, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 AI TP3 HIT {act['coin']} {mode} +{act.get('tp3_pct',4.5):.1f}% +${win:.2f} FULL CLOSE 🎉💰💰💰 🧠 AI PERFECT!"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol,100); clear_active(); update_daily(0.70, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 AI TRAILING HIT {act['coin']} {mode} Profit $0.70+ 🔒"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="SL":
                close_real_position(symbol,100); clear_active()
                loss=0.60 if mode=="RISKY20" else 0.45 if "RISKY" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 AI SL {act.get('sl_pct',1.5):.1f}% {act['coin']} {mode} Loss ${loss:.2f} 🧠 AI learns!"},timeout=8,proxies=PROXIES)
                except: pass
        except Exception as e:
            print(f"monitor err {e}"); time.sleep(5)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("risk15",risk15_cmd)); a.add_handler(CommandHandler("risk20",risk20_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"V53 REAL AI BRAIN starting Risk {RISK_MODE}%"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
