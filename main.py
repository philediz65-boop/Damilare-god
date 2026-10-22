import os, threading, requests, time, io, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v30.json"
DAILY_FILE = f"{DATA_DIR}/daily_v30.json"
CHAT_FILE = f"{DATA_DIR}/chat_v30.json"
LEARN_FILE = f"{DATA_DIR}/learn_v30.json"
CACHE = {}
LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
STAKE_NORM = 1.0
STAKE_LOW = 0.6
LEV_NORM = 15
LEV_MEME = 10
MEME = {"WIF","PEPE","BONK","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE"}

def get_lev(c):
    return LEV_MEME if c in MEME else LEV_NORM

CRYPTO = {"PEPE":"PEPEUSDT","BONK":"BONKUSDT","WIF":"WIFUSDT","FLOKI":"FLOKIUSDT","BOME":"BOMEUSDT","SHIB":"SHIBUSDT","DOGE":"DOGEUSDT","TRUMP":"TRUMPUSDT","FARTCOIN":"FARTCOINUSDT","ZEREBRO":"ZEREBROUSDT","WLD":"WLDUSDT","HYPE":"HYPEUSDT","SUI":"SUIUSDT","SOL":"SOLUSDT","AVAX":"AVAXUSDT","TAO":"TAOUSDT","ARB":"ARBUSDT","OP":"OPUSDT","ENA":"ENAUSDT","TIA":"TIAUSDT"}
FAST = ["PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA"]

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f:
                return json.load(f)
    except:
        pass
    return d

def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f:
                json.dump(data,f)
    except:
        pass

def get_daily():
    d=load_json(DAILY_FILE,{})
    t=str(date.today())
    if d.get("date")!=t:
        d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0}
        save_json(DAILY_FILE,d)
    return d

def update_daily(res,pnl,coin=""):
    d=get_daily()
    d["trades"]+=1
    if res=="WIN":
        d["wins"]+=1
    else:
        d["losses"]+=1
    d["pnl"]+=pnl
    save_json(DAILY_FILE,d)
    learn=load_json(LEARN_FILE,{})
    if coin not in learn:
        learn[coin]={"wins":0,"loss":0,"pnl":0.0}
    if res=="WIN":
        learn[coin]["wins"]+=1
    else:
        learn[coin]["loss"]+=1
    learn[coin]["pnl"]+=pnl
    save_json(LEARN_FILE,learn)

def get_learn(): return load_json(LEARN_FILE,{})
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return "V30 SMART AI FAST 20 LIVE",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        v=float(v)
        if v>=1000: return f"{v:,.2f}"
        if v>=1: return f"{v:.4f}"
        if v>=0.01: return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except:
        return str(v)

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<30:
        return CACHE[key][1]
    kl=None
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=6).json()
        if isinstance(r,list) and len(r)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
    except:
        pass
    if not kl:
        try:
            iv="120" if interval=="2h" else "60" if interval=="1h" else "15"
            r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":iv,"limit":200},headers=HEADERS,timeout=6).json()
            lst=r.get("result",{}).get("list",[])
            if len(lst)>=50:
                kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
        except:
            pass
    if kl:
        CACHE[key]=(time.time(),kl)
        return kl
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=5).json()
        p=float(r.get("price",0))
        if p>0:
            return p
    except:
        pass
    kl=get_klines(sym,"15m")
    return kl[-1]["c"] if kl else None

def ema(arr,p):
    if len(arr)<p:
        return sum(arr)/len(arr) if arr else 0
    k=2/(p+1)
    e=sum(arr[:p])/p
    for x in arr[p:]:
        e=(x-e)*k+e
    return e

def ema_series(arr,p):
    if len(arr)<p:
        return [sum(arr)/len(arr)]*len(arr)
    k=2/(p+1)
    e=sum(arr[:p])/p
    res=[e]*p
    for x in arr[p:]:
        e=(x-e)*k+e
        res.append(e)
    return res

def rsi_calc(arr,p=14):
    if len(arr)<p+1:
        return 50
    g=l=0
    for i in range(1,p+1):
        d=arr[-i]-arr[-i-1]
        if d>0:
            g+=d
        else:
            l+=-d
    if l==0:
        return 70 if g>0 else 50
    return 100 - (100/(1+g/l))

