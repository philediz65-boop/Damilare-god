import os, re, threading, requests, time, io, json
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import datetime, date

# ================= V20.2 BALANCED 100% - NO EMERGENCY =================
BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)

DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v20.json"
DAILY_FILE = f"{DATA_DIR}/daily_v20.json"
CHAT_FILE = f"{DATA_DIR}/chat_v20.json"

CACHE = {}
LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}

STAKE_NORM = 1.0
STAKE_LOW = 0.5
LEV_NORM = 15
LEV_MEME = 10
MEME = {"WIF","PEPE","BONK","FLOKI","BOME","SHIB","NOT","FARTCOIN","ZEREBRO","BR","TRUMP"}

def get_lev(c): return LEV_MEME if c in MEME else LEV_NORM

CRYPTO = {
 "BTC":"BTCUSDT","ETH":"ETHUSDT","BNB":"BNBUSDT","SOL":"SOLUSDT","XRP":"XRPUSDT",
 "DOGE":"DOGEUSDT","ADA":"ADAUSDT","AVAX":"AVAXUSDT","LINK":"LINKUSDT","DOT":"DOTUSDT",
 "MATIC":"MATICUSDT","LTC":"LTCUSDT","UNI":"UNIUSDT","PEPE":"PEPEUSDT","BONK":"BONKUSDT",
 "SHIB":"SHIBUSDT","FLOKI":"FLOKIUSDT","WIF":"WIFUSDT","BOME":"BOMEUSDT","SUI":"SUIUSDT",
 "ARB":"ARBUSDT","OP":"OPUSDT","APT":"APTUSDT","TAO":"TAOUSDT","NOT":"NOTUSDT","PAXG":"PAXGUSDT",
 "ENA":"ENAUSDT","FARTCOIN":"FARTCOINUSDT","TIA":"TIAUSDT","WLD":"WLDUSDT","ZEREBRO":"ZEREBROUSDT",
 "ASTER":"ASTERUSDT","HBAR":"HBARUSDT","ONDO":"ONDOUSDT","TRUMP":"TRUMPUSDT","HYPE":"HYPEUSDT",
 "QNT":"QNTUSDT","NEAR":"NEARUSDT","JUP":"JUPUSDT"
}
FAST = ["WLD","ZEREBRO","TRUMP","HYPE","ONDO","APT","ENA","NEAR","BTC","ETH","SOL","XRP","AVAX","LINK","SUI","LTC","UNI","QNT","HBAR","DOGE","DOT","ARB","OP","TAO","PEPE","BONK","FLOKI","WIF","SHIB","BNB","ADA","MATIC","ASTER","TIA","PAXG"]

print(f"💀 V20.2 BALANCED {DATA_DIR}")

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
def home(): return "V20.2 BALANCED READY - No Emergency",200
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
    try:
        gran="2H" if interval=="2h" else "1H" if interval=="1h" else "15m"
        r=requests.get("https://api.bitget.com/api/v2/mix/market/candles",params={"symbol":sym,"productType":"USDT-FUTURES","granularity":gran,"limit":"200"},headers=HEADERS,timeout=5).json()
        lst=r.get("data",[])
        if len(lst)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
            CACHE[key]=(time.time(),kl); return kl
    except: pass
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    parsers=[
     ("https://fapi.binance.com/fapi/v1/ticker/price",{"symbol":sym},lambda j: float(j.get("price",0))),
     ("https://api.bybit.com/v5/market/tickers",{"category":"linear","symbol":sym},lambda j: float(j.get("result",{}).get("list",[{}])[0].get("lastPrice",0))),
     ("https://www.okx.com/api/v5/market/ticker",{"instId":sym.replace("USDT","-USDT")},lambda j: float(j.get("data",[{}])[0].get("last",0))),
     ("https://api.bitget.com/api/v2/mix/market/ticker",{"symbol":sym,"productType":"USDT-FUTURES"},lambda j: float((j.get("data",[{}])[0] if isinstance(j.get("data"),list) else j.get("data",{})).get("lastPr",0))),
    ]
    for url,params,fn in parsers:
        try:
            r=requests.get(url,params=params,headers=HEADERS,timeout=4).json()
            p=fn(r)
            if p>0 and not (sym=="BTCUSDT" and p<50000): return p
        except: continue
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
    if l==0: return 75 if g>0 else 50
    return 100 - (100/(1+g/l))
