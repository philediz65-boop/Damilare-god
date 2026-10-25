import os, threading, requests, time, json, urllib.parse, hmac, hashlib
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET","").strip()
BINANCE_SECRET = BINANCE_API_SECRET or os.getenv("BINANCE_SECRET","").strip()
BASE_TRADE = float(os.getenv("TRADE_AMOUNT_USDT","3"))
PORT = int(os.getenv("PORT","10000"))
BINANCE_PROXY = os.getenv("BINANCE_PROXY","").strip()

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v40.json"
DAILY_FILE = f"{DATA_DIR}/daily_v40.json"
CHAT_FILE = f"{DATA_DIR}/chat_v40.json"
CACHE = {}; LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

def binance_signed_request(method, endpoint, params={}):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    try:
        params['timestamp'] = int(time.time()*1000)
        params['recvWindow'] = 10000
        query = urllib.parse.urlencode(params)
        signature = hmac.new(BINANCE_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com{endpoint}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        r = requests.request(method, url, headers=headers, proxies=PROXIES, timeout=20)
        data = r.json()
        if r.status_code != 200: print(f"Binance Error {endpoint}: {data}")
        return data
    except Exception as e:
        print(f"Signed req fail {endpoint}: {e}"); return None

def get_futures_balance():
    data = binance_signed_request("GET", "/fapi/v2/balance")
    if isinstance(data, list):
        for b in data:
            if b.get('asset') == 'USDT': return float(b.get('balance',0))
    return 8.0

def get_trade_amount():
    bal = get_futures_balance()
    if bal is None: bal = 8.0
    if bal >= 30: return 10.0
    if bal >= 20: return 6.0
    if bal >= 15: return 5.0
    if bal >= 10: return 4.0
    return BASE_TRADE

def setup_symbol(symbol):
    try: binance_signed_request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"})
    except: pass
    try: binance_signed_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": 10})
    except: pass

def place_real_order(symbol, direction, usdt_amount):
    try:
        rp = requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}", proxies=PROXIES, headers=HEADERS, timeout=10).json()
        price = float(rp.get('price',0))
        if price==0: return None
        qty = (usdt_amount * 10) / price
        try:
            info = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", proxies=PROXIES, timeout=10).json()
            for s in info['symbols']:
                if s['symbol']==symbol:
                    qty = round(qty, int(s['quantityPrecision'])); break
        except: qty = round(qty, 3)
        setup_symbol(symbol)
        order = binance_signed_request("POST", "/fapi/v1/order", {"symbol": symbol, "side": "BUY" if direction=="BUY" else "SELL", "type": "MARKET", "quantity": qty})
        if order and order.get('orderId'): return order
        return None
    except Exception as e:
        print(f"ORDER FAIL: {e}"); return None