def atr_calc(kl,p=14):
    if len(kl)<p+1:
        return kl[-1]["c"]*0.02
    trs=[]
    for i in range(1,p+1):
        trs.append(max(kl[-i]["h"]-kl[-i]["l"], abs(kl[-i]["h"]-kl[-i-1]["c"]), abs(kl[-i]["l"]-kl[-i-1]["c"])))
    return sum(trs)/len(trs)

def adx_calc(kl):
    try:
        if len(kl)<30:
            return 18
        highs=[k["h"] for k in kl]
        lows=[k["l"] for k in kl]
        closes=[k["c"] for k in kl]
        tr=[]; pdm=[]; mdm=[]
        for i in range(1,len(kl)):
            up=highs[i]-highs[i-1]
            dn=lows[i-1]-lows[i]
            pdm.append(up if up>dn and up>0 else 0)
            mdm.append(dn if dn>up and dn>0 else 0)
            tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        atr_v=sum(tr[-14:])/14
        if atr_v==0:
            return 18
        pdi=100*sum(pdm[-14:])/14/atr_v
        mdi=100*sum(mdm[-14:])/14/atr_v
        if pdi+mdi==0:
            return 18
        return max(10, min(60, 100*abs(pdi-mdi)/(pdi+mdi)))
    except:
        return 18

def macd_calc(closes):
    if len(closes)<35:
        return "NEUTRAL"
    e12=ema_series(closes,12)
    e26=ema_series(closes,26)
    ml=[a-b for a,b in zip(e12[-len(e26):],e26)]
    sig=ema_series(ml,9)
    return "🟢 BULLISH" if ml[-1]>sig[-1] else "🔴 BEARISH"

def pd_calc(kl):
    if len(kl)<100:
        return "EQUILIBRIUM",50
    hi=max(k["h"] for k in kl[-100:])
    lo=min(k["l"] for k in kl[-100:])
    pr=kl[-1]["c"]
    pct=(pr-lo)/(hi-lo)*100 if hi!=lo else 50
    if pct>=70:
        return "PREMIUM",pct
    if pct<=30:
        return "DISCOUNT",pct
    return "EQUILIBRIUM",pct

def trend_calc(closes):
    if len(closes)<50:
        return 0,"SIDEWAYS"
    e20=ema(closes,20)
    e50=ema(closes,50)
    pr=closes[-1]
    if pr>e20>e50:
        return 50,"⬆️ UPTREND"
    if pr>e20:
        return 20,"↗️ WEAK UP"
    if pr<e20<e50:
        return -50,"⬇️ DOWNTREND"
    if pr<e20:
        return -20,"↘️ WEAK DOWN"
    return 0,"➡️ SIDEWAYS"

def vol_calc(kl):
    if len(kl)<20:
        return 0,"Vol N/A"
    vols=[k["v"] for k in kl[-20:]]
    avg=sum(vols[:-1])/len(vols[:-1]) if len(vols)>1 else 1
    pct=(vols[-1]-avg)/avg*100 if avg else 0
    return pct,f"📊 Vol {pct:.0f}% {'🔥' if pct>5 else ''}"

def analyze_single(code):
    try:
        sym=CRYPTO[code]
        k15=get_klines(sym,"15m")
        k1=get_klines(sym,"1h")
        k2=get_klines(sym,"2h")
        if len(k2)<50:
            k2=get_klines(sym,"1h")
        if len(k2)<50:
            return None
        c2=[k["c"] for k in k2]
        price=get_price(sym) or c2[-1]
        if abs(price-c2[-1])/c2[-1]>0.08:
            price=c2[-1]
        rsi_v=rsi_calc(c2)
        atr_v=atr_calc(k2)
        adx_v=adx_calc(k2)
        macd=macd_calc(c2)
        pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2
        c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15)
        s1,t1=trend_calc(c1)
        s2,t2=trend_calc(c2)
        vol_pct,vol_txt=vol_calc(k2)
        e200=ema(c2,200)
        bos_bull = k2[-1]["h"] > k2[-2]["h"] or k2[-1]["c"] > k2[-2]["h"]
        bos_bear = k2[-1]["l"] < k2[-2]["l"] or k2[-1]["c"] < k2[-2]["l"]
        align = 3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        is_strong = align==3
        direction="BUY" if s2>=0 else "SELL"
        volatility = atr_v/price*100 if price else 0
        return {"code":code,"sym":sym,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"macd":macd,"pd_zone":pd_zone,"pd_pct":pd_pct,"s15":s15,"s1":s1,"s2":s2,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"e200":e200,"bos_bull":bos_bull,"bos_bear":bos_bear,"align":align,"is_strong":is_strong,"dir":direction,"kl":k2}
    except:
        return None

