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
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return None
    try:
        params['timestamp'] = int(time.time()*1000)
        params['recvWindow'] = 10000
        query = urllib.parse.urlencode(params)
        signature = hmac.new(BINANCE_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com{endpoint}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        r = requests.request(method, url, headers=headers, proxies=PROXIES, timeout=20)
        data = r.json()
        if r.status_code != 200:
            print(f"Binance Error {endpoint}: {data}")
        return data
    except Exception as e:
        print(f"Signed req fail {endpoint}: {e}")
        return None

def get_futures_balance():
    data = binance_signed_request("GET", "/fapi/v2/balance")
    if isinstance(data, list):
        for b in data:
            if b.get('asset') == 'USDT':
                return float(b.get('balance',0))
    return 8.0

def get_trade_amount():
    # 🧠 AUTO-COMPOUND LOGIC 💰
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
                    qty = round(qty, int(s['quantityPrecision']))
                    break
        except: qty = round(qty, 3)
        setup_symbol(symbol)
        order = binance_signed_request("POST", "/fapi/v1/order", {"symbol": symbol, "side": "BUY" if direction=="BUY" else "SELL", "type": "MARKET", "quantity": qty})
        if order and order.get('orderId'):
            return order
        return None
    except Exception as e:
        print(f"ORDER FAIL: {e}")
        return None

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
                            close_qty = round(close_qty, int(s['quantityPrecision']))
                            break
                except: close_qty = round(close_qty, 3)
                res = binance_signed_request("POST", "/fapi/v1/order", {"symbol": symbol, "side": side, "type": "MARKET", "quantity": close_qty, "reduceOnly": "true"})
                print(f"CLOSED {qty_percent}% {symbol}")
                return res
    except Exception as e:
        print(f"Close fail: {e}")
    return None

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
    bal = get_futures_balance()
    amt = get_trade_amount()
    return f"🚀 V43 EMOJI TRAILING+COMPOUND 💰 Bal ${bal:.2f} Trade ${amt} LIVE",200
@app.get("/health")
def health(): return "OK ✅",200

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
    if key in CACHE and time.time()-CACHE[key][0]<50:
        return CACHE[key][1]
    kl=None
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7, proxies=PROXIES).json()
        if isinstance(r,list) and len(r)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
    except: pass
    if kl:
        CACHE[key]=(time.time(),kl)
        return kl
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=5, proxies=PROXIES).json()
        if "price" in r: return float(r["price"])
    except: pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

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

def analyze_single(code):
    try:
        sym=CRYPTO[code]; k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<40: k2=k1 if len(k1)>=40 else k15
        if len(k2)<40: return None
        c2=[k["c"] for k in k2]; price=get_price(sym) or c2[-1]
        rsi_v=rsi_calc(c2); atr_v=atr_calc(k2); adx_v=adx_calc(k2); pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2; c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15); s1,t1=trend_calc(c1); s2,t2=trend_calc(c2)
        vol_pct,vol_txt=vol_calc(k2)
        align=3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"; volatility=atr_v/price*100 if price else 0
        return {"code":code,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"align":align,"dir":direction,"kl":k2,"closes":c2}
    except: return None

def ai_score_perfect(r, market_adx):
    score=0
    if r["dir"]=="BUY":
        if r["pd_pct"]<=28: score+=20
        elif r["pd_pct"]<=40: score+=14
        elif r["pd_pct"]<=50: score+=7
        else: score-=10
    else:
        if r["pd_pct"]>=72: score+=20
        elif r["pd_pct"]>=60: score+=14
        elif r["pd_pct"]>=50: score+=7
        else: score-=10
    if 44<=r["rsi"]<=56: score+=15
    elif 40<=r["rsi"]<=60: score+=10
    else: score-=5
    if 18<=r["adx"]<=50: score+=15
    elif r["adx"]>=14: score+=9
    else: score-=5
    if r["volatility"]>=1.3: score+=10
    if r["vol_pct"]>=5: score+=6
    if r["align"]==3: score+=10
    elif r["align"]==2: score+=4
    else: score-=3
    return max(0, min(95, score))