def atr(kl,p=14):
    if len(kl)<p+1: return kl[-1]["c"]*0.015
    trs=[]
    for i in range(1,p+1):
        c=kl[-i]; pc=kl[-i-1]
        trs.append(max(c["h"]-c["l"], abs(c["h"]-pc["c"]), abs(c["l"]-pc["c"])))
    return sum(trs)/len(trs)
def adx_calc(kl,p=14):
    if len(kl)<p+5: return 18
    highs=[k["h"] for k in kl]; lows=[k["l"] for k in kl]; closes=[k["c"] for k in kl]
    pdm=mdm=tr=[]
    for i in range(1,len(kl)):
        up=highs[i]-highs[i-1]; dn=lows[i-1]-lows[i]
        pdm.append(up if up>dn and up>0 else 0)
        mdm.append(dn if dn>up and dn>0 else 0)
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    if len(tr)<p: return 18
    atr_v=sum(tr[-p:])/p; pdi=100*sum(pdm[-p:])/p/atr_v if atr_v else 0; mdi=100*sum(mdm[-p:])/p/atr_v if atr_v else 0
    if pdi+mdi==0: return 18
    return min(80,max(5,100*abs(pdi-mdi)/(pdi+mdi)))
def macd_calc(closes):
    if len(closes)<35: return "NEUTRAL"
    e12=ema_series(closes,12); e26=ema_series(closes,26)
    ml=[a-b for a,b in zip(e12[-len(e26):],e26)]; sig=ema_series(ml,9)
    return "🟢 BULLISH" if ml[-1]>sig[-1] else "🔴 BEARISH"
def pd_calc(kl):
    if len(kl)<100: return "EQUILIBRIUM",50
    hi=max(k["h"] for k in kl[-100:]); lo=min(k["l"] for k in kl[-100:]); pr=kl[-1]["c"]
    pct=(pr-lo)/(hi-lo)*100 if hi!=lo else 50
    if pct>=70: return "PREMIUM",pct
    if pct<=30: return "DISCOUNT",pct
    return "EQUILIBRIUM",pct
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
    return pct,f"📊 Vol {pct:.0f}% {'🔥' if pct>20 else ''}"
def candle_calc(kl):
    if len(kl)<3: return "NONE"
    c2,c3=kl[-2],kl[-1]
    if c2["c"]>c2["o"] and c3["c"]<c3["o"] and c3["o"]>=c2["c"]: return "🐻 BEARISH ENGULFING SELL"
    if c2["c"]<c2["o"] and c3["c"]>c3["o"] and c3["o"]<=c2["c"]: return "🐂 BULLISH ENGULFING BUY"
    if c3["h"]-max(c3["o"],c3["c"])>(c3["h"]-c3["l"])*0.6: return "⭐ SHOOTING STAR SELL"
    if min(c3["o"],c3["c"])-c3["l"]>(c3["h"]-c3["l"])*0.6: return "🔨 HAMMER BUY"
    return "NONE"
def fvg_calc(kl):
    for i in range(len(kl)-10, len(kl)-1):
        a,b=kl[i-1],kl[i]
        if b["l"]>a["h"] and (b["l"]-a["h"])/a["h"]>0.0005: return {"type":"🟢 BULL FVG","side":"BUY","b":a["h"],"t":b["l"]}
        if b["h"]<a["l"] and (a["l"]-b["h"])/a["l"]>0.0005: return {"type":"🔴 BEAR FVG","side":"SELL","b":b["h"],"t":a["l"]}
    return None
def ob_calc(kl):
    last=kl[-4] if len(kl)>=4 else kl[-1]
    if last["c"]<last["o"]: return {"type":"🟥 BEARISH OB","side":"SELL","l":last["l"],"h":last["h"]}
    else: return {"type":"🟩 BULLISH OB","side":"BUY","l":last["l"],"h":last["h"]}

