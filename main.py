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
HEADERS = {"User-Agent":"SKELLY-V90.1-WIDE-SL"}
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
    return 7.03

def set_leverage(symbol, lev=10):
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
        set_leverage(real_symbol, 10)
        minQty, step = get_symbol_filters(real_symbol)
        if minQty is None:
            minQty, step = 1.0, 1.0
        usdt_to_use = 3.0
        if bal < 3.5:
            usdt_to_use = round(bal * 0.45, 2)
            if usdt_to_use < 1: usdt_to_use = 1.0
        qty = usdt_to_use * 10 / entry_price
        precision = int(round(-math.log10(step),0)) if step<1 else 0
        if precision<0: precision=0
        qty = math.floor(qty / step) * step
        qty = round(qty, precision)
        if qty < minQty: qty = minQty
        side = "BUY" if direction=="BUY" else "SELL"
        result = place_real_futures_order(real_symbol, side, qty)
        if result and "Invalid symbol" in str(result):
            alt = "PEPEUSDT" if "1000PEPE" in real_symbol else real_symbol
            result = place_real_futures_order(alt, side, qty)
        if result and result.get("orderId"):
            time.sleep(0.6)
            close_side = "SELL" if direction=="BUY" else "BUY"
            sl_res = place_sl_tp_order(real_symbol, close_side, sl)
            print(f"SL set {sl} result: {sl_res}")
        return result, qty, usdt_to_use, real_symbol
    except Exception as e:
        return {"error": str(e)}, 0, 0, symbol

def get_real_alt_futures():
    SAFE_VALID = [
        "1000PEPEUSDT","1000FLOKIUSDT","1000BONKUSDT","1000SHIBUSDT",
        "WIFUSDT","DOGEUSDT","MEMEUSDT","BOMEUSDT","POPCATUSDT","PNUTUSDT",
        "GOATUSDT","MOODENGUSDT","FARTCOINUSDT","SOLUSDT","AVAXUSDT","LINKUSDT",
        "ENAUSDT","VIRTUALUSDT","PENGUUSDT","WUSDT","NOTUSDT","ARBUSDT","OPUSDT",
        "APTUSDT","SUIUSDT","SEIUSDT","INJUSDT","RNDRUSDT","FETUSDT","WLDUSDT","TIAUSDT"
    ]
    return list(dict.fromkeys(SAFE_VALID))[:32]

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
def home(): return f"V90.1 WIDE SL LIVE Bal ${get_futures_balance():.2f}",200
@app.get("/health")
def health(): return "OK V90.1 WIDE SL",200

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
        if key in CACHE and time.time()-CACHE[key][0]<45: return CACHE[key][1]
    for base_url in ["https://fapi.binance.com/fapi/v1/klines","https://data-api.binance.vision/api/v3/klines","https://api.binance.com/api/v3/klines"]:
        try:
            r=requests.get(base_url,params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7,proxies=PROXIES).json()
            if isinstance(r,list) and len(r)>=60:
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

def get_trend(candles):
    if len(candles)<50: return "NEUTRAL", 50
    c=[k["c"] for k in candles]
    e20=ema(c,20); e50=ema(c,50); rsi=rsi_calc(c)
    if c[-1]>e20 and e20>e50 and rsi>38: return "BUY", rsi
    if c[-1]<e20 and e20<e50 and rsi<62: return "SELL", rsi
    return "NEUTRAL", rsi

def make_colored_chart(klines):
    if not klines or len(klines)<10: return "🟨🟨🟨🟨🟨🟨🟨🟨🟨🟨"
    last10 = klines[-10:]
    chart=""
    for k in last10:
        if k["c"]>k["o"]: chart+="🟩"
        elif k["c"]<k["o"]: chart+="🟥"
        else: chart+="🟨"
    return chart

