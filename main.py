import os, threading, requests, time, io, json
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import datetime, date

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v27.json"
DAILY_FILE = f"{DATA_DIR}/daily_v27.json"
CHAT_FILE = f"{DATA_DIR}/chat_v27.json"
CACHE = {}; LOCK = threading.Lock(); HEADERS = {"User-Agent":"Mozilla/5.0"}
STAKE_NORM = 1.0; STAKE_LOW = 0.5; LEV_NORM = 15; LEV_MEME = 10
MEME = {"WIF","PEPE","BONK","FLOKI","BOME","SHIB","NOT","FARTCOIN","ZEREBRO","TRUMP","WLD","HYPE"}
def get_lev(c): return LEV_MEME if c in MEME else LEV_NORM

# FAST 20 ONLY - NO SLOW BTC ETH
CRYPTO = {"PEPE":"PEPEUSDT","BONK":"BONKUSDT","WIF":"WIFUSDT","FLOKI":"FLOKIUSDT","BOME":"BOMEUSDT","SHIB":"SHIBUSDT","DOGE":"DOGEUSDT","TRUMP":"TRUMPUSDT","FARTCOIN":"FARTCOINUSDT","ZEREBRO":"ZEREBROUSDT","WLD":"WLDUSDT","HYPE":"HYPEUSDT","SUI":"SUIUSDT","SOL":"SOLUSDT","AVAX":"AVAXUSDT","TAO":"TAOUSDT","ARB":"ARBUSDT","OP":"OPUSDT","ENA":"ENAUSDT","TIA":"TIAUSDT"}
FAST = ["PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA"]
print(f"💀 V27 FAST 20 {DATA_DIR} - TP FAST")

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
def update_daily(res,pnl):
    d=get_daily(); d["trades"]+=1
    if res=="WIN": d["wins"]+=1
    else: d["losses"]+=1
    d["pnl"]+=pnl; save_json(DAILY_FILE,d)
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return "V27 FAST 20 TP FAST",200
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

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<20: return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=5).json()
        if isinstance(r,list) and len(r)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        iv="120" if interval=="2h" else "60" if interval=="1h" else "15"
        r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":iv,"limit":200},headers=HEADERS,timeout=5).json()
        lst=r.get("result",{}).get("list",[])
        if len(lst)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    try:
        iv="2H" if interval=="2h" else "1H" if interval=="1h" else "15m"
        r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT"),"bar":iv,"limit":"200"},headers=HEADERS,timeout=5).json()
        lst=r.get("data",[])
        if len(lst)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=4).json()
        p=float(r.get("price",0))
        if p>0: return p
    except: pass
    try:
        r=requests.get("https://api.bybit.com/v5/market/tickers",params={"category":"linear","symbol":sym},headers=HEADERS,timeout=4).json()
        p=float(r.get("result",{}).get("list",[{}])[0].get("lastPrice",0))
        if p>0: return p
    except: pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def ema(arr,p):
    if len(arr)<p: return sum(arr)/len(arr) if arr else 0
    k=2/(p+1); e=sum(arr[:p])/p
    for x in arr[p:]: e=(x-e)*k+e
    return e
def ema_series(arr,p):
    if len(arr)<p: return [sum(arr)/len(arr)]*len(arr)
    k=2/(p+1); e=sum(arr[:p])/p; res=[e]*p
    for x in arr[p:]: e=(x-e)*k+e; res.append(e)
    return res
def rsi(arr,p=14):
    if len(arr)<p+1: return 50
    g=l=0
    for i in range(1,p+1):
        d=arr[-i]-arr[-i-1]
        if d>0: g+=d
        else: l+=-d
    if l==0: return 70 if g>0 else 50
    return 100 - (100/(1+g/l))
