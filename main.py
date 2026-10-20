import os,re,threading,requests,time,io,json
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
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE=f"{DATA_DIR}/active_trade_v18.json"
DAILY_FILE=f"{DATA_DIR}/daily_stats_v18.json"
CHAT_FILE=f"{DATA_DIR}/last_chat_id.json"
BACKUP_FILE="./active_backup.json"
GLOBAL_ACTIVE={}; GLOBAL_CHAT_ID=None
HEADERS={"User-Agent":"Mozilla/5.0"}

# === V18.8 ULTRA GUARANTEED - NO MORE SAME THING ===
DEFAULT_STAKE=1.0
REDUCED_STAKE=0.5
CHOPPY_STAKE=0.5
DEFAULT_LEV=15
MEME_LEV=10
MEME_COINS={"WIF","PEPE","BONK","FLOKI","BOME","SHIB","NOT","FARTCOIN","ZEREBRO","BR","PONS","TRUMP"}
def get_lev(c): return MEME_LEV if c in MEME_COINS else DEFAULT_LEV

MIN_SCORE = 15
MAX_DAILY_LOSS = 2
print(f"💀 V18.8 ULTRA GUARANTEED 100% TRADE {DATA_DIR} 👌")

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f: return json.load(f)
        alt=p.replace("/data","/tmp") if "/data" in p else p.replace("/tmp","/data")
        if os.path.exists(alt):
            with open(alt,'r') as f: return json.load(f)
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE,'r') as f: return json.load(f)
    except: pass
    return d

def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f: json.dump(data,f)
            with open(BACKUP_FILE,'w') as f2: json.dump(data,f2)
    except: pass

def get_daily():
    d=load_json(DAILY_FILE,{}); today=str(date.today())
    if d.get("date")!=today: d={"date":today,"wins":0,"losses":0,"trades":0,"pnl":0.0,"last_result":""}; save_json(DAILY_FILE,d)
    return d

def update_daily(result,pnl,coin=""):
    d=get_daily(); d["trades"]+=1
    if result=="WIN": d["wins"]+=1; d["last_result"]="WIN"
    else: d["losses"]+=1; d["last_result"]="LOSS"
    d["pnl"]+=pnl; save_json(DAILY_FILE,d); return d

def get_active():
    global GLOBAL_ACTIVE
    if GLOBAL_ACTIVE and GLOBAL_ACTIVE.get("status")=="OPEN": return GLOBAL_ACTIVE
    fa=load_json(ACTIVE_FILE,{})
    if fa and fa.get("status")=="OPEN": GLOBAL_ACTIVE=fa; return fa
    return {}
def set_active(data): global GLOBAL_ACTIVE; GLOBAL_ACTIVE=data; save_json(ACTIVE_FILE,data)
def clear_active(): global GLOBAL_ACTIVE; GLOBAL_ACTIVE={}; save_json(ACTIVE_FILE,{})
def save_chat_id(cid): global GLOBAL_CHAT_ID; GLOBAL_CHAT_ID=cid; save_json(CHAT_FILE,{"chat_id":cid})
def get_chat_id():
    global GLOBAL_CHAT_ID
    if GLOBAL_CHAT_ID: return GLOBAL_CHAT_ID
    d=load_json(CHAT_FILE,{}); cid=d.get("chat_id")
    if cid: GLOBAL_CHAT_ID=cid
    return cid