def close_real_position(symbol, qty_percent=100):
    try:
        pos = binance_signed_request("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        if not isinstance(pos, list): return None
        for p in pos:
            if p.get('symbol')!=symbol: continue
            amt = float(p.get('positionAmt',0))
            if amt != 0:
                side = "SELL" if amt>0 else "BUY"
                close_qty = abs(amt) * qty_percent / 100.0
                try:
                    info = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", proxies=PROXIES, timeout=10).json()
                    for s in info['symbols']:
                        if s['symbol']==symbol:
                            close_qty = round(close_qty, int(s['quantityPrecision'])); break
                except: close_qty = round(close_qty, 3)
                res = binance_signed_request("POST", "/fapi/v1/order", {"symbol": symbol, "side": side, "type": "MARKET", "quantity": close_qty, "reduceOnly": "true"})
                print(f"CLOSED {qty_percent}% {symbol}"); return res
    except Exception as e: print(f"Close fail: {e}")
    return None

def get_orderbook_score(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":20},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        bids=float(sum([float(x[0])*float(x[1]) for x in r.get('bids',[])[:10]]))
        asks=float(sum([float(x[0])*float(x[1]) for x in r.get('asks',[])[:10]]))
        if bids==0 or asks==0: return 0, "OB N/A"
        ratio = bids/asks if direction=="BUY" else asks/bids
        if ratio>=1.25: return 10, f"OB Strong Bull {ratio:.2f} 🟢🟢"
        if ratio>=1.1: return 6, f"OB Bull {ratio:.2f} 🟢"
        if ratio>=1.02: return 2, f"OB Slight Bull {ratio:.2f}"
        if ratio<=0.85: return -4, f"OB Bear Wall {ratio:.2f} 🔴"
        return 0, f"OB Neutral {ratio:.2f}"
    except: return 0, "OB N/A"

def get_oi_funding_score(symbol):
    try:
        prem=requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",params={"symbol":symbol},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        funding=float(prem.get('lastFundingRate',0)) if isinstance(prem,dict) else 0
        score=0; txts=[]
        if funding>0.0015: score-=4; txts.append(f"Fund Very High {funding*100:.3f}% 🔥")
        elif funding>0.0008: score-=2; txts.append(f"Fund High {funding*100:.3f}%")
        elif funding<-0.0015: score+=6; txts.append(f"Fund Very Low {funding*100:.3f}% 🟢🟢")
        elif funding<-0.0008: score+=3; txts.append(f"Fund Low {funding*100:.3f}% 🟢")
        else: score+=2; txts.append(f"Fund Neutral {funding*100:.3f}% ✅")
        return score, " | ".join(txts), 0, funding
    except: return 0, "Fund OK", 0, 0

def get_ls_ratio_score(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",params={"symbol":symbol,"period":"15m","limit":1},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        if isinstance(r,list) and len(r)>0:
            ratio=float(r[-1].get('longShortRatio',1))
            long_pct=ratio/(1+ratio)*100
            if direction=="BUY" and long_pct>78: return -4, f"LS Crowd Long {long_pct:.0f}% 🔴 Trap"
            if direction=="SELL" and long_pct<22: return -4, f"LS Crowd Short {100-long_pct:.0f}% 🔴 Trap"
            if direction=="BUY" and long_pct<35: return 6, f"LS Short Crowd {100-long_pct:.0f}% 🟢 Squeeze!"
            if direction=="SELL" and long_pct>65: return 6, f"LS Long Crowd {long_pct:.0f}% 🟢 Squeeze!"
            if 45<=long_pct<=55: return 5, f"LS Balanced {long_pct:.0f}% ✅ Perfect"
            return 0, f"LS {long_pct:.0f}%"
        return 0, "LS N/A"
    except: return 0, "LS N/A"

def calc_cvd(kl):
    try:
        cvd=0
        for k in kl[-20:]:
            if k["c"]>k["o"]: cvd+=k["v"]
            else: cvd-=k["v"]
        if cvd>0: return 4, f"CVD Bull 💪"
        else: return -2, f"CVD Bear 📉"
    except: return 0, "CVD N/A"

def calc_bos(kl):
    try:
        highs=[k["h"] for k in kl[-30:]]; lows=[k["l"] for k in kl[-30:]]
        last_h=max(highs[-20:-1]) if len(highs)>20 else highs[-1]
        last_l=min(lows[-20:-1]) if len(lows)>20 else lows[-1]
        curr=kl[-1]["c"]
        if curr>last_h: return 10, f"BOS UP Break 🚀 Strong!"
        if curr<last_l: return 10, f"BOS DOWN Break 📉 Strong!"
        return -2, "No BOS - Choppy ⏳"
    except: return 0, "BOS N/A"

def calc_fib_entry(kl, direction):
    try:
        hi=max(k["h"] for k in kl[-50:]); lo=min(k["l"] for k in kl[-50:]); curr=kl[-1]["c"]
        if hi==lo: return 0, "Fib N/A"
        fib_range=hi-lo
        fib_50=lo+fib_range*0.5; fib_62=lo+fib_range*0.618
        if direction=="BUY":
            if fib_50*0.98<=curr<=fib_62*1.02: return 12, f"Fib GOLDEN 50-62% 🎯 PERFECT BUY!"
            if curr<lo+fib_range*0.35: return 6, f"Fib Deep Discount ✅"
            if curr>hi-fib_range*0.25: return -3, f"Fib Premium - Wait Pullback ⚠️"
        else:
            if curr>=lo+fib_range*0.65: return 12, f"Fib Premium 65-75% 🎯 PERFECT SELL!"
            if curr<lo+fib_range*0.25: return -3, f"Fib Discount - Wait Bounce ⚠️"
        return 0, f"Fib {((curr-lo)/fib_range*100):.0f}% Mid"
    except: return 0, "Fib N/A"

def calc_divergence(kl, closes):
    try:
        if len(closes)<30: return 0, "Div N/A"
        price_low=min(closes[-20:-1]); price_now=closes[-1]
        rsi_arr=[rsi_calc(closes[:i]) for i in range(15,len(closes))]
        if len(rsi_arr)<20: return 0, "Div N/A"
        rsi_low=min(rsi_arr[-20:-1]); rsi_now=rsi_arr[-1]
        if price_now<price_low and rsi_now>rsi_low+4: return 8, f"Bull Div 📈 Reversal!"
        if price_now>max(closes[-20:-1]) and rsi_now<max(rsi_arr[-20:-1])-4: return 8, f"Bear Div 📉 Reversal!"
        return 0, "No Div"
    except: return 0, "Div N/A"

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        change=float(r.get('priceChangePercent',0))
        if change>=2: return 4, f"BTC +{change:.1f}% Bull 🌞"
        if change<=-2: return -3, f"BTC {change:.1f}% Bear 🌧️"
        return 0, f"BTC {change:.1f}% Neutral"
    except: return 0, "BTC N/A"

FAST = ["PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA","PENGU","POPCAT","MEW","MOODENG","GOAT","PNUT","ACT","BRETT","MOG","TURBO","1000PEPE","NEIRO","DOG","SPX","W","LADYS","WOJAK","MEME","PONKE","MYRO","WEN","TOSHI","CAT","BABYDOGE","NOT","DOGS","HMSTR","EIGEN","ZK","ZRO"]
CRYPTO = {k:f"{k}USDT" for k in FAST}
CRYPTO["1000PEPE"]="1000PEPEUSDT"
LEV = {k:10 for k in FAST}

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
    except: pass
    return d
def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f: json.dump(data,f)
    except: pass
def get_daily():
    d=load_json(DAILY_FILE,{}); t=str(date.today())
    if d.get("date")!=t: d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): 
    bal = get_futures_balance(); amt = get_trade_amount()
    return f"🚀 V45.3 BALANCED PERFECT 🎯 Bal ${bal:.2f} Trade ${amt} LIVE 85-95% 🏆",200
@app.get("/health")
def health(): return "OK ✅ V45.3 BALANCED",200

def fmt(v):
    try:
        v=float(v)
        if v>=1000: return f"{v:,.2f}"
        if v>=1: return f"{v:.4f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<50: return CACHE[key][1]
    kl=None
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=6, proxies=PROXIES).json()
        if isinstance(r,list) and len(r)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
    except: pass
    if kl: CACHE[key]=(time.time(),kl); return kl
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=4, proxies=PROXIES).json()
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
    g=l=0
    for i in range(1,p+1):
        d=arr[-i]-arr[-i-1]
        if d>0: g+=d
        else: l+=-d
    if l==0: return 70 if g>0 else 50
    return 100 - (100/(1+g/l))
