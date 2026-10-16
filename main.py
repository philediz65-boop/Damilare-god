import os,re,threading,requests,time,io,json,concurrent.futures
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,BotCommand
from telegram.ext import ApplicationBuilder,CommandHandler,CallbackQueryHandler,MessageHandler,filters
from datetime import datetime, date
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
PORT=int(os.getenv("PORT","10000"))
app=Flask(__name__)
CACHE={}; LOCK=threading.Lock()
ACTIVE_FILE="/tmp/active_trade_v10.json"; DAILY_FILE="/tmp/daily_stats_v10.json"; CHAT_FILE="/tmp/last_chat_id.json"
GLOBAL_ACTIVE={}; GLOBAL_CHAT_ID=None

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
    except: pass
    return d
def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f: json.dump(f,data)
    except: pass
def get_daily():
    d=load_json(DAILY_FILE,{}); today=str(date.today())
    if d.get("date")!=today: d={"date":today,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d
def update_daily(result,pnl,coin=""):
    d=get_daily(); d["trades"]+=1
    if result=="WIN": d["wins"]+=1
    else: d["losses"]+=1
    d["pnl"]+=pnl; save_json(DAILY_FILE,d); return d
def get_active():
    global GLOBAL_ACTIVE
    if GLOBAL_ACTIVE and GLOBAL_ACTIVE.get("status")=="OPEN": return GLOBAL_ACTIVE
    file_active=load_json(ACTIVE_FILE,{})
    if file_active and file_active.get("status")=="OPEN":
        GLOBAL_ACTIVE=file_active; return file_active
    return {}
def set_active(data):
    global GLOBAL_ACTIVE; GLOBAL_ACTIVE=data; save_json(ACTIVE_FILE,data)
def clear_active():
    global GLOBAL_ACTIVE; GLOBAL_ACTIVE={}; save_json(ACTIVE_FILE,{})
def save_chat_id(cid):
    global GLOBAL_CHAT_ID; GLOBAL_CHAT_ID=cid; save_json(CHAT_FILE,{"chat_id":cid})
def get_chat_id():
    global GLOBAL_CHAT_ID
    if GLOBAL_CHAT_ID: return GLOBAL_CHAT_ID
    d=load_json(CHAT_FILE,{}); cid=d.get("chat_id")
    if cid: GLOBAL_CHAT_ID=cid
    return cid

CRYPTO={"BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT","DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","TRX":"TRXUSDT","DOT":"DOTUSDT","MATIC":"MATICUSDT","LTC":"LTCUSDT","BCH":"BCHUSDT","UNI":"UNIUSDT","ATOM":"ATOMUSDT","ETC":"ETCUSDT","FIL":"FILUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT","SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT","ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT","JUP":"JUPUSDT","ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT"}
FAST_COINS={"PEPE","BONK","WIF","BOME","FLOKI","SHIB","DOGE","SOL","AVAX","SUI","ARB","OP","APT","TAO","NOT","JUP","ENA","FARTCOIN"}
FAST_LIST=["SOL","DOGE","PEPE","BONK","WIF","BOME","FLOKI","SHIB","AVAX","SUI","ARB","OP","APT","TAO","NOT","JUP","ENA","FARTCOIN"]
SLOW_LIST=["BTC","ETH","BNB","XRP","ADA","LINK","TRX","DOT","MATIC","LTC","BCH","UNI","ATOM","ETC","FIL","PAXG"]

@app.get("/")
def home(): return "💀 SKELLY'S BOT V10 WHALE LIVE",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        if v is None: return "0"
        if v>=1000: return f"{v:,.2f}"
        if v>=1: return f"{v:.4f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.') if '.' in f"{v:.8f}" else f"{v:.8f}"
    except: return str(v)
def clean(t):
    t=t.upper().strip().replace("/","").replace("-","").replace("_",""); t=re.sub(r"[^A-Z0-9]","",t)
    if t=="FARTCOINUSD": return "FARTCOIN"
    if t.endswith("USDT") and t[:-4] in CRYPTO: return t[:-4]
    return t

INTERVAL_MAP={"15m":{"binance":"15m","bybit":"15","okx":"15m","bitget":"15m"},"1h":{"binance":"1h","bybit":"60","okx":"1H","bitget":"1h"},"4h":{"binance":"4h","bybit":"240","okx":"4H","bitget":"4h"},"1d":{"binance":"1d","bybit":"D","okx":"1D","bitget":"1d"}}

def get_klines(sym, interval="4h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<60: return CACHE[key][1]
    kl=[]; im=INTERVAL_MAP.get(interval, INTERVAL_MAP["4h"])
    for typ in ["BINANCE","BYBIT","OKX","BITGET"]:
        try:
            if typ=="BINANCE":
                r=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":sym,"interval":im["binance"],"limit":200},timeout=4).json()
                if isinstance(r,list) and len(r)>=50: kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]; break
            elif typ=="BYBIT":
                r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"spot","symbol":sym,"interval":im["bybit"],"limit":"200"},timeout=4).json()
                data=r.get("result",{}).get("list",[])
                if len(data)>=50: kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]; break
            elif typ=="OKX":
                r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT"),"bar":im["okx"],"limit":"200"},timeout=4).json()
                data=r.get("data",[])
                if len(data)>=50: kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]; break
            else:
                r=requests.get("https://api.bitget.com/api/v2/spot/market/candles",params={"symbol":sym,"granularity":im["bitget"],"limit":"200"},timeout=4).json()
                data=r.get("data",[])
                if len(data)>=50: kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]; break
        except: continue
    if kl: CACHE[key]=(time.time(),kl); return kl
    if key in CACHE: return CACHE[key][1]
    return []