def analyze_PERFECT(symbol):
    try:
        k15=get_klines(symbol,"15m"); k1h=get_klines(symbol,"1h"); k2h=get_klines(symbol,"2h"); k4h=get_klines(symbol,"4h")
        if len(k15)<80 or len(k1h)<60 or len(k4h)<60: return None
        c15=[k["c"] for k in k15]; c1h=[k["c"] for k in k1h]; c2h=[k["c"] for k in k2h]; c4h=[k["c"] for k in k4h]
        rsi15_series = rsi_series(c15,14); rsi1h_series = rsi_series(c1h,14)
        rsi15 = rsi15_series[-1]; rsi1h = rsi1h_series[-1]
        rsi2h = rsi_calc(c2h); rsi4h = rsi_calc(c4h)
        price=get_price(symbol) or c15[-1]
        trend15, _ = get_trend(k15); trend1h, _ = get_trend(k1h); trend2h, _ = get_trend(k2h); trend4h, _ = get_trend(k4h)
        aligns = [trend15,trend1h,trend2h,trend4h].count(trend15)
        if aligns<3 or trend15=="NEUTRAL": return None
        direction=trend15
        is_meme = any(x in symbol for x in ["1000PEPE","1000BONK","1000FLOKI","BONK","PEPE","WIF","FLOKI","SHIB","MEME","BOME"])
        # GOD RSI FILTER
        if direction=="BUY":
            if is_meme:
                if not (30 <= rsi15 <= 65): return None
                if rsi1h > 68 or rsi4h > 66: return None
            else:
                if not (32 <= rsi15 <= 68): return None
                if rsi1h > 72 or rsi4h > 70: return None
            if rsi15_series[-1] < rsi15_series[-6]: return None
            if rsi15 > 72: return None
        else:
            if is_meme:
                if not (35 <= rsi15 <= 70): return None
                if rsi1h < 30 or rsi4h < 32: return None
            else:
                if not (32 <= rsi15 <= 70): return None
            if rsi15_series[-1] > rsi15_series[-6]: return None
            if rsi15 < 28: return None
        # Divergence check
        if len(c15)>=20:
            recent_high_price = max(c15[-20:-5]); current_high_price = max(c15[-5:])
            recent_high_rsi = max(rsi15_series[-20:-5]); current_high_rsi = max(rsi15_series[-5:])
            if direction=="BUY" and current_high_price > recent_high_price and current_high_rsi < recent_high_rsi - 2:
                return None
        ma7=sma(c15,7); ma25=sma(c15,25); ma99=sma(c15,99) if len(c15)>=99 else ema(c15,99)
        adx=adx_calc(k15); atr=atr_calc(k15,14)
        ema20=ema(c15,20); ema50=ema(c15,50)
        if adx<14: return None
        score=0
        if (ema20>ema50 and direction=="BUY") or (ema20<ema50 and direction=="SELL"): score+=2
        if 38 < rsi15 < 62: score+=3
        elif 35 < rsi15 < 65: score+=2
        if adx>20: score+=1
        if aligns==4: score+=2
        if is_meme and rsi15<60: score+=1
        if score<5: return None

        # === WIDE SL FIX - 6.5% normal, 8% MEME ===
        buf=atr*1.8 if atr else price*0.015
        max_sl_pct = 0.08 if is_meme else 0.065
        min_sl_pct = 0.035
        
        if direction=="BUY":
            sl=price-buf*2.2
            pct = (price-sl)/price
            if pct > max_sl_pct:
                sl=price*(1-max_sl_pct)
            if pct < min_sl_pct:
                sl=price*(1-min_sl_pct)
            tp1=price+(price-sl)*1.0; tp2=price+(price-sl)*1.8; tp3=price+(price-sl)*2.8; tp4=price+(price-sl)*4.0
        else:
            sl=price+buf*2.2
            pct = (sl-price)/price
            if pct > max_sl_pct:
                sl=price*(1+max_sl_pct)
            if pct < min_sl_pct:
                sl=price*(1+min_sl_pct)
            tp1=price-(sl-price)*1.0; tp2=price-(sl-price)*1.8; tp3=price-(sl-price)*2.8; tp4=price-(sl-price)*4.0

        rr=abs(tp2-price)/abs(price-sl) if abs(price-sl)>0 else 0
        if rr<1.5: return None
        conf_base=89
        if aligns==4: conf_base+=2
        if adx>22: conf_base+=1
        if 40<rsi15<60: conf_base+=2
        confidence=min(93, max(89, conf_base))
        pattern=f"RSI PERFECT {rsi15:.0f} WIDE SL"
        real_sym = fix_symbol(symbol)
        return {
            "symbol":symbol,"real_symbol":real_sym,"code":real_sym.replace("USDT",""),"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,
            "rsi":rsi15,"adx":adx,"ma7":ma7,"ma25":ma25,"ma99":ma99,"ema20":ema20,"ema50":ema50,"score":score,"rr":rr,"conf":confidence,
            "trend15":trend15,"trend1h":trend1h,"trend2h":trend2h,"trend4h":trend4h,
            "rsi15":rsi15,"rsi1h":rsi1h,"rsi2h":rsi2h,"rsi4h":rsi4h,
            "chart15":make_colored_chart(k15),"chart1h":make_colored_chart(k1h),"chart2h":make_colored_chart(k2h),"chart4h":make_colored_chart(k4h),
            "pattern":pattern,"perfect_entry": price, "sl_pct": max_sl_pct
        }
    except Exception as e:
        print(f"RSI Filter error {symbol}: {e}")
        return None