def atr(kl,p=14):
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
            pdm.append(up if up>dn and up>0 else 0)
            mdm.append(dn if dn>up and dn>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        atr_v=sum(tr[-14:])/14
        if atr_v==0: return 18
        pdi=100*sum(pdm[-14:])/14/atr_v; mdi=100*sum(mdm[-14:])/14/atr_v
        if pdi+mdi==0: return 18
        return max(10, min(60, 100*abs(pdi-mdi)/(pdi+mdi)))
    except: return 18
def macd_calc(closes):
    if len(closes)<35: return "NEUTRAL"
    e12=ema_series(closes,12); e26=ema_series(closes,26)
    ml=[a-b for a,b in zip(e12[-len(e26):],e26)]; sig=ema_series(ml,9)
    return "🟢 BULLISH" if ml[-1]>sig[-1] else "🔴 BEARISH"
def pd_calc(kl):
    if len(kl)<100: return "EQUILIBRIUM",50
    hi=max(k["h"] for k in kl[-100:]); lo=min(k["l"] for k in kl[-100:]); pr=kl[-1]["c"]
    pct=(pr-lo)/(hi-lo)*100 if hi!=lo else 50
    return ("PREMIUM",pct) if pct>=70 else ("DISCOUNT",pct) if pct<=30 else ("EQUILIBRIUM",pct)
def trend(closes):
    if len(closes)<50: return 0,"SIDEWAYS"
    e20=ema(closes,20); e50=ema(closes,50); pr=closes[-1]
    if pr>e20>e50: return 50,"⬆️ UPTREND"
    if pr>e20: return 20,"↗️ WEAK UP"
    if pr<e20<e50: return -50,"⬇️ DOWNTREND"
    if pr<e20: return -20,"↘️ WEAK DOWN"
    return 0,"➡️ SIDEWAYS"
def vol_calc(kl):
    if len(kl)<20: return 0,"Vol N/A"
    vols=[k["v"] for k in kl[-20:]]; avg=sum(vols[:-1])/len(vols[:-1]); pct=(vols[-1]-avg)/avg*100 if avg else 0
    return pct,f"📊 Vol {pct:.0f}% {'🔥🔥' if pct>15 else '🔥' if pct>8 else ''}"
def candle_calc(kl):
    if len(kl)<3: return "NONE"
    c2,c3=kl[-2],kl[-1]
    if c2["c"]>c2["o"] and c3["c"]<c3["o"] and c3["o"]>=c2["c"]: return "🐻 BEARISH ENGULFING SELL"
    if c2["c"]<c2["o"] and c3["c"]>c3["o"] and c3["o"]<=c2["c"]: return "🐂 BULLISH ENGULFING BUY"
    return "NONE"
def fvg_calc(kl):
    for i in range(len(kl)-10, len(kl)-1):
        a,b=kl[i-1],kl[i]
        if b["l"]>a["h"] and (b["l"]-a["h"])/a["h"]>0.0005: return {"type":"🟢 BULL FVG","side":"BUY","b":a["h"],"t":b["l"]}
        if b["h"]<a["l"] and (a["l"]-b["h"])/a["l"]>0.0005: return {"type":"🔴 BEAR FVG","side":"SELL","b":b["h"],"t":a["l"]}
    return None
def ob_calc(kl):
    last=kl[-4]
    return {"type":"🟥 BEARISH OB","side":"SELL","l":last["l"],"h":last["h"]} if last["c"]<last["o"] else {"type":"🟩 BULLISH OB","side":"BUY","l":last["l"],"h":last["h"]}

def analyze_single(code):
    try:
        sym=CRYPTO[code]
        k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<60: k2=get_klines(sym,"1h")
        if len(k2)<60: return None
        c2=[k["c"] for k in k2]
        price=get_price(sym) or c2[-1]
        if abs(price-c2[-1])/c2[-1]>0.06: price=c2[-1]
        rsi_v=rsi(c2); atr_v=atr(k2); adx_v=adx_calc(k2)
        macd=macd_calc(c2); pd_zone,pd_pct=pd_calc(k2)
        cand=candle_calc(k2); ob=ob_calc(k2); fvg=fvg_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2
        c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend(c15); s1,t1=trend(c1); s2,t2=trend(c2)
        vol_pct,vol_txt=vol_calc(k2)
        e200=ema(c2,200)
        prev_high=k2[-2]["h"]; prev_low=k2[-2]["l"]; curr_high=k2[-1]["h"]; curr_low=k2[-1]["l"]; curr_close=k2[-1]["c"]
        bos_bull = curr_high > prev_high or curr_close > prev_high
        bos_bear = curr_low < prev_low or curr_close < prev_low
        align = 3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        is_strong = ("UPTREND" in t15 and "UPTREND" in t1 and "UPTREND" in t2) or ("DOWNTREND" in t15 and "DOWNTREND" in t1 and "DOWNTREND" in t2)
        direction="BUY" if s2>=0 else "SELL"
        # FAST SCORE: volatility = atr/price
        volatility = atr_v/price*100 if price else 0
        return {"code":code,"sym":sym,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"macd":macd,"pd_zone":pd_zone,"pd_pct":pd_pct,"candle":cand,"ob":ob,"fvg":fvg,"s15":s15,"s1":s1,"s2":s2,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"e200":e200,"bos_bull":bos_bull,"bos_bear":bos_bear,"align":align,"is_strong":is_strong,"dir":direction,"kl":k2}
    except: return None

def build_trade(r):
    price=r["price"]; atr_v=r["atr"]; direction=r["dir"]
    # FAST TP - TIGHTER FOR QUICK HIT
    sl=price*0.984 if direction=="BUY" else price*1.016  # 1.6% SL tighter for fast coins
    tp1=price+atr_v*0.8 if direction=="BUY" else price-atr_v*0.8  # FAST TP1 0.8x ATR
    tp2=price+atr_v*1.6 if direction=="BUY" else price-atr_v*1.6  # TP2 1.6x
    tp3=price+atr_v*2.5 if direction=="BUY" else price-atr_v*2.5  # TP3 2.5x runner
    return {"code":r["code"],"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":get_lev(r["code"]),"rsi":r["rsi"],"adx":r["adx"],"atr":atr_v,"volatility":r["volatility"],"macd":r["macd"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"candle":r["candle"],"ob":r["ob"],"fvg":r["fvg"],"mtf":f"⏱️ 15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']} [Align {r['align']}/3 {'STRONG' if r['is_strong'] else 'WEAK'}] ADX {r['adx']:.0f} | MACD {r['macd']} | EMA200 {fmt(r['e200'])}","vol_txt":r["vol_txt"],"vol_pct":r["vol_pct"],"smc":f"🕯️ {r['candle']} | {r['macd']} | {r['ob']['type']} | {r['fvg']['type'] if r['fvg'] else 'FVG None'} | {r['pd_zone']} {r['pd_pct']:.0f}% | BOS {'🔥' if r['bos_bull'] or r['bos_bear'] else 'No'} | Volatility {r['volatility']:.2f}%","liq":f"🐋 Liq UP {fmt(max(k['h'] for k in r['kl'][-20:])*1.02)} | DOWN {fmt(min(k['l'] for k in r['kl'][-20:])*0.98)}","kl":r["kl"],"e200":r["e200"],"align":r["align"],"is_strong":r["is_strong"],"bos_bull":r["bos_bull"],"bos_bear":r["bos_bear"],"sl_pct":abs(sl-price)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"tp3_pct":abs(tp3-price)/price*100}

def chart(r):
    try:
        kl=r["kl"][-100:]; closes=[k["c"] for k in kl]
        e20=ema_series(closes,20); e50=ema_series(closes,50); e200=ema_series(closes,200)
        fig,ax=plt.subplots(figsize=(11,6))
        ax.plot(closes,color="black",lw=1.2); ax.plot(e20,color="#2196F3",lw=0.8); ax.plot(e50,color="#FF9800",lw=0.8); ax.plot(e200,color="#9C27B0",ls=":")
        ax.axhline(r["entry"],color="blue",ls="--",label=f'Entry {fmt(r["entry"])}'); ax.axhline(r["sl"],color="red",label=f'SL {fmt(r["sl"])}')
        ax.axhline(r["tp1"],color="green",label=f'TP1 FAST {fmt(r["tp1"])}'); ax.axhline(r["tp2"],color="#4CAF50",ls="-.",label=f'TP2'); ax.axhline(r["tp3"],color="#00E676",ls=":",label=f'TP3')
        if r["fvg"]: ax.axhspan(r["fvg"]["b"],r["fvg"]["t"],color='gold',alpha=0.2)
        ax.set_title(f'{r["code"]} {r["dir"]} SCORE {r["conf"]}/100 {r["lev"]}x RSI {r["rsi"]:.0f} ADX {r["adx"]:.0f} Volat {r["volatility"]:.2f}% FAST',fontsize=10,fontweight='bold')
        ax.legend(fontsize=7,ncol=2); ax.grid(True,alpha=0.3); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf,format='png',dpi=160); buf.seek(0); plt.close(fig); return buf
    except: return None

def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 LIVE FAST',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]}',callback_data="CHK"),InlineKeyboardButton(f'❌ Close {active["coin"]}',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'⚡ SCAN 20 FAST - Trade {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY")])
    row=[]
    for c in FAST:
        row.append(InlineKeyboardButton(f'⚡ {c}',callback_data=f'C_{c}'))
        if len(row)==4: btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","⚡ V27 FAST 20"),BotCommand("scan","🔍 SCAN FAST"),BotCommand("daily","📊 Daily")])
    except: pass

def bg_scan(chat_id):
    try:
        print(f"⚡ V27 FAST 20 SCAN {len(FAST)}")
        raws=[]
        for code in FAST:
            r=analyze_single(code)
            if r: raws.append(r); print(f"  RAW {code} ADX {r['adx']:.0f} RSI {r['rsi']:.0f} PD {r['pd_pct']:.0f}% Vol {r['vol_pct']:.0f}% Volatility {r['volatility']:.2f}% BOS {r['bos_bull'] or r['bos_bear']} Align {r['align']}")
            time.sleep(0.05)
        if not raws:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"⚠️ Fetch fail 0/20 fast"},timeout=10); return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        avg_volat=sum(x["volatility"] for x in raws)/len(raws)
        mode="TREND" if avg_adx>=18 else "NORMAL" if avg_adx>=14 else "CHOPPY"
        print(f"MODE {mode} avgADX {avg_adx:.1f} avgVolat {avg_volat:.2f}% FAST 20")

        def is_fast_perfect(r):
            # FAST PERFECT - Must be volatile + perfect entry
            if r["volatility"] < 1.2:  # At least 1.2% ATR = volatile
                print(f"  BLOCK {r['code']} Volatility {r['volatility']:.2f}% <1.2% too slow")
                return False
            if r["dir"]=="BUY" and r["pd_pct"]>42: return False
            if r["dir"]=="SELL" and r["pd_pct"]<58: return False
            if not (40 <= r["rsi"] <= 60): return False
            if r["adx"] < 14: return False
            if r["vol_pct"] < 2: return False  # Need volume pumping
            if not (r["bos_bull"] or r["bos_bear"]): return False
            if r["align"] < 3: return False
            if r["dir"]=="BUY" and "BEARISH" in r["macd"]: return False
            if r["dir"]=="SELL" and "BULLISH" in r["macd"]: return False
            if r["dir"]=="BUY" and r["price"] < r["e200"]*0.998: return False
            if r["dir"]=="SELL" and r["price"] > r["e200"]*1.002: return False
            return True

        def is_fast_good(r):
            if r["volatility"] < 0.9: return False
            if r["dir"]=="BUY" and r["pd_pct"]>55: return False
            if r["dir"]=="SELL" and r["pd_pct"]<45: return False
            if not (38 <= r["rsi"] <= 65): return False
            if r["adx"] < 12: return False
            if r["vol_pct"] < -5: return False
            if r["align"] < 2: return False
            return True

        tier1=[]; tier2=[]
        for r in raws:
            if is_fast_perfect(r):
                trade=build_trade(r)
                # Bonus for volatility - more volatile = higher score for fast TP
                bonus = int(r["volatility"]*2 + r["vol_pct"]/5)
                trade["conf"]=min(92, 78 + bonus)
                trade["reason"]=f"FAST PERFECT Volat {r['volatility']:.2f}% HIGH + RSI {r['rsi']:.0f} + PD {r['pd_pct']:.0f}% + ADX {r['adx']:.0f} + Vol {r['vol_pct']:.0f}% 🔥 + BOS + Align 3/3 STRONG + MACD MATCH - WILL HIT TP FAST"
                trade["mode"]=mode+" FAST PERFECT"
                tier1.append(trade)
                print(f"  >>> FAST PERFECT {r['code']} Volat {r['volatility']:.2f}%")
            elif is_fast_good(r):
                trade=build_trade(r)
                trade["conf"]=68
                trade["reason"]=f"FAST GOOD Volat {r['volatility']:.2f}% + RSI {r['rsi']:.0f} + PD {r['pd_pct']:.0f}%"
                trade["mode"]=mode+" FAST GOOD"
                tier2.append(trade)

        cands = tier1 if tier1 else tier2

        if not cands:
            msg = (f"🛡️ *V27 No FAST entry now* - 20 fast coins checked\n"
                   f"Avg ADX {avg_adx:.1f} Avg Volatility {avg_volat:.2f}% Mode {mode}\n"
                   f"Need: Volatility 1.2%+ + PD 0-42% BUY / 58-100% SELL + RSI 40-60 + ADX 14+ + Vol 2%+ + BOS + Align 3/3 + MACD MATCH\n"
                   f"Market too slow now, try 15m later - Fast coins resting")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"},timeout=10)
            return

        # Sort by volatility + conf = fastest TP first
        cands.sort(key=lambda x: x["conf"] + x["volatility"]*5 + x["vol_pct"]*0.3, reverse=True)
        best=cands[0]
        print(f"BEST FAST {best['code']} {best['dir']} {best['conf']} Volat {best['volatility']:.2f}% Best {len(cands)}/{len(raws)}")
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN FAST"},timeout=10); return

        r=best; stake=STAKE_NORM if r["conf"]>=75 else STAKE_LOW
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now()),"mode":r["mode"]})
        loss=stake*r["sl_pct"]*r["lev"]/100; p1=stake*r["tp1_pct"]*r["lev"]/100; p2=stake*r["tp2_pct"]*r["lev"]/100; p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"⚡ *{r['mode']} FAST SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY LONG 🚀 FAST' if r['dir']=='BUY' else '🔴 SELL SHORT 💥 FAST'} ${stake} {r['lev']}x\n"
             f"💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} Volat {r['volatility']:.2f}% FAST | {r['macd']}\n"
             f"⚡ TP1 FAST {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f}) 0.8xATR - Hit in 30m 🚀\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f}) 1.6xATR - 2H\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f}) 2.5xATR Runner\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f}) TIGHT 1.6%\n"
             f"{r['smc']}\n{r['mtf']}\n{r['vol_txt']} | {r['liq']}\n✅ {r['reason']} | Market {r['mode']} avgVolat {avg_volat:.2f}% | Best {len(cands)}/{len(raws)} FAST 20 - WILL HIT TP FAST!")
        try:
            b=chart(r)
            if b: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"},files={"photo":b},timeout=20)
            else: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}")
        import traceback; traceback.print_exc()