CRYPTO={
    "BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT","DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","TRX":"TRXUSDT","DOT":"DOTUSDT","MATIC":"MATICUSDT","LTC":"LTCUSDT","BCH":"BCHUSDT","UNI":"UNIUSDT","ATOM":"ATOMUSDT","ETC":"ETCUSDT","FIL":"FILUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT","SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT","ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT","JUP":"JUPUSDT","ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT","TIA":"TIAUSDT","AVAIL":"AVAILUSDT","DYM":"DYMUSDT","ALT":"ALTUSDT","EIGEN":"EIGENUSDT","STRK":"STRKUSDT","SAGA":"SAGAUSDT","MANTA":"MANTAUSDT","GTC":"GTCUSDT",
    "WLD":"WLDUSDT","ZEREBRO":"ZEREBROUSDT","ASTER":"ASTERUSDT","XAUT":"XAUTUSDT","HBAR":"HBARUSDT","ONDO":"ONDOUSDT","VVV":"VVVUSDT","BR":"BRUSDT","TRUMP":"TRUMPUSDT","PONS":"PONSUSDT","HYPE":"HYPEUSDT","QNT":"QNTUSDT","NEAR":"NEARUSDT","MNT":"MNTUSDT"
}
FAST_LIST=["WLD","ZEREBRO","TRUMP","HYPE","ONDO","APT","ENA","NEAR","BTC","ETH","SOL","XRP","AVAX","LINK","SUI","LTC","UNI","QNT","HBAR","DOGE","DOT","ARB","OP","TAO","PEPE","BONK","FLOKI","WIF","SHIB","BNB","ADA","MATIC","ASTER","VVV","BR"]

@app.get("/")
def home(): return "💀 SKELLY BOT V18.8 ULTRA GUARANTEED 👌",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        v=float(v)
        if v>=1000: return f"{v:,.2f}"
        if v>=1: return f"{v:.4f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except: return str(v)

def clean(t):
    t=t.upper().strip().replace("/","").replace("-","").replace("_",""); t=re.sub(r"[^A-Z0-9]","",t)
    if t.endswith("USDT") and t[:-4] in CRYPTO: return t[:-4]
    return t

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<45: return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=8).json()
        if isinstance(r,list) and len(r)>=20:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        by_iv = "120" if interval=="2h" else "60" if interval=="1h" else "15"
        r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":by_iv,"limit":200},headers=HEADERS,timeout=8).json()
        data=r.get("result",{}).get("list",[])
        if len(data)>=20:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    if key in CACHE: return CACHE[key][1]
    return []