def build_trade(r):
    price=r["price"]; d=r["dir"]
    sl_pct=0.009
    tp1_pct=0.008
    tp2_pct=0.018
    tp3_pct=0.032
    if d=="BUY":
        sl=price*(1-sl_pct)
        tp1=price*(1+tp1_pct)
        tp2=price*(1+tp2_pct)
        tp3=price*(1+tp3_pct)
    else:
        sl=price*(1+sl_pct)
        tp1=price*(1-tp1_pct)
        tp2=price*(1-tp2_pct)
        tp3=price*(1-tp3_pct)
    return {"code":r["code"],"dir":d,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":LEV[r["code"]],"rsi":r["rsi"],"adx":r["adx"],"volatility":r["volatility"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']}","vol_txt":r["vol_txt"],"kl":r["kl"],"closes":r["closes"],"sl_pct":sl_pct*100,"tp1_pct":tp1_pct*100}

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {"BUY" if active["dir"]=="BUY" else "SELL"} {active["coin"]} TP{active.get("stage",0)}/3 💰',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 CHK {active["coin"]}',callback_data="CHK"),InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🔍 SCAN REAL {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} 💵',callback_data="DAILY")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try: await app.bot.set_my_commands([BotCommand("start","🚀 V43 REAL AI"),BotCommand("scan","🔍 SCAN REAL")])
    except: pass

def bg_scan(chat_id):
    try:
        amt = get_trade_amount()
        bal = get_futures_balance()
        raws=[]
        for code in FAST:
            r=analyze_single(code)
            if r: raws.append(r)
            time.sleep(0.02)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"❌ No data 😴"},timeout=10, proxies=PROXIES)
            return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        cands=[]
        for r in raws:
            if r["vol_pct"] < -40: continue
            if r["adx"] < 11: continue
            score = ai_score_perfect(r, avg_adx)
            if score < 65: continue
            trade=build_trade(r); trade["conf"]=int(score); cands.append(trade)
        if not cands:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"😴 No quality trade now, market dey dull..."},timeout=10, proxies=PROXIES)
            return
        cands.sort(key=lambda x: x["conf"], reverse=True)
        best=cands[0]
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN 🔒"},timeout=10, proxies=PROXIES)
            return
        real_symbol = CRYPTO[best["code"]]
        order_res = place_real_order(real_symbol, best["dir"], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol} 😭 Check Futures has ${amt*2}+ USDT 💸"},timeout=10, proxies=PROXIES)
            return
        set_active({"status":"OPEN","coin":best["code"],"symbol":real_symbol,"dir":best["dir"],"entry":best["entry"],"sl":best["sl"],"tp1":best["tp1"],"tp2":best["tp2"],"tp3":best["tp3"],"conf":best["conf"],"stake":amt,"lev":best["lev"],"stage":0,"highest":best["entry"],"lowest":best["entry"],"time":str(__import__('datetime').datetime.now())})
        txt=(f"🚀 REAL V43 {best['conf']}/100 🔥\n💎 {best['code']} {best['dir']} @ {fmt(best['entry'])}\n💰 ${amt} {best['lev']}x | SL 0.9% TP 0.8/1.8/3.2\n🆔 ORDER {order_res.get('orderId')} ✅\n📈 TP1 50% + BE 🛡️ | TP2 30% + TRAILING 🏃 | TP3 20% 🚀\n💵 Bal ${bal:.2f} | Compound ${amt}")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10, proxies=PROXIES)
    except Exception as e:
        print(f"SCAN ERR {e}")