# ================= CORE V20.2 BALANCED =================
def analyze(code):
    try:
        sym=CRYPTO[code]
        k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<50: k2=get_klines(sym,"1h")
        if len(k2)<50: return None
        c15=[k["c"] for k in k15] if k15 else [k["c"] for k in k2]
        c1=[k["c"] for k in k1] if k1 else [k["c"] for k in k2]
        c2=[k["c"] for k in k2]
        price=get_price(sym)
        if not price: price=c2[-1]
        rsi_v=rsi(c2); atr_v=atr(k2); adx_v=adx_calc(k2)
        macd=macd_calc(c2); pd_zone,pd_pct=pd_calc(k2)
        cand=candle_calc(k2); ob=ob_calc(k2); fvg=fvg_calc(k2)
        s15,t15=trend(c15); s1,t1=trend(c1); s2,t2=trend(c2)
        vol_pct,vol_txt=vol_calc(k2)
        e200=ema(c2,200); e50=ema(c2,50); e20=ema(c2,20)
        prev_high=k2[-2]["h"]; prev_low=k2[-2]["l"]; curr_high=k2[-1]["h"]; curr_low=k2[-1]["l"]; curr_close=k2[-1]["c"]
        bos_bull = curr_high > prev_high or curr_close > prev_high
        bos_bear = curr_low < prev_low or curr_close < prev_low
        if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0): align=3
        elif (s1>0 and s2>0) or (s1<0 and s2<0): align=2
        else: align=1
        direction="BUY" if s2>=0 else "SELL"
        # HARD BLOCK - Fix WLD 97%, DOT 70% BEARISH, APT SHOOTING STAR
        if "SHOOTING STAR SELL" in cand or "BEARISH ENGULFING SELL" in cand:
            if direction=="BUY": return None
            direction="SELL"
        if "HAMMER BUY" in cand or "BULLISH ENGULFING BUY" in cand:
            if direction=="SELL": return None
            direction="BUY"
        if fvg and fvg["side"]!=direction and align<3: return None
        if direction=="BUY" and pd_pct>=65: return None
        if direction=="SELL" and pd_pct<=35: return None
        if direction=="BUY" and "BEARISH" in macd: return None
        if direction=="SELL" and "BULLISH" in macd: return None
        if direction=="BUY" and rsi_v>=75: return None
        if direction=="SELL" and rsi_v<=25: return None
        # SOFT SCORE - Vol, EMA200, BOS not block, only score
        score=0; reasons=[]
        if align==3: score+=20; reasons.append(f"Align 3/3 {direction} +20")
        elif align==2: score+=12; reasons.append(f"Align 2/3 +12")
        else: score+=4; reasons.append(f"Align {align}/3 +4")
        if 20<=adx_v<=60: score+=12; reasons.append(f"ADX {adx_v:.0f} +12")
        else: score+=3; reasons.append(f"ADX {adx_v:.0f} +3")
        if vol_pct>=15: score+=12; reasons.append(f"Vol {vol_pct:.0f}% 🔥 +12")
        elif vol_pct>=5: score+=6; reasons.append(f"Vol {vol_pct:.0f}% +6")
        else: score+=2; reasons.append(f"Vol {vol_pct:.0f}% low +2")
        if ob and ob["side"]==direction: score+=10; reasons.append(f"OB {ob['type']} +10")
        if fvg and fvg["side"]==direction: score+=10; reasons.append(f"FVG {fvg['type']} +10")
        if pd_zone=="DISCOUNT" and direction=="BUY": score+=12; reasons.append(f"DISCOUNT {pd_pct:.0f}% BUY +12")
        elif pd_zone=="PREMIUM" and direction=="SELL": score+=12; reasons.append(f"PREMIUM {pd_pct:.0f}% SELL +12")
        else: score+=6; reasons.append(f"{pd_zone} {pd_pct:.0f}% +6")
        if "BULLISH" in macd and direction=="BUY": score+=8; reasons.append(f"MACD BULLISH +8")
        if "BEARISH" in macd and direction=="SELL": score+=8; reasons.append(f"MACD BEARISH +8")
        if direction=="BUY" and price>e200: score+=8; reasons.append(f"Price>EMA200 +8")
        elif direction=="SELL" and price<e200: score+=8; reasons.append(f"Price<EMA200 +8")
        else: score+=2; reasons.append(f"Near EMA200 +2")
        if bos_bull and direction=="BUY": score+=6; reasons.append(f"BOS High +6")
        elif bos_bear and direction=="SELL": score+=6; reasons.append(f"BOS Low +6")
        else: score+=1; reasons.append(f"No BOS +1")
        if score<35: score=35
        sl=price*0.982 if direction=="BUY" else price*1.018
        tp1=price+atr_v*1.0 if direction=="BUY" else price-atr_v*1.0
        tp2=price+atr_v*2.0 if direction=="BUY" else price-atr_v*2.0
        tp3=price+atr_v*3.2 if direction=="BUY" else price-atr_v*3.2
        return {
         "code":code,"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,
         "lev":get_lev(code),"conf":int(score),"rsi":rsi_v,"adx":adx_v,"atr":atr_v,
         "macd":macd,"pd_zone":pd_zone,"pd_pct":pd_pct,"candle":cand,"ob":ob,"fvg":fvg,
         "mtf":f"⏱️ 15m {t15} | 1H {t1} | 2H {t2} [Align {align}/3] ADX {adx_v:.0f} | MACD {macd} | EMA200 {fmt(e200)}",
         "vol_txt":vol_txt,"vol_pct":vol_pct,"smc":f"🕯️ {cand} | MACD {macd} | {ob['type']} | {fvg['type'] if fvg else 'FVG None'} | {pd_zone} {pd_pct:.0f}% | BOS {'🔥' if bos_bull or bos_bear else 'No'}",
         "liq":f"🐋 Liq UP {fmt(max(k['h'] for k in k2[-20:])*1.02)} | DOWN {fmt(min(k['l'] for k in k2[-20:])*0.98)}",
         "reason":f"SCORE {int(score)}/100 - {' | '.join(reasons)}",
         "kl":k2,"e200":e200,
         "sl_pct":abs(sl-price)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"tp3_pct":abs(tp3-price)/price*100
        }
    except Exception as e:
        print(f"analyze {code} err {e}")
        return None