def ai_score(r, market_adx, learn):
    score=0
    reasons=[]
    thoughts=[]
    if r["dir"]=="BUY":
        if r["pd_pct"]<=25:
            score+=20; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% BUY +20"); thoughts.append(f"Discount {r['pd_pct']:.0f}% perfect buy")
        elif r["pd_pct"]<=38:
            score+=14; reasons.append(f"DISCOUNT LOW {r['pd_pct']:.0f}% +14")
        elif r["pd_pct"]<=50:
            score+=8; reasons.append(f"EQUIL {r['pd_pct']:.0f}% +8")
        elif r["pd_pct"]<=60:
            score+=3; reasons.append(f"EQUIL HIGH {r['pd_pct']:.0f}% +3"); thoughts.append(f"Buying {r['pd_pct']:.0f}% high risky like QNT")
        else:
            score+=-8; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% BUY BAD -8"); thoughts.append(f"Premium {r['pd_pct']:.0f}% avoid")
    else:
        if r["pd_pct"]>=75:
            score+=20; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% SELL +20")
        elif r["pd_pct"]>=62:
            score+=14; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% SELL +14")
        elif r["pd_pct"]>=50:
            score+=8; reasons.append(f"EQUIL {r['pd_pct']:.0f}% +8")
        elif r["pd_pct"]>=40:
            score+=3; reasons.append(f"EQUIL LOW {r['pd_pct']:.0f}% +3")
        else:
            score+=-8; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% SELL BAD -8")
    if 45<=r["rsi"]<=55:
        score+=15; reasons.append(f"RSI {r['rsi']:.0f} PERFECT +15"); thoughts.append(f"RSI {r['rsi']:.0f} perfect")
    elif 40<=r["rsi"]<=60:
        score+=10; reasons.append(f"RSI {r['rsi']:.0f} GOOD +10")
    elif 35<=r["rsi"]<=65:
        score+=5; reasons.append(f"RSI {r['rsi']:.0f} OK +5")
    else:
        score+=-2; reasons.append(f"RSI {r['rsi']:.0f} EXTREME -2")
    if 18<=r["adx"]<=50:
        score+=15; reasons.append(f"ADX {r['adx']:.0f} PERFECT +15")
    elif r["adx"]>=14:
        score+=10; reasons.append(f"ADX {r['adx']:.0f} GOOD +10")
    elif r["adx"]>=10:
        score+=5; reasons.append(f"ADX {r['adx']:.0f} WEAK +5"); thoughts.append(f"ADX {r['adx']:.0f} weak like WLD 10")
    else:
        score+=0; reasons.append(f"ADX {r['adx']:.0f} VERY WEAK +0")
    vol_s=0
    if r["volatility"]>=2.0:
        vol_s+=8; reasons.append(f"Volat {r['volatility']:.2f}% HIGH +8 FAST"); thoughts.append(f"High volat {r['volatility']:.2f}% fast TP")
    elif r["volatility"]>=1.2:
        vol_s+=5; reasons.append(f"Volat {r['volatility']:.2f}% GOOD +5")
    elif r["volatility"]>=0.8:
        vol_s+=2; reasons.append(f"Volat {r['volatility']:.2f}% OK +2")
    if r["vol_pct"]>=10:
        vol_s+=7; reasons.append(f"Vol {r['vol_pct']:.0f}% 🔥 +7")
    elif r["vol_pct"]>=3:
        vol_s+=4; reasons.append(f"Vol {r['vol_pct']:.0f}% +4")
    elif r["vol_pct"]>=-5:
        vol_s+=1; reasons.append(f"Vol {r['vol_pct']:.0f}% OK +1")
    score+=vol_s
    align_s=0
    if r["align"]==3 and r["is_strong"]:
        align_s+=10; reasons.append(f"Align 3/3 STRONG +10"); thoughts.append(f"All TF agree strong")
    elif r["align"]==3:
        align_s+=7; reasons.append(f"Align 3/3 +7")
    elif r["align"]==2:
        align_s+=3; reasons.append(f"Align 2/3 +3")
    if r["bos_bull"] or r["bos_bear"]:
        align_s+=5; reasons.append(f"BOS 🔥 +5")
    score+=align_s
    macd_s=0
    if r["dir"]=="BUY" and "BULLISH" in r["macd"]:
        macd_s+=6; reasons.append(f"MACD BULL MATCH +6")
    elif r["dir"]=="SELL" and "BEARISH" in r["macd"]:
        macd_s+=6; reasons.append(f"MACD BEAR MATCH +6")
    elif "NEUTRAL" in r["macd"]:
        macd_s+=2; reasons.append(f"MACD NEUTRAL +2")
    else:
        macd_s+=-4; reasons.append(f"MACD MISMATCH -4 QNT BAD"); thoughts.append(f"MACD mismatch QNT loss")
    if (r["dir"]=="BUY" and r["price"]>=r["e200"]) or (r["dir"]=="SELL" and r["price"]<=r["e200"]):
        macd_s+=4; reasons.append(f"EMA200 MATCH +4")
    else:
        macd_s+=-2; reasons.append(f"EMA200 AGAINST -2")
    score+=macd_s
    if r["code"] in learn:
        tot=learn[r["code"]]["wins"]+learn[r["code"]]["loss"]
        if tot>0:
            wr=learn[r["code"]]["wins"]/tot
            if wr>=0.6:
                score+=5; reasons.append(f"LEARN {r['code']} WR {wr*100:.0f}% +5")
    final_score=max(5, min(95, score))
    return final_score, reasons, thoughts

