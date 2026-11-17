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

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active.json"
DAILY_FILE = f"{DATA_DIR}/daily.json"
CHAT_FILE = f"{DATA_DIR}/chat.json"
PENDING_FILE = f"{DATA_DIR}/pending.json"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"SKELLY-V97-ALLFUTURES"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

SYMBOL_FIX = {
    "PEPEUSDT": "1000PEPEUSDT",
    "FLOKIUSDT": "1000FLOKIUSDT",
    "BONKUSDT": "1000BONKUSDT",
    "SHIBUSDT": "1000SHIBUSDT",
    "RATSUSDT": "1000RATSUSDT",
    "SATSUSDT": "1000SATSUSDT",
    "LUNCUSDT": "1000LUNCUSDT",
    "XECUSDT": "1000XECUSDT"
}

def fix_symbol(sym):
    return SYMBOL_FIX.get(sym, sym)

def binance_signed_request(method, endpoint, params={}, retries=1):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    try:
        p = dict(params); p['timestamp'] = int(time.time()*1000); p['recvWindow'] = 10000
        query = urllib.parse.urlencode(p)
        sig = hmac.new(BINANCE_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com{endpoint}?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        r = requests.request(method, url, headers=headers, proxies=PROXIES, timeout=10)
        print(f"Binance {endpoint} {r.status_code} {r.text[:400]}")
        if r.status_code == 200: return r.json()
        return {"error": r.text, "code": r.status_code}
    except Exception as e: return {"error": str(e)}

def get_futures_balance():
    data = binance_signed_request("GET", "/fapi/v2/balance")
    if isinstance(data, list):
        for b in data:
            if b.get('asset') == 'USDT':
                try: return float(b.get('balance',0))
                except: pass
    return 3.0

def set_leverage(symbol, lev=3):
    symbol = fix_symbol(symbol)
    return binance_signed_request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": lev})

def get_symbol_filters(symbol):
    symbol = fix_symbol(symbol)
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", headers=HEADERS, timeout=8, proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==symbol:
                for f in s['filters']:
                    if f['filterType']=='LOT_SIZE':
                        return float(f['minQty']), float(f['stepSize'])
    except: pass
    return 1.0, 1.0

def get_price_precision(symbol):
    symbol = fix_symbol(symbol)
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", headers=HEADERS, timeout=8, proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==symbol:
                for f in s['filters']:
                    if f['filterType']=='PRICE_FILTER':
                        return float(f['tickSize'])
    except: pass
    return 0.0000001

def place_real_futures_order(symbol, side, quantity):
    symbol = fix_symbol(symbol)
    params={"symbol": symbol, "side": side, "type": "MARKET", "quantity": quantity}
    return binance_signed_request("POST", "/fapi/v1/order", params)

def place_sl_tp_order(symbol, side, stop_price):
    symbol = fix_symbol(symbol)
    tick = get_price_precision(symbol)
    precision = int(round(-math.log10(tick),0)) if tick<1 else 0
    stop_price = round(stop_price, precision)
    params={
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "stopPrice": stop_price,
        "closePosition": True
    }
    return binance_signed_request("POST", "/fapi/v1/order", params)

def place_real_trade(symbol, direction, entry_price, sl, tp1, bal):
    try:
        real_symbol = fix_symbol(symbol)
        set_leverage(real_symbol, 3)
        minQty, step = get_symbol_filters(real_symbol)
        if minQty is None:
            minQty, step = 1.0, 1.0
        usdt_to_use = 3.0
        if bal >= 20:
            usdt_to_use = round(bal * 0.005 * 3, 2)
            if usdt_to_use < 3: usdt_to_use = 3.0
            if usdt_to_use > 15: usdt_to_use = 15.0
        else:
            usdt_to_use = round(bal * 0.45, 2)
            if usdt_to_use < 1: usdt_to_use = 1.0
        qty = usdt_to_use * 3 / entry_price
        precision = int(round(-math.log10(step),0)) if step<1 else 0
        if precision<0: precision=0
        qty = math.floor(qty / step) * step
        qty = round(qty, precision)
        if qty < minQty: qty = minQty
        side = "BUY" if direction=="BUY" else "SELL"
        print(f"REAL TRADE 3x: {side} {real_symbol} qty {qty}")
        result = place_real_futures_order(real_symbol, side, qty)
        if result and "Invalid symbol" in str(result):
            alt = "PEPEUSDT" if "1000PEPE" in real_symbol else real_symbol
            result = place_real_futures_order(alt, side, qty)
        if result and result.get("orderId"):
            time.sleep(0.6)
            close_side = "SELL" if direction=="BUY" else "BUY"
            sl_res = place_sl_tp_order(real_symbol, close_side, sl)
            print(f"SL set: {sl_res}")
        return result, qty, usdt_to_use, real_symbol
    except Exception as e:
        return {"error": str(e)}, 0, 0, symbol

def get_real_alt_futures():
    try:
        # FETCH ALL BINANCE FUTURES PERP USDT
        ex_url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        tick_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        ex = requests.get(ex_url, headers=HEADERS, timeout=10, proxies=PROXIES).json()
        perp = []
        for s in ex.get('symbols', []):
            if s.get('status') == 'TRADING' and s.get('contractType') == 'PERPETUAL' and s.get('quoteAsset') == 'USDT':
                if 'BULL' not in s['symbol'] and 'BEAR' not in s['symbol'] and 'USD_' not in s['symbol']:
                    perp.append(s['symbol'])
        t24 = requests.get(tick_url, headers=HEADERS, timeout=10, proxies=PROXIES).json()
        t24 = [x for x in t24 if x['symbol'] in perp]
        t24_sorted = sorted(t24, key=lambda x: float(x.get('quoteVolume',0)), reverse=True)
        top80 = [x['symbol'] for x in t24_sorted[:80]]
        print(f"ALL FUTURES: total {len(perp)} perp, scanning top {len(top80)} by volume")
        return top80 if len(top80) >= 20 else perp[:80]
    except Exception as e:
        print(f"Futures fetch error: {e}")
        return [
            "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT",
            "1000PEPEUSDT","1000FLOKIUSDT","1000BONKUSDT","1000SHIBUSDT","WIFUSDT","BOMEUSDT","POPCATUSDT",
            "ENAUSDT","WUSDT","ARBUSDT","OPUSDT","APTUSDT","SUIUSDT","SEIUSDT","TAOUSDT","NEARUSDT",
            "RENDERUSDT","FETUSDT","WLDUSDT","ONDOUSDT","JUPUSDT","INJUSDT","TIAUSDT","PENDLEUSDT"
        ]

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
            with open(p+".tmp",'w') as f: json.dump(data,f)
            os.replace(p+".tmp",p)
    except: pass
def get_daily():
    d=load_json(DAILY_FILE,{}); t=str(date.today())
    if d.get("date")!=t: d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def get_pending(): return load_json(PENDING_FILE,{})
def set_pending(d): save_json(PENDING_FILE,d)
def clear_pending(): save_json(PENDING_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})