def chart(r):
    try:
        kl=r["kl"][-100:]; closes=[k["c"] for k in kl]
        e20=ema_series(closes,20); e50=ema_series(closes,50); e200=ema_series(closes,200)
        fig,ax=plt.subplots(figsize=(11,6))
        ax.plot(closes,color="black",label="Price",lw=1.2)
        ax.plot(e20,color="#2196F3",label="EMA20",lw=0.8)
        ax.plot(e50,color="#FF9800",label="EMA50",lw=0.8)
        ax.plot(e200,color="#9C27B0",label="EMA200",lw=1.0,ls=":")
        ax.axhline(r["entry"],color="blue",ls="--",label=f'Entry {fmt(r["entry"])}')
        ax.axhline(r["sl"],color="red",ls="-",label=f'SL {fmt(r["sl"])}')
        ax.axhline(r["tp1"],color="green",label=f'TP1 {fmt(r["tp1"])}')
        ax.axhline(r["tp2"],color="#4CAF50",ls="-.",label=f'TP2 {fmt(r["tp2"])}')
        ax.axhline(r["tp3"],color="#00E676",ls=":",label=f'TP3 {fmt(r["tp3"])}')
        ax.axhline(r["e200"],color="purple",ls=":",label=f'EMA200 {fmt(r["e200"])}')
        if r["fvg"]: ax.axhspan(r["fvg"]["b"],r["fvg"]["t"],color='gold',alpha=0.2,label=r["fvg"]["type"])
        ax.set_title(f'{r["code"]} {r["dir"]} SCORE {r["conf"]}/100 {r["lev"]}x RSI {r["rsi"]:.0f} ADX {r["adx"]:.0f} {r["pd_zone"]} {r["macd"]}',fontsize=10,fontweight='bold')
        ax.legend(fontsize=7,ncol=2); ax.grid(True,alpha=0.3); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf,format='png',dpi=160); buf.seek(0); plt.close(fig); return buf
    except: return None