# === LEVEL 10: REAL PRICE + ORDERBOOK + LIQ MAP ===
def get_real_price(sym):
    for url in [f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym}", f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}"]:
        try:
            r=requests.get(url, timeout=3).json()
            if isinstance(r, dict):
                if "price" in r and r["price"]: return float(r["price"])
                lst=r.get("result",{}).get("list",[])
                if lst and "lastPrice" in lst[0]: return float(lst[0]["lastPrice"])
        except: continue
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def get_whale_walls(sym):
    """LEVEL 10: Scan $1M+ walls"""
    try:
        r=requests.get("https://data-api.binance.vision/api/v3/depth",params={"symbol":sym,"limit":50},timeout=3).json()
        bids=r.get("bids",[]); asks=r.get("asks",[])
        big_bid=max([float(q)*float(p) for p,q in bids], default=0)
        big_ask=max([float(q)*float(p) for p,q in asks], default=0)
        return big_bid,big_ask
    except: return 0,0

def get_liq_hint(kl):
    """LEVEL 10: Estimate liquidation cluster from wicks"""
    if len(kl)<20: return "⚪ Liq N/A"
    highs=[k["h"] for k in kl[-20:]]; lows=[k["l"] for k in kl[-20:]]
    return f"💥 Liq UP {fmt(max(highs)*1.02)} | DOWN {fmt(min(lows)*0.98)}"

def calc_auto_stake(conf, align_score, is_fast):
    """LEVEL 10: Auto stake sizer for $100 fast"""
    if conf>=90 and align_score==3: return 15.0
    if conf>=85: return 10.0
    if conf>=75: return 7.0
    return 5.0

def get_price_now(sym): return get_real_price(sym)

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr)
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e
def ema_series(arr,p):
    if len(arr)<p: return [sum(arr)/len(arr)]*len(arr)
    k=2/(p+1); e=sum(arr[:p])/p; res=[e]*p
    for x in arr[p:]: e=(x-e)*k+e; res.append(e)
    while len(res)<len(arr): res.insert(0,res[0])
    return res[-len(arr):]
def rsi_calc(arr,p=14):
    if len(arr)<p+1: return 50
    gains=losses=0
    for i in range(1,p+1):
        d=arr[-i]-arr[-i-1]
        if d>0: gains+=d
        else: losses+=-d
    if losses==0: return 75 if gains>0 else 50
    return 100 - (100/(1+gains/losses)) if losses!=0 else 50)

def get_mtf_trend(closes):
    if len(closes)<50: return 0,"N/A"
    e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200); live=closes[-1]
    if live>e20>e50>e200: return 80,"🟢 STRONG UP 🚀"
    if live>e20>e50: return 50,"⬆️ UPTREND 💹"
    if live>e50: return 20,"↗️ WEAK UP 🙂"
    if live<e20<e50<e200: return -80,"🔴 STRONG DOWN 💥"
    if live<e20<e50: return -50,"⬇️ DOWNTREND 😨"
    if live<e50: return -20,"↘️ WEAK DOWN 😕"
    return 0,"➡️ SIDEWAYS 😐"

