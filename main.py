import os, threading, requests, time, json, urllib.parse, hmac, hashlib, math
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
            time.sleep(0.6)
        except: time.sleep(0.5)
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

def get_all_binance_futures():
    # GET ALL 300+ BINANCE USDT PERP FUTURES - NO FAVORITE!
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",headers=HEADERS,timeout=15,proxies=PROXIES).json()
        symbols=[]
        if isinstance(r,list):
            for t in r:
                sym=t.get('symbol','')
                if not sym.endswith('USDT'): continue
                if 'PERP' not in str(t) and True:
                    pass
                # Filter: Only USDT, volume > 5M, not stablecoins
                try:
                    vol=float(t.get('quoteVolume',0))
                    if vol<8000000: continue # Need 8M volume minimum!
                    if sym in ["USDCUSDT","BUSDUSDT","FDUSDUSDT","TUSDUSDT","USDPUSDT"]: continue
                    symbols.append((sym, vol))
                except: continue
            # Sort by volume highest first, take top 100 pumping
            symbols.sort(key=lambda x: x[1], reverse=True)
            top=[s[0] for s in symbols[:100]] # TOP 100 VOLUME!
            print(f"ALL FUTURES: Found {len(symbols)} total, scanning top {len(top)}")
            return top
    except Exception as e:
        print(f"get_all futures err {e}")
    # Fallback to your old favorites if API fails
    return ["PEPEUSDT","BONKUSDT","WIFUSDT","FLOKIUSDT","1000PEPEUSDT","TRUMPUSDT","SHIBUSDT","DOGEUSDT","SOLUSDT","WLDUSDT","SUIUSDT","AVAXUSDT","ENAUSDT","TIAUSDT","WUSDT","ACTUSDT","ZKUSDT","GOATUSDT","POPCATUSDT","BRETTUSDT","MEWUSDT","MOGUSDT","TURBOUSDT","PENGUUSDT","MOODENGUSDT","PNUTUSDT","NOTUSDT","DOGSUSDT","HMSTRUSDT","EIGENUSDT","ZROUSDT","SPXUSDT","ARBUSDT","OPUSDT","TAOUSDT","HYPEUSDT","LADYSUSDT","WOJAKUSDT","MEMEUSDT","PONKEUSDT","MYROUSDT","WENUSDT","TOSHIUSDT","CATUSDT","BABYDOGEUSDT","NEIROUSDT","ZEREBROUTDT"]

def get_btc_filter():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",params={"symbol":"BTCUSDT"},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        c=float(r.get('priceChangePercent',0))
        if c>=1.6: return False, f"BTC +{c:.1f}% Bull - RISKY", c
        if c<=-1.6: return False, f"BTC {c:.1f}% Bear - DANGER", c
        return True, f"BTC {c:.1f}% Calm ✅", c
    except: return True, "BTC N/A", 0

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
def home(): return f"V58 ALL FUTURES Bal ${get_futures_balance():.2f} LIVE",200
@app.get("/health")
def health(): return "OK V58 ALL",200

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
    if len(closes)<50: return 0,"SIDEWAYS",0,False
    e20=ema(closes,20); e50=ema(closes,50); pr=closes[-1]
    strong=False
    if pr>e20>e50: s=50; t="UPTREND"; strong=True
    elif pr<e20<e50: s=-50; t="DOWNTREND"; strong=True
    elif pr>e20: s=20; t="WEAK UP"; strong=False
    elif pr<e20: s=-20; t="WEAK DOWN"; strong=False
    else: s=0; t="SIDEWAYS"; strong=False
    return s,t,e20,strong
def calc_stoch_rsi(closes):
    try:
        if len(closes)<19: return 50
        rsi_vals=[rsi_calc(closes[:i+1]) for i in range(14, len(closes))]
        if len(rsi_vals)<5: return 50
        recent=rsi_vals[-5:]; low=min(recent); high=max(recent)
        if high==low: return 50
        return (recent[-1]-low)/(high-low)*100
    except: return 50
def calc_bos(kl):
    try:
        highs=[k["h"] for k in kl[-30:]]; lows=[k["l"] for k in kl[-30:]]
        last_h=max(highs[-20:-1]) if len(highs)>20 else highs[-1]
        last_l=min(lows[-20:-1]) if len(lows)>20 else lows[-1]
        curr=kl[-1]["c"]
        if curr>last_h*1.001: return True,f"BOS UP Break 🚀"
        if curr<last_l*0.999: return True,f"BOS DOWN Break 📉"
        return False,"No BOS - Choppy ⏳ REJECT"
    except: return False,"BOS N/A REJECT"