def kb(active=None):
    daily=get_daily()
    if active and active.get("status")=="OPEN":
        return InlineKeyboardMarkup([[InlineKeyboardButton(f'🟢 {active["dir"]} {active["real_symbol"]} ${active.get("usdt",3)} {active.get("conf",89)}%',callback_data="MON")],[InlineKeyboardButton(f'👀 MONITOR',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")]])
    pend=get_pending()
    btns=[]
    if pend: btns.append([InlineKeyboardButton(f'⏳ PENDING {pend.get("real_symbol",pend["symbol"])} {pend["dir"]} {pend.get("conf",89)}%',callback_data="SHOW_PENDING")])
    btns.append([InlineKeyboardButton(f'⚡ SCAN 32 SAFE WIDE SL RSI GOD',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'🔄 RESET',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app_):
    try:
        await app_.bot.set_my_commands([
            BotCommand("start","🚀 V90.1 WIDE SL"),
            BotCommand("scan","⚡ SCAN WIDE SL"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 DAILY"),
            BotCommand("reset","🔄 RESET")
        ])
    except: pass

def bg_scan(chat_id):
    try:
        bal=get_futures_balance(); syms=get_real_alt_futures()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚡🔍 V90.1 WIDE SL Scanning {len(syms)} SAFE...\n📊 RSI 30-65 + SL 6.5%/8% Wide!\nBal ${bal:.2f} | Trade $3 only!"},timeout=10,proxies=PROXIES)
        raws=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            res=list(ex.map(analyze_PERFECT, syms))
        for t in res:
            if t: raws.append(t)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"😑💤 Dull market... RSI Overbought! No trade.\nBal ${bal:.2f}"},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x:(x['conf'],x['score'],x['rr']), reverse=True)
        best=raws[0]; set_pending(best)
        display_sym = best.get("real_symbol", best["symbol"])
        sl_pct_display = int(best.get("sl_pct",0.065)*100)
        mk=InlineKeyboardMarkup([
            [InlineKeyboardButton(f'✅ YES $3 {display_sym.replace("USDT","")} {best["conf"]}% SL {sl_pct_display}%', callback_data=f'YES_{best["symbol"]}_{best["dir"]}'), InlineKeyboardButton(f'😑💤 NO', callback_data='NO')]
        ])
        txt=(
            f"💎🔥 RSI GOD WIDE SL FOUND! {best['conf']}% SURE! 👑✨\n\n"
            f"💱 {display_sym} | {best['dir']} | ⭐ Score {best['score']}/8 | 📈 RR {best['rr']:.1f}\n"
            f"🕯️ Pattern: {best['pattern']} RSI {best['rsi15']:.0f} 💎\n"
            f"🎯 Entry: {fmt(best['perfect_entry'])}\n"
            f"🛡️ SL {sl_pct_display}% Wide = {fmt(best['sl'])} Auto-Set! No too close!\n"
            f"💰 TP1 55% = {fmt(best['tp1'])} 25% + BE 🔒\n"
            f"💰 TP2 80% = {fmt(best['tp2'])} 25%\n"
            f"💰 TP3 120% = {fmt(best['tp3'])} 25%\n"
            f"💰 TP4 180% = {fmt(best['tp4'])} 25% 🏆\n\n"
            f"📊 15m: {best['chart15']} {best['trend15']} RSI {best['rsi15']:.0f} ✅\n"
            f"📊 1h: {best['chart1h']} {best['trend1h']} RSI {best['rsi1h']:.0f}\n"
            f"📊 2h: {best['chart2h']} {best['trend2h']} RSI {best['rsi2h']:.0f}\n"
            f"📊 4h: {best['chart4h']} {best['trend4h']} RSI {best['rsi4h']:.0f}\n\n"
            f"💰 Bal ${bal:.2f} | $3 only | Wide SL {sl_pct_display}% | RSI God!\n\n"
            f"👉 REAL $3 WIDE SL TRADE? YES!"
        )
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt, "reply_markup": mk.to_dict()},timeout=10,proxies=PROXIES)
    except Exception as e: print(f"SCAN ERR {e}")

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    txt=(
        f"🧠💎 V90.1 WIDE SL + RSI GOD 👑✨\n"
        f"💰 Futures ${bal:.2f} USDT | $3 ONLY + Auto SL Wide!\n\n"
        f"✅ RSI 30-65 Only - No Top!\n"
        f"✅ SL WIDE 6.5% Normal, 8% MEME!\n"
        f"✅ No too close - Wick safe!\n"
        f"✅ Auto SL for Binance!\n"
        f"🏆 89-93% SURE!\n\n"
        f"Press SCAN! ⚡🔍"
    )
    await u.message.reply_text(txt, reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("⚡ V90.1 WIDE SL Scanning 32 SAFE...")

async def daily_cmd(u,c): d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active()))
async def reset_cmd(u,c):
    save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
    clear_active(); clear_pending()
    await u.message.reply_text("🔄 RESET DONE! V90.1 WIDE SL Ready!", reply_markup=kb(get_active()))
async def monitor_cmd(u,c):
    act=get_active()
    if not act.get("status")=="OPEN": await u.message.reply_text("😴💤 No active",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
    pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
    await u.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% Conf {act.get('conf',89)}% Wide SL ${act.get('usdt',3)}", reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data=="RESET": save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); await q.message.reply_text("🔄 RESET!", reply_markup=kb(get_active())); return
    if data=="NO": clear_pending(); await q.message.reply_text("😑💤 Dull skipped! Wide SL protected you!", reply_markup=kb(get_active())); return
    if data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending 😑💤"); return
        mk=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ YES $3 {pend.get("real_symbol",pend["symbol"])} {pend["conf"]}% SL Wide', callback_data=f'YES_{pend["symbol"]}_{pend["dir"]}'), InlineKeyboardButton(f'😑💤 NO', callback_data='NO')]])
        await q.message.reply_text(f"⏳ PENDING {pend.get('real_symbol',pend['symbol'])} {pend['dir']} {pend['conf']}% RSI {pend['rsi15']:.0f} Entry {fmt(pend['perfect_entry'])} SL {fmt(pend['sl'])} Wide {int(pend.get('sl_pct',0.065)*100)}%", reply_markup=mk); return
    if data.startswith("YES_"):
        parts=data.split("_"); symbol=parts[1]; direction=parts[2]
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending, scan again!"); return
        bal=get_futures_balance()
        real_sym = fix_symbol(symbol)
        await q.message.reply_text(f"⏳ Placing REAL $3 WIDE SL {real_sym} RSI {pend['rsi15']:.0f} {direction} SL {fmt(pend['sl'])} {int(pend.get('sl_pct',0.065)*100)}%... Bal ${bal:.2f}")
        result, qty, usdt_used, fixed_sym = place_real_trade(symbol, direction, pend['perfect_entry'], pend['sl'], pend['tp1'], bal)
        if result and "error" not in result and result.get("orderId"):
            set_active({"status":"OPEN","coin":fixed_sym.replace("USDT",""),"symbol":symbol,"real_symbol":fixed_sym,"dir":direction,"entry":pend['perfect_entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"qty":qty,"usdt":usdt_used,"orderId":result.get("orderId"),"time":str(datetime.now())})
            await q.message.reply_text(f"✅🔥 REAL $3 WIDE SL EXECUTED! 🚀\n{fixed_sym} {direction} {pend['conf']}% SL {int(pend.get('sl_pct',0.065)*100)}% Wide!\nQty {qty} | ${usdt_used} x10 | SL Auto-Set {fmt(pend['sl'])}\nOrderID {result.get('orderId')}\nEntry {fmt(pend['perfect_entry'])}\nBal left ~${bal-usdt_used:.2f} safe!\nCheck Binance!", reply_markup=kb(get_active()))
        else:
            err = result.get("error","Unknown") if isinstance(result, dict) else str(result)
            await q.message.reply_text(f"⚠️ Binance Error: {err[:500]}\nBal ${bal:.2f}? Symbol {real_sym}?", reply_markup=kb(get_active()))
        clear_pending(); return
    if data=="MON":
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴💤 No active",reply_markup=kb()); return
        price=get_price(act.get("real_symbol",act["symbol"])) or act["entry"]; entry=act["entry"]; pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        await q.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% {act.get('conf',89)}% Wide SL ${act.get('usdt',3)}",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); clear_pending(); await q.message.reply_text("😑💤 Closed!",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("⚡ V90.1 WIDE SL Scanning..."); return

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("reset",reset_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V90.1 WIDE SL LIVE"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    run_bot()