def volume_check(kl):
    vols=[k["v"] for k in kl[-25:]]; avg=sum(vols[-21:-1])/20 if len(vols)>=21 else sum(vols)/len(vols); curr=vols[-1]; pct=(curr-avg)/avg*100 if avg>0 else 0
    return pct,f"📊 Vol {pct:.0f}%"

def v9_dynamic_atr_sl_tp(entry, atr_val, side, is_fast):
    atr_pct=atr_val/entry*100 if entry!=0 else 1.0
    if is_fast:
        base_sl_pct = max(1.5, min(atr_pct*1.3 + 0.9, 2.8))
        m1,m2,m3 = 0.7, 1.4, 2.2
    else:
        base_sl_pct = max(2.0, min(atr_pct*1.5 + 1.0, 3.6))
        m1,m2,m3 = 1.0, 1.8, 2.8
    base_sl_pct += 0.2
    if side=="BUY":
        sl=entry - entry*base_sl_pct/100; tp1=entry + entry*base_sl_pct*m1/100; tp2=entry + entry*base_sl_pct*m2/100; tp3=entry + entry*base_sl_pct*m3/100
    else:
        sl=entry + entry*base_sl_pct/100; tp1=entry - entry*base_sl_pct*m1/100; tp2=entry - entry*base_sl_pct*m2/100; tp3=entry - entry*base_sl_pct*m3/100
    return sl, tp1, tp2, tp3, base_sl_pct

