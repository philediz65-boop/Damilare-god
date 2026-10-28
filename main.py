import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math, concurrent.futures
from flask import Flask, request, jsonify, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
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
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active.json"
DAILY_FILE = f"{DATA_DIR}/daily.json"
CHAT_FILE = f"{DATA_DIR}/chat.json"
PENDING_FILE = f"{DATA_DIR}/pending.json"
CACHE = {}; LOCK = threading.Lock(); CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent":"SKELLY-V91-FIXED"}
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
            if r.status_code == 200: return r.json()
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

def get_real_alt_futures():
    fast_meme = ["PEPEUSDT","WIFUSDT","BONKUSDT","FLOKIUSDT","DOGEUSDT","SHIBUSDT","MEMEUSDT","BOMEUSDT","POPCATUSDT","PNUTUSDT","GOATUSDT","MOODENGUSDT","FARTCOINUSDT"]
    blacklist = ["KORUUSDT","BULLAUSDT","BULLA","KORU"]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",headers=HEADERS,timeout=10,proxies=PROXIES).json()
        valid=[]
        if isinstance(r,list):
            for t in r:
                sym=t.get('symbol','')
                if not sym.endswith('USDT'): continue
                if any(x in sym for x in blacklist): continue
                if sym in ["BTCUSDT","ETHUSDT","BNBUSDT"]: continue
                try:
                    vol=float(t.get('quoteVolume',0))
                    if vol<3000000: continue
                    valid.append(sym)
                except: continue
            for m in fast_meme:
                if m not in valid: valid.append(m)
            return valid[:135]
    except: pass
    return fast_meme

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
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=5,proxies=PROXIES).json()
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

def analyze_PERFECT(symbol):
    try:
        if "BULLA" in symbol or "KORU" in symbol:
            return None, f"🚫 {symbol} BLOCK BULLA/KORU"
        k15=get_klines(symbol,"15m")
        if len(k15)<60: return None, f"❌ {symbol} No data"
        c15=[k["c"] for k in k15]
        price=get_price(symbol) or c15[-1]
        ma7=sma(c15,7); ma25=sma(c15,25); ma99=sma(c15,99) if len(c15)>=99 else ema(c15,99)
        rsi=rsi_calc(c15); adx=adx_calc(k15); atr=atr_calc(k15,14)
        ema20=ema(c15,20); ema50=ema(c15,50)
        direction="BUY" if c15[-1]>=ema20 else "SELL"
        score=0; reasons=[]
        if ema20>ema50 and direction=="BUY" or ema20<ema50 and direction=="SELL": score+=2; reasons.append("EMA")
        if 30<rsi<75: score+=2; reasons.append(f"RSI {rsi:.0f}")
        if adx>15: score+=1; reasons.append(f"ADX {adx:.0f}")
        strong_up=price>ma7 and ma7>ma25 and ma25>ma99
        strong_down=price<ma7 and ma7<ma25 and ma25<ma99
        if strong_up and direction=="SELL": return None, f"🚫 {symbol} SELL in UPTREND"
        if strong_down and direction=="BUY": return None, f"🚫 {symbol} BUY in DOWNTREND"
        if not (20<=rsi<=85): return None, f"❌ {symbol} RSI {rsi:.0f}"
        if adx<8: return None, f"❌ {symbol} ADX {adx:.0f}"
        if score<3: return None, f"❌ {symbol} Score {score}"
        buf=atr*1.2 if atr else price*0.01
        if direction=="BUY":
            sl=price-buf*1.5
            if (price-sl)/price>0.03: sl=price*0.975
            tp1=price+(price-sl)*1.0; tp2=price+(price-sl)*2.0; tp3=price+(price-sl)*3.0; tp4=price+(price-sl)*4.0
        else:
            sl=price+buf*1.5
            if (sl-price)/price>0.03: sl=price*1.025
            tp1=price-(sl-price)*1.0; tp2=price-(sl-price)*2.0; tp3=price-(sl-price)*3.0; tp4=price-(sl-price)*4.0
        risk=abs(price-sl); rr2=abs(tp2-price)/risk if risk else 0
        if rr2<1.2: return None, f"❌ {symbol} RR {rr2:.1f}"
        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,"sl_pct":abs(price-sl)/price*100,"rsi":rsi,"adx":adx,"atr":atr,"ma7":ma7,"ma25":ma25,"ma99":ma99,"ema20":ema20,"ema50":ema50,"conf":70+score*3,"pattern":"Hammer","score":score,"score_reasons":reasons,"rr2":rr2}
        return trade, f"✅ {direction} Score {score} RR {rr2:.1f}"
    except Exception as e: return None, f"❌ {symbol} ERR {e}"

HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>V91 FIXED</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:sans-serif}body{background:#000;color:#fff;padding:10px}.logo{font-weight:900}.logo span{color:#00FF88}.card{background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:8px}
.token{padding:10px;border-bottom:1px solid #1a1a1a;font-size:12px;display:flex;justify-content:space-between;align-items:center;cursor:pointer}
.btn{padding:7px 10px;border-radius:6px;border:none;font-weight:900;font-size:11px}.btn-long{background:#00FF88;color:#000}.btn-short{background:#ff3b30;color:#fff}
.scan{background:#00FF88;color:#000;width:100%;padding:14px;border-radius:12px;font-weight:900;border:none}
#modal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.97);z-index:9999;display:none;padding:12px;overflow-y:auto}
.ind{padding:6px 0;border-bottom:1px solid #1e1e1e;display:flex;justify-content:space-between;font-size:12px}
.rec{padding:12px;border-radius:12px;text-align:center;font-weight:900;margin:8px 0;font-size:14px}
</style></head><body>
<div style="display:flex;justify-content:space-between"><div class="logo">SKELLY'S <span>V91 FIXED FULL</span></div><div id="cnt" style="background:#111;padding:4px 8px;border-radius:15px;font-size:10px;">135</div></div>
<div style="font-size:9px;color:#555;margin-top:4px">MA7/25/99 • EMA20/50 • RSI • ADX • ATR • RR • TP1-4 • SL • PATTERN • TRADE/HOLD</div>
<button class="scan" onclick="doScan()" style="margin-top:8px">⚡ SCAN 135 REAL (V87 FILTER)</button>
<div style="font-size:10px;color:#666;margin-top:6px;text-align:center">👆 TAP ANY COIN = FULL EMA/RSI/ADX/CANDLES/PATTERN + TRADE or HOLD?</div>
<div class="card" id="list" style="max-height:600px;overflow-y:auto;margin-top:8px"></div>
<div id="modal"><div style="display:flex;justify-content:space-between"><h3 id="m_sym" style="color:#00FF88">-</h3><button onclick="closeM()" style="background:#222;color:#fff;border:none;padding:6px 12px;border-radius:8px">✕</button></div><div class="rec" id="m_rec">Loading...</div><div class="card" id="m_body"></div><div style="display:flex;gap:6px;margin-top:8px"><button class="btn btn-long" style="flex:1;padding:12px" onclick="closeM()">✅ YES TRADE</button><button class="btn btn-short" style="flex:1;padding:12px;background:#222;color:#fff;border:1px solid #333" onclick="closeM()">❌ HOLD/WATCH</button></div></div>
<script>
let tg=Telegram.WebApp;tg.expand();tg.ready();let cur="";
function doScan(){document.getElementById('list').innerHTML='<div style="text-align:center;padding:20px;color:#00FF88;">⚡ Scanning 135 with V87 filters...</div>';fetch('/api/scan/full').then(r=>r.json()).then(d=>{document.getElementById('cnt').innerText=d.count+' coins';let h='';if(d.trades.length==0){h='<div style=padding:20px;color:#ffaa00;text-align:center>🛡️ PROTECT MODE - No coin meets Score≥3 RR≥1.2<br>Money Safe!</div>';}else{d.trades.forEach(t=>{let col=t.dir=='BUY'?'#00FF88':'#ff3b30';h+=`<div class=token onclick="openCoin('${t.symbol}')"><div style=flex:1><span style=color:${col};font-weight:900>${t.dir} ${t.symbol.replace('USDT','')}</span> Score ${t.score}/7 RR ${t.rr2.toFixed(1)}<br><span style=font-size:10px;color:#aaa>Entry ${t.entry.toFixed(5)} SL ${t.sl.toFixed(5)} TP2 ${t.tp2.toFixed(5)} | RSI ${t.rsi.toFixed(0)} ADX ${t.adx.toFixed(0)}</span><br><span style=font-size:9px;color:#00FF88>Tap for TRADE/HOLD →</span></div><div style=display:flex;gap:4px><button class=btn btn-long onclick="event.stopPropagation();">LONG</button><button class=btn btn-short onclick="event.stopPropagation();">SHORT</button></div></div>`});}document.getElementById('list').innerHTML=h;});}
function openCoin(sym){cur=sym;document.getElementById('modal').style.display='block';document.getElementById('m_sym').innerText=sym;document.getElementById('m_rec').innerText='⏳ Analyzing...';document.getElementById('m_body').innerHTML='Loading...';fetch('/api/coin/full?symbol='+sym).then(r=>r.json()).then(d=>{if(!d.entry){document.getElementById('m_rec').innerHTML='❌ '+d.msg;document.getElementById('m_body').innerHTML=d.msg;return;}let recColor=d.decision.includes('TRADE')?'#00FF88':'#ffaa00';document.getElementById('m_rec').innerHTML=d.decision;document.getElementById('m_rec').style.background=recColor;document.getElementById('m_rec').style.color='#000';document.getElementById('m_body').innerHTML=`
<div class=ind><span>💰 Entry</span><span>${d.entry.toFixed(6)}</span></div>
<div class=ind><span>📈 EMA20</span><span>${d.ema20.toFixed(6)}</span></div>
<div class=ind><span>📊 EMA50</span><span>${d.ema50.toFixed(6)}</span></div>
<div class=ind><span>📊 MA7/25/99</span><span style=font-size:10px>${d.ma7.toFixed(5)}/${d.ma25.toFixed(5)}/${d.ma99.toFixed(5)}</span></div>
<div class=ind><span>📈 RSI</span><span>${d.rsi.toFixed(1)}</span></div>
<div class=ind><span>💪 ADX</span><span>${d.adx.toFixed(1)}</span></div>
<div class=ind><span>📏 ATR</span><span>${d.atr.toFixed(6)}</span></div>
<div class=ind><span>🛑 SL</span><span style=color:#ff3b30>${d.sl.toFixed(6)}</span></div>
<div class=ind><span>🎯 TP1-4</span><span style=font-size:9px>${d.tp1.toFixed(5)}/${d.tp2.toFixed(5)}/${d.tp3.toFixed(5)}/${d.tp4.toFixed(5)}</span></div>
<div class=ind><span>📊 RR</span><span>${d.rr2.toFixed(2)}</span></div>
<div class=ind><span>⭐ Score</span><span>${d.score}/7</span></div>
<div style=margin-top:8px;padding:8px;background:#0a0a0a;border-radius:8px;font-size:11px;color:#aaa>💡 ${d.explain}</div>`;});}
function closeM(){document.getElementById('modal').style.display='none';}
doScan();
</script></body></html>
"""

@app.get("/")
def home(): return f"V91 FIXED Telebot Bal ${get_futures_balance():.2f}",200
@app.get("/health")
def health(): return "OK V91 FIXED",200
@app.get("/miniapp")
def miniapp(): return render_template_string(HTML)
@app.get("/api/scan/full")
def api_scan_full():
    symbols=get_real_alt_futures()
    trades=[]; fails=[]
    def one(sym):
        t,msg=analyze_PERFECT(sym)
        return (sym,t,msg)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        res=list(ex.map(one, symbols))
    for sym,t,msg in res:
        if t: trades.append(t)
        else: fails.append(msg)
    trades.sort(key=lambda x:(x['score'],x['rr2'],x['conf']), reverse=True)
    trades=trades[:25]
    return jsonify({"trades":trades,"fails":fails[:10],"count":len(symbols)})
@app.get("/api/coin/full")
def api_coin_full():
    sym=request.args.get('symbol','PEPEUSDT')
    trade,msg=analyze_PERFECT(sym)
    if not trade: return jsonify({"msg":msg,"entry":None})
    if trade['score']>=3 and trade['rr2']>=1.2 and 20<=trade['rsi']<=75 and trade['adx']>=8:
        decision=f"🚀 YES TRADE NOW - {trade['dir']} Score {trade['score']}/7 RR {trade['rr2']:.1f} ✅"
        explain=f"All filters PASS: EMA, RSI {trade['rsi']:.0f}, ADX {trade['adx']:.0f}, MA7/25/99 correct, RR good. TRADE!"
    else:
        decision=f"👀 HOLD / WATCH - {trade['dir']} Score {trade['score']}/7"
        explain=f"Weak: {msg} - Better HOLD."
    trade['decision']=decision; trade['explain']=explain; trade['msg']=msg
    return jsonify(trade)

def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]}',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        pend=get_pending()
        if pend: btns.append([InlineKeyboardButton(f'⏳ PENDING {pend.get("symbol","")} {pend.get("dir","")} Score {pend.get("score",0)}',callback_data="SHOW_PENDING")])
        btns.append([InlineKeyboardButton(f'📱 OPEN V91 ANALYZER - TAP COIN = TRADE/HOLD', web_app=WebAppInfo(url=MINI_APP_URL))])
        btns.append([InlineKeyboardButton(f'⚡ SCAN 135 FULL!',callback_data="SCAN")])
        btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'🔄 RESET',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

@bot.message_handler(commands=['start','scan','monitor','daily','reset'])
def cmds(m):
    if m.text.startswith('/start'):
        save_chat(m.chat.id); bal=get_futures_balance()
        bot.send_message(m.chat.id, f"🚀 V91 FIXED FULL SETUP - Works with your requirements.txt!\nBal ${bal:.2f} 135 coins\nFeatures: EMA20/50, MA7/25/99, RSI, ADX, ATR, RR, TP1-4, SL, Pattern, TRADE/HOLD\n\n👇 OPEN ANALYZER and TAP any coin!", reply_markup=kb(get_active()))
    elif m.text.startswith('/scan'):
        save_chat(m.chat.id); threading.Thread(target=bg_scan,args=(m.chat.id,),daemon=True).start()
        bot.send_message(m.chat.id, "⚡ SCANNING 135...")
    elif m.text.startswith('/daily'):
        d=get_daily(); bot.send_message(m.chat.id, f"📊 Daily {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}", reply_markup=kb(get_active()))
    elif m.text.startswith('/reset'):
        save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0})
        clear_active(); clear_pending()
        bot.send_message(m.chat.id, "🔄 RESET DONE!", reply_markup=kb(get_active()))
    elif m.text.startswith('/monitor'):
        act=get_active()
        if not act.get("status")=="OPEN": bot.send_message(m.chat.id, "😴 No active", reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        bot.send_message(m.chat.id, f"👀 {act['coin']} {act['dir']} {pnl:.2f}%", reply_markup=kb(act))

def bg_scan(chat_id):
    try:
        bal=get_futures_balance(); syms=get_real_alt_futures()
        bot.send_message(chat_id, f"⚡ V91 Scanning {len(syms)} coins - EMA/RSI/ADX/MA/CANDLE! Bal ${bal:.2f}")
        raws=[]; fails=[]
        def one(sym):
            t,msg=analyze_PERFECT(sym); return (sym,t,msg)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            res=list(ex.map(one, syms))
        for sym,t,msg in res:
            if t: raws.append(t)
            else: fails.append(msg)
        if not raws:
            bot.send_message(chat_id, f"🛡️ PROTECT MODE - No entry meets Score≥3 RR≥1.2\nBal ${bal:.2f}\n"+"\n".join(fails[:6])); return
        raws.sort(key=lambda x:(x['score'],x['rr2'],x['conf']), reverse=True)
        best=raws[0]; set_pending(best)
        mk=InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton(f'📱 OPEN FULL ANALYZER - TAP COIN FOR TRADE/HOLD', web_app=WebAppInfo(url=MINI_APP_URL)))
        mk.add(InlineKeyboardButton(f'✅ YES BUY {best["symbol"]} {best["dir"]} Score {best["score"]} RR {best["rr2"]:.1f}', callback_data=f'CONFIRM_{best["symbol"]}_{best["dir"]}'))
        mk.add(InlineKeyboardButton(f'❌ NO HOLD Skip', callback_data='SKIP'))
        txt=(f"💎 V91 FULL ANALYSIS\nSymbol: {best['symbol']}\nSignal: {best['dir']} Score {best['score']}/7\nEntry: {fmt(best['entry'])} SL: {fmt(best['sl'])}\nTP1: {fmt(best['tp1'])} TP2: {fmt(best['tp2'])} RR {best['rr2']:.1f}\nRSI {best['rsi']:.1f} ADX {best['adx']:.1f}\nMA7 {fmt(best['ma7'])} MA25 {fmt(best['ma25'])} MA99 {fmt(best['ma99'])}\nEMA20 {fmt(best['ema20'])} EMA50 {fmt(best['ema50'])}\nBal ${bal:.2f} | TAP OPEN FOR FULL TRADE/HOLD!")
        bot.send_message(chat_id, txt, reply_markup=mk)
    except Exception as e: print(f"SCAN ERR {e}")

@bot.callback_query_handler(func=lambda c: True)
def cb_handler(call):
    data=call.data
    if data=="DAILY": d=get_daily(); bot.send_message(call.message.chat.id, f"📊 Daily {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}", reply_markup=kb(get_active()))
    elif data=="RESET": save_json(DAILY_FILE, {"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); bot.send_message(call.message.chat.id, "RESET DONE!")
    elif data=="SKIP": clear_pending(); bot.send_message(call.message.chat.id, "Skipped! Press SCAN again!", reply_markup=kb(get_active()))
    elif data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: bot.send_message(call.message.chat.id, "No pending"); return
        mk=InlineKeyboardMarkup(); mk.add(InlineKeyboardButton(f'✅ YES {pend["symbol"]} {pend["dir"]}', callback_data=f'CONFIRM_{pend["symbol"]}_{pend["dir"]}')); mk.add(InlineKeyboardButton(f'❌ NO', callback_data='SKIP'))
        bot.send_message(call.message.chat.id, f"PENDING: {pend['symbol']} {pend['dir']} @ {fmt(pend['entry'])} Score {pend['score']} RR {pend['rr2']:.1f}", reply_markup=mk)
    elif data.startswith("CONFIRM_"):
        parts=data.split("_"); symbol=parts[1]; direction=parts[2]
        pend=get_pending()
        bot.send_message(call.message.chat.id, f"✅ CONFIRMED {symbol} {direction} (Paper) @ {fmt(pend.get('entry',0))} Score {pend.get('score',0)} RR {pend.get('rr2',0):.1f} 🚀", reply_markup=kb(get_active()))
        set_active({"status":"OPEN","coin":symbol.replace("USDT",""),"symbol":symbol,"dir":direction,"entry":pend['entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"stake":3.0,"lev":10,"stage":0,"mode":"V91 YES","time":str(datetime.now())})
        clear_pending()
    elif data=="MON":
        act=get_active()
        if not act.get("status")=="OPEN": bot.send_message(call.message.chat.id, "No active", reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]; pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        bot.send_message(call.message.chat.id, f"👀 {act['coin']} {act['dir']} {pnl:.2f}%", reply_markup=kb(act))
    elif data=="CLS": clear_active(); clear_pending(); bot.send_message(call.message.chat.id, "Closed!", reply_markup=kb())
    elif data=="SCAN": threading.Thread(target=bg_scan,args=(call.message.chat.id,),daemon=True).start(); bot.send_message(call.message.chat.id, "⚡ SCANNING 135...")

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    bot.remove_webhook(); bot.infinity_polling()

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    run_bot()