def atr_calc(kl,p=14):
    if len(kl)<p+1: return kl[-1]["c"]*0.02
    trs=[max(kl[-i]["h"]-kl[-i]["l"], abs(kl[-i]["h"]-kl[-i-1]["c"]), abs(kl[-i]["l"]-kl[-i-1]["c"])) for i in range(1,p+1)]
    return sum(trs)/len(trs)
def adx_calc(kl):
    try:
        if len(kl)<30: return 18
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
        return max(10, min(60, 100*abs(pdi-mdi)/(pdi+mdi)))
    except: return 18
def pd_calc(kl):
    if len(kl)<100: return "EQUILIBRIUM",50
    hi=max(k["h"] for k in kl[-100:]); lo=min(k["l"] for k in kl[-100:]); pr=kl[-1]["c"]
    pct=(pr-lo)/(hi-lo)*100 if hi!=lo else 50
    return ("PREMIUM",pct) if pct>=70 else ("DISCOUNT",pct) if pct<=30 else ("EQUILIBRIUM",pct)
def trend_calc(closes):
    if len(closes)<50: return 0,"SIDEWAYS"
    e20=ema(closes,20); e50=ema(closes,50); pr=closes[-1]
    if pr>e20>e50: return 50,"UPTREND"
    if pr>e20: return 20,"WEAK UP"
    if pr<e20<e50: return -50,"DOWNTREND"
    if pr<e20: return -20,"WEAK DOWN"
    return 0,"SIDEWAYS"