def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 LIVE',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]}',callback_data="CHK"),InlineKeyboardButton(f'❌ Close {active["coin"]}',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🔍 SCAN 35 BALANCED - Trade {daily["trades"]+1}/3 💀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY")])
    row=[]
    for c in FAST:
        row.append(InlineKeyboardButton(f'⚡ {c}',callback_data=f'C_{c}'))
        if len(row)==3: btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","💀 V20.2 BALANCED"),BotCommand("scan","🔍 SCAN"),BotCommand("daily","📊 Daily")])
    except: pass

def bg_scan(chat_id):
    try:
        print(f"💀 V20.2 BALANCED SCAN {len(FAST)}")
        cands=[]
        for code in FAST:
            r=analyze(code)
            if r:
                cands.append(r)
                print(f"  {code} {r['dir']} score {r['conf']} pd {r['pd_pct']:.0f}% vol {r['vol_pct']:.0f}%")
            time.sleep(0.12)
        if not cands:
            print("No cands - market super choppy")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Market choppy - No coin pass HARD filters (PD/MACD/Candle). Try again in 30m. 0/35 passed."},timeout=10)
            return
        cands.sort(key=lambda x: x["conf"]+x["adx"]*0.2+x["vol_pct"]*0.1, reverse=True)
        best=cands[0]
        print(f"BEST {best['code']} {best['dir']} {best['conf']} Best {len(cands)}/35")
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN"},timeout=10)
            return
        r=best; stake=STAKE_NORM if r["conf"]>=50 else STAKE_LOW
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(datetime.now())})
        loss=stake*r["sl_pct"]*r["lev"]/100; p1=stake*r["tp1_pct"]*r["lev"]/100; p2=stake*r["tp2_pct"]*r["lev"]/100; p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"💀 *V20.2 BALANCED SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY LONG 🚀' if r['dir']=='BUY' else '🔴 SELL SHORT 💥'} ${stake} {r['lev']}x\n"
             f"💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} | {r['macd']}\n"
             f"⚡ TP1 {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f}) FAST\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f})\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f})\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f}) SAFE\n"
             f"{r['smc']}\n{r['mtf']}\n{r['vol_txt']} | {r['liq']}\n✅ {r['reason']} | Best {len(cands)}/35 BALANCED")
        try:
            b=chart(r)
            if b:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"},files={"photo":b},timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}")

async def start(u,c): save_chat(u.message.chat.id); await u.message.reply_text(f"💀 *V20.2 BALANCED - NO EMERGENCY 👌*\n✅ HARD: PD 0-65% BUY, MACD match, Candle match, RSI safe = Fix WLD/DOT/APT bugs\n✅ SOFT SCORE: Vol 15%+ 🔥 +12, EMA200 +8, BOS +6, OB +10, FVG +10 = Best 25-35/35, Score 55-78\n✅ No more Best 1/35 Emergency, Real price 4 exchanges",parse_mode="Markdown",reply_markup=kb())
async def scan_cmd(u,c): save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start(); await u.message.reply_text("🔍 V20.2 BALANCED SCANNING 35... No Emergency 👌")
async def daily_cmd(u,c): save_chat(u.message.chat.id); d=get_daily(); await u.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L Trades {d['trades']}/3 ${d['pnl']:.2f}",parse_mode="Markdown",reply_markup=kb())
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("No active",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl_pct=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"📡 {act['coin']} {act['dir']} Now {fmt(price)} Entry {fmt(act['entry'])} P&L {pnl_pct:.2f}%",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); await q.message.reply_text("✅ Closed",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("🔍 SCANNING 35 BALANCED..."); return
    if data.startswith("C_"):
        code=data[2:]; r=analyze(code)
        if not r: await q.message.reply_text(f"⚠️ SKIP {code} - Fail HARD filters (PD/MACD/Candle/RSI) - Your WLD/DOT bug blocked",reply_markup=kb()); return
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":STAKE_NORM,"lev":r["lev"],"time":str(datetime.now())})
        b=chart(r); txt=f"💀 *V20.2 BALANCED SCORE {r['conf']}/100 {r['code']} {r['dir']}* @ {fmt(r['entry'])}\n✅ {r['reason']}"
        if b: await q.message.reply_photo(photo=b,caption=txt,parse_mode="Markdown",reply_markup=kb(get_active()))
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb(get_active()))

def monitor():
    while True:
        try:
            time.sleep(35)
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
                    msg=f"💀 {hit}! {act['coin']} +{pct:.0f}% +${pnl:.2f} BALANCED!"; update_daily("WIN",pnl); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL {act['coin']} -{pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":msg},timeout=8)
                except: pass
        except: time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V20.2 BALANCED starting"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