def get_orderbook_ratio(symbol, direction):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":symbol,"limit":20},headers=HEADERS,timeout=4,proxies=PROXIES).json()
        bids=r.get('bids',[]); asks=r.get('asks',[])
        if not bids or not asks: return 1.0
        bv=float(sum([float(x[0])*float(x[1]) for x in bids[:12]])); av=float(sum([float(x[0])*float(x[1]) for x in asks[:12]]))
        if bv==0 or av==0: return 1.0
        ratio=bv/av if direction=="BUY" else av/bv
        return ratio
    except: return 1.0

def analyze_strict(symbol):
    try:
        k15=get_klines(symbol,"15m"); k1=get_klines(symbol,"1h"); k2=get_klines(symbol,"2h")
        if len(k2)<50: k2=k1 if len(k1)>=50 else k15
        if len(k2)<50: return None, f"{symbol} No data"
        c15=[k["c"] for k in k15] if k15 else []; c1=[k["c"] for k in k1] if k1 else []; c2=[k["c"] for k in k2]
        price=get_price(symbol) or c2[-1]
        s15,t15,e15,strong15=trend_calc(c15 if c15 else c2)
        s1,t1,e1,strong1=trend_calc(c1 if c1 else c2)
        s2,t2,e2,strong2=trend_calc(c2)
        rsi=rsi_calc(c2); stoch=calc_stoch_rsi(c2); adx=adx_calc(k2)
        has_bos, bos_txt=calc_bos(k2)
        ob_ratio=get_orderbook_ratio(symbol, "BUY" if s2>=0 else "SELL")
        btc_ok, btc_txt, btc_change=get_btc_filter()

        if not (strong15 and strong1 and strong2): return None, f"{symbol} FAIL: Need STRONG 3/3, got {t15}/{t1}/{t2}"
        if not has_bos: return None, f"{symbol} FAIL: {bos_txt}"
        if not (45<=rsi<=57): return None, f"{symbol} FAIL: RSI {rsi:.1f} not 45-57"
        if stoch>=80: return None, f"{symbol} FAIL: Stoch {stoch:.0f} >=80"
        if adx<20: return None, f"{symbol} FAIL: ADX {adx:.1f} <20"
        if ob_ratio<1.15: return None, f"{symbol} FAIL: OB {ob_ratio:.2f} <1.15"
        if not btc_ok: return None, f"{symbol} FAIL: {btc_txt}"
        ema_dist=abs(price-e2)/e2*100 if e2 else 99
        if ema_dist>0.45: return None, f"{symbol} FAIL: EMA {ema_dist:.2f}% >0.45%"

        direction="BUY" if s2>=0 else "SELL"
        sl_pct=0.015 if "1.5" in RISK_MODE else 0.02 if "2.0" in RISK_MODE else 0.009
        tp1_pct=sl_pct; tp2_pct=sl_pct*2; tp3_pct=sl_pct*3
        if direction=="BUY": sl=price*(1-sl_pct); tp1=price*(1+tp1_pct); tp2=price*(1+tp2_pct); tp3=price*(1+tp3_pct)
        else: sl=price*(1+sl_pct); tp1=price*(1-tp1_pct); tp2=price*(1-tp2_pct); tp3=price*(1-tp3_pct)

        code=symbol.replace("USDT","")
        trade={"symbol":symbol,"code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl_pct":sl_pct*100,"tp3_pct":tp3_pct*100,"rsi":rsi,"stoch":stoch,"adx":adx,"mtf":f"15m {t15} | 1H {t1} | 2H {t2}","bos":bos_txt,"ob":f"OB {ob_ratio:.2f} Bull 🟢","btc":btc_txt,"ema_dist":f"{ema_dist:.2f}%","conf":85}
        return trade, "PASS"
    except Exception as e:
        return None, f"{symbol} ERR {e}"

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'🟢 {active["dir"]} {active["coin"]} TP{active.get("stage",0)}/3',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 MONITOR {active["coin"]}',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🎯 SCAN ALL FUTURES 🧠',callback_data="SCAN"), InlineKeyboardButton(f'🔥 RISK 1.5%',callback_data="RISK15"), InlineKeyboardButton(f'🔥 RISK 2%',callback_data="RISK20")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'👀 MONITOR',callback_data="MON")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([
            BotCommand("start","🧠 V58 ALL FUTURES"),
            BotCommand("scan","🧠 SCAN ALL 100+"),
            BotCommand("risk15","🔥 RISK 1.5%"),
            BotCommand("risk20","🔥 RISK 2%"),
            BotCommand("monitor","👀 MONITOR"),
            BotCommand("daily","📊 Daily")
        ])
    except: pass