def vol_calc(kl):
    if len(kl)<20: return 0,"Vol N/A"
    vols=[k["v"] for k in kl[-20:]]; avg=sum(vols[:-1])/len(vols[:-1]) if vols[:-1] else 1; pct=(vols[-1]-avg)/avg*100 if avg else 0
    return pct,f"Vol {pct:.0f}%"

def analyze_single_quick(code):
    try:
        sym=CRYPTO[code]; k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<40: k2=k1 if len(k1)>=40 else k15
        if len(k2)<40: return None
        c2=[k["c"] for k in k2]; price=get_price(sym) or c2[-1]
        rsi_v=rsi_calc(c2); atr_v=atr_calc(k2); adx_v=adx_calc(k2); pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2; c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15); s1,t1=trend_calc(c1); s2,t2=trend_calc(c2)
        e20_2h=ema(c2,20); e50_2h=ema(c2,50)
        vol_pct,vol_txt=vol_calc(k2)
        align=3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"; volatility=atr_v/price*100 if price else 0
        conf_quick=0
        if direction=="BUY" and pd_pct<=35: conf_quick+=20
        if direction=="SELL" and pd_pct>=65: conf_quick+=20
        if direction=="BUY" and pd_pct<=50: conf_quick+=10
        if direction=="SELL" and pd_pct>=50: conf_quick+=10
        if adx_v>=18: conf_quick+=15
        return {"code":code,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"align":align,"dir":direction,"kl":k2,"closes":c2,"conf_quick":conf_quick,"ema20":e20_2h,"ema50":e50_2h}
    except Exception as e:
        print(f"quick err {code}: {e}")
        return None

def ai_score_quick(r, market_adx):
    score=r.get("conf_quick",0)
    if 42<=r["rsi"]<=58: score+=15
    if r["volatility"]>=1.3: score+=10
    if r["align"]==3: score+=12
    elif r["align"]==2: score+=4
    else: score-=2
    if r["vol_pct"]>=10: score+=5
    return score

def add_ultimate_analysis(r):
    sym=CRYPTO[r["code"]]
    ob_score, ob_txt = get_orderbook_score(sym, r["dir"])
    oi_score, oi_txt, oi_val, funding = get_oi_funding_score(sym)
    ls_score, ls_txt = get_ls_ratio_score(sym, r["dir"])
    cvd_score, cvd_txt = calc_cvd(r["kl"])
    bos_score, bos_txt = calc_bos(r["kl"])
    fib_score, fib_txt = calc_fib_entry(r["kl"], r["dir"])
    div_score, div_txt = calc_divergence(r["kl"], r["closes"])
    btc_score, btc_txt = get_btc_filter()
    if r["dir"]=="BUY" and btc_score<0: extra_btc = btc_score
    else: extra_btc = max(0, btc_score)
    extra_score = ob_score + oi_score + ls_score + cvd_score + bos_score + fib_score + div_score + extra_btc
    # CAP NEGATIVE TO -8 ONLY
    if extra_score < -8: extra_score = -8
    r["extra_score"]=extra_score; r["ob_txt"]=ob_txt; r["oi_txt"]=oi_txt; r["ls_txt"]=ls_txt; r["cvd_txt"]=cvd_txt; r["bos_txt"]=bos_txt; r["fib_txt"]=fib_txt; r["div_txt"]=div_txt; r["btc_txt"]=btc_txt; r["funding"]=funding; r["oi"]=oi_val
    return r

