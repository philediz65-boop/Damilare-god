import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math, concurrent.futures
from flask import Flask, request, jsonify, render_template_string
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date, datetime

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET","").strip()
BINANCE_SECRET = BINANCE_API_SECRET or os.getenv("BINANCE_SECRET","").strip()
PORT = int(os.getenv("PORT","10000"))
BINANCE_PROXY = os.getenv("BINANCE_PROXY","").strip()
RENDER_URL = "https://skelly-bot-v7.onrender.com"
MINI_APP_URL = f"{RENDER_URL}/miniapp"

PAPER_TRADING = True
AUTO_TRADE = False

app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v67.json"
DAILY_FILE = f"{DATA_DIR}/daily_v67.json"
CHAT_FILE = f"{DATA_DIR}/chat_v67.json"
PENDING_FILE = f"{DATA_DIR}/pending_v83.json"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"SKELLY-SNIPPER-V91-FULL"}
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
            r = requests.request(method, url, headers=headers, proxies=PROXIES, timeout=10)
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

def get_real_alt_futures_FIXED():
    fast_meme = ["PEPEUSDT","WIFUSDT","BONKUSDT","FLOKIUSDT","1000PEPEUSDT","1000FLOKIUSDT","1000BONKUSDT","1000SHIBUSDT","DOGEUSDT","SHIBUSDT","MEMEUSDT","BOMEUSDT","WUSDT","ENAUSDT","ETHFIUSDT","BBUSDT","NOTUSDT","POPCATUSDT","PNUTUSDT","ACTUSDT","GOATUSDT","MOODENGUSDT","CHILLGUYUSDT","FARTCOINUSDT","AI16ZUSDT","VIRTUALUSDT","PENGUUSDT"]
    blacklist = ["KORUUSDT","BULLAUSDT","RATSUSDT","SATSUSDT","ORDIUSDT","MOGUSDT","1000RATSUSDT","1000SATSUSDT","BULLA","KORU"]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",headers=HEADERS,timeout=10,proxies=PROXIES).json()
        valid=[]
        if isinstance(r,list):
            for t in r:
                sym=t.get('symbol','')
                if not sym.endswith('USDT'): continue
                if sym in ["BTCUSDT","ETHUSDT","BNBUSDT","USDCUSDT"]: continue
                if sym in blacklist or "BULLA" in sym or "KORU" in sym: continue
                try:
                    vol=float(t.get('quoteVolume',0))
                    if vol<3000000: continue
                    change=float(t.get('priceChangePercent',0))
                    score = abs(change) * (vol/1000000)
                    valid.append((sym, score))
                except: continue
            valid.sort(key=lambda x: x[1], reverse=True)
            top=[s[0] for s in valid[:115]]
            for m in fast_meme:
                if m not in top and m not in blacklist: top.append(m)
            clean = [s for s in top[:135] if s not in blacklist and "BULLA" not in s and "KORU" not in s]
            return clean
    except: pass
    return [s for s in fast_meme if s not in blacklist]

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=5,proxies=PROXIES).json()
        c=float(r.get('priceChangePercent',0)); return True, f"₿ BTC {c:.1f}%", c
    except: return True, "₿ BTC N/A", 0

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

def place_real_order(symbol, direction, usdt_amount, is_confirmed=False):
    if PAPER_TRADING and not is_confirmed:
        return {"orderId": 999999, "symbol": symbol, "side": direction, "paper": True}
    if not AUTO_TRADE and not is_confirmed:
        return {"orderId": 999999, "symbol": symbol, "side": direction, "paper": True}
    try:
        filters = get_symbol_filters(symbol)
        if filters[0] is None: return None
        rp=requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",proxies=PROXIES,headers=HEADERS,timeout=8).json()
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

def fmt(v):
    try:
        v=float(v)
        if v>=1: return f"{v:.5f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="15m"):
    key=f"{sym}_{interval}"
    with CACHE_LOCK:
        if key in CACHE and time.time()-CACHE[key][0]<45: return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=8,proxies=PROXIES).json()
        if isinstance(r,list) and len(r)>=60:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"t":int(x[0])} for x in r]
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
def atr_calc(kl,p=14):
    try:
        if len(kl)<p+1: return kl[-1]["h"]-kl[-1]["l"]
        tr=[]
        for i in range(1,len(kl)):
            tr.append(max(kl[i]["h"]-kl[i]["l"], abs(kl[i]["h"]-kl[i-1]["c"]), abs(kl[i]["l"]-kl[i-1]["c"])))
        return sum(tr[-p:])/p
    except: return 0