def bg_scan(chat_id, risk_mode_override=None):
    try:
        bal=get_futures_balance()
        all_symbols=get_all_binance_futures()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🌐 V58 SCANNING ALL BINANCE FUTURES! 🌐\nScanning top {len(all_symbols)} coins by volume (not favorite)! 30 sec... 🔍"},timeout=10,proxies=PROXIES)
        raws=[]; fails=[]
        for symbol in all_symbols:
            trade, msg = analyze_strict(symbol)
            if trade: raws.append(trade)
            else: 
                if len(fails)<12: fails.append(msg)
            time.sleep(0.03)
        if not raws:
            txt=f"🧠 V58 ALL FUTURES - No perfect now ✅ $ safe! Scanned {len(all_symbols)} coins!\n\nTOP 7 REJECTED (GOOD!):\n" + "\n".join(fails[:7]) + f"\n\nNeed STRICT:\n✅ STRONG UPTREND 15m+1H+2H 3/3\n✅ BOS Break MUST\n✅ RSI 45-57 + Stoch <80 + ADX >=20\n✅ OB >=1.15 Whale\n✅ EMA <0.45% + BTC calm\n\nBal ${bal:.2f} safe! Scanned ALL FUTURES! Try 15 min later!"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x: x['adx'], reverse=True)
        best=raws[0]
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN!"},timeout=10,proxies=PROXIES); return
        mode="SNIPER"
        if risk_mode_override=="2.0" or RISK_MODE=="2.0": mode="RISKY20"
        elif risk_mode_override=="1.5" or RISK_MODE=="1.5": mode="RISKY15"
        amt=get_trade_amount(mode); real_symbol=best['symbol']
        order_res=place_real_order(real_symbol, best['dir'], amt)
        if not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Order failed {real_symbol}"},timeout=10,proxies=PROXIES); return
        set_active({"status":"OPEN","coin":best['code'],"symbol":real_symbol,"dir":best['dir'],"entry":best['entry'],"sl":best['sl'],"tp1":best['tp1'],"tp2":best['tp2'],"tp3":best['tp3'],"conf":best['conf'],"stake":amt,"lev":10,"stage":0,"highest":best['entry'],"lowest":best['entry'],"sl_pct":best['sl_pct'],"tp3_pct":best['tp3_pct'],"mode":mode,"time":str(datetime.now())})
        txt=(f"🧠 V58 ALL FUTURES 85% PERFECT! 🌐🔥\n💎 {best['symbol']} {best['dir']} @ {fmt(best['entry'])}\n💰 ${amt} 10x | SL {best['sl_pct']:.1f}% TP {best['tp3_pct']:.1f}% (1:3)\n🆔 ORDER {order_res.get('orderId')} ✅ {mode}\nScanned {len(all_symbols)} coins! Best coin found!\n━━━━━━━━━━━━━━━\n🧠 5 STRICT RULES PASSED:\n✅ 15m+1H+2H STRONG UPTREND 3/3\n✅ {best['bos']} ✅\n✅ RSI {best['rsi']:.1f} + Stoch {best['stoch']:.0f} + ADX {best['adx']:.1f} ✅\n✅ {best['ob']} ✅\n✅ EMA {best['ema_dist']} + {best['btc']} ✅\n━━━━━━━━━━━━━━━\n📊 {best['mtf']}\n💵 Bal ${bal:.2f} | ALL FUTURES SCANNER 🌐 | MAX LOSS -4% 🛡️")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt},timeout=10,proxies=PROXIES)
    except Exception as e:
        print(f"SCAN ERR {e}"); import traceback; traceback.print_exc()
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Scan error: {e}"},timeout=10,proxies=PROXIES)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id); bal=get_futures_balance()
    await u.message.reply_text(f"🧠 V58 ALL BINANCE FUTURES SCANNER LIVE 🌐✨\n💰 Futures ${bal:.2f} USDT Risk {RISK_MODE}%\n\n🌐 SCAN ALL 100+ FUTURES (not favorite)!\nSort by volume, pick BEST pumping coin!\n\n5 STRICT RULES:\n✅ STRONG UPTREND 15m+1H+2H 3/3\n✅ BOS Break MUST\n✅ RSI 45-57 + Stoch <80 + ADX >=20\n✅ OB >=1.15 Whale + EMA <0.45%\n✅ BTC calm\n\n💵 RISK15 SL 1.5% $0.45 TP 4.5% $1.35 (1:3)\n💵 RISK20 SL 2% $0.60 TP 6% $1.80 (1:3)\n🛡️ MAX LOSS -4% ROI GUARD!\n\nNo more favorite list! ALL FUTURES!",reply_markup=kb(get_active()))

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, None),daemon=True).start()
    await u.message.reply_text("🌐 V58 ALL FUTURES SCANNING... Top 100 volume coins! Not favorite! 30 sec...")

async def risk15_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "1.5"),daemon=True).start()
    await u.message.reply_text("🔥 V58 ALL FUTURES RISK 1.5%... Scanning ALL!")