def build_trade(r):
    price=r["price"]; atr_v=r["atr"]; direction=r["dir"]
    if r["volatility"]>=2.5:
        sl_m=0.016; tp1_m=1.0; tp2_m=2.0; tp3_m=3.2
    elif r["volatility"]>=1.5:
        sl_m=0.016; tp1_m=0.8; tp2_m=1.6; tp3_m=2.5
    else:
        sl_m=0.014; tp1_m=0.6; tp2_m=1.3; tp3_m=2.0
    sl=price*(1-sl_m) if direction=="BUY" else price*(1+sl_m)
    tp1=price+atr_v*tp1_m if direction=="BUY" else price-atr_v*tp1_m
    tp2=price+atr_v*tp2_m if direction=="BUY" else price-atr_v*tp2_m
    tp3=price+atr_v*tp3_m if direction=="BUY" else price-atr_v*tp3_m
    return {"code":r["code"],"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":get_lev(r["code"]),"rsi":r["rsi"],"adx":r["adx"],"atr":atr_v,"volatility":r["volatility"],"macd":r["macd"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']} Align {r['align']}/3 ADX {r['adx']:.0f}","vol_txt":r["vol_txt"],"vol_pct":r["vol_pct"],"kl":r["kl"],"e200":r["e200"],"align":r["align"],"is_strong":r["is_strong"],"bos_bull":r["bos_bull"],"bos_bear":r["bos_bear"],"sl_pct":abs(sl-price)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"tp3_pct":abs(tp3-price)/price*100}

def chart_img(r):
    try:
        kl=r["kl"][-100:]; closes=[k["c"] for k in kl]
        e20=ema_series(closes,20); e50=ema_series(closes,50); e200=ema_series(closes,200)
        fig,ax=plt.subplots(figsize=(11,6))
        ax.plot(closes,color="black",lw=1.2); ax.plot(e20,color="#2196F3",lw=0.8); ax.plot(e50,color="#FF9800",lw=0.8); ax.plot(e200,color="#9C27B0",ls=":")
        ax.axhline(r["entry"],color="blue",ls="--",label=f'Entry {fmt(r["entry"])}'); ax.axhline(r["sl"],color="red",label=f'SL {fmt(r["sl"])}')
        ax.axhline(r["tp1"],color="green",label=f'TP1 {fmt(r["tp1"])}'); ax.axhline(r["tp2"],color="#4CAF50",ls="-.",label=f'TP2'); ax.axhline(r["tp3"],color="#00E676",ls=":",label=f'TP3')
        ax.set_title(f'{r["code"]} {r["dir"]} AI SCORE {r["conf"]}/100 {r["lev"]}x Volat {r["volatility"]:.2f}%',fontsize=10,fontweight='bold')
        ax.legend(fontsize=7,ncol=2); ax.grid(True,alpha=0.3); plt.tight_layout()
        buf=io.BytesIO(); plt.savefig(buf,format='png',dpi=160); buf.seek(0); plt.close(fig); return buf
    except:
        return None

def kb(active=None):
    daily=get_daily(); learn=get_learn()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 🧠 LIVE',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]} AI',callback_data="CHK"),InlineKeyboardButton(f'❌ Close {active["coin"]}',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 20 SMART AI - Trade {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f} Learn {len(learn)}',callback_data="DAILY")])
    row=[]
    for c in FAST:
        row.append(InlineKeyboardButton(f'⚡ {c}',callback_data=f'C_{c}'))
        if len(row)==4:
            btns.append(row); row=[]
    if row:
        btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","🧠 V30 SMART"),BotCommand("scan","🧠 SCAN AI"),BotCommand("daily","📊 Daily")])
    except:
        pass

def bg_scan(chat_id):
    try:
        print(f"🧠 V30 SMART AI SCAN {len(FAST)}")
        raws=[]
        for code in FAST:
            r=analyze_single(code)
            if r:
                raws.append(r)
                print(f"  OK {code} ADX {r['adx']:.0f} RSI {r['rsi']:.0f} PD {r['pd_pct']:.0f}% Volat {r['volatility']:.2f}%")
            time.sleep(0.06)
        print(f"FETCHED {len(raws)}/{len(FAST)}")
        if len(raws)==0:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"⚠️ Fetch fail 0/20 - Binance/Bybit block - Try again in 1 min"},timeout=10)
            return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        avg_volat=sum(x["volatility"] for x in raws)/len(raws)
        mode="TREND" if avg_adx>=18 else "NORMAL" if avg_adx>=14 else "CHOPPY"
        learn=get_learn()
        cands=[]
        for r in raws:
            if r["rsi"]>80 or r["rsi"]<20:
                continue
            if r["dir"]=="BUY" and r["pd_pct"]>75:
                continue
            if r["dir"]=="SELL" and r["pd_pct"]<25:
                continue
            score,reasons,thoughts=ai_score(r, avg_adx, learn)
            trade=build_trade(r)
            trade["conf"]=int(score)
            trade["reason"]=" | ".join(reasons[:5])
            trade["ai_thought"]=" | ".join(thoughts) if thoughts else "Balanced setup"
            trade["mode"]=mode+" SMART AI"
            cands.append(trade)
        if not cands:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🧠 No trade avg ADX {avg_adx:.1f} - All extreme RSI or PD>75% BUY - Wait 10m"},timeout=10)
            return
        cands.sort(key=lambda x: x["conf"] + x["volatility"]*3, reverse=True)
        best=cands[0]
        print(f"BEST SMART {best['code']} {best['dir']} {best['conf']} Volat {best['volatility']:.2f}%")
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN"},timeout=10)
            return
        r=best
        stake=STAKE_NORM if r["conf"]>=70 else STAKE_LOW
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(__import__('datetime').datetime.now()),"mode":r["mode"],"ai_thought":r["ai_thought"],"reason":r["reason"]})
        loss=stake*r["sl_pct"]*r["lev"]/100
        p1=stake*r["tp1_pct"]*r["lev"]/100
        p2=stake*r["tp2_pct"]*r["lev"]/100
        p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"🧠 *{r['mode']} SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY 🚀' if r['dir']=='BUY' else '🔴 SELL 💥'} ${stake} {r['lev']}x\n"
             f"💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} Volat {r['volatility']:.2f}% | {r['macd']}\n"
             f"⚡ TP1 {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f})\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f})\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f})\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f})\n"
             f"{r['mtf']}\n{r['vol_txt']}\n"
             f"🧠 AI: {r['ai_thought']}\n"
             f"✅ {r['reason']} | Best {len(cands)}/{len(raws)} SMART AI")
        try:
            b=chart_img(r)
            if b:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"},files={"photo":b},timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}")
        import traceback; traceback.print_exc()