@app.get("/")
def home(): return f"V97 ALL-FUTURES 80 Bal ${get_futures_balance():.2f}",200
@app.get("/health")
def health(): return "OK V97 ALL-FUTURES",200

def fmt(v):
    try:
        v=float(v)
        if v>=1: return f"{v:.5f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="15m"):
    sym = fix_symbol(sym)
    key=f"{sym}_{interval}"
    with CACHE_LOCK:
        if key in CACHE and time.time()-CACHE[key][0]<60: return CACHE[key][1]
    for base_url in ["https://fapi.binance.com/fapi/v1/klines","https://data-api.binance.vision/api/v3/klines","https://api.binance.com/api/v3/klines"]:
        try:
            r=requests.get(base_url,params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7,proxies=PROXIES).json()
            if isinstance(r,list) and len(r)>=70:
                kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"t":int(x[0])} for x in r]
                with CACHE_LOCK: CACHE[key]=(time.time(),kl)
                return kl
        except: continue
    with CACHE_LOCK:
        if key in CACHE: return CACHE[key][1]
    return []

def get_price(sym):
    sym = fix_symbol(sym)
    for base_url in ["https://fapi.binance.com/fapi/v1/ticker/price","https://data-api.binance.vision/api/v3/ticker/price"]:
        try:
            r=requests.get(base_url,params={"symbol":sym},headers=HEADERS,timeout=3,proxies=PROXIES).json()
            if "price" in r: return float(r["price"])
        except: continue
    kl=get_klines(sym,"1h"); return kl[-1]["c"] if kl else None

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e
def sma(arr,p): return sum(arr[-p:])/p if len(arr)>=p else sum(arr)/len(arr) if arr else 0
def rsi_calc(arr,p=14):
    if len(arr)<p+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(arr)):
        d=arr[i]-arr[i-1]
        gains.append(d if d>0 else 0); losses.append(-d if d<0 else 0)
    avg_g=sum(gains[-p:])/p; avg_l=sum(losses[-p:])/p
    if avg_l==0: return 70
    return 100-(100/(1+avg_g/avg_l))