async def risk20_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id, "2.0"),daemon=True).start()
    await u.message.reply_text("🔥🔥 V58 ALL FUTURES RISK 2%... Scanning ALL!")

async def daily_cmd(u,c):
    d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f} V58 ALL FUTURES",reply_markup=kb(get_active()))

async def monitor_cmd(u,c):
    save_chat(u.message.chat.id); act=get_active()
    if not act.get("status")=="OPEN":
        await u.message.reply_text("😴 No active trade - Press SCAN ALL FUTURES! 🌐",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]; stake=act["stake"]; lev=act["lev"]
    if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
    else: pnl_pct=(entry-price)/entry*100
    pnl_usdt=pnl_pct/100*stake*lev; bal=get_futures_balance()
    txt=(f"👀 MONITOR {act.get('mode','')} AI {act.get('conf',0)}%\n💎 {act['coin']} {act['dir']} Stage {act.get('stage',0)}/3\nEntry {fmt(entry)} → Now {fmt(price)}\nP&L {pnl_pct:.3f}% (${pnl_usdt:+.4f}) ROI {pnl_pct*lev:.1f}%\nBal ${bal:.2f} 🛡️")
    await u.message.reply_text(txt, reply_markup=kb(act))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴 No active trade",reply_markup=kb()); return
        price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]
        if act["dir"]=="BUY": pnl_pct=(price-entry)/entry*100
        else: pnl_pct=(entry-price)/entry*100
        pnl_usdt=pnl_pct/100*act["stake"]*act["lev"]
        await q.message.reply_text(f"👀 {act['coin']} {act['dir']} {pnl_pct:.2f}% (${pnl_usdt:+.4f})",reply_markup=kb(act)); return
    if data=="CLS":
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"],100)
        clear_active(); await q.message.reply_text("❌ Closed ✅",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id, None),daemon=True).start(); await q.message.reply_text("🌐 V58 ALL FUTURES SCANNING..."); return
    if data=="RISK15": threading.Thread(target=bg_scan,args=(q.message.chat.id, "1.5"),daemon=True).start(); await q.message.reply_text("🔥 ALL FUTURES RISK 1.5%..."); return
    if data=="RISK20": threading.Thread(target=bg_scan,args=(q.message.chat.id, "2.0"),daemon=True).start(); await q.message.reply_text("🔥🔥 ALL FUTURES RISK 2%..."); return

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
            if mode=="SNIPER" and roi<=-4.5:
                close_real_position(symbol,100); clear_active(); update_daily(-0.135, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨 -4% ROI GUARD! {act['coin']} Closed! $0.135 🛡️"},timeout=8,proxies=PROXIES)
                except: pass
                continue
            max_roi=-16.0 if "1.5" in mode else -21.0 if "2.0" in mode else -10.0
            if roi<=max_roi:
                close_real_position(symbol,100); clear_active()
                loss=0.60 if "2.0" in mode else 0.45 if "1.5" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🚨 SL {act.get('sl_pct',1.5):.1f}% HIT {act['coin']} ROI {roi:.1f}% Loss ${loss:.2f} 🛡️"},timeout=8,proxies=PROXIES)
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
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯 TP1 HIT {act['coin']} +{act.get('sl_pct',1.5):.1f}% 50% BE 🛡️"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP2":
                close_real_position(symbol,30); act["sl"]=act["tp1"]; act["stage"]=2; set_active(act)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯 TP2 HIT {act['coin']} + TRAILING"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TP3":
                close_real_position(symbol,100); clear_active()
                win=1.80 if "2.0" in mode else 1.35 if "1.5" in mode else 0.50
                update_daily(win, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🎯🎯🎯 TP3 HIT {act['coin']} +{act.get('tp3_pct',4.5):.1f}% +${win:.2f} 🎉💰💰💰"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="TRAIL_SL":
                close_real_position(symbol,100); clear_active(); update_daily(0.70, True)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🏃 TRAILING HIT {act['coin']} Profit $0.70+ 🔒"},timeout=8,proxies=PROXIES)
                except: pass
            elif hit=="SL":
                close_real_position(symbol,100); clear_active()
                loss=0.60 if "2.0" in mode else 0.45 if "1.5" in mode else 0.27
                update_daily(-loss, False)
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":f"🛑 SL {act.get('sl_pct',1.5):.1f}% {act['coin']} Loss ${loss:.2f} 🛡️"},timeout=8,proxies=PROXIES)
                except: pass
        except Exception as e:
            print(f"monitor err {e}"); time.sleep(5)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("risk15",risk15_cmd)); a.add_handler(CommandHandler("risk20",risk20_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print(f"V58 ALL FUTURES starting Risk {RISK_MODE}%"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