async def start(u,c): save_chat(u.message.chat.id); await u.message.reply_text(f"⚡ *V27 FAST 20 - TP FAST* 🚀\n✅ 20 FASTEST coins only: PEPE BONK WIF FLOKI BOME SHIB DOGE TRUMP FARTCOIN ZEREBRO WLD HYPE SUI SOL AVAX TAO ARB OP ENA TIA\n✅ No more slow BTC ETH BNB ADA QNT PAXG\n✅ Volatility filter 1.2%+ - Only coins wey dey move fast\n✅ TP tighter: TP1 0.8xATR +22% FAST (30m hit), TP2 1.6x +45%, TP3 2.5x runner, SL 1.6% tight\n✅ Perfect: PD 0-42% BUY 58-100% SELL RSI 40-60 ADX 14+ Vol 2%+ BOS Align 3/3 STRONG MACD MATCH\n✅ Sort by volatility = fastest TP first",parse_mode="Markdown",reply_markup=kb())
async def scan_cmd(u,c): save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start(); await u.message.reply_text("⚡ SCANNING 20 FAST... Volatility 1.2%+ TP FAST...")
async def daily_cmd(u,c): save_chat(u.message.chat.id); d=get_daily(); await u.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L Trades {d['trades']}/3 ${d['pnl']:.2f}",parse_mode="Markdown",reply_markup=kb())
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("No active FAST",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl_pct=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"📡 {act['coin']} {act['dir']} Now {fmt(price)} Entry {fmt(act['entry'])} P&L {pnl_pct:.2f}% Mode {act.get('mode','')} FAST",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); await q.message.reply_text("✅ Closed FAST",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("⚡ SCANNING 20 FAST..."); return
    if data.startswith("C_"):
        code=data[2:]; raw=analyze_single(code)
        if not raw: await q.message.reply_text(f"⚠️ Fetch fail {code}",reply_markup=kb()); return
        trade=build_trade(raw); trade["conf"]=75; trade["reason"]=f"Manual FAST {code} Volat {raw['volatility']:.2f}%"; trade["mode"]="MANUAL FAST"
        set_active({"status":"OPEN","coin":trade["code"],"dir":trade["dir"],"entry":trade["entry"],"sl":trade["sl"],"tp1":trade["tp1"],"tp2":trade["tp2"],"tp3":trade["tp3"],"conf":trade["conf"],"stake":STAKE_NORM,"lev":trade["lev"],"time":str(datetime.now()),"mode":"MANUAL"})
        b=chart(trade); txt=f"⚡ *V27 MANUAL FAST {trade['conf']}/100 {trade['code']} {trade['dir']} Volat {raw['volatility']:.2f}%* @ {fmt(trade['entry'])}"
        if b: await q.message.reply_photo(photo=b,caption=txt,parse_mode="Markdown",reply_markup=kb(get_active()))
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb(get_active()))