def rsi_series(closes, p=14):
    if len(closes) < p+1: return [50]*len(closes)
    gains=[0]*len(closes); losses=[0]*len(closes)
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains[i]=d if d>0 else 0; losses[i]=-d if d<0 else 0
    avg_g=sum(gains[1:p+1])/p; avg_l=sum(losses[1:p+1])/p
    rsi=[50]*len(closes)
    for i in range(p, len(closes)):
        if i>p:
            avg_g=(avg_g*(p-1)+gains[i])/p
            avg_l=(avg_l*(p-1)+losses[i])/p
        if avg_l==0: rsi[i]=75
        else:
            rs=avg_g/avg_l
            rsi[i]=100-(100/(1+rs))
    return rsi
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
def atr_calc(kl,p=14):
    try:
        if len(kl)<p+1: return kl[-1]["h"]-kl[-1]["l"]
        tr=[]
        for i in range(1,len(kl)):
            tr.append(max(kl[i]["h"]-kl[i]["l"], abs(kl[i]["h"]-kl[i-1]["c"]), abs(kl[i]["l"]-kl[i-1]["c"])))
        return sum(tr[-p:])/p
    except: return 0
def macd_calc(closes):
    if len(closes)<35: return 0,0
    e12=ema(closes,12); e26=ema(closes,26)
    macd_line=e12-e26
    series=[ema(closes[:i+1],12)-ema(closes[:i+1],26) for i in range(26,len(closes))]
    signal=ema(series,9) if series else 0
    return macd_line, signal

def get_trend(candles):
    if len(candles)<60: return "NEUTRAL", 50, 0, 0
    c=[k["c"] for k in candles]
    e20=ema(c,20); e50=ema(c,50); e200=ema(c,200) if len(c)>=200 else e50
    r=rsi_calc(c)
    macd_line,sig=macd_calc(c)
    adx=adx_calc(candles)
    if c[-1]>e20 and e20>e50 and c[-1]>e200 and macd_line>sig: return "BUY", r, e20, e50
    if c[-1]<e20 and e20<e50 and c[-1]<e200 and macd_line<sig: return "SELL", r, e20, e50
    return "NEUTRAL", r, e20, e50

def make_colored_chart(klines):
    if not klines or len(klines)<10: return "🟨🟨🟨🟨🟨🟨🟨🟨🟨🟨"
    return "".join(["🟩" if k["c"]>k["o"] else "🟥" if k["c"]<k["o"] else "🟨" for k in klines[-10:]])