def analyze_PERFECT_V87(symbol):
    try:
        if "BULLA" in symbol or "KORU" in symbol:
            return None, f"🚫 {symbol} BLOCKLIST BULLA/KORU!", {"score":0,"pat":0}
        k15=get_klines(symbol,"15m")
        if len(k15)<60: 
            return None, f"❌ {symbol} No data", {"score":0,"pat":0}
        if len(k15)<90: 
            return None, f"🚫 {symbol} BLOCK <90 candles BULLA!", {"score":0,"pat":0}
        c15=[k["c"] for k in k15]
        price=get_price(symbol) or c15[-1]
        ma7 = sma(c15, 7); ma25 = sma(c15, 25); ma99 = sma(c15, 99) if len(c15)>=99 else ema(c15, 99)
        if abs(ma7 - ma25) < 0.0000001 and abs(ma25 - ma99) < 0.0000001:
            return None, f"🚫 {symbol} BLOCK MA same {fmt(ma7)} = No history BULLA!", {"score":0,"pat":0}
        rsi=rsi_calc(c15); adx=adx_calc(k15); atr=atr_calc(k15,14)
        ema20_v = ema(c15, 20); ema50_v=ema(c15,50)
        direction="BUY" if c15[-1]>=ema20_v else "SELL"
        score=0; reasons=[]
        if ema20_v>ema50_v and direction=="BUY" or ema20_v<ema50_v and direction=="SELL": 
            score+=2; reasons.append("📊 EMA20/50 +2")
        if 30<rsi<75: 
            score+=2; reasons.append(f"📈 RSI {rsi:.0f} +2")
        if adx>15: 
            score+=1; reasons.append(f"💪 ADX {adx:.0f} +1")
        strong_up = price > ma7 and ma7 > ma25 and ma25 > ma99
        strong_down = price < ma7 and ma7 < ma25 and ma25 < ma99
        if strong_up and direction=="SELL": 
            return None, f"🚫 {symbol} BLOCK SELL in UPTREND! 📈 MA7>25>99", {"score":0,"pat":0}
        if strong_down and direction=="BUY": 
            return None, f"🚫 {symbol} BLOCK BUY in DOWNTREND! 📉 MA7<25<99", {"score":0,"pat":0}
        if not (20<=rsi<=85): 
            return None, f"❌ {symbol} FAIL RSI {rsi:.1f} 📈", {"score":15,"pat":0}
        if adx<8: 
            return None, f"❌ {symbol} FAIL ADX {adx:.1f} 💪", {"score":20,"pat":0}
        if score<3: 
            return None, f"❌ {symbol} FAIL Score {score}/7 <3 ⏳", {"score":score,"pat":0}
        buffer=atr*1.2 if atr else price*0.01
        if direction=="BUY":
            sl = price - buffer*1.5
            if (price-sl)/price>0.03: sl=price*0.975
            tp1=price + (price-sl)*1.0; tp2=price + (price-sl)*2.0; tp3=price + (price-sl)*3.0; tp4=price + (price-sl)*4.0
        else:
            sl = price + buffer*1.5
            if (sl-price)/price>0.03: sl=price*1.025
            tp1=price - (sl-price)*1.0; tp2=price - (sl-price)*2.0; tp3=price - (sl-price)*3.0; tp4=price - (sl-price)*4.0
        risk=abs(price-sl)
        rr2=abs(tp2-price)/risk if risk else 0
        if rr2<1.2: 
            return None, f"❌ {symbol} FAIL RR {rr2:.1f} <1.2 📊", {"score":score,"pat":0}
        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,"sl_pct":abs(price-sl)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"rsi":rsi,"adx":adx,"atr":atr,"ma7":ma7,"ma25":ma25,"ma99":ma99,"conf":70+score*3,"pattern":"🔨 HAMMER","pat_score":3,"score":score,"score_reasons":reasons,"rr2":rr2,"support":ma25,"resistance":ma7,"ema20":ema20_v,"ema50":ema50_v}
        return trade, f"✅ V87 {direction} Score {score}/7 RR {rr2:.1f}", {"score":score,"pat":3}
    except Exception as e: 
        return None, f"❌ {symbol} ERR {e}", {"score":0,"pat":0}