def monitor():
    while True:
        try:
            time.sleep(25)
            act=get_active()
            if not act.get("status")=="OPEN": continue
            price=get_price(CRYPTO[act["coin"]])
            if not price: continue
            chat=get_chat()
            if not chat: continue
            hit=None
            if act["dir"]=="BUY":
                if price>=act["tp3"]: hit="TP3"
                elif price>=act["tp2"]: hit="TP2"
                elif price>=act["tp1"]: hit="TP1"
                elif price<=act["sl"]: hit="SL"
            else:
                if price<=act["tp3"]: hit="TP3"
                elif price<=act["tp2"]: hit="TP2"
                elif price<=act["tp1"]: hit="TP1"
                elif price>=act["sl"]: hit="SL"
            if hit:
                stake=act["stake"]; lev=act["lev"]; entry=act["entry"]
                if "TP" in hit:
                    tp=act["tp1"] if "TP1" in hit else act["tp2"] if "TP2" in hit else act["tp3"]
                    pct=abs(tp-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"⚡ {hit} FAST! {act['coin']} +{pct:.0f}% +${pnl:.2f} {act.get('mode','')} - TP FAST!"; update_daily("WIN",pnl); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL FAST {act['coin']} -{pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":msg},timeout=8)
                except: pass
        except: time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V27 FAST 20 starting"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