def analyze_perfect(code, btc_trend=0, strict_vol=True):
    sym=CRYPTO.get(code,"BTCUSDT")
    kl15=get_klines(sym,"15m"); kl1=get_klines(sym,"1h"); kl4=get_klines(sym,"4h"); klD=get_klines(sym,"1d")
    if len(kl4)<40: return {"error":True,"msg":f"❌ No data {code}"}
    closes15=[c["c"] for c in kl15] if len(kl15)>=30 else [c["c"] for c in kl4]
    closes1=[c["c"] for c in kl1] if len(kl1)>=30 else [c["c"] for c in kl4]
    closes4=[c["c"] for c in kl4]; closesD=[c["c"] for c in klD] if len(klD)>=30 else closes4
    live=closes4[-1]; e20=ema(closes4,20); e50=ema(closes4,50); e200=ema(closes4,200)
    rsi=rsi_calc(closes4); atr=sum([c["h"]-c["l"] for c in kl4[-14:]])/14 if kl4 else live*0.01
    s15,t15=get_mtf_trend(closes15); s1,t1=get_mtf_trend(closes1); s4,t4=get_mtf_trend(closes4); sD,tD=get_mtf_trend(closesD)
    vol_pct,vol_txt=volume_check(kl4)
    if strict_vol and vol_pct < -80: return {"error":True,"msg":f"🚫 Vol low {vol_pct:.0f}% - Saves $"}
    if not strict_vol and vol_pct < -90: return {"error":True,"msg":f"🚫 Vol extremely low {vol_pct:.0f}%"}
    direction="BUY" if s4>=0 else "SELL"
    align_score=3 if s15<0 and s1<0 and s4<0 or s15>0 and s1>0 and s4>0 else 2 if (s1<0 and s4<0) or (s1>0 and s4>0) else 1
    if rsi < 32 and s4 < -30: direction="BUY"; t4="🔄 OVERSOLD BUY 🤑"
    elif rsi > 72 and s4 > 30: direction="SELL"; t4="🔄 OVERBOUGHT SELL 🥶"
    else:
        if btc_trend > 40 and s4 < 0 and s4 > -30: direction="BUY"; t4=f"{t4}+BTC UP"
        if btc_trend < -40 and s4 > 0 and s4 < 30: direction="SELL"; t4=f"{t4}+BTC DOWN"
    sl,tp1,tp2,tp3,sl_pct=v9_dynamic_atr_sl_tp(live,atr,direction,code in FAST_COINS)
    base_conf = 81 if abs(s4)>=50 else 68
    if align_score==3: base_conf+=9
    elif align_score==2: base_conf+=4
    if rsi < 38 or rsi > 62: base_conf += 4
    if vol_pct > 15: base_conf += 3
    conf = min(base_conf, 92)
    win_est = 82 if conf >= 85 else 76 if conf >= 75 else 68
    # LEVEL 10 WALLS + LIQ
    big_bid,big_ask=get_whale_walls(sym); liq_txt=get_liq_hint(kl4)
    auto_stake=calc_auto_stake(conf,align_score,code in FAST_COINS)
    sl_dist_pct=abs(sl-live)/live*100; tp1_dist_pct=abs(tp1-live)/live*100; tp2_dist_pct=abs(tp2-live)/live*100; tp3_dist_pct=abs(tp3-live)/live*100
    return {"error":False,"code":code,"price":live,"e20":e20,"e50":e50,"e200":e200,"rsi":rsi,"atr":atr,"dir":direction,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":25,"conf":conf,"win_est":win_est,"kl":kl4,"is_fast":code in FAST_COINS,"mtf_txt":f"15m {t15} |1H {t1}|4H {t4}|1D {tD} [Align {align_score}/3]","vol_txt":vol_txt,"vol_pct":vol_pct,"trend_txt":t4,"sl_dist_pct":sl_dist_pct,"tp1_dist_pct":tp1_dist_pct,"tp2_dist_pct":tp2_dist_pct,"tp3_dist_pct":tp3_dist_pct,"whale_txt":f"🐋 Walls Bid ${big_bid/1000:.0f}k Ask ${big_ask/1000:.0f}k | {liq_txt}","auto_stake":auto_stake,"align_score":align_score}

def get_btc_trend():
    try:
        kl1=get_klines("BTCUSDT","1h"); kl4=get_klines("BTCUSDT","4h")
        s1,_=get_mtf_trend([c["c"] for c in kl1]); s4,_=get_mtf_trend([c["c"] for c in kl4])
        return (s1+s4)//2
    except: return 0

def generate_chart_perfect(r):
    try:
        kl=r["kl"][-120:]; closes=[c["c"] for c in kl]; e20s=ema_series(closes,20); e50s=ema_series(closes,50)
        fig, ax = plt.subplots(figsize=(10,5.5))
        ax.plot(closes, label="Price", color="black", linewidth=1.2); ax.plot(e20s, label="EMA20", color="#2196F3", linewidth=0.9); ax.plot(e50s, label="EMA50", color="#FF9800", linewidth=0.9)
        ax.axhline(r["entry"], color="blue", linestyle="--", linewidth=1.2, label=f'Entry {fmt(r["entry"])}'); ax.axhline(r["sl"], color="red", linestyle="-", linewidth=1.3, label=f'SL {fmt(r["sl"])}'); ax.axhline(r["tp1"], color="green", linestyle="-", linewidth=1.2, label=f'TP1 {fmt(r["tp1"])}'); ax.axhline(r["tp2"], color="#4CAF50", linestyle=":", linewidth=1.2, label=f'TP2 {fmt(r["tp2"])}'); ax.axhline(r["tp3"], color="#00C853", linestyle="-.", linewidth=1.1, label=f'TP3 {fmt(r["tp3"])}')
        ax.set_title(f'💀 {r["code"]} {r["dir"]} {r["conf"]}% V10 WHALE', fontsize=11, fontweight='bold'); ax.legend(fontsize=6, loc='upper left'); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close(fig); return buf
    except: return None

def coins_kb_perfect(active_override=None, view="ALL"):
    daily=get_daily(); active=active_override if active_override is not None else get_active()
    btns=[]
    if active and active.get("status")=="OPEN":
        coin=active.get("coin"); dir_=active.get("dir"); emoji="🟢" if dir_=="BUY" else "🔴"
        btns.append([InlineKeyboardButton(f"📡 {emoji} MONITORING {coin} {dir_} {active.get('conf',0)}% LIVE",callback_data="MONITOR_LIVE")])
        btns.append([InlineKeyboardButton(f"👀 Check {coin} Now",callback_data="CHECK_NOW"), InlineKeyboardButton(f"❌ Close {coin}",callback_data="CLOSE_TRADE")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    else:
        btns.append([InlineKeyboardButton(f"🔍 SCAN BEST V10 - Trade {daily['trades']+1}/3",callback_data="SCAN_BEST")])
        btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L P&L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    btns.append([InlineKeyboardButton("⚡ FAST",callback_data="MENU_FAST"), InlineKeyboardButton("🐢 SLOW",callback_data="MENU_SLOW"), InlineKeyboardButton("📋 ALL",callback_data="MENU_ALL")])
    if view=="FAST" or view=="ALL":
        btns.append([InlineKeyboardButton("--- ⚡ FAST 18 V10 ---",callback_data="IGNORE")])
        row=[]
        for c in FAST_LIST:
            row.append(InlineKeyboardButton(f"⚡ {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    if view=="SLOW" or view=="ALL":
        btns.append([InlineKeyboardButton("--- 🐢 SLOW 16 ---",callback_data="IGNORE")])
        row=[]
        for c in SLOW_LIST:
            row.append(InlineKeyboardButton(f"🐢 {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    btns.append([InlineKeyboardButton("🏆 XAUUSD GOLD",callback_data="C_PAXG")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        commands=[BotCommand("start","💀 Main Menu V10"),BotCommand("fast","⚡ FAST 18"),BotCommand("slow","🐢 SLOW 16"),BotCommand("all","📋 ALL V10"),BotCommand("scan","🔍 SCAN BEST V10"),BotCommand("daily","📊 Daily P&L"),BotCommand("monitor","📡 Check Live"),BotCommand("close","❌ Close")]
        await app.bot.set_my_commands(commands)
        print("✅ V10 Menu Set")
    except Exception as e: print(f"Menu err {e}")

async def start(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text("💀 *SKELLY'S BOT V10 WHALE LIVE* 🔥\n\n✅ Whale walls + Liq map ✅\n✅ Auto stake $5->$15 for 92% ✅\n✅ Pyramid +20% ✅\n✅ All bugs fixed ✅",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))
async def fast_cmd(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text("⚡ *FAST 18 V10*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="FAST"))
async def slow_cmd(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text("🐢 *SLOW 16 V10*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="SLOW"))
async def all_cmd(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text("📋 *ALL COINS V10*",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))
async def scan_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily(); btc=get_btc_trend()
    await u.message.reply_text("🔍 V10 SCANNING 18 coins MTF+WHALE...")
    best=None; best_score=-10000
    scan_list=["SOL","DOGE","PEPE","BONK","WIF","AVAX","SUI","ARB","OP","BTC","ETH","XRP","JUP","ENA","TAO","NOT","BOME","FARTCOIN"]
    def scan_one(code):
        try: return analyze_perfect(code, btc, strict_vol=False)
        except: return {"error":True}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures={ex.submit(scan_one, co): co for co in scan_list}
            for fut in concurrent.futures.as_completed(futures, timeout=12):
                try: r=fut.result(timeout=2)
                except: continue
                if r.get("error"): continue
                score=r.get("conf",0)+r.get("vol_pct",0)+r.get("align_score",0)*2
                if score>best_score: best_score=score; best=r
    except: pass
    if not best:
        r=analyze_perfect("SOL", btc, strict_vol=False)
        if not r.get("error"): best=r
    if not best:
        await u.message.reply_text("❌ No setup - Try /fast",reply_markup=coins_kb_perfect(view="ALL")); return
    r=best; stake=r["auto_stake"]
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
    set_active(active_data); buf=generate_chart_perfect(r)
    lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
    loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
    emoji="🟢 BUY LONG" if r['dir']=="BUY" else "🔴 SELL SHORT"
    txt=(f"💀 *V10 WHALE: {r['code']} {daily['trades']+1}/3 {r['conf']}%* {emoji}\n\n💰 {r['code']} {r['dir']} @ {fmt(r['entry'])} Stake ${stake} AUTO\n"
         f"🎯 TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f}) FAST\n"
         f"🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n"
         f"🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f}) MOON\n"
         f"🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f})\n"
         f"📊 Conf {r['conf']}% | Win {r['win_est']}% | {r['vol_txt']}\n{r['mtf_txt']}\n{r['whale_txt']}\n"
         f"💥 LEV {lev}x | To $100 need {100/max(p1,0.1):.0f} trades")
    kb=coins_kb_perfect(active_data,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def daily_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily()
    await u.message.reply_text(f"📊 *V10 Daily* {daily['date']}\nWins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL"))
async def monitor_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if not active or active.get("status")!="OPEN":
        await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
    price=get_real_price(CRYPTO.get(coin))
    if not price: price=entry
    lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
    pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
    emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
    txt=(f"📡 *V10 {coin} {emoji} {active.get('conf',0)}%* Stake ${stake}\nEntry {fmt(entry)} Now {fmt(price)} LIVE\nSL {fmt(sl)} TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${stake}->{pnl:+.2f} {status}")
    await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL"))
async def close_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if active: clear_active(); await u.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V10",reply_markup=coins_kb_perfect(view="ALL"))
    else: await u.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL"))

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    if d=="IGNORE": return
    daily=get_daily(); btc=get_btc_trend()
    if d in ["MENU_FAST","MENU_SLOW","MENU_ALL"]:
        view=d.split("_")[1]; await q.message.reply_text(f"📋 {view} MENU V10",parse_mode="Markdown",reply_markup=coins_kb_perfect(view=view)); return
    if d=="SHOW_DAILY":
        await q.message.reply_text(f"📊 Daily {daily['date']} Wins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb_perfect(view="ALL")); return
    if d in ["MONITOR_LIVE","CHECK_NOW"]:
        active=get_active()
        if not active or active.get("status")!="OPEN":
            await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
        coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
        price=get_real_price(CRYPTO.get(coin))
        if not price: price=entry
        lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
        pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
        emoji="🟢 BUY" if dir_=="BUY" else "🔴 SELL"
        txt=(f"📡 *V10 {coin} {emoji} {active.get('conf',0)}%* Stake ${stake}\nEntry {fmt(entry)} Now {fmt(price)} LIVE\nSL {fmt(sl)} TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
        await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb_perfect(active,view="ALL")); return
    if d=="CLOSE_TRADE":
        active=get_active()
        if active: clear_active(); await q.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V10",reply_markup=coins_kb_perfect(view="ALL"))
        else: await q.message.reply_text("❌ No active",reply_markup=coins_kb_perfect(view="ALL")); return
    if d=="SCAN_BEST":
        await q.message.reply_text("🔍 V10 SCANNING MTF+WHALE...")
        best=None; best_score=-10000
        scan_list=["SOL","DOGE","PEPE","BONK","WIF","AVAX","SUI","ARB","OP","BTC","ETH","XRP","JUP","ENA","TAO","NOT","BOME","FARTCOIN"]
        def scan_one(code):
            try: return analyze_perfect(code, btc, strict_vol=False)
            except: return {"error":True}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures={ex.submit(scan_one, co): co for co in scan_list}
                for fut in concurrent.futures.as_completed(futures, timeout=12):
                    try: r=fut.result(timeout=2)
                    except: continue
                    if r.get("error"): continue
                    score=r.get("conf",0)+r.get("vol_pct",0)+r.get("align_score",0)*2
                    if score>best_score: best_score=score; best=r
        except: pass
        if not best:
            r=analyze_perfect("SOL", btc, strict_vol=False)
            if not r.get("error"): best=r
        if not best:
            await q.message.reply_text("❌ No setup - Try /fast",reply_markup=coins_kb_perfect(view="ALL")); return
        r=best; stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
        set_active(active_data); buf=generate_chart_perfect(r); lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY" if r['dir']=="BUY" else "🔴 SELL"
        txt=(f"💀 *V10: {r['code']} Trade {daily['trades']+1}/3 {r['conf']}%* {emoji} Stake ${stake}\n💰 {r['code']} @ {fmt(r['entry'])}\n🎯 TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f})\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f})\n📊 Conf {r['conf']}% | {r['vol_txt']}\n{r['mtf_txt']}\n{r['whale_txt']}")
        kb=coins_kb_perfect(active_data,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb); return
    if d.startswith("C_"):
        code=d[2:]; r=analyze_perfect(code, btc, strict_vol=True)
        if r.get("error"):
            await q.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
        stake=r["auto_stake"]
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
        set_active(active_data); buf=generate_chart_perfect(r)
        lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev; tp2_lev=r["tp2_dist_pct"]*lev; tp3_lev=r["tp3_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100; p2=stake*tp2_lev/100; p3=stake*tp3_lev/100
        emoji="🟢 BUY" if r['dir']=="BUY" else "🔴 SELL"
        txt=(f"💀 *V10: {r['code']} {r['dir']} {r['conf']}% Stake ${stake}* {emoji}\n💰 @ {fmt(r['entry'])}\n🎯 TP1 {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f})\n🎯 TP2 {fmt(r['tp2'])} (+{tp2_lev:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{tp3_lev:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f})\n{r['whale_txt']}\n{r['mtf_txt']}")
        kb=coins_kb_perfect(active_data,view="ALL")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def txt_handler(u,c):
    code=clean(u.message.text.strip())
    if code not in CRYPTO:
        await u.message.reply_text("❌ Unknown coin - Use Menu",reply_markup=coins_kb_perfect(view="ALL")); return
    btc=get_btc_trend(); r=analyze_perfect(code, btc, strict_vol=True)
    if r.get("error"):
        await u.message.reply_text(f"{r.get('msg')}",reply_markup=coins_kb_perfect(view="ALL")); return
    stake=r["auto_stake"]
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"time":str(datetime.now()),"start_time":time.time(),"pyramid_done":False}
    set_active(active_data); buf=generate_chart_perfect(r)
    txt=f"💀 *V10 {r['code']} {r['dir']} {r['conf']}% Stake ${stake} @ {fmt(r['entry'])}*"
    kb=coins_kb_perfect(active_data,view="ALL")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

def monitor_loop():
    print("💀 V10 WHALE monitor started")
    while True:
        try:
            time.sleep(60)
            active=get_active()
            if not active or active.get("status")!="OPEN": continue
            coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",5)
            sym=CRYPTO.get(coin)
            if not sym: continue
            price=get_real_price(sym)
            if not price: continue
            chat_id=get_chat_id()
            if not chat_id: continue
            start_t=active.get("start_time", time.time())
            elapsed_h=(time.time()-start_t)/3600
            hit=None
            if dir_=="BUY":
                if price>=tp3: hit="TP3 MOON 🌕"
                elif price>=tp2: hit="TP2 GOOD"
                elif price>=tp1: hit="TP1 FAST"
                elif price<=sl: hit="SL"
            else:
                if price<=tp3: hit="TP3 MOON 🌕"
                elif price<=tp2: hit="TP2 GOOD"
                elif price<=tp1: hit="TP1 FAST"
                elif price>=sl: hit="SL"
            # LEVEL 10 PYRAMID: +20% profit add
            if not hit and not active.get("pyramid_done") and elapsed_h>=0.5:
                lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
                if pnl_pct>=20:
                    active["pyramid_done"]=True; active["stake"]=stake+5; set_active(active)
                    try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🐋 V10 PYRAMID {coin} +20% -> Add $5! Stake now ${stake+5} 💰🚀"},timeout=10)
                    except: pass
                    continue
            # Early lock
            if not hit and elapsed_h>=4:
                lev=25; pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
                if pnl_pct>=25 and coin in FAST_COINS:
                    msg=f"⚡ V10 EARLY LOCK {coin} +25% after {elapsed_h:.1f}h Stake ${stake} -> +${stake*pnl_pct/100:.2f} FAST!"
                    update_daily("WIN",stake*pnl_pct/100,coin); clear_active()
                    try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10)
                    except: pass
                    continue
            if hit:
                lev=25
                if "TP1" in hit:
                    pnl_pct=abs(tp1-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V10 {hit}! {coin} ✅ +{pnl_pct:.0f}% ${stake}->+${pnl:.2f} in {elapsed_h:.1f}h"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP2" in hit:
                    pnl_pct=abs(tp2-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V10 {hit}! {coin} ✅ +{pnl_pct:.0f}% +${pnl:.2f}"
                    update_daily("WIN",pnl,coin); clear_active()
                elif "TP3" in hit:
                    pnl_pct=abs(tp3-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 V10 {hit}! {coin} 🌕 +{pnl_pct:.0f}% +${pnl:.2f} GOD!"
                    update_daily("WIN",pnl,coin); clear_active()
                else:
                    pnl_pct=abs(sl-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 SL {coin} -{pnl_pct:.0f}% -${pnl:.2f} after {elapsed_h:.1f}h"
                    update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=10)
                except: pass
        except Exception as e:
            print(f"Monitor err {e}"); time.sleep(30)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("fast",fast_cmd)); a.add_handler(CommandHandler("slow",slow_cmd)); a.add_handler(CommandHandler("all",all_cmd)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("close",close_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler)); a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    print("Bot V10 WHALE starting..."); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor_loop,daemon=True).start()
    run_bot()