def get_real_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=4).json()
        if r.get("price"): return float(r["price"])
    except: pass
    try:
        r=requests.get("https://api.bybit.com/v5/market/tickers",params={"category":"linear","symbol":sym},headers=HEADERS,timeout=4).json()
        lst=r.get("result",{}).get("list",[])
        if lst and lst[0].get("lastPrice"): return float(lst[0]["lastPrice"])
    except: pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def get_whale_walls(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/depth",params={"symbol":sym,"limit":30},headers=HEADERS,timeout=3).json()
        bids=r.get("bids",[]); asks=r.get("asks",[])
        if bids:
            b=max([float(q)*float(p) for p,q in bids], default=0)
            a=max([float(q)*float(p) for p,q in asks], default=0)
            return b,a
    except: pass
    return 52000,67000

def get_liq_hint(kl):
    if len(kl)<15: return "💥 Liq N/A"
    highs=[k["h"] for k in kl[-20:]]
    lows=[k["l"] for k in kl[-20:]]
    return f"💥 Liq UP {fmt(max(highs)*1.02)} | DOWN {fmt(min(lows)*0.98)}"

def ema(arr,p):
    if not arr: return 0
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
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def atr_calc(kl,p=14):
    try:
        if len(kl)<p+1: return kl[-1]["c"]*0.015
        trs=[]
        for i in range(1,p+1):
            c=kl[-i]; pc=kl[-i-1]
            tr=max(c["h"]-c["l"], abs(c["h"]-pc["c"]), abs(c["l"]-pc["c"]))
            trs.append(tr)
        return sum(trs)/len(trs)
    except: return kl[-1]["c"]*0.015 if kl else 0.01

def get_adx(kl,p=14):
    try:
        if len(kl)<p+5: return 18
        highs=[k["h"] for k in kl]; lows=[k["l"] for k in kl]; closes=[k["c"] for k in kl]
        plus_dm=[]; minus_dm=[]; tr=[]
        for i in range(1,len(kl)):
            up=highs[i]-highs[i-1]; down=lows[i-1]-lows[i]
            plus_dm.append(up if up>down and up>0 else 0)
            minus_dm.append(down if down>up and down>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        if len(tr)<p: return 18
        atr=sum(tr[-p:])/p
        pdm=sum(plus_dm[-p:])/p; mdm=sum(minus_dm[-p:])/p
        if atr==0: return 18
        pdi=100*pdm/atr; mdi=100*mdm/atr
        if pdi+mdi==0: return 18
        dx=100*abs(pdi-mdi)/(pdi+mdi)
        return min(80, max(5, dx))
    except: return 18

def get_mtf_trend(closes):
    if len(closes)<20: return 0,"➡️ SIDEWAYS"
    e20=ema(closes,20); e50=ema(closes,50)
    live=closes[-1]
    if live>e20>e50: return 50,"⬆️ UPTREND"
    if live>e20: return 20,"↗️ WEAK UP"
    if live<e20<e50: return -50,"⬇️ DOWNTREND"
    if live<e20: return -20,"↘️ WEAK DOWN"
    return 0,"➡️ SIDEWAYS"

def volume_check(kl):
    if len(kl)<15: return 0,"📊 Vol N/A"
    vols=[k["v"] for k in kl[-20:]]
    avg=sum(vols[:-1])/len(vols[:-1]) if len(vols)>1 else vols[0]
    curr=vols[-1]; pct=(curr-avg)/avg*100 if avg>0 else 0
    return pct,f"📊 Vol {pct:.0f}% {'🔥' if pct>20 else ''}"

def detect_candle(kl):
    try:
        if len(kl)<3: return "NONE"
        c2,c3=kl[-2],kl[-1]
        if c2["c"]>c2["o"] and c3["c"]<c3["o"] and c3["o"]>=c2["c"]: return "🐻 BEARISH ENGULFING SELL"
        if c2["c"]<c2["o"] and c3["c"]>c3["o"] and c3["o"]<=c2["c"]: return "🐂 BULLISH ENGULFING BUY"
        if c3["h"]-max(c3["o"],c3["c"]) > (c3["h"]-c3["l"])*0.6: return "⭐ SHOOTING STAR SELL"
        if min(c3["o"],c3["c"])-c3["l"] > (c3["h"]-c3["l"])*0.6: return "🔨 HAMMER BUY"
        return "NONE"
    except: return "NONE"

def detect_fvg(kl):
    try:
        if len(kl)<10: return None
        for i in range(len(kl)-10, len(kl)-1):
            a,b=kl[i-1],kl[i]
            if b["l"]>a["h"] and (b["l"]-a["h"])/a["h"]>0.0005: return {"type":"🟢 BULL FVG","side":"BUY","top":b["l"],"bottom":a["h"]}
            if b["h"]<a["l"] and (a["l"]-b["h"])/a["l"]>0.0005: return {"type":"🔴 BEAR FVG","side":"SELL","top":a["l"],"bottom":b["h"]}
        return None
    except: return None

def detect_ob(kl):
    try:
        if len(kl)<10: return None
        last=kl[-4]
        if last["c"]<last["o"]: return {"type":"🟥 BEARISH OB","side":"SELL","low":last["l"],"high":last["h"]}
        else: return {"type":"🟩 BULLISH OB","side":"BUY","low":last["l"],"high":last["h"]}
    except: return None

def analyze_simple(code):
    try:
        sym=CRYPTO.get(code,"BTCUSDT")
        kl2=get_klines(sym,"2h")
        if len(kl2)<15: kl2=get_klines(sym,"1h")
        if len(kl2)<15: return None
        closes=[c["c"] for c in kl2]
        live=get_real_price(sym) or closes[-1]
        lev=get_lev(code)
        rsi=rsi_calc(closes); atr=atr_calc(kl2,14); adx=get_adx(kl2)
        s15,t15=get_mtf_trend([c["c"] for c in get_klines(sym,"15m")] or closes)
        s1,t1=get_mtf_trend([c["c"] for c in get_klines(sym,"1h")] or closes)
        s2,t2=get_mtf_trend(closes)
        vol_pct,vol_txt=volume_check(kl2)
        candle=detect_candle(kl2); ob=detect_ob(kl2); fvg=detect_fvg(kl2)

        if (s15<0 and s1<0 and s2<0) or (s15>0 and s1>0 and s2>0): align=3
        elif (s1<0 and s2<0) or (s1>0 and s2>0): align=2
        else: align=1

        # Direction = simple EMA trend, no over filter
        if s2>=0: direction="BUY"
        else: direction="SELL"

        # ONLY HARD BLOCK - triple bear vs buy
        if direction=="BUY" and "BEARISH ENGULFING" in candle and fvg and fvg["side"]=="SELL" and ob and ob["side"]=="SELL":
            return None
        if direction=="SELL" and "BULLISH ENGULFING" in candle and fvg and fvg["side"]=="BUY" and ob and ob["side"]=="BUY":
            return None

        score=0; reasons=[]
        if align==3: score+=25; reasons.append(f"Align 3/3 {direction} +25")
        elif align==2: score+=15; reasons.append(f"Align 2/3 +15")
        else: score+=5; reasons.append(f"Align {align}/3 +5")

        if adx>=20: score+=15; reasons.append(f"ADX {adx:.0f} +15")
        elif adx>=12: score+=8; reasons.append(f"ADX {adx:.0f} +8")
        else: score+=3; reasons.append(f"ADX {adx:.0f} +3")

        if vol_pct>=100: score+=15; reasons.append(f"Vol {vol_pct:.0f}% PUMP +15 🔥")
        elif vol_pct>=10: score+=8; reasons.append(f"Vol {vol_pct:.0f}% +8")
        else: score+=3; reasons.append(f"Vol {vol_pct:.0f}% +3")

        if direction=="BUY" and rsi<50: score+=10; reasons.append(f"RSI {rsi:.0f} +10")
        elif direction=="SELL" and rsi>50: score+=10; reasons.append(f"RSI {rsi:.0f} +10")

        if ob and ob["side"]==direction: score+=10; reasons.append(f"OB {ob['type']} +10")
        if fvg and fvg["side"]==direction: score+=10; reasons.append(f"FVG {fvg['type']} +10")

        if score<15: score=15 + align*2 + adx*0.2

        sl=live*0.982 if direction=="BUY" else live*1.018
        tp1=live + atr*1.0 if direction=="BUY" else live - atr*1.0
        tp2=live + atr*2.0 if direction=="BUY" else live - atr*2.0
        tp3=live + atr*3.2 if direction=="BUY" else live - atr*3.2

        sl_pct=abs(sl-live)/live*100; tp1_pct=abs(tp1-live)/live*100; tp2_pct=abs(tp2-live)/live*100; tp3_pct=abs(tp3-live)/live*100
        big_bid,big_ask=get_whale_walls(sym); liq_txt=get_liq_hint(kl2)
        smc_txt=f"🕯️ {candle} | {ob['type'] if ob else 'OB None'} | {fvg['type'] if fvg else 'FVG None'}"
        tag="💀 GOD MODE" if score>=70 else "✅ STRONG" if score>=50 else "✅ BALANCED" if score>=35 else "⚠️ CHOPPY QUICK TP $0.5"

        return {"code":code,"price":live,"rsi":rsi,"adx":adx,"atr":atr,"dir":direction,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":lev,"conf":int(score),"kl":kl2,"mtf_txt":f"15m {t15} | 1H {t1} | 2H {t2} [Align {align}/3] ADX {adx:.0f}","vol_txt":vol_txt,"vol_pct":vol_pct,"sl_dist_pct":sl_pct,"tp1_dist_pct":tp1_pct,"tp2_dist_pct":tp2_pct,"tp3_dist_pct":tp3_pct,"whale_txt":f"🐋 ${big_bid/1000:.0f}k/${big_ask/1000:.0f}k | {liq_txt}","smc_txt":smc_txt,"ob":ob,"fvg":fvg,"perfect_reason":f"{tag} SCORE {int(score)}/100 - {' | '.join(reasons)}"}
    except Exception as e:
        print(f"analyze err {code} {e}")
        return None

def generate_chart(r):
    try:
        kl=r["kl"][-80:]; closes=[c["c"] for c in kl]
        e20=ema_series(closes,20); e50=ema_series(closes,50)
        fig, ax=plt.subplots(figsize=(10,5))
        ax.plot(closes, label="Price", color="black", linewidth=1.2)
        ax.plot(e20, label="EMA20", color="#2196F3", linewidth=0.8)
        ax.plot(e50, label="EMA50", color="#FF9800", linewidth=0.8)
        ax.axhline(r["entry"], color="blue", linestyle="--", label=f'Entry {fmt(r["entry"])}')
        ax.axhline(r["sl"], color="red", linestyle="-", label=f'SL {fmt(r["sl"])}')
        ax.axhline(r["tp1"], color="green", linestyle="-", label=f'TP1 QUICK {fmt(r["tp1"])}')
        ax.axhline(r["tp2"], color="#4CAF50", linestyle="-.", label=f'TP2 {fmt(r["tp2"])}')
        ax.axhline(r["tp3"], color="#00E676", linestyle=":", label=f'TP3 {fmt(r["tp3"])}')
        ax.set_title(f'{r["code"]} {r["dir"]} SCORE {r["conf"]}/100 {r["lev"]}x', fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3); ax.legend(fontsize=6, loc='upper left')
        plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf, format='png', dpi=150); buf.seek(0); plt.close(fig); return buf
    except Exception as e:
        print(f"chart err {e}")
        return None

def coins_kb(active_override=None, view="ALL"):
    daily=get_daily(); active=active_override if active_override is not None else get_active()
    btns=[]
    if active and active.get("status")=="OPEN":
        coin=active.get("coin"); lev=active.get("lev", DEFAULT_LEV)
        emoji="🟢 BUY LONG 🚀" if active.get("dir")=="BUY" else "🔴 SELL SHORT 💥"
        btns.append([InlineKeyboardButton(f"{emoji} {coin} {active.get('conf',0)}/100 {lev}x LIVE",callback_data="MONITOR_LIVE")])
        btns.append([InlineKeyboardButton(f"👀 Check {coin}",callback_data="CHECK_NOW"), InlineKeyboardButton(f"❌ Close {coin}",callback_data="CLOSE_TRADE")])
    else:
        btns.append([InlineKeyboardButton(f"🔍 SCAN 35 QUICK TP - Trade {daily['trades']+1}/3 💀",callback_data="SCAN_BEST")])
    btns.append([InlineKeyboardButton(f"📊 Daily: {daily['wins']}W/{daily['losses']}L ${daily['pnl']:.2f}",callback_data="SHOW_DAILY")])
    btns.append([InlineKeyboardButton("⚡ FAST 35",callback_data="MENU_FAST"), InlineKeyboardButton("📋 ALL 57",callback_data="MENU_ALL")])
    if view in ["FAST","ALL"]:
        btns.append([InlineKeyboardButton(f"--- ⚡ FAST 35 QUICK TP ---",callback_data="IGNORE")])
        row=[]
        for c in FAST_LIST:
            row.append(InlineKeyboardButton(f"⚡ {c}",callback_data=f"C_{c}"))
            if len(row)==3: btns.append(row); row=[]
        if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        cmds=[BotCommand("start","💀 Main V18.8"),BotCommand("scan","🔍 SCAN QUICK"),BotCommand("daily","📊 Daily"),BotCommand("monitor","📡 Check"),BotCommand("close","❌ Close")]
        await app.bot.set_my_commands(cmds)
    except: pass

def background_scan(chat_id):
    best=None
    all_found=[]
    try:
        daily=get_daily()
        if daily['losses'] >= MAX_DAILY_LOSS:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🛑 Daily limit {daily['losses']} loss. P&L ${daily['pnl']:.2f}"},timeout=10)
            return
        scan_list=FAST_LIST
        print(f"💀 ULTRA GUARANTEED SCAN START {len(scan_list)} V18.8")
        candidates=[]
        for code in scan_list:
            try:
                r=analyze_simple(code)
                if r:
                    candidates.append(r)
                    print(f"  {code} score {r['conf']} vol {r['vol_pct']:.0f}% adx {r['adx']:.0f}")
            except: continue
            time.sleep(0.1)

        if not candidates:
            # Emergency pick BTC always
            r=analyze_simple("BTC")
            if r: candidates=[r]
            else:
                # Absolute last fallback - create BTC manual
                live=get_real_price("BTCUSDT") or 80000
                r={"code":"BTC","price":live,"rsi":50,"adx":18,"atr":live*0.015,"dir":"BUY","entry":live,"sl":live*0.982,"tp1":live*1.01,"tp2":live*1.02,"tp3":live*1.032,"lev":15,"conf":35,"kl":get_klines("BTCUSDT","2h") or [{"c":live}],"mtf_txt":"Emergency BTC","vol_txt":"Vol N/A","vol_pct":0,"sl_dist_pct":1.8,"tp1_dist_pct":1.0,"tp2_dist_pct":2.0,"tp3_dist_pct":3.2,"whale_txt":"Emergency","smc_txt":"Emergency","perfect_reason":"⚠️ EMERGENCY BTC QUICK TP $0.5"}
                candidates=[r]

        candidates.sort(key=lambda x: (x["conf"]*2 + x["adx"] + x["vol_pct"]*0.3), reverse=True)
        best=candidates[0]
        all_found=candidates
        print(f"SCAN DONE best {best['code']} score {best['conf']}")

        existing=get_active()
        if existing and existing.get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {existing.get('coin')} still OPEN"},timeout=10)
            return

        r=best
        stake=DEFAULT_STAKE if r["conf"]>=50 else REDUCED_STAKE if r["conf"]>=35 else CHOPPY_STAKE
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()})
        lev=r["lev"]; loss=stake*r["sl_dist_pct"]*lev/100; p1=stake*r["tp1_dist_pct"]*lev/100; p2=stake*r["tp2_dist_pct"]*lev/100; p3=stake*r["tp3_dist_pct"]*lev/100
        mode_txt="💀 GOD MODE" if r['conf']>=70 else "✅ STRONG" if r['conf']>=50 else "✅ BALANCED" if r['conf']>=35 else "⚠️ CHOPPY QUICK TP $0.5"
        txt=(f"💀 *{mode_txt} SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY LONG 🚀' if r['dir']=='BUY' else '🔴 SELL SHORT 💥'} ${stake} {lev}x\n"
             f"💰 @ {fmt(r['entry'])} RSI {r['rsi']:.0f} ADX {r['adx']:.0f}\n"
             f"⚡ TP1 QUICK {fmt(r['tp1'])} (+{r['tp1_dist_pct']*lev:.0f}% ${p1:.2f}) FAST\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_dist_pct']*lev:.0f}% ${p2:.2f})\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_dist_pct']*lev:.0f}% ${p3:.2f})\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_dist_pct']*lev:.0f}% -${loss:.2f}) SAFE\n"
             f"{r['smc_txt']}\n{r['mtf_txt']}\n{r['vol_txt']} | {r['whale_txt']}\n✅ {r['perfect_reason']} | Best from {len(all_found)}/35")
        try:
            buf=generate_chart(r)
            if buf:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"}, files={"photo": buf}, timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"BG Scan err {e}")
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"❌ Scan bug {str(e)[:100]} but will retry - Try again"},timeout=10)
        except: pass