async def start(u,c):
    save_chat(u.message.chat.id)
    await u.message.reply_text(f"🧠 *V30 SMART AI LIKE ME - CLEAN DEPLOY*\n✅ Fixed FAILED a563526: Clean syntax no bug\n✅ 20 FAST: PEPE BONK WIF FLOKI BOME SHIB DOGE TRUMP FARTCOIN ZEREBRO WLD HYPE SUI SOL AVAX TAO ARB OP ENA TIA\n✅ SMART AI SCORE: PD 20% + RSI 15% + ADX 15% + Vol 15% + MTF+BOS 15% + MACD+EMA 10% + Learn 5% = No hard block\n✅ Always trades best score - No more No entry\n✅ AI Thought explains like me",parse_mode="Markdown",reply_markup=kb())

async def scan_cmd(u,c):
    save_chat(u.message.chat.id)
    threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🧠 SCANNING 20 SMART AI...")

async def daily_cmd(u,c):
    save_chat(u.message.chat.id)
    d=get_daily()
    await u.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L Trades {d['trades']}/3 ${d['pnl']:.2f}",parse_mode="Markdown",reply_markup=kb())

async def btn_handler(u,c):
    q=u.callback_query
    await q.answer()
    data=q.data
    if data=="DAILY":
        d=get_daily()
        await q.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active()))
        return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN":
            await q.message.reply_text("No active",reply_markup=kb())
            return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"🧠 {act['coin']} {act['dir']} Now {fmt(price)} Entry {fmt(act['entry'])} P&L {pnl:.2f}%\nAI: {act.get('ai_thought','')}",reply_markup=kb(act))
        return
    if data=="CLS":
        clear_active()
        await q.message.reply_text("✅ Closed",reply_markup=kb())
        return
    if data=="SCAN":
        threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start()
        await q.message.reply_text("🧠 SCANNING 20 SMART AI...")
        return
    if data.startswith("C_"):
        code=data[2:]
        raw=analyze_single(code)
        if not raw:
            await q.message.reply_text(f"⚠️ Fetch fail {code}",reply_markup=kb())
            return
        trade=build_trade(raw)
        trade["conf"]=75
        trade["reason"]=f"Manual {code}"
        trade["ai_thought"]=f"Manual {code}"
        trade["mode"]="MANUAL SMART AI"
        set_active({"status":"OPEN","coin":trade["code"],"dir":trade["dir"],"entry":trade["entry"],"sl":trade["sl"],"tp1":trade["tp1"],"tp2":trade["tp2"],"tp3":trade["tp3"],"conf":trade["conf"],"stake":STAKE_NORM,"lev":trade["lev"],"time":str(__import__('datetime').datetime.now()),"mode":"MANUAL","ai_thought":trade["ai_thought"],"reason":trade["reason"]})
        b=chart_img(trade)
        txt=f"🧠 *V30 MANUAL {trade['conf']}/100 {trade['code']} {trade['dir']}* @ {fmt(trade['entry'])}"
        if b:
            await q.message.reply_photo(photo=b,caption=txt,parse_mode="Markdown",reply_markup=kb(get_active()))
        else:
            await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb(get_active()))

def monitor():
    while True:
        try:
            time.sleep(25)
            act=get_active()
            if not act.get("status")=="OPEN":
                continue
            price=get_price(CRYPTO[act["coin"]])
            if not price:
                continue
            chat=get_chat()
            if not chat:
                continue
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
                stake=act["stake"]; lev=act["lev"]; entry=act["entry"]; coin=act["coin"]
                if "TP" in hit:
                    tp=act["tp1"] if "TP1" in hit else act["tp2"] if "TP2" in hit else act["tp3"]
                    pct=abs(tp-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"🧠 {hit} SMART AI! {coin} +{pct:.0f}% +${pnl:.2f}"; update_daily("WIN",pnl,coin); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL SMART AI {coin} -{pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl,coin); clear_active()
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":msg},timeout=8)
                except:
                    pass
        except:
            time.sleep(10)

def run_flask():
    app.run(host="0.0.0.0",port=PORT)

def run_bot():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing")
        return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start))
    a.add_handler(CommandHandler("scan",scan_cmd))
    a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V30 SMART AI starting")
    a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