def ai_score_perfect(r, market_adx):
    score=0
    if r["dir"]=="BUY":
        if r["pd_pct"]<=25: score+=22
        elif r["pd_pct"]<=35: score+=16
        elif r["pd_pct"]<=50: score+=6
        else: score-=2
    else:
        if r["pd_pct"]>=75: score+=22
        elif r["pd_pct"]>=65: score+=16
        elif r["pd_pct"]>=50: score+=6
        else: score-=2
    if 42<=r["rsi"]<=58: score+=18
    elif 38<=r["rsi"]<=62: score+=10
    else: score-=2
    if 20<=r["adx"]<=50: score+=18
    elif r["adx"]>=14: score+=10
    else: score-=2
    if r["volatility"]>=1.5: score+=10
    elif r["volatility"]>=1.0: score+=5
    if r["vol_pct"]>=10: score+=6
    if r["align"]==3: score+=12
    elif r["align"]==2: score+=6
    else: score-=2
    score+=r.get("extra_score",0)
    return max(0, min(100, score))

def build_trade(r):
    price=r["price"]; d=r["dir"]; atr=r["atr"]; atr_pct=r["volatility"]/100
    sl_pct=max(0.007, min(0.015, atr_pct*1.3))
    tp1_pct=sl_pct*0.9; tp2_pct=sl_pct*2.1; tp3_pct=sl_pct*3.8
    if d=="BUY":
        sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
    else:
        sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)
    return {"code":r["code"],"dir":d,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":LEV[r["code"]],"rsi":r["rsi"],"adx":r["adx"],"volatility":r["volatility"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']}","vol_txt":r["vol_txt"],"kl":r["kl"],"closes":r["closes"],"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100,"tp2_pct":tp2_pct*100,"tp3_pct":tp3_pct*100,"atr":atr,"ema20":r.get("ema20",0),"ema50":r.get("ema50",0),"align":r.get("align",0)}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/3 💰',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR {active["coin"]} PERFECT 📊',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🎯 SCAN SNIPER PERFECT 85% 🏆',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 💵',callback_data="DAILY"), InlineKeyboardButton(f'👀 MONITOR 📡',callback_data="MON")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try: await app.bot.set_my_commands([
        BotCommand("start","🎯 SNIPER PERFECT 85% #1"),
        BotCommand("scan","🎯 SCAN SNIPER PERFECT"),
        BotCommand("monitor","👀 MONITOR PERFECT"),
        BotCommand("daily","📊 Daily P&L")
    ])
    except: pass