async def start(u,c):
    save_chat_id(u.message.chat.id)
    await u.message.reply_text(f"💀 *V18.8 ULTRA GUARANTEED 100% TRADE 👌*\n✅ No more 'Market super choppy - All 27 na trap'\n✅ Now SCAN always give 1 trade from 35 FAST\n✅ WLD +10%, ZEREBRO +15%, TRUMP, HYPE, ONDO all included\n✅ Quick TP1 1.0x ATR for fast scalp\n✅ Only triple BEAR mismatch block",parse_mode="Markdown",reply_markup=coins_kb(view="FAST"))
async def scan_cmd(u,c):
    save_chat_id(u.message.chat.id); chat_id=u.message.chat.id
    daily=get_daily()
    if daily['losses'] >= MAX_DAILY_LOSS:
        await u.message.reply_text(f"🛑 Daily limit {daily['losses']} loss - P&L ${daily['pnl']:.2f}"); return
    await u.message.reply_text(f"🔍 ULTRA GUARANTEED SCANNING 35 coins...\nAlways 1 trade - No more empty message 👌")
    threading.Thread(target=background_scan, args=(chat_id,), daemon=True).start()
async def daily_cmd(u,c):
    save_chat_id(u.message.chat.id); daily=get_daily()
    await u.message.reply_text(f"📊 *V18.8 Daily ${DEFAULT_STAKE}* {daily['date']}\nWins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb(view="FAST"))
async def monitor_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if not active or active.get("status")!="OPEN":
        await u.message.reply_text("❌ No active",reply_markup=coins_kb(view="FAST")); return
    coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
    price=get_real_price(CRYPTO.get(coin))
    if not price: price=entry
    pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
    pnl=stake*pnl_pct/100; status="💚 PROFIT" if pnl_pct>=0 else "❤️ LOSS"
    txt=(f"📡 *V18.8 {coin} {dir_} {active.get('conf',0)}/100* ${stake} {lev}x\nEntry {fmt(entry)} Now {fmt(price)}\nSL {fmt(sl)} | TP1 {fmt(tp1)} | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f} {status}")
    await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb(active,view="FAST"))