async def start(u,c):
    save_chat(u.message.chat.id)
    bal = get_futures_balance()
    amt = get_trade_amount()
    bal_text = f"\n💰 Futures: ${bal:.2f} USDT\n🚀 V43 TRAILING+COMPOUND 🔥" if bal is not None else "\n❌ Balance fail 😭"
    await u.message.reply_text(f"🤖 V43 FIXED LIVE ✨{bal_text}\n💵 Trade: ${amt} 10x (Auto-Compound)\n🎯 SL 0.9% TP1 0.8% TP2 1.8% TP3 3.2%\n🏃 Trailing after TP2 + 📈 Compound",parse_mode="Markdown",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🔍 SCANNING V43... 🧠🤖🚀")
async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} 💵",reply_markup=kb())
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L 💰",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"👀 {act['coin']} {act['dir']} Stage {act.get('stage',0)}/3 📈 P&L {pnl:.2f}% 💰",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed on Binance ✅",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("🔍 SCANNING... 🚀"); return

def monitor():
    while True:
        try:
            time.sleep(12)
            act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(CRYPTO[act["coin"]])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            stage = act.get("stage",0)
            entry = act["entry"]
            symbol = act["symbol"]
            if act["dir"]=="BUY":
                act["highest"] = max(act.get("highest", entry), price)
            else:
                act["lowest"] = min(act.get("lowest", entry), price)
            hit = None
            if stage>=2:
                trail_pct = 0.006
                if act["dir"]=="BUY":
                    new_trail_sl = act["highest"] * (1 - trail_pct)
                    if new_trail_sl > act["sl"]:
                        act["sl"] = new_trail_sl
                        set_active(act)
                        try:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING UP! {act['coin']} SL moved to {fmt(new_trail_sl)} 🔒 High {fmt(act['highest'])} 🚀"},timeout=8, proxies=PROXIES)
                        except: pass
                else:
                    new_trail_sl = act["lowest"] * (1 + trail_pct)
                    if new_trail_sl < act["sl"]:
                        act["sl"] = new_trail_sl
                        set_active(act)
                        try:
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING DOWN! {act['coin']} SL moved to {fmt(new_trail_sl)} 🔒 Low {fmt(act['lowest'])} 📉"},timeout=8, proxies=PROXIES)
                        except: pass
                if act["dir"]=="BUY" and price <= act["sl"]:
                    hit="TRAIL_SL"
                elif act["dir"]=="SELL" and price >= act["sl"]:
                    hit="TRAIL_SL"
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
                close_real_position(symbol, 50)
                new_sl = entry * 1.001 if act["dir"]=="BUY" else entry * 0.999
                act["sl"] = new_sl
                act["stage"] = 1
                set_active(act)
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 HIT! {act['coin']} +0.8% 💰 50% CLOSED ✅ SL->BE @ {fmt(new_sl)} 🛡️ RISK-FREE! 🚀"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol, 60)
                new_sl = act["tp1"]
                act["sl"] = new_sl
                act["stage"] = 2
                set_active(act)
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 TP2 HIT! {act['coin']} +1.8% 💰💰 80% total ✅ SL->TP1 @ {fmt(new_sl)} 🏃 TRAILING ACTIVATED! 🌙🚀"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol, 100)
                clear_active()
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 TP3 HIT! {act['coin']} +3.2% 🌕 FULL CLOSE! 🎉💰💰💰 🔥"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol, 100)
                clear_active()
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃💰 TRAILING SL HIT! {act['coin']} 🔒 Profit locked! 🧠✅"},timeout=8, proxies=PROXIES)
                except: pass
            elif hit=="SL":
                if stage==0:
                    close_real_position(symbol, 100)
                    clear_active()
                    try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL 0.9% {act['coin']} Closed 😢 Small loss 🛡️"},timeout=8, proxies=PROXIES)
                    except: pass
                else:
                    close_real_position(symbol, 100)
                    clear_active()
                    try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"⚖️ BE HIT {act['coin']} Breakeven - TP profit kept! 💰 🤖"},timeout=8, proxies=PROXIES)
                    except: pass
        except Exception as e:
            print(f"monitor err {e}")
            time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("🚀 V43 TRAILING+COMPOUND starting 💰"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