def analyze_PERFECT(symbol):
    try:
        k1h=get_klines(symbol,"1h")
        k4h=get_klines(symbol,"4h")
        k6h=get_klines(symbol,"6h")
        if len(k1h)<90 or len(k4h)<70 or len(k6h)<70:
            return None
        c1h=[k["c"] for k in k1h]
        c4h=[k["c"] for k in k4h]
        c6h=[k["c"] for k in k6h]
        h1h=[k["h"] for k in k1h]
        l1h=[k["l"] for k in k1h]
        rsi1h_series=rsi_series(c1h,14)
        rsi4h_series=rsi_series(c4h,14)
        rsi6h_series=rsi_series(c6h,14)
        rsi1h=rsi1h_series[-1]
        rsi4h=rsi4h_series[-1]
        rsi6h=rsi6h_series[-1]
        price=get_price(symbol) or c1h[-1]
        trend1h,_,_,_ = get_trend(k1h)
        trend4h,_,_,_ = get_trend(k4h)
        trend6h,_,_,_ = get_trend(k6h)
        if not (trend4h == trend6h and trend4h != "NEUTRAL"):
            return None
        if trend1h != "NEUTRAL" and trend1h != trend4h:
            return None
        direction=trend4h
        is_meme = any(x in symbol for x in ["1000PEPE","1000BONK","1000FLOKI","BONK","PEPE","WIF","FLOKI","SHIB","MEME","BOME"])
        if direction=="BUY":
            if is_meme:
                if not (28 <= rsi1h <= 62 and 30 <= rsi4h <= 65 and 30 <= rsi6h <= 65): return None
                if rsi1h > 65 or rsi4h > 67 or rsi6h > 67: return None
            else:
                if not (30 <= rsi1h <= 67 and 32 <= rsi4h <= 68 and 32 <= rsi6h <= 68): return None
                if rsi1h > 70 or rsi4h > 71 or rsi6h > 71: return None
            if rsi1h_series[-1] < rsi1h_series[-3]: return None
        else:
            if rsi1h < 28: return None
            if rsi1h_series[-1] > rsi1h_series[-3]: return None
        prev_high = max(h1h[-21:-1])
        prev_low = min(l1h[-21:-1])
        curr_close = c1h[-1]
        prev_low_wick = l1h[-2]
        prev_high_wick = h1h[-2]
        sweep_bull = prev_low_wick < prev_low and curr_close > prev_low
        sweep_bear = prev_high_wick > prev_high and curr_close < prev_high
        if direction=="BUY" and not sweep_bull: return None
        if direction=="SELL" and not sweep_bear: return None
        bos_bull = curr_close > prev_high
        bos_bear = curr_close < prev_low
        if direction=="BUY" and not bos_bull: return None
        if direction=="SELL" and not bos_bear: return None
        fvg = False
        if l1h[-1] > h1h[-3]: fvg = True
        if h1h[-1] < l1h[-3]: fvg = True
        if not fvg: return None
        vol=[k["v"] for k in k1h]; avg_vol=sma(vol,20)
        if vol[-1] < avg_vol*0.65: return None
        ma7=sma(c1h,7); ma25=sma(c1h,25); ma99=sma(c1h,99) if len(c1h)>=99 else ema(c1h,99)
        adx1h=adx_calc(k1h); adx4h=adx_calc(k4h)
        ema20=ema(c1h,20); ema50=ema(c1h,50)
        atr=atr_calc(k1h,14)
        if adx1h<18 or adx4h<16: return None
        score=0
        if trend4h==trend6h: score+=3
        if 38 < rsi1h < 60: score+=2
        if adx1h>22: score+=1
        if vol[-1]>avg_vol: score+=1
        if score<5: return None
        buf=atr*2.0 if atr else price*0.016
        max_sl=0.08 if is_meme else 0.065
        min_sl=0.035
        if direction=="BUY":
            sl=price-buf*2.2
            pct=(price-sl)/price
            if pct>max_sl: sl=price*(1-max_sl)
            if pct<min_sl: sl=price*(1-min_sl)
            tp1=price+(price-sl)*1.0; tp2=price+(price-sl)*1.9; tp3=price+(price-sl)*3.0; tp4=price+(price-sl)*4.5
        else:
            sl=price+buf*2.2
            pct=(sl-price)/price
            if pct>max_sl: sl=price*(1+max_sl)
            if pct<min_sl: sl=price*(1+min_sl)
            tp1=price-(sl-price)*1.0; tp2=price-(sl-price)*1.9; tp3=price-(sl-price)*3.0; tp4=price-(sl-price)*4.5
        rr=abs(tp2-price)/abs(price-sl) if abs(price-sl)>0 else 0
        if rr<1.7: return None
        conf_base=89
        if trend4h==trend6h: conf_base+=3
        if adx1h>24: conf_base+=1
        if 40<rsi1h<58: conf_base+=2
        confidence=min(94, max(89, conf_base))
        pattern=f"4H+6H {rsi4h:.0f}/{rsi6h:.0f} + Sweep+BOS+FVG"
        real_sym = fix_symbol(symbol)
        return {
            "symbol":symbol,"real_symbol":real_sym,"code":real_sym.replace("USDT",""),"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,
            "rsi":rsi1h,"adx":adx1h,"ma7":ma7,"ma25":ma25,"ma99":ma99,"ema20":ema20,"ema50":ema50,"score":score,"rr":rr,"conf":confidence,
            "trend1h":trend1h,"trend4h":trend4h,"trend6h":trend6h,
            "rsi1h":rsi1h,"rsi4h":rsi4h,"rsi6h":rsi6h,
            "chart1h":make_colored_chart(k1h),"chart4h":make_colored_chart(k4h),"chart6h":make_colored_chart(k6h),
            "pattern":pattern,"perfect_entry": price, "sl_pct":max_sl, "vol": vol[-1]/avg_vol if avg_vol else 1,
            "sweep": "Bear Trap" if direction=="BUY" else "Bull Trap"
        }
    except Exception as e:
        print(f"SECRET Filter error {symbol}: {e}")
        return None