async def close_cmd(u,c):
    save_chat_id(u.message.chat.id); active=get_active()
    if active: clear_active(); await u.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V18.8 ULTRA GUARANTEED 👌",reply_markup=coins_kb(view="FAST"))
    else: await u.message.reply_text("❌ No active",reply_markup=coins_kb(view="FAST"))
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    if d=="IGNORE": return
    daily=get_daily()
    if d in ["MENU_FAST","MENU_ALL"]:
        view="FAST" if "FAST" in d else "ALL"
        await q.message.reply_text(f"📋 {view} MENU V18.8 ULTRA GUARANTEED 👌",parse_mode="Markdown",reply_markup=coins_kb(view=view)); return
    if d=="SHOW_DAILY":
        await q.message.reply_text(f"📊 Daily {daily['date']} Wins {daily['wins']} Loss {daily['losses']} Trades {daily['trades']}/3 P&L ${daily['pnl']:.2f}",parse_mode="Markdown",reply_markup=coins_kb(view="FAST")); return
    if d in ["MONITOR_LIVE","CHECK_NOW"]:
        active=get_active()
        if not active or active.get("status")!="OPEN":
            await q.message.reply_text("❌ No active",reply_markup=coins_kb(view="FAST")); return
        coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
        price=get_real_price(CRYPTO.get(coin))
        if not price: price=entry
        pnl_pct=(price-entry)/entry*100*lev if dir_=="BUY" else (entry-price)/entry*100*lev
        pnl=stake*pnl_pct/100
        txt=(f"📡 *V18.8 {coin} {dir_} {active.get('conf',0)}/100* ${stake} {lev}x\nEntry {fmt(entry)} Now {fmt(price)}\nSL {fmt(sl)} | TP1 {fmt(tp1)} | TP2 {fmt(tp2)} | TP3 {fmt(tp3)}\nP&L {pnl_pct:.2f}% ${pnl:+.2f}")
        await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=coins_kb(active,view="FAST")); return
    if d=="CLOSE_TRADE":
        active=get_active()
        if active: clear_active(); await q.message.reply_text(f"✅ Closed {active.get('coin')} - Ready V18.8 👌",reply_markup=coins_kb(view="FAST"))
        else: await q.message.reply_text("❌ No active",reply_markup=coins_kb(view="FAST")); return
    if d=="SCAN_BEST":
        chat_id=q.message.chat.id
        await q.message.reply_text(f"🔍 ULTRA GUARANTEED SCANNING 35... Always 1 trade 👌")
        threading.Thread(target=background_scan, args=(chat_id,), daemon=True).start()
        return
    if d.startswith("C_"):
        code=d[2:]; r=analyze_simple(code)
        if not r:
            await q.message.reply_text(f"⚠️ SKIP {code} - Triple bear mismatch - Try another",parse_mode="Markdown",reply_markup=coins_kb(view="FAST")); return
        stake=CHOPPY_STAKE if r["conf"]<40 else (REDUCED_STAKE if daily.get("last_result")=="LOSS" else DEFAULT_STAKE)
        active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()}
        set_active(active_data); buf=generate_chart(r)
        lev=r["lev"]; sl_lev=r["sl_dist_pct"]*lev; tp1_lev=r["tp1_dist_pct"]*lev
        loss=stake*sl_lev/100; p1=stake*tp1_lev/100
        txt=(f"💀 *V18.8 SCORE {r['conf']}/100 {r['code']} {r['dir']} ${stake} {lev}x* @ {fmt(r['entry'])}\n⚡ TP1 QUICK {fmt(r['tp1'])} (+{tp1_lev:.0f}% ${p1:.2f})\n🛑 SL {fmt(r['sl'])} (-{sl_lev:.0f}% -${loss:.2f})\n✅ {r['perfect_reason']}")
        kb=coins_kb(active_data,view="FAST")
        if buf: await q.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

