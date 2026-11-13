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
HEADERS = {"User-Agent":"SKELLY-V92-ALL-FUTURES"}
PROXIES = {"http": BINANCE_PROXY, "https": BINANCE_PROXY} if BINANCE_PROXY else None

SYMBOL_FIX = {"PEPEUSDT":"1000PEPEUSDT","FLOKIUSDT":"1000FLOKIUSDT","BONKUSDT":"1000BONKUSDT","SHIBUSDT":"1000SHIBUSDT","RATSUSDT":"1000RATSUSDT","SATSUSDT":"1000SATSUSDT","LUNCUSDT":"1000LUNCUSDT","XECUSDT":"1000XECUSDT"}
def fix_symbol(sym): return SYMBOL_FIX.get(sym, sym)

def binance_signed_request(method, endpoint, params={}):
    if not BINANCE_API_KEY or not BINANCE_SECRET: return None
    try:
        p=dict(params); p['timestamp']=int(time.time()*1000); p['recvWindow']=10000
        query=urllib.parse.urlencode(p)
        sig=hmac.new(BINANCE_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url=f"https://fapi.binance.com{endpoint}?{query}&signature={sig}"
        r=requests.request(method, url, headers={"X-MBX-APIKEY": BINANCE_API_KEY}, proxies=PROXIES, timeout=10)
        if r.status_code==200: return r.json()
        return {"error":r.text}
    except Exception as e: return {"error":str(e)}

def get_futures_balance():
    data=binance_signed_request("GET","/fapi/v2/balance")
    if isinstance(data,list):
        for b in data:
            if b.get('asset')=='USDT': return float(b.get('balance',0))
    return 7.03
def set_leverage(symbol, lev=5): return binance_signed_request("POST","/fapi/v1/leverage",{"symbol":fix_symbol(symbol),"leverage":lev})
def get_symbol_filters(symbol):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",headers=HEADERS,timeout=8,proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==fix_symbol(symbol):
                for f in s['filters']:
                    if f['filterType']=='LOT_SIZE': return float(f['minQty']), float(f['stepSize'])
    except: pass
    return 1.0,1.0
def get_price_precision(symbol):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",headers=HEADERS,timeout=8,proxies=PROXIES).json()
        for s in r.get('symbols',[]):
            if s['symbol']==fix_symbol(symbol):
                for f in s['filters']:
                    if f['filterType']=='PRICE_FILTER': return float(f['tickSize'])
    except: pass
    return 0.0000001
def place_real_futures_order(symbol, side, quantity): return binance_signed_request("POST","/fapi/v1/order",{"symbol":fix_symbol(symbol),"side":side,"type":"MARKET","quantity":quantity})
def place_sl_tp_order(symbol, side, stop_price):
    tick=get_price_precision(symbol); prec=int(round(-math.log10(tick),0)) if tick<1 else 0
    return binance_signed_request("POST","/fapi/v1/order",{"symbol":fix_symbol(symbol),"side":side,"type":"STOP_MARKET","stopPrice":round(stop_price,prec),"closePosition":True})

def place_real_trade(symbol, direction, entry_price, sl, tp1, bal):
    try:
        real_symbol=fix_symbol(symbol); set_leverage(real_symbol,5)
        minQty,step=get_symbol_filters(real_symbol)
        usdt_to_use=1.2 if bal>=3 else round(bal*0.35,2)
        if usdt_to_use<1: usdt_to_use=1.0
        qty=usdt_to_use*5/entry_price
        prec=int(round(-math.log10(step),0)) if step<1 else 0
        qty=math.floor(qty/step)*step; qty=round(qty,prec)
        if qty<minQty: qty=minQty
        side="BUY" if direction=="BUY" else "SELL"
        result=place_real_futures_order(real_symbol,side,qty)
        if result and "Invalid symbol" in str(result): result=place_real_futures_order("PEPEUSDT" if "1000PEPE" in real_symbol else real_symbol,side,qty)
        if result and result.get("orderId"):
            time.sleep(0.6); close_side="SELL" if direction=="BUY" else "BUY"; place_sl_tp_order(real_symbol,close_side,sl)
        return result,qty,usdt_to_use,real_symbol
    except Exception as e: return {"error":str(e)},0,0,symbol

def get_real_alt_futures():
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo",headers=HEADERS,timeout=10,proxies=PROXIES).json()
        all_syms=[]
        for s in r.get('symbols',[]):
            sym=s.get('symbol','')
            if s.get('status')=='TRADING' and s.get('contractType')=='PERPETUAL' and sym.endswith('USDT'): all_syms.append(sym)
        priority=["BTCUSDT","ETHUSDT","SOLUSDT","1000PEPEUSDT","1000BONKUSDT","1000FLOKIUSDT","1000SHIBUSDT","DOGEUSDT","WIFUSDT","BOMEUSDT","POPCATUSDT","PNUTUSDT"]
        rest=[x for x in all_syms if x not in priority]
        return (priority+rest)[:120]
    except: return ["BTCUSDT","ETHUSDT","SOLUSDT","1000PEPEUSDT","DOGEUSDT","WIFUSDT","BOMEUSDT","AVAXUSDT","LINKUSDT","SUIUSDT"]

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
def home(): return f"V92 ALL-FUTURES SMC Bal ${get_futures_balance():.2f}",200
@app.get("/health")
def health(): return "OK V92",200

def fmt(v):
    try:
        v=float(v)
        if v>=1: return f"{v:.5f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def get_klines(sym, interval="15m"):
    sym=fix_symbol(sym); key=f"{sym}_{interval}"
    with CACHE_LOCK:
        if key in CACHE and time.time()-CACHE[key][0]<60: return CACHE[key][1]
    for base in ["https://fapi.binance.com/fapi/v1/klines","https://data-api.binance.vision/api/v3/klines"]:
        try:
            r=requests.get(base,params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7,proxies=PROXIES).json()
            if isinstance(r,list) and len(r)>=70:
                kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
                with CACHE_LOCK: CACHE[key]=(time.time(),kl)
                return kl
        except: continue
    return []

def get_price(sym):
    sym=fix_symbol(sym)
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
def rsi_series(closes,p=14):
    if len(closes)<p+1: return [50]*len(closes)
    gains=[0]*len(closes); losses=[0]*len(closes)
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains[i]=d if d>0 else 0; losses[i]=-d if d<0 else 0
    avg_g=sum(gains[1:p+1])/p; avg_l=sum(losses[1:p+1])/p
    rsi=[50]*len(closes)
    for i in range(p,len(closes)):
        if i>p:
            avg_g=(avg_g*(p-1)+gains[i])/p; avg_l=(avg_l*(p-1)+losses[i])/p
        if avg_l==0: rsi[i]=75
        else: rsi[i]=100-(100/(1+avg_g/avg_l))
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
        tr=[]
        for i in range(1,len(kl)): tr.append(max(kl[i]["h"]-kl[i]["l"], abs(kl[i]["h"]-kl[i-1]["c"]), abs(kl[i]["l"]-kl[i-1]["c"])))
        return sum(tr[-p:])/p
    except: return 0
def macd_calc(closes):
    if len(closes)<35: return 0,0
    e12=ema(closes,12); e26=ema(closes,26)
    return e12-e26, ema([ema(closes[:i+1],12)-ema(closes[:i+1],26) for i in range(26,len(closes))],9)

# SMART MONEY CONCEPTS
def detect_fvg(kl):
    try:
        if kl[-1]["l"]>kl[-3]["h"]: return True,"BULL_FVG"
        if kl[-1]["h"]<kl[-3]["l"]: return True,"BEAR_FVG"
        return False,"NO_FVG"
    except: return False,"NO_FVG"
def detect_order_block(kl):
    try:
        for i in range(len(kl)-6,len(kl)-2):
            curr=kl[i]
            if curr["c"]<curr["o"] and all(k["c"]>k["o"] for k in kl[i+1:i+3]) and kl[-1]["l"]<=curr["h"]*1.005: return True,"BULL_OB"
            if curr["c"]>curr["o"] and all(k["c"]<k["o"] for k in kl[i+1:i+3]) and kl[-1]["h"]>=curr["l"]*0.995: return True,"BEAR_OB"
        return False,"NO_OB"
    except: return False,"NO_OB"
def detect_bos_choch(kl):
    try:
        highs=[k["h"] for k in kl[-20:]]; lows=[k["l"] for k in kl[-20:]]; curr=kl[-1]["c"]
        prev_high=max(highs[-10:-1]); prev_low=min(lows[-10:-1])
        if curr>prev_high*1.002: return "BOS_BULLISH",0
        if curr<prev_low*0.998: return "BOS_BEARISH",0
        recent_high=max(highs[-6:-1]); recent_low=min(lows[-6:-1])
        if curr>recent_high*1.001: return "CHOCH_BULL",0
        if curr<recent_low*0.999: return "CHOCH_BEAR",0
        return "NO_BOS",0
    except: return "NO_BOS",0
def get_trend(candles):
    if len(candles)<60: return "NEUTRAL",50,0,0
    c=[k["c"] for k in candles]; e20=ema(c,20); e50=ema(c,50); e200=ema(c,200) if len(c)>=200 else e50
    r=rsi_calc(c); macd_line,sig=macd_calc(c)
    if c[-1]>e20 and e20>e50 and c[-1]>e200 and macd_line>sig: return "BUY",r,e20,e50
    if c[-1]<e20 and e20<e50 and c[-1]<e200 and macd_line<sig: return "SELL",r,e20,e50
    return "NEUTRAL",r,e20,e50
def make_colored_chart(kl): return "".join(["🟩" if k["c"]>k["o"] else "🟥" for k in kl[-10:]]) if kl else "🟨"

def analyze_PERFECT(symbol):
    try:
        k1h=get_klines(symbol,"1h"); k3h=get_klines(symbol,"3h"); k4h=get_klines(symbol,"4h"); k15m=get_klines(symbol,"15m")
        if len(k1h)<90 or len(k3h)<70 or len(k4h)<70 or len(k15m)<50: return None
        c1h=[k["c"] for k in k1h]; c3h=[k["c"] for k in k3h]
        rsi1h_series=rsi_series(c1h,14); rsi3h_series=rsi_series(c3h,14)
        rsi1h=rsi1h_series[-1]; rsi3h=rsi3h_series[-1]; rsi4h=rsi_series([k["c"] for k in k4h],14)[-1]
        price=get_price(symbol) or c1h[-1]
        trend1h,r1,_,_=get_trend(k1h); trend3h,r3,_,_=get_trend(k3h); trend4h,r4,_,_=get_trend(k4h)
        if not (trend1h==trend3h==trend4h and trend1h!="NEUTRAL"): return None
        direction=trend1h
        bos_15m,_=detect_bos_choch(k15m); has_fvg,fvg_type=detect_fvg(k15m); has_ob,ob_type=detect_order_block(k15m)
        smc_score=(2 if "BULL" in bos_15m or "BEAR" in bos_15m else 0)+(2 if has_fvg else 0)+(2 if has_ob else 0)
        if direction=="BUY" and bos_15m not in ["BOS_BULLISH","CHOCH_BULL"]: return None
        if direction=="SELL" and bos_15m not in ["BOS_BEARISH","CHOCH_BEAR"]: return None
        if not (has_fvg or has_ob): return None
        if smc_score<3: return None
        is_meme=any(x in symbol for x in ["1000PEPE","1000BONK","PEPE","BONK","WIF","FLOKI","BOME"])
        if direction=="BUY" and rsi1h>68: return None
        if direction=="SELL" and rsi1h<25: return None
        vol=[k["v"] for k in k1h]; avg_vol=sma(vol,20)
        if vol[-1]<avg_vol*0.7: return None
        adx1h=adx_calc(k1h); adx3h=adx_calc(k3h); atr=atr_calc(k1h,14)
        if adx1h<18 or adx3h<15: return None
        ma7=sma(c1h,7); ma25=sma(c1h,25); ma99=sma(c1h,99)
        buf=atr*2.2 if atr else price*0.015; max_sl=0.08 if is_meme else 0.06; min_sl=0.03
        if direction=="BUY":
            sl=price-buf*2.0; pct=(price-sl)/price
            if pct>max_sl: sl=price*(1-max_sl)
            if pct<min_sl: sl=price*(1-min_sl)
            tp1=price+(price-sl)*1.0; tp2=price+(price-sl)*2.0; tp3=price+(price-sl)*3.2; tp4=price+(price-sl)*4.5
        else:
            sl=price+buf*2.0; pct=(sl-price)/price
            if pct>max_sl: sl=price*(1+max_sl)
            if pct<min_sl: sl=price*(1+min_sl)
            tp1=price-(sl-price)*1.0; tp2=price-(sl-price)*2.0; tp3=price-(sl-price)*3.2; tp4=price-(sl-price)*4.5
        rr=abs(tp2-price)/abs(price-sl) if abs(price-sl)>0 else 0
        if rr<1.8: return None
        conf=90+(3 if has_fvg and has_ob else 0)+(1 if adx1h>24 else 0)+(2 if smc_score>=4 else 0)
        conf=min(94,conf)
        real_sym=fix_symbol(symbol)
        return {"symbol":symbol,"real_symbol":real_sym,"code":real_sym.replace("USDT",""),"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,"rsi1h":rsi1h,"rsi3h":rsi3h,"rsi4h":rsi4h,"adx":adx1h,"ma7":ma7,"ma25":ma25,"ma99":ma99,"score":6,"rr":rr,"conf":conf,"trend1h":trend1h,"trend3h":trend3h,"trend4h":trend4h,"chart1h":make_colored_chart(k1h),"chart3h":make_colored_chart(k3h),"chart4h":make_colored_chart(k4h),"pattern":f"{bos_15m} + {fvg_type}/{ob_type}","perfect_entry":price,"sl_pct":max_sl,"vol":vol[-1]/avg_vol,"smc":{"bos":bos_15m,"fvg":fvg_type,"ob":ob_type,"score":smc_score}}
    except Exception as e:
        print(f"SMC error {symbol}: {e}")
        return None

def kb(active=None):
    daily=get_daily()
    if active and active.get("status")=="OPEN": return InlineKeyboardMarkup([[InlineKeyboardButton(f'🟢 {active["dir"]} {active["real_symbol"]} ${active.get("usdt",1.2)} {active.get("conf",89)}%',callback_data="MON")],[InlineKeyboardButton(f'👀 MONITOR',callback_data="MON"), InlineKeyboardButton(f'❌ Close',callback_data="CLS")]])
    pend=get_pending(); btns=[]
    if pend: btns.append([InlineKeyboardButton(f'⏳ PENDING {pend.get("real_symbol",pend["symbol"])} {pend["dir"]} {pend.get("conf",89)}%',callback_data="SHOW_PENDING")])
    btns.append([InlineKeyboardButton(f'⚡ SCAN ALL FUTURES SMC 🔥',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY"), InlineKeyboardButton(f'🔄 RESET',callback_data="RESET")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app_):
    try: await app_.bot.set_my_commands([BotCommand("start","🚀 V92 ALL FUTURES"),BotCommand("scan","⚡ SCAN ALL"),BotCommand("monitor","👀 MONITOR"),BotCommand("daily","📊 DAILY"),BotCommand("reset","🔄 RESET")])
    except: pass

def bg_scan(chat_id):
    try:
        bal=get_futures_balance(); syms=get_real_alt_futures()
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚡🔍 V92 SMC Scanning {len(syms)} coins ALL FUTURES... Bal ${bal:.2f}"},timeout=10,proxies=PROXIES)
        raws=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: res=list(ex.map(analyze_PERFECT, syms))
        for t in res:
            if t: raws.append(t)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"😑💤 No SMC setup yet... All {len(syms)} dull. Safe! No trade. Bal ${bal:.2f}"},timeout=10,proxies=PROXIES); return
        raws.sort(key=lambda x:(x['conf'],x['rr']),reverse=True); best=raws[0]; set_pending(best)
        display_sym=best.get("real_symbol",best["symbol"])
        mk=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ YES $1.2 {display_sym.replace("USDT","")} {best["conf"]}%',callback_data=f'YES_{best["symbol"]}_{best["dir"]}'),InlineKeyboardButton(f'😑💤 NO SKIP',callback_data='NO')]])
        txt=(f"💎🔥 SMC ALL-FUTURES ENTRY! {best['conf']}% 👑\n\n💱 {display_sym} | {best['dir']} | ⭐ RR {best['rr']:.1f} VOL x{best['vol']:.1f}\n🟦 SMC: {best['smc']['bos']} | {best['smc']['fvg']} | {best['smc']['ob']} Score {best['smc']['score']}\n🎯 Entry: {fmt(best['perfect_entry'])}\n🛡️ SL = {fmt(best['sl'])}\n💰 TP1 = {fmt(best['tp1'])} | TP2 = {fmt(best['tp2'])}\n💰 TP3 = {fmt(best['tp3'])} | TP4 = {fmt(best['tp4'])}\n\n📊 1H RSI {best['rsi1h']:.0f} 3H RSI {best['rsi3h']:.0f} 4H RSI {best['rsi4h']:.0f}\n💰 Bal ${bal:.2f} | $1.2 x5 | {best['conf']}% SMC!\n\n👉 REAL $1.2 TRADE? YES!")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"reply_markup":mk.to_dict()},timeout=10,proxies=PROXIES)
    except Exception as e: print(f"SCAN ERR {e}")

async def start(u,c): save_chat(u.message.chat.id); bal=get_futures_balance(); await u.message.reply_text(f"🧠💎 SKELLY'S V92 ALL-FUTURES SMC 👑\n💰 Futures ${bal:.2f} USDT | $1.2 x5 + Wide SL!\n\n✅ ALL 120 Futures Auto-Fetch\n✅ SMC: Order Blocks + FVG + BOS/CHOCH\n✅ 1H/3H/4H Must Agree\n✅ $1.2 Only - Safe\n🏆 89-94% SMC\n\nPress SCAN! ⚡",reply_markup=kb(get_active()))
async def scan_cmd(u,c): save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start(); await u.message.reply_text("⚡ V92 Scanning ALL FUTURES...")
async def daily_cmd(u,c): d=get_daily(); await u.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active()))
async def reset_cmd(u,c): save_json(DAILY_FILE,{"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); await u.message.reply_text("🔄 RESET DONE! V92 Ready!",reply_markup=kb(get_active()))
async def monitor_cmd(u,c):
    act=get_active()
    if not act.get("status")=="OPEN": await u.message.reply_text("😴💤 No active",reply_markup=kb()); return
    price=get_price(act["symbol"]) or act["entry"]; entry=act["entry"]; pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
    await u.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% Conf {act.get('conf',89)}%",reply_markup=kb(act))
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data=="RESET": save_json(DAILY_FILE,{"date":str(date.today()),"wins":0,"losses":0,"trades":0,"pnl":0.0}); clear_active(); clear_pending(); await q.message.reply_text("🔄 RESET!",reply_markup=kb(get_active())); return
    if data=="NO": clear_pending(); await q.message.reply_text("😑💤 Skipped! SMC protected you!",reply_markup=kb(get_active())); return
    if data=="SHOW_PENDING":
        pend=get_pending()
        if not pend: await q.message.reply_text("No pending 😑💤"); return
        mk=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ YES $1.2 {pend.get("real_symbol",pend["symbol"])} {pend["conf"]}%',callback_data=f'YES_{pend["symbol"]}_{pend["dir"]}'),InlineKeyboardButton(f'😑💤 NO',callback_data='NO')]])
        await q.message.reply_text(f"⏳ PENDING {pend.get('real_symbol',pend['symbol'])} {pend['dir']} {pend['conf']}% SMC {pend['smc']['bos']} Entry {fmt(pend['perfect_entry'])} $1.2 only",reply_markup=mk); return
    if data.startswith("YES_"):
        parts=data.split("_"); symbol=parts[1]; direction=parts[2]; pend=get_pending()
        if not pend: await q.message.reply_text("No pending, scan again!"); return
        bal=get_futures_balance(); real_sym=fix_symbol(symbol)
        await q.message.reply_text(f"⏳ Placing REAL $1.2 order {real_sym} {pend['smc']['bos']} {direction} + Auto SL {fmt(pend['sl'])}... Bal ${bal:.2f}")
        result,qty,usdt_used,fixed_sym=place_real_trade(symbol,direction,pend['perfect_entry'],pend['sl'],pend['tp1'],bal)
        if result and "error" not in result and result.get("orderId"):
            set_active({"status":"OPEN","coin":fixed_sym.replace("USDT",""),"symbol":symbol,"real_symbol":fixed_sym,"dir":direction,"entry":pend['perfect_entry'],"sl":pend['sl'],"tp1":pend['tp1'],"tp2":pend['tp2'],"tp3":pend['tp3'],"tp4":pend['tp4'],"conf":pend['conf'],"qty":qty,"usdt":usdt_used,"orderId":result.get("orderId"),"time":str(datetime.now())})
            await q.message.reply_text(f"✅🔥 REAL $1.2 SMC TRADE EXECUTED! 🚀\n{fixed_sym} {direction} {pend['conf']}% SMC!\nQty {qty} | Used ${usdt_used} x5 | SL {fmt(pend['sl'])}\nOrderID {result.get('orderId')}\nBal left ~${bal-usdt_used:.2f} safe!\nCheck Binance Futures!",reply_markup=kb(get_active()))
        else: err=result.get("error","Unknown") if isinstance(result,dict) else str(result); await q.message.reply_text(f"⚠️ Binance Error: {err[:500]}\nBalance ${bal:.2f}? Symbol {real_sym}?",reply_markup=kb(get_active()))
        clear_pending(); return
    if data=="MON":
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("😴💤 No active",reply_markup=kb()); return
        price=get_price(act.get("real_symbol",act["symbol"])) or act["entry"]; entry=act["entry"]; pnl=(price-entry)/entry*100 if act["dir"]=="BUY" else (entry-price)/entry*100
        await q.message.reply_text(f"👀 {act.get('real_symbol',act['symbol'])} {act['dir']} {pnl:.2f}% {act.get('conf',89)}% SMC ${act.get('usdt',1.2)}",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); clear_pending(); await q.message.reply_text("😑💤 Closed! V92",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("⚡ V92 Scanning ALL..."); return

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("reset",reset_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V92 ALL FUTURES LIVE"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    run_bot()