def kb(active=None):
    daily=get_daily()
    if active and active.get("status")=="OPEN":
        return InlineKeyboardMarkup([[InlineKeyboardButton(f'🟢 {active["dir"]} {active["real_symbol"]} ${active.get("usdt",3)} {active.get("conf",89)}%',callback_data="MON")],[InlineKeyboardButton(f'👀 MONITOR',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")]])
    pend=get_pending()
    btns=[]
    if pend: btns.append([InlineKeyboardButton(f'⏳ PENDING {pend.get("real_symbol",pend["symbol"])} {pend["dir"]} {pend.get("conf",89)}%',callback_data="SHOW_PENDING")])
    btns.append([InlineKeyboardButton(f'⚡ SCAN 80 FUTURES SECRET 🔥',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'🔄 RESET',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app_):
    try:
        await app_.bot.set_my_commands([
            BotCommand("start","🚀 V97 ALL FUTURES"),
            BotCommand("scan","⚡ SCAN 80"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 DAILY"),
            BotCommand("reset","🔄 RESET")
        ])
    except: pass

def bg_scan(chat_id):
    try:
        bal=get_futures_balance(); syms=get_real_alt_futures()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚡🔍 V97 Scanning {len(syms)} FUTURES (Top Vol)...\n📊 4H+6H Agree + 1H Sweep+BOS+FVG + 3x Lev\nBal ${bal:.2f}"},timeout=10,proxies=PROXIES)
        raws=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            res=list(ex.map(analyze_PERFECT, syms))
        for t in res:
            if t: raws.append(t)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"😑💤 No secret setup in top {len(syms)} futures. Patient = profit 🛡️\nBal ${bal:.2f}"},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x:(x['conf'],x['score'],x['rr']), reverse=True)
        best=raws[0]; set_pending(best)
        display_sym = best.get("real_symbol", best["symbol"])
        mk=InlineKeyboardMarkup([
            [InlineKeyboardButton(f'✅ YES TRADE 3x {display_sym.replace("USDT","")} {best["conf"]}%', callback_data=f'YES_{best["symbol"]}_{best["dir"]}'), InlineKeyboardButton(f'😑💤 NO SKIP', callback_data='NO')]
        ])
        txt=(
            f"💎🔥 SECRET ENTRY! {best['conf']}% SURE! 👑\n\n"
            f"💱 {display_sym} | {best['dir']} | ⭐ Score {best['score']}/8 | 📈 RR {best['rr']:.1f} VOL x{best['vol']:.1f}\n"
            f"🕯️ Pattern: {best['pattern']} + {best['sweep']} 💎\n"
            f"🎯 Entry: {fmt(best['perfect_entry'])}\n"
            f"🛡️ SL {int(best['sl_pct']*100)}% Wide = {fmt(best['sl'])} Auto!\n"
            f"💰 TP1 = {fmt(best['tp1'])} BE + 50% | TP2 = {fmt(best['tp2'])} 25%\n"
            f"💰 TP3 = {fmt(best['tp3'])} | TP4 = {fmt(best['tp4'])} 🏆\n\n"
            f"📊 1H: {best['chart1h']} RSI {best['rsi1h']:.0f} {best['trend1h']}\n"
            f"📊 4H: {best['chart4h']} RSI {best['rsi4h']:.0f} {best['trend4h']} ✅\n"
            f"📊 6H: {best['chart6h']} RSI {best['rsi6h']:.0f} {best['trend6h']} ✅\n\n"
            f"📈 MA7 {fmt(best['ma7'])} | MA25 {fmt(best['ma25'])} | MA99 {fmt(best['ma99'])}\n"
            f"💪 ADX {best['adx']:.0f} | LEV 3x ONLY 🛡️\n"
            f"💰 Bal ${bal:.2f} | Risk 0.5% | {best['conf']}% SURE!\n\n"
            f"👉 REAL 3x SECRET TRADE? YES!"
        )
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt, "reply_markup": mk.to_dict()},timeout=10,proxies=PROXIES)
    except Exception as e: print(f"SCAN ERR {e}")

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    txt=(
        f"🧠💎 SKELLY'S V97 ALL-FUTURES 3x 👑\n"
        f"💰 Futures ${bal:.2f} | 3x Lev + 0.5% Risk!\n\n"
        f"✅ Scan TOP 80 Binance Futures by Volume LIVE!\n"
        f"✅ 4H+6H MUST AGREE!\n"
        f"✅ 1H Sweep + BOS + FVG!\n"
        f"✅ SL Wide 6.5%/8% Wick Safe!\n"
        f"🏆 89-94% SURE!\n\n"
        f"Press SCAN! ⚡"
    )
    await u.message.reply_text(txt, reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("⚡ V97 Scanning 80 Futures...")

async def daily_cmd(u,c): d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active()))
async def reset_cmd(u,c):
    save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
    clear_active(); clear_pending()
    await u.message.reply_text("🔄 RESET DONE! V97 Ready!", reply_markup=kb(get_active()))
async def monitor_cmd(u,c):
    act=get_active()
    if not act.get("status")=="OPEN": await u.message.reply_text("😴💤 No active",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
    pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
    await u.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% Conf {act.get('conf',89)}%", reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data=="RESET": save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); await q.message.reply_text("🔄 RESET!", reply_markup=kb(get_active())); return
    if data=="NO": clear_pending(); await q.message.reply_text("😑💤 Skipped! Secret protected you! 🛡️", reply_markup=kb(get_active())); return
    if data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending 😑💤"); return
        mk=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ YES 3x {pend.get("real_symbol",pend["symbol"])} {pend["conf"]}%', callback_data=f'YES_{pend["symbol"]}_{pend["dir"]}'), InlineKeyboardButton(f'😑💤 NO', callback_data='NO')]])
        await q.message.reply_text(f"⏳ PENDING {pend.get('real_symbol',pend['symbol'])} {pend['dir']} {pend['conf']}% RSI {pend['rsi1h']:.0f}/{pend['rsi4h']:.0f}/{pend['rsi6h']:.0f} Entry {fmt(pend['perfect_entry'])} Sweep {pend['sweep']} 3x only", reply_markup=mk); return
    if data.startswith("YES_"):
        parts=data.split("_"); symbol=parts[1]; direction=parts[2]
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending, scan again!"); return
        bal=get_futures_balance()
        real_sym = fix_symbol(symbol)
        await q.message.reply_text(f"⏳ Placing REAL 3x order {real_sym} RSI {pend['rsi1h']:.0f}/{pend['rsi4h']:.0f}/{pend['rsi6h']:.0f} {direction} + Auto SL Wide {fmt(pend['sl'])}... Bal ${bal:.2f}")
        result, qty, usdt_used, fixed_sym = place_real_trade(symbol, direction, pend['perfect_entry'], pend['sl'], pend['tp1'], bal)
        if result and "error" not in result and result.get("orderId"):
            set_active({"status":"OPEN","coin":fixed_sym.replace("USDT",""),"symbol":symbol,"real_symbol":fixed_sym,"dir":direction,"entry":pend['perfect_entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"qty":qty,"usdt":usdt_used,"orderId":result.get("orderId"),"time":str(datetime.now())})
            await q.message.reply_text(f"✅🔥 REAL 3x SECRET TRADE! 🚀\n{fixed_sym} {direction} {pend['conf']}% 4H+6H!\nQty {qty} | Used ${usdt_used} x3 Lev | SL Wide {fmt(pend['sl'])} {int(pend['sl_pct']*100)}%\nOrderID {result.get('orderId')}\nEntry {fmt(pend['perfect_entry'])} TP1 BE 50% TP2 25%\nBal left ~${bal-usdt_used:.2f} safe!", reply_markup=kb(get_active()))
        else:
            err = result.get("error","Unknown") if isinstance(result, dict) else str(result)
            await q.message.reply_text(f"⚠️ Binance Error: {err[:500]}\n\nFix: Enable Futures trading in API? Balance ${bal:.2f}? Symbol {real_sym}?", reply_markup=kb(get_active()))
        clear_pending(); return
    if data=="MON":
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴💤 No active",reply_markup=kb()); return
        price=get_price(act.get("real_symbol",act["symbol"])) or act["entry"]; entry=act["entry"]; pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        await q.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% {act.get('conf',89)}% 3x ${act.get('usdt',3)}",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); clear_pending(); await q.message.reply_text("😑💤 Closed! V97 SECRET",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("⚡ V97 Scanning 80 Futures..."); return

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("reset",reset_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V97 ALL-FUTURES LIVE"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    run_bot()