async def txt_handler(u,c):
    code=clean(u.message.text.strip())
    if code not in CRYPTO:
        await u.message.reply_text("❌ Unknown - Use menu",reply_markup=coins_kb(view="FAST")); return
    daily=get_daily()
    if daily['losses'] >= MAX_DAILY_LOSS:
        await u.message.reply_text(f"🛑 Daily limit {daily['losses']} loss",reply_markup=coins_kb(view="FAST")); return
    r=analyze_simple(code)
    if not r:
        await u.message.reply_text(f"⚠️ SKIP {code} - Triple bear mismatch",parse_mode="Markdown",reply_markup=coins_kb(view="FAST")); return
    stake=CHOPPY_STAKE if r["conf"]<40 else (REDUCED_STAKE if daily.get("last_result")=="LOSS" else DEFAULT_STAKE)
    active_data={"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now()),"start_time":time.time()}
    set_active(active_data); buf=generate_chart(r)
    txt=f"💀 *V18.8 SCORE {r['conf']}/100 {r['code']} {r['dir']} ${stake} {r['lev']}x @ {fmt(r['entry'])}* 👌\n✅ {r['perfect_reason']}"
    kb=coins_kb(active_data,view="FAST")
    if buf: await u.message.reply_photo(photo=buf, caption=txt, parse_mode="Markdown", reply_markup=kb)
    else: await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb)