def bg_scan(chat_id):
    try:
        amt = get_trade_amount(); bal = get_futures_balance()
        raws=[]
        for code in FAST:
            r=analyze_single_quick(code)
            if r: raws.append(r)
            time.sleep(0.02)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"❌ No data 😴"},timeout=10, proxies=PROXIES); return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        cands=[]
        for r in raws:
            if r["vol_pct"] < -50: continue
            if r["adx"] < 11: continue
            if r["align"] < 1: continue
            score = ai_score_quick(r, avg_adx)
            if score < 35: continue
            r["conf_quick"]=score
            cands.append(r)
        if not cands:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"😴 No quality 35+ now... Market too dull 💤 BTC sideways"},timeout=10, proxies=PROXIES); return
        cands.sort(key=lambda x: x["conf_quick"], reverse=True)
        top10 = cands[:10]
        ultimate_cands=[]
        report_lines=[]
        for r_quick in top10:
            r_full = add_ultimate_analysis(r_quick)
            score = ai_score_perfect(r_full, avg_adx)
            trade=build_trade(r_full); trade["conf"]=int(score); trade["raw"]=r_full; ultimate_cands.append(trade)
            reason=[]
            if r_full["pd_pct"]>50 and r_full["dir"]=="BUY": reason.append("PD mid")
            if "No BOS" in r_full["bos_txt"]: reason.append("No BOS")
            if "Bear Wall" in r_full["ob_txt"]: reason.append("OB Bear")
            report_lines.append(f"{r_full['code']} {score}/100 RSI {r_full['rsi']:.0f} ADX {r_full['adx']:.0f} {r_full['t2']} PD {r_full['pd_pct']:.0f}% EMA {'Bull' if 'UP' in r_full['t2'] else 'Bear'} ({','.join(reason) if reason else 'Close'})")

        perfect_cands = [x for x in ultimate_cands if x["conf"]>=60]
        
        if not perfect_cands:
            top_report = "\n".join(report_lines[:5])
            msg = f"🎯 SNIPER BALANCED - No 60%+ now\nMarket dull, waiting... ⏳\n\n📊 TOP 5 FULL Analysis:\n{top_report}\n\n💡 Need for 85%:\n✅ RSI 42-58 | ADX 20+ | EMA UPTREND\n✅ PD 25-35% Discount | MTF Align 3\n✅ BOS Break | OB Bull | Fib Golden\n\nTop was {top10[0]['code']} {ultimate_cands[0]['conf']}/100 - Try in 10 min 🔍"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10, proxies=PROXIES); return
        
        perfect_cands.sort(key=lambda x: x["conf"], reverse=True)
        best=perfect_cands[0]
        
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN 🔒 Use /monitor 👀"},timeout=10, proxies=PROXIES); return
        real_symbol = CRYPTO[best["code"]]
        order_res = place_real_order(real_symbol, best["dir"], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol} 😭 Check Futures has ${amt*2}+ USDT 💸"},timeout=10, proxies=PROXIES); return
        set_active({"status":"OPEN","coin":best["code"],"symbol":real_symbol,"dir":best["dir"],"entry":best["entry"],"sl":best["sl"],"tp1":best["tp1"],"tp2":best["tp2"],"tp3":best["tp3"],"conf":best["conf"],"stake":amt,"lev":best["lev"],"stage":0,"highest":best["entry"],"lowest":best["entry"],"sl_pct":best["sl_pct"],"tp1_pct":best["tp1_pct"],"time":str(__import__('datetime').datetime.now()),"rsi":best["rsi"],"adx":best["adx"],"pd_pct":best["pd_pct"],"pd_zone":best["pd_zone"],"mtf":best["mtf"],"vol_txt":best["vol_txt"],"ema20":best["ema20"],"ema50":best["ema50"],"align":best["align"]})
        sure = "95% SURE 🔥🔥🔥" if best["conf"]>=85 else "90% SURE 🔥🔥" if best["conf"]>=75 else "85% SURE ✅" if best["conf"]>=68 else "75% SURE ⚡" if best["conf"]>=60 else "60% OK"
        txt=(
            f"🎯 SNIPER BALANCED {best['conf']}/100 {sure}\n"
            f"💎 {best['code']} {best['dir']} @ {fmt(best['entry'])}\n"
            f"💰 ${amt} {best['lev']}x | ATR SL {best['sl_pct']:.2f}% TP {best['tp1_pct']:.2f}/{best['tp2_pct']:.2f}/{best['tp3_pct']:.2f}\n"
            f"🆔 ORDER {order_res.get('orderId')} ✅\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 CORE:\n"
            f"• RSI: {best['rsi']:.1f} {'✅' if 42<=best['rsi']<=58 else '⚠️'}\n"
            f"• ADX: {best['adx']:.1f} {'✅ Strong' if best['adx']>=20 else 'OK'}\n"
            f"• EMA: 20={fmt(best['ema20'])} 50={fmt(best['ema50'])} {'🟢 BULLISH' if 'UP' in best['raw']['t2'] else '🔴 BEARISH'} {best['raw']['t2']}\n"
            f"• PD: {best['pd_pct']:.0f}% {best['pd_zone']}\n"
            f"• MTF: {best['mtf']} | Align {best['align']}/3\n"
            f"• {best['vol_txt']} | ATR {best['volatility']:.2f}%\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🧠 ULTIMATE:\n"
            f"🧱 {best['raw']['ob_txt']}\n"
            f"🐳 {best['raw']['oi_txt']}\n"
            f"🔄 {best['raw']['ls_txt']}\n"
            f"🏗️ {best['raw']['bos_txt']}\n"
            f"📐 {best['raw']['fib_txt']}\n"
            f"⚡ {best['raw']['div_txt']}\n"
            f"💪 {best['raw']['cvd_txt']}\n"
            f"₿ {best['raw']['btc_txt']}\n"
            f"💵 Bal ${bal:.2f} - {sure} 🏆"
        )
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10, proxies=PROXIES)
    except Exception as e:
        print(f"SCAN ERR {e}")
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Scan error: {e} 😭"},timeout=10, proxies=PROXIES)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id); bal = get_futures_balance(); amt = get_trade_amount()
    bal_text = f"\n💰 Futures: ${bal:.2f} USDT\n🎯 SNIPER BALANCED 85-95% 🏆" if bal is not None else "\n❌ Balance fail 😭"
    await u.message.reply_text(f"🤖 V45.3 BALANCED FINAL LIVE ✨{bal_text}\n💵 Trade: ${amt} 10x (Auto-Compound)\n📊 EMA + RSI + ADX + PD + MTF + Vol + ATR\n🧠 + 7 ULTIMATE + BTC Filter\n🎯 60+ (75%) | 68+ (85%) | 75+ (90%) | 85+ (95%)\n⚡ FAST 12s + Trailing 🏃\n👀 /monitor to see LIVE!",parse_mode="Markdown",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🎯 SCANNING SNIPER BALANCED... 🏆\nChecking 60 coins with REALISTIC scoring! 12 sec...")

async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💵 SNIPER BALANCED",reply_markup=kb(get_active()))

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN":
        await u.message.reply_text("😴 No active trade now 📭\nPress SCAN SNIPER BALANCED to find trade! 🎯🚀🏆",reply_markup=kb()); return
    price=get_price(CRYPTO[act["coin"]]) or act["entry"]; entry=act["entry"]; stake=act["stake"]; lev=act["lev"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    pnl_usdt=pnl_pct/100 * stake * lev; pnl_emoji="🟢💰" if pnl_usdt>0 else "🔴📉" if pnl_usdt<0 else "⚪"
    bal=get_futures_balance(); stage=act.get("stage",0)
    stage_txt=["Just Started 🚀 85% Sniper","TP1 Done ✅ BE Safe 🛡️","TP2 Done ✅ Trailing 🏃"][stage] if stage<3 else "Running 🌙"
    sure = "95% 🔥🔥🔥" if act.get('conf',0)>=85 else "90% 🔥🔥" if act.get('conf',0)>=75 else "85% ✅"
    txt=(f"👀 MONITOR BALANCED 📡 {sure}\n━━━━━━━━━━━━━━━\n💎 {act['coin']} {act['dir']} {pnl_emoji}\n📍 Stage: {stage}/3 - {stage_txt}\n📍 Entry: {fmt(entry)} → Now: {fmt(price)}\n📈 P&L: {pnl_pct:.3f}% (${pnl_usdt:+.4f}) {pnl_emoji}\n━━━━━━━━━━━━━━━\n📊 RSI {act.get('rsi',0):.1f} | ADX {act.get('adx',0):.1f} | PD {act.get('pd_pct',0):.0f}% {act.get('pd_zone','')}\n📈 {act.get('mtf','')} | {act.get('vol_txt','')}\n🛡️ SL: {fmt(act['sl'])} ({act.get('sl_pct',0.9):.2f}%)\n🎯 TP1: {fmt(act['tp1'])} | TP2: {fmt(act['tp2'])} | TP3: {fmt(act['tp3'])}\n━━━━━━━━━━━━━━━\n💰 Bal: ${bal:.2f} | Stake: ${stake} | {sure} 🏆")
    await u.message.reply_text(txt, reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💵 BALANCED",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade 📭",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        pnl_usdt=pnl_pct/100 * act["stake"] * act["lev"]; pnl_emoji="🟢💰" if pnl_usdt>0 else "🔴"
        stage=act.get("stage",0)
        txt=(f"👀 BALANCED MONITOR {act['coin']} LIVE 📊\n{act['dir']} Stage {stage}/3 | RSI {act.get('rsi',0):.0f} ADX {act.get('adx',0):.0f}\nEntry {fmt(entry)} → Now {fmt(price)}\nP&L {pnl_pct:.2f}% (${pnl_usdt:+.4f}) {pnl_emoji}\nSL {fmt(act['sl'])} ({act.get('sl_pct',0):.2f}%)")
        await q.message.reply_text(txt,reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed on Binance ✅",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("🎯 SCANNING SNIPER BALANCED... 🏆"); return

def monitor():
    while True:
        try:
            time.sleep(12); act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(CRYPTO[act["coin"]])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            stage = act.get("stage",0); entry = act["entry"]; symbol = act["symbol"]
            if act["dir"]=="BUY": act["highest"] = max(act.get("highest", entry), price)
            else: act["lowest"] = min(act.get("lowest", entry), price)
            hit = None
            if stage>=2:
                trail_pct = 0.006
                if act["dir"]=="BUY":
                    new_trail_sl = act["highest"] * (1 - trail_pct)
                    if new_trail_sl > act["sl"]:
                        act["sl"] = new_trail_sl; set_active(act)
                        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING UP! {act['coin']} SL {fmt(new_trail_sl)} 🔒 High {fmt(act['highest'])} 🚀"},timeout=8, proxies=PROXIES)
                        except: pass
                else:
                    new_trail_sl = act["lowest"] * (1 + trail_pct)
                    if new_trail_sl < act["sl"]:
                        act["sl"] = new_trail_sl; set_active(act)
                        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING DOWN! {act['coin']} SL {fmt(new_trail_sl)} 🔒 Low {fmt(act['lowest'])} 📉"},timeout=8, proxies=PROXIES)
                        except: pass
                if act["dir"]=="BUY" and price <= act["sl"]: hit="TRAIL_SL"
                elif act["dir"]=="SELL" and price >= act["sl"]: hit="TRAIL_SL"
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
                close_real_position(symbol, 50); new_sl = entry * 1.001 if act["dir"]=="BUY" else entry * 0.999
                act["sl"] = new_sl; act["stage"] = 1; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 HIT! {act['coin']} +{act.get('tp1_pct',0.8):.2f}% 💰 50% CLOSED ✅ SL->BE 🛡️"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol, 60); new_sl = act["tp1"]; act["sl"] = new_sl; act["stage"] = 2; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 TP2 HIT! {act['coin']} +{act.get('tp2_pct',1.8):.2f}% 💰💰 80% total ✅ TRAILING 🏃"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol, 100); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 TP3 HIT! {act['coin']} +{act.get('tp3_pct',3.2):.2f}% 🌕 FULL CLOSE! 🎉💰💰💰 🔥"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol, 100); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃💰 TRAILING SL HIT! {act['coin']} 🔒 Profit locked!"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="SL":
                close_real_position(symbol, 100); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL {act.get('sl_pct',0.9):.2f}% {act['coin']} Closed 😢 Small loss 🛡️"},timeout=8, proxies=PROXIES)
                except: pass
        except Exception as e:
            print(f"monitor err {e}"); time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("🚀 V45.3 BALANCED starting 🎯🏆"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