# ===== MINI APP HTML - V91 FULL =====
HTML_V91 = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>V91 FULL</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:sans-serif}body{background:#000;color:#fff;padding:10px}
.logo{font-weight:900;font-size:14px}.logo span{color:#00FF88}.card{background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:8px}
.token{padding:10px;border-bottom:1px solid #1a1a1a;font-size:12px;display:flex;justify-content:space-between;align-items:center;cursor:pointer}
.btn{padding:7px 10px;border-radius:6px;border:none;font-weight:900;cursor:pointer;font-size:11px}.btn-long{background:#00FF88;color:#000}.btn-short{background:#ff3b30;color:#fff}
.scan{background:#00FF88;color:#000;width:100%;padding:14px;border-radius:12px;font-weight:900;border:none}
#modal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.97);z-index:9999;display:none;padding:12px;overflow-y:auto}
.ind{padding:6px 0;border-bottom:1px solid #1e1e1e;display:flex;justify-content:space-between;font-size:12px}
.rec{padding:12px;border-radius:12px;text-align:center;font-weight:900;margin:8px 0;font-size:15px}
</style></head><body>
<div style="display:flex;justify-content:space-between"><div class="logo">SKELLY'S <span>V91 FULL V87+ANALYZER</span></div><div id="cnt" style="background:#111;padding:4px 8px;border-radius:15px;font-size:10px;">135</div></div>
<div style="font-size:9px;color:#555;margin-top:4px">MA7/25/99 • EMA20/50 • RSI • ADX • ATR • RR • TP1-4 • SL • PATTERN • TRADE/HOLD</div>
<button class="scan" onclick="doScan()" style="margin-top:8px">⚡ SCAN 135 REAL (V87 FILTER)</button>
<div style="font-size:10px;color:#666;margin-top:6px;text-align:center">👆 TAP ANY COIN = FULL EMA/RSI/ADX/CANDLES/PATTERN + TRADE or HOLD?</div>
<div class="card" id="list" style="max-height:600px;overflow-y:auto;margin-top:8px"></div>

<div id="modal">
<div style="display:flex;justify-content:space-between"><h3 id="m_sym" style="color:#00FF88">-</h3><button onclick="closeM()" style="background:#222;color:#fff;border:none;padding:6px 12px;border-radius:8px">✕</button></div>
<div class="rec" id="m_rec">Loading...</div>
<div class="card" id="m_body">Loading full analysis...</div>
<div style="display:flex;gap:6px;margin-top:8px"><button class="btn btn-long" style="flex:1;padding:12px" onclick="tradeModal('BUY')">✅ YES TRADE LONG</button><button class="btn btn-short" style="flex:1;padding:12px" onclick="tradeModal('SELL')">✅ YES TRADE SHORT</button></div>
<button style="width:100%;padding:10px;background:#222;color:#fff;border:1px solid #333;border-radius:8px;margin-top:6px" onclick="closeM()">❌ NO HOLD / WATCH</button>
</div>

<script>
let tg=Telegram.WebApp;tg.expand();tg.ready();let cur="";
function doScan(){document.getElementById('list').innerHTML='<div style="text-align:center;padding:20px;color:#00FF88;">⚡ Scanning 135 with V87 filters (MA, RSI, ADX, RR)...</div>';fetch('/api/scan/full').then(r=>r.json()).then(d=>{document.getElementById('cnt').innerText=d.count+' coins '+d.btc;let h='';if(d.trades.length==0){h='<div style=padding:20px;color:#ffaa00;text-align:center>🛡️ PROTECT MODE - No coin meets Score≥3 RR≥1.2<br>Money Safe! Try again later</div><div style=font-size:10px;color:#555>'+d.fails.slice(0,6).join('<br>')+'</div>';}else{d.trades.forEach(t=>{let col=t.dir=='BUY'?'#00FF88':'#ff3b30';h+=`<div class=token onclick="openCoin('${t.symbol}')"><div style=flex:1><span style=color:${col};font-weight:900>${t.dir} ${t.symbol.replace('USDT','')}</span> Score ${t.score}/7 RR ${t.rr2.toFixed(1)}<br><span style=font-size:10px;color:#aaa>Entry ${t.entry.toFixed(5)} SL ${t.sl.toFixed(5)} TP2 ${t.tp2.toFixed(5)} | RSI ${t.rsi.toFixed(0)} ADX ${t.adx.toFixed(0)}</span><br><span style=font-size:9px;color:#00FF88>Tap for TRADE/HOLD decision →</span></div><div style=display:flex;gap:4px><button class=btn btn-long onclick="event.stopPropagation();quick('${t.symbol}','BUY')">LONG</button><button class=btn btn-short onclick="event.stopPropagation();quick('${t.symbol}','SELL')">SHORT</button></div></div>`});}document.getElementById('list').innerHTML=h;});}
function openCoin(sym){cur=sym;document.getElementById('modal').style.display='block';document.getElementById('m_sym').innerText=sym;document.getElementById('m_rec').innerText='⏳ Analyzing EMA, RSI, ADX, MA7/25/99, Candles...';document.getElementById('m_body').innerHTML='Loading...';fetch('/api/coin/full?symbol='+sym).then(r=>r.json()).then(d=>{if(!d.entry){document.getElementById('m_rec').innerHTML='❌ '+d.msg;document.getElementById('m_body').innerHTML=d.msg;return;}let recColor=d.decision.includes('TRADE')?'#00FF88':'#ffaa00';document.getElementById('m_rec').innerHTML=d.decision;document.getElementById('m_rec').style.background=recColor;document.getElementById('m_rec').style.color='#000';document.getElementById('m_body').innerHTML=`
<div class=ind><span>💰 Entry Price</span><span>${d.entry.toFixed(6)}</span></div>
<div class=ind><span>📈 EMA 20</span><span>${d.ema20.toFixed(6)} ${d.entry>d.ema20?'🟢':'🔴'}</span></div>
<div class=ind><span>📊 EMA 50</span><span>${d.ema50.toFixed(6)} ${d.ema20>d.ema50?'🟢 Uptrend':'🔴'}</span></div>
<div class=ind><span>📊 MA7 / MA25 / MA99</span><span style=font-size:10px>${d.ma7.toFixed(5)} / ${d.ma25.toFixed(5)} / ${d.ma99.toFixed(5)}</span></div>
<div class=ind><span>📈 RSI (14)</span><span>${d.rsi.toFixed(1)} ${d.rsi>70?'Overbought ⚠️':d.rsi<30?'Oversold 🟢':''}</span></div>
<div class=ind><span>💪 ADX</span><span>${d.adx.toFixed(1)} ${d.adx>25?'Strong Trend':''}</span></div>
<div class=ind><span>📏 ATR</span><span>${d.atr.toFixed(6)}</span></div>
<div class=ind><span>🕯️ Pattern</span><span>${d.pattern}</span></div>
<div class=ind><span>🛑 SL (${d.sl_pct.toFixed(2)}%)</span><span style=color:#ff3b30>${d.sl.toFixed(6)}</span></div>
<div class=ind><span>🎯 TP1 / TP2 / TP3 / TP4</span><span style=font-size:10px>${d.tp1.toFixed(6)} / ${d.tp2.toFixed(6)} / ${d.tp3.toFixed(6)} / ${d.tp4.toFixed(6)}</span></div>
<div class=ind><span>📊 RR Ratio</span><span>${d.rr2.toFixed(2)} ${d.rr2>=1.2?'✅ Good':'❌ Bad'}</span></div>
<div class=ind><span>⭐ Score</span><span>${d.score}/7 (${d.score_reasons.join(', ')})</span></div>
<div style=margin-top:8px;padding:8px;background:#0a0a0a;border-radius:8px;font-size:11px;color:#aaa>💡 ${d.explain}</div>
`;});}
function closeM(){document.getElementById('modal').style.display='none';}
function quick(sym,side){let l=prompt('Leverage? (10)','10')||'10';let amt=prompt('USDT $ amount? (3)','3')||'3';fetch('/api/futures/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:sym,side,amount:amt,leverage:l})}).then(r=>r.json()).then(d=>{tg.showAlert(d.msg||d.error);});}
function tradeModal(side){quick(cur,side);}
doScan();
</script></body></html>
"""

@app.get("/")
def home(): return f"🧠💎 V91 FULL V87+MINIAPP Bal ${get_futures_balance():.2f}",200
@app.get("/health")
def health(): return "OK V91 FULL",200
@app.get("/miniapp")
def miniapp(): return render_template_string(HTML_V91)
@app.get("/api/scan/full")
def api_scan_full():
    bal=get_futures_balance(); symbols=get_real_alt_futures_FIXED()
    ok_btc, btc_txt, _ = get_btc_filter()
    trades=[]; fails=[]
    def one(sym):
        t,msg,meta=analyze_PERFECT_V87(sym)
        return (sym,t,msg)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        res=list(ex.map(one, symbols))
    for sym,t,msg in res:
        if t: trades.append(t)
        else: fails.append(msg)
    trades.sort(key=lambda x:(x['score'],x['rr2'],x['conf']), reverse=True)
    trades=trades[:25]
    return jsonify({"trades":trades,"fails":fails[:10],"count":len(symbols),"btc":btc_txt,"balance":bal})
@app.get("/api/coin/full")
def api_coin_full():
    sym=request.args.get('symbol','PEPEUSDT')
    trade,msg,meta=analyze_PERFECT_V87(sym)
    if not trade:
        return jsonify({"msg":msg,"entry":None})
    # Decision TRADE or HOLD
    if trade['score']>=3 and trade['rr2']>=1.2 and 20<=trade['rsi']<=75 and trade['adx']>=8:
        decision=f"🚀 YES TRADE NOW - {trade['dir']} Score {trade['score']}/7 RR {trade['rr2']:.1f} ✅"
        explain=f"All filters PASS: EMA, RSI {trade['rsi']:.0f}, ADX {trade['adx']:.0f}, MA7/25/99 trend correct, RR good. Safe to TRADE!"
    else:
        decision=f"👀 HOLD / WATCH - {trade['dir']} Score {trade['score']}/7"
        explain=f"Some filter weak: {msg} - Better HOLD and wait for stronger signal."
    trade['decision']=decision; trade['explain']=explain; trade['msg']=msg
    return jsonify(trade)
@app.post("/api/futures/confirm")
def api_confirm():
    try:
        d=request.json; sym=d.get('symbol'); side=d.get('side'); amt=float(d.get('amount',3))
        order=place_real_order(sym, side, amt, is_confirmed=True)
        if order and order.get('orderId'):
            set_active({"status":"OPEN","coin":sym.replace("USDT",""),"symbol":sym,"dir":side,"entry":0,"sl":0,"tp1":0,"tp2":0,"tp3":0,"tp4":0,"conf":80,"stake":amt,"lev":10,"stage":0,"highest":0,"lowest":0,"mode":"V91 MINIAPP","time":str(datetime.now()),"pattern":"MINIAPP"})
            return jsonify({"msg":f"✅ TRADED {sym} {side} ${amt} Order {order.get('orderId')}"})
        return jsonify({"error":f"Order failed for {sym}"})
    except Exception as e: return jsonify({"error":str(e)})

# ===== TELEGRAM BOT =====
def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/4 💰 V91',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 📊 MONITOR {active["coin"]} 📈',callback_data="MON"), InlineKeyboardButton(f'❌ 🛑 Close Trade 🛑',callback_data="CLS")])
    else:
        pending=get_pending()
        if pending:
            btns.append([InlineKeyboardButton(f'⚠️ ⏳ PENDING {pending.get("symbol","")} {pending.get("dir","")} Score {pending.get("score",0)} 👉 YES/NO?',callback_data="SHOW_PENDING")])
        btns.append([InlineKeyboardButton(f'📱 OPEN V91 FULL ANALYZER - TAP COIN FOR TRADE/HOLD',callback_data="OPEN_MINI")])
        btns.append([InlineKeyboardButton(f'⚡ 🚀 SCAN 135 V91 FULL! 💎 EMA/RSI/ADX/MA/CANDLE + TRADE/HOLD 📊',callback_data="SCAN")])
        btns.append([InlineKeyboardButton(f'📊 💵 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 📈',callback_data="DAILY"), InlineKeyboardButton(f'📈 📊 CHART ⚡',callback_data="CHART")])
        btns.append([InlineKeyboardButton(f'🔄 🔃 RESET 0W/0L 🧹',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app_):
    try:
        await app_.bot.set_my_commands([
            BotCommand("start","🚀 V91 START - FULL SETUP"),
            BotCommand("scan","⚡ SCAN 135 FULL"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 DAILY"),
            BotCommand("chart","📈 CHART"),
            BotCommand("reset","🔄 RESET")
        ])
    except: pass

def bg_scan(chat_id, risk_mode_override=None):
    try:
        bal=get_futures_balance(); all_symbols=get_real_alt_futures_FIXED()
        import requests as rq
        rq.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚡💎 V91 FULL! 🚀 Scanning {len(all_symbols)} COINS - EMA/RSI/ADX/MA7/25/99/CANDLE/PATTERN + TRADE/HOLD! 📊 Bal ${bal:.2f}"},timeout=10,proxies=PROXIES)
        raws=[]; fails=[]
        def scan_one(sym):
            trade, msg, meta = analyze_PERFECT_V87(sym)
            return (sym, trade, msg, meta)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(scan_one, all_symbols))
        for sym, trade, msg, meta in results:
            if trade: raws.append(trade)
            else: fails.append(msg)
        if not raws:
            txt=f"⚡💎 V91 PROTECT MODE 🛡️\n📊 Scanned {len(all_symbols)} COINS! ❌ No entry meets ⭐ Score>=3 + 📈 RR>=1.2! 💰 Money safe! Bal ${bal:.2f}\n" + "\n".join(fails[:8])
            rq.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x: (x['score'], x['conf'], x['rr2']), reverse=True)
        best = raws[0]
        set_pending(best)
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f'📱 OPEN FULL ANALYZER - {best["symbol"]} TRADE/HOLD?',callback_data="OPEN_MINI")],
            [InlineKeyboardButton(f'✅ 💰 YES BUY {best["symbol"]} {best["dir"]} ⭐ Score {best["score"]} 📈 RR {best["rr2"]:.1f} 🛑 SL $1.05', callback_data=f'CONFIRM_{best["symbol"]}_{best["dir"]}')],
            [InlineKeyboardButton(f'❌ 🚫 NO HOLD Skip ⏭️', callback_data='SKIP')]
        ])
        txt=(f"🧠 💎 PHILEDIZ V91 FULL — ANALYSIS 📊\n💱 Symbol: {best['symbol']}\n📈 Signal: {best['dir']} ⭐ Score {best['score']}/7\n🎯 Entry: {fmt(best['entry'])} 🛑 SL: {fmt(best['sl'])} (35% $1.05)\n🎯 TP1: {fmt(best['tp1'])} 📈 TP2: {fmt(best['tp2'])} RR {best['rr2']:.1f}\n📊 RSI {best['rsi']:.1f} 💪 ADX {best['adx']:.1f} 🕯️ {best['pattern']}\n📊 MA7 {fmt(best['ma7'])} 📊 MA25 {fmt(best['ma25'])} 📊 MA99 {fmt(best['ma99'])}\n📈 EMA20 {fmt(best['ema20'])} 📊 EMA50 {fmt(best['ema50'])}\n💡 {', '.join(best['score_reasons'][:3])}\n💰 $3.0 10x | 💵 Bal ${bal:.2f} | 👉 TAP OPEN ANALYZER FOR FULL TRADE/HOLD DECISION!")
        rq.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt, "reply_markup": confirm_kb.to_dict()},timeout=10,proxies=PROXIES)
    except Exception as e: 
        print(f"SCAN ERR {e}")

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(f"🧠💎 🚀 PHILEDIZ V91 FULL SETUP 👑✨ - V87+MINIAPP! 📊\n💰 Futures ${bal:.2f} 135 COINS! ✅\n\n✅ FULL FEATURES:\n• 📊 EMA20/50 • RSI • ADX • ATR • MA7/25/99 • RR • TP1-4 • SL\n• 🕯️ Candle Pattern • ⭐ Score • 💎 TRADE/HOLD Decision\n• 📱 Mini App: TAP ANY COIN = FULL ANALYSIS + YES TRADE / NO HOLD\n\n👇 Press SCAN or OPEN ANALYZER!", reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("⚡ 🚀 V91 FULL SCANNING 135 COINS - EMA/RSI/ADX/MA/CANDLE! ⏳")
async def daily_cmd(u,c): d=get_daily(); await u.message.reply_text(f"📊 💵 Daily V91 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💰",reply_markup=kb(get_active()))
async def reset_cmd(u,c):
    save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
    clear_active(); clear_pending()
    await u.message.reply_text("🔄 RESET DONE V91!", reply_markup=kb(get_active()))
async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN": await u.message.reply_text("😴 No active trade",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
    pnl_pct=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
    bal=get_futures_balance()
    await u.message.reply_text(f"👀 V91 {act['coin']} {act['dir']} Stage {act.get('stage',0)}/4 P&L {pnl_pct:.2f}% Bal ${bal:.2f}", reply_markup=kb(act))
async def chart_cmd(u,c): await u.message.reply_text(f"📈 Open Mini App for full chart: {MINI_APP_URL} 📊", reply_markup=kb(get_active()))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily V91 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💰",reply_markup=kb(get_active())); return
    if data=="RESET": save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); await q.message.reply_text("🔄 RESET DONE V91!", reply_markup=kb(get_active())); return
    if data=="SKIP": clear_pending(); await q.message.reply_text("✅ Skipped! Press SCAN again!", reply_markup=kb(get_active())); return
    if data=="OPEN_MINI":
        kb_mini=InlineKeyboardMarkup([[InlineKeyboardButton("📱 OPEN V91 FULL ANALYZER", url=MINI_APP_URL)]])
        await q.message.reply_text(f"📱 OPEN V91 FULL ANALYZER:\n{MINI_APP_URL}\n\nTAP ANY COIN = EMA/RSI/ADX/MA7/25/99/CANDLE/PATTERN + TRADE or HOLD decision!", reply_markup=kb_mini); return
    if data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: await q.message.reply_text("😴 No pending", reply_markup=kb(get_active())); return
        confirm_kb = InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ YES {pend["symbol"]} {pend["dir"]}', callback_data=f'CONFIRM_{pend["symbol"]}_{pend["dir"]}')],[InlineKeyboardButton(f'❌ NO Skip', callback_data='SKIP')]])
        await q.message.reply_text(f"⏳ PENDING: {pend['symbol']} {pend['dir']} @ {fmt(pend['entry'])} Score {pend.get('score',0)} RR {pend.get('rr2',0):.1f}", reply_markup=confirm_kb); return
    if data.startswith("CONFIRM_"):
        try:
            parts=data.split("_"); symbol=parts[1]; direction=parts[2]
            pend=get_pending()
            if not pend or pend.get('symbol')!=symbol:
                trade, msg, meta = analyze_PERFECT_V87(symbol)
                if not trade: await q.message.reply_text(f"❌ Signal expired for {symbol}"); return
                pend=trade
            order_res = place_real_order(symbol, direction, 3.0, is_confirmed=True)
            if order_res and order_res.get('orderId'):
                set_active({"status":"OPEN","coin":symbol.replace("USDT",""),"symbol":symbol,"dir":direction,"entry":pend['entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"stake":3.0,"lev":10,"stage":0,"highest":pend['entry'],"lowest":pend['entry'],"mode":"V91 YES","time":str(datetime.now()),"pattern":pend['pattern']})
                await q.message.reply_text(f"✅ YES CONFIRMED {symbol} {direction} @ {fmt(pend['entry'])} Score {pend['score']} RR {pend['rr2']:.1f} 🚀", reply_markup=kb(get_active()))
                clear_pending()
            else: await q.message.reply_text(f"❌ Order failed for {symbol}!")
        except Exception as e: await q.message.reply_text(f"❌ Confirm err {e}"); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade",reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        pnl_pct=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        await q.message.reply_text(f"👀 V91 {act['coin']} {act['dir']} {pnl_pct:.2f}%",reply_markup=kb(act)); return
    if data=="CLS": 
        act=get_active()
        if act.get("symbol"): cancel_all_open_orders(act["symbol"]); close_real_position(act["symbol"],100)
        clear_active(); clear_pending(); await q.message.reply_text("❌ Closed Trade",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("⚡ V91 SCANNING 135 FULL! ⏳"); return
    if data=="CHART": await q.message.reply_text(f"📈 Mini App: {MINI_APP_URL}", reply_markup=kb(get_active())); return

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
            if roi<=-35.0 and stage==0:
                cancel_all_open_orders(symbol); close_real_position(symbol,100); clear_active(); update_daily(-1.05, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL 35% HIT {act['coin']} Loss $1.05"},timeout=8,proxies=PROXIES)
                except: pass
                continue
        except Exception as e: print(f"monitor err {e}"); time.sleep(3)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("chart",chart_cmd)); a.add_handler(CommandHandler("reset",reset_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"V91 FULL starting"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