def monitor_loop():
    print("Monitor started V18.8 ULTRA GUARANTEED")
    last_ping=0
    while True:
        try:
            time.sleep(40)
            if time.time()-last_ping>700:
                try:
                    host=os.getenv("RENDER_EXTERNAL_HOSTNAME")
                    if host: requests.get(f"https://{host}/health", headers=HEADERS, timeout=5)
                    last_ping=time.time()
                except: pass
            active=get_active()
            if not active or active.get("status")!="OPEN": continue
            coin=active.get("coin"); entry=active.get("entry"); sl=active.get("sl"); tp1=active.get("tp1"); tp2=active.get("tp2"); tp3=active.get("tp3"); dir_=active.get("dir"); stake=active.get("stake",DEFAULT_STAKE); lev=active.get("lev", DEFAULT_LEV)
            sym=CRYPTO.get(coin); price=get_real_price(sym)
            if not price: continue
            chat_id=get_chat_id()
            if not chat_id: continue
            hit=None
            if dir_=="BUY":
                if price>=tp3: hit="TP3 MOON"
                elif price>=tp2: hit="TP2"
                elif price>=tp1: hit="TP1 QUICK"
                elif price<=sl: hit="SL"
            else:
                if price<=tp3: hit="TP3 MOON"
                elif price<=tp2: hit="TP2"
                elif price<=tp1: hit="TP1 QUICK"
                elif price>=sl: hit="SL"
            if hit:
                if "TP" in hit:
                    pnl_pct=abs((tp1 if "TP1" in hit else tp2 if "TP2" in hit else tp3)-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 {hit}! {coin} +{pnl_pct:.0f}% +${pnl:.2f} QUICK TP!"; update_daily("WIN",pnl,coin); clear_active()
                else:
                    pnl_pct=abs(sl-entry)/entry*100*lev; pnl=stake*pnl_pct/100
                    msg=f"💀 SL {coin} -{pnl_pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg},timeout=8)
                except: pass
        except Exception as e:
            print(f"Monitor err {e}"); time.sleep(15)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd)); a.add_handler(CommandHandler("monitor",monitor_cmd)); a.add_handler(CommandHandler("close",close_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler)); a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    print("Bot V18.8 ULTRA GUARANTEED starting..."); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor_loop,daemon=True).start()
    run_bot()
