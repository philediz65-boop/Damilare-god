import os, threading, requests, time, json, urllib.parse
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v34.json"
DAILY_FILE = f"{DATA_DIR}/daily_v34.json"
CHAT_FILE = f"{DATA_DIR}/chat_v34.json"
LEARN_FILE = f"{DATA_DIR}/learn_v34.json"
CACHE = {}
LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}
FAST = ["PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA"]
CRYPTO = {k:f"{k}USDT" for k in FAST}
LEV = {k:10 if k in {"PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE"} else 15 for k in FAST}

def load_json(p,d):
    try:
        if os.path.exists(p):
            with open(p,'r') as f:
                return json.load(f)
    except: pass
    return d
def save_json(p,data):
    try:
        with LOCK:
            with open(p,'w') as f:
                json.dump(data,f)
    except: pass
def get_daily():
    d=load_json(DAILY_FILE,{}); t=str(date.today())
    if d.get("date")!=t:
        d={"date":t,"wins":0,"losses":0,"trades":0,"pnl":0.0}; save_json(DAILY_FILE,d)
    return d
def update_daily(res,pnl,coin=""):
    d=get_daily(); d["trades"]+=1
    if res=="WIN": d["wins"]+=1
    else: d["losses"]+=1
    d["pnl"]+=pnl; save_json(DAILY_FILE,d)
    learn=load_json(LEARN_FILE,{})
    if coin not in learn: learn[coin]={"wins":0,"loss":0,"pnl":0.0}
    if res=="WIN": learn[coin]["wins"]+=1
    else: learn[coin]["loss"]+=1
    learn[coin]["pnl"]+=pnl
    save_json(LEARN_FILE,learn)
def get_learn(): return load_json(LEARN_FILE,{})
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return "V34 SMART AI PERFECT + LIGHT CHART LIVE",200
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
    if key in CACHE and time.time()-CACHE[key][0]<45:
        return CACHE[key][1]
    kl=None
    for fn in [
        lambda: requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7).json(),
        lambda: requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":("120" if interval=="2h" else "60" if interval=="1h" else "15"),"limit":200},headers=HEADERS,timeout=7).json().get("result",{}).get("list",[]),
        lambda: requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":sym.replace("USDT","-USDT"),"bar":("2H" if interval=="2h" else "1H" if interval=="1h" else "15m"),"limit":"200"},headers=HEADERS,timeout=7).json().get("data",[]),
    ]:
        try:
            r=fn()
            lst=r if isinstance(r,list) else []
            if len(lst)>=50:
                # Normalize OKX/Bybit reverse
                if isinstance(lst[0], list) and len(lst[0])>4 and isinstance(lst[0][0], str): # OKX timestamp string
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
                elif isinstance(lst[0], list): # Bybit
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
                else:
                    kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
                if kl: break
        except: pass
    if not kl:
        try:
            r=requests.get("https://api.bitget.com/api/v2/mix/market/candles",params={"symbol":sym,"productType":"USDT-FUTURES","granularity":("2H" if interval=="2h" else "1H" if interval=="1h" else "15m"),"limit":"200"},headers=HEADERS,timeout=7).json()
            lst=r.get("data",[])
            if len(lst)>=50:
                kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
        except: pass
    if kl:
        CACHE[key]=(time.time(),kl)
        return kl
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/ticker/price",params={"symbol":sym},headers=HEADERS,timeout=5).json()
        p=float(r.get("price",0))
        if p>0: return p
    except: pass
    try:
        r=requests.get("https://www.okx.com/api/v5/market/ticker",params={"instId":sym.replace("USDT","-USDT")},headers=HEADERS,timeout=5).json()
        lst=r.get("data",[])
        if lst:
            p=float(lst[0].get("last",0))
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
            pdm.append(up if up>dn and up>0 else 0)
            mdm.append(dn if dn>up and dn>0 else 0)
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
    if pr>e20>e50: return 50,"⬆️ UPTREND"
    if pr>e20: return 20,"↗️ WEAK UP"
    if pr<e20<e50: return -50,"⬇️ DOWNTREND"
    if pr<e20: return -20,"↘️ WEAK DOWN"
    return 0,"➡️ SIDEWAYS"
def vol_calc(kl):
    if len(kl)<20: return 0,"Vol N/A"
    vols=[k["v"] for k in kl[-20:]]; avg=sum(vols[:-1])/len(vols[:-1]); pct=(vols[-1]-avg)/avg*100 if avg else 0
    return pct,f"Vol {pct:.0f}%"

def analyze_single(code):
    try:
        sym=CRYPTO[code]
        k15=get_klines(sym,"15m"); k1=get_klines(sym,"1h"); k2=get_klines(sym,"2h")
        if len(k2)<40: k2=get_klines(sym,"1h")
        if len(k2)<40: k2=get_klines(sym,"15m")
        if len(k2)<40: return None
        c2=[k["c"] for k in k2]
        price=get_price(sym) or c2[-1]
        if abs(price-c2[-1])/c2[-1]>0.08: price=c2[-1]
        rsi_v=rsi_calc(c2); atr_v=atr_calc(k2); adx_v=adx_calc(k2)
        pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2
        c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15); s1,t1=trend_calc(c1); s2,t2=trend_calc(c2)
        vol_pct,vol_txt=vol_calc(k2)
        e200=ema(c2,200)
        bos_bull=k2[-1]["h"]>k2[-2]["h"]; bos_bear=k2[-1]["l"]<k2[-2]["l"]
        align=3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"
        volatility=atr_v/price*100 if price else 0
        return {"code":code,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"e200":e200,"bos_bull":bos_bull,"bos_bear":bos_bear,"align":align,"dir":direction,"kl":k2,"closes":c2}
    except: return None

def ai_score_perfect(r, market_adx, learn):
    score=0; reasons=[]; thoughts=[]
    # PD 20 - PERFECT LIKE ME
    if r["dir"]=="BUY":
        if r["pd_pct"]<=28: score+=20; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% BUY PERFECT +20"); thoughts.append(f"Discount {r['pd_pct']:.0f}% perfect buy zone banks buy here")
        elif r["pd_pct"]<=40: score+=14; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% GOOD +14")
        elif r["pd_pct"]<=50: score+=7; reasons.append(f"EQUIL {r['pd_pct']:.0f}% OK +7")
        elif r["pd_pct"]<=58: score+=2; reasons.append(f"EQUIL HIGH {r['pd_pct']:.0f}% WEAK +2"); thoughts.append(f"Buying at {r['pd_pct']:.0f}% high like QNT")
        else: score-=10; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% BUY BAD -10"); thoughts.append(f"Premium {r['pd_pct']:.0f}% avoid buying top")
    else:
        if r["pd_pct"]>=72: score+=20; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% SELL PERFECT +20"); thoughts.append(f"Premium {r['pd_pct']:.0f}% perfect sell zone")
        elif r["pd_pct"]>=60: score+=14; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% GOOD +14")
        elif r["pd_pct"]>=50: score+=7; reasons.append(f"EQUIL {r['pd_pct']:.0f}% OK +7")
        elif r["pd_pct"]>=42: score+=2; reasons.append(f"EQUIL LOW {r['pd_pct']:.0f}% WEAK +2")
        else: score-=10; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% SELL BAD -10")
    # RSI 15
    if 44<=r["rsi"]<=56: score+=15; reasons.append(f"RSI {r['rsi']:.0f} PERFECT 44-56 +15"); thoughts.append(f"RSI {r['rsi']:.0f} perfect neutral")
    elif 40<=r["rsi"]<=60: score+=10; reasons.append(f"RSI {r['rsi']:.0f} GOOD 40-60 +10")
    elif 36<=r["rsi"]<=66: score+=4; reasons.append(f"RSI {r['rsi']:.0f} OK +4")
    else: score-=5; reasons.append(f"RSI {r['rsi']:.0f} EXTREME -5")
    # ADX 15 - REJECT WEAK LIKE WLD ADX 10
    if 18<=r["adx"]<=50: score+=15; reasons.append(f"ADX {r['adx']:.0f} STRONG TREND +15"); thoughts.append(f"ADX {r['adx']:.0f} strong trend fast TP")
    elif r["adx"]>=14: score+=9; reasons.append(f"ADX {r['adx']:.0f} GOOD +9")
    elif r["adx"]>=12: score+=3; reasons.append(f"ADX {r['adx']:.0f} WEAK +3"); thoughts.append(f"ADX {r['adx']:.0f} weak slow")
    else: score-=5; reasons.append(f"ADX {r['adx']:.0f} VERY WEAK -5 like WLD 10"); thoughts.append(f"ADX {r['adx']:.0f} too weak like WLD screenshot")
    # VOLATILITY + VOL 20 - REJECT -76%
    vs=0
    if r["volatility"]>=2.2: vs+=10; reasons.append(f"Volat {r['volatility']:.2f}% HIGH +10 FAST"); thoughts.append(f"High volat {r['volatility']:.2f}% will hit TP fast like PEPE")
    elif r["volatility"]>=1.3: vs+=6; reasons.append(f"Volat {r['volatility']:.2f}% GOOD +6")
    elif r["volatility"]>=1.0: vs+=2; reasons.append(f"Volat {r['volatility']:.2f}% OK +2")
    else: vs-=5; reasons.append(f"Volat {r['volatility']:.2f}% LOW -5 SLOW")
    if r["vol_pct"]>=15: vs+=10; reasons.append(f"Vol {r['vol_pct']:.0f}% 🔥🔥 +10")
    elif r["vol_pct"]>=5: vs+=6; reasons.append(f"Vol {r['vol_pct']:.0f}% 🔥 +6")
    elif r["vol_pct"]>= -10: vs+=2; reasons.append(f"Vol {r['vol_pct']:.0f}% OK +2")
    elif r["vol_pct"]>= -30: vs-=2; reasons.append(f"Vol {r['vol_pct']:.0f}% LOW -2")
    else: vs-=10; reasons.append(f"Vol {r['vol_pct']:.0f}% DEAD -10 like WLD -76%"); thoughts.append(f"Vol {r['vol_pct']:.0f}% dead no momentum")
    score+=vs
    # MTF + BOS 15
    a_s=0
    if r["align"]==3: a_s+=10; reasons.append(f"Align 3/3 STRONG +10"); thoughts.append(f"All TF agree strong high prob")
    elif r["align"]==2: a_s+=4; reasons.append(f"Align 2/3 +4")
    else: a_s-=3; reasons.append(f"Align 1/3 WEAK -3")
    if r["bos_bull"] or r["bos_bear"]: a_s+=5; reasons.append(f"BOS 🔥 +5 breakout")
    else: a_s-=1; reasons.append(f"BOS No -1 no breakout")
    score+=a_s
    # EMA200 10
    if (r["dir"]=="BUY" and r["price"]>=r["e200"]) or (r["dir"]=="SELL" and r["price"]<=r["e200"]): score+=6; reasons.append(f"EMA200 MATCH +6")
    else: score-=4; reasons.append(f"EMA200 AGAINST -4")
    # LEARN 5
    if r["code"] in learn:
        tot=learn[r["code"]]["wins"]+learn[r["code"]]["loss"]
        if tot>0:
            wr=learn[r["code"]]["wins"]/tot
            if wr>=0.6: score+=5; reasons.append(f"LEARN WR {wr*100:.0f}% +5"); thoughts.append(f"Remember {r['code']} won {wr*100:.0f}% boost")
            elif wr<=0.3: score-=3; reasons.append(f"LEARN Low WR -3")
    return max(0, min(95, score)), reasons, thoughts

def build_trade(r):
    price=r["price"]; atr_v=r["atr"]; d=r["dir"]
    if r["volatility"]>=2.2: sl_m=0.016; tp1_m=0.8; tp2_m=1.6; tp3_m=2.6
    elif r["volatility"]>=1.3: sl_m=0.015; tp1_m=0.7; tp2_m=1.5; tp3_m=2.4
    else: sl_m=0.013; tp1_m=0.6; tp2_m=1.2; tp3_m=2.0
    sl=price*(1-sl_m) if d=="BUY" else price*(1+sl_m)
    tp1=price+atr_v*tp1_m if d=="BUY" else price-atr_v*tp1_m
    tp2=price+atr_v*tp2_m if d=="BUY" else price-atr_v*tp2_m
    tp3=price+atr_v*tp3_m if d=="BUY" else price-atr_v*tp3_m
    return {"code":r["code"],"dir":d,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":LEV[r["code"]],"rsi":r["rsi"],"adx":r["adx"],"volatility":r["volatility"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']} Align {r['align']}/3 ADX {r['adx']:.0f}","vol_txt":r["vol_txt"],"vol_pct":r["vol_pct"],"kl":r["kl"],"closes":r["closes"],"sl_pct":abs(sl-price)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"tp3_pct":abs(tp3-price)/price*100}

def get_light_chart(r):
    try:
        closes=r["closes"][-50:]
        e20=ema_series(closes,20)[-50:]
        labels=[str(i) for i in range(len(closes))]
        cfg={
            "type":"line",
            "data":{
                "labels":labels,
                "datasets":[
                    {"label":r["code"],"data":closes,"borderColor":"black","fill":False,"pointRadius":0,"borderWidth":2},
                    {"label":"EMA20","data":e20,"borderColor":"#2196F3","fill":False,"pointRadius":0,"borderWidth":1},
                ]
            },
            "options":{
                "title":{"display":True,"text":f'{r["code"]} {r["dir"]} SCORE {r["conf"]}/100 Volat {r["volatility"]:.2f}% SMART AI'},
                "annotation":{
                    "annotations":[
                        {"type":"line","mode":"horizontal","scaleID":"y-axis-0","value":r["entry"],"borderColor":"blue","borderWidth":2,"label":{"enabled":True,"content":f'Entry {fmt(r["entry"])}'}},
                        {"type":"line","mode":"horizontal","scaleID":"y-axis-0","value":r["sl"],"borderColor":"red","borderWidth":2,"label":{"enabled":True,"content":f'SL'}},
                        {"type":"line","mode":"horizontal","scaleID":"y-axis-0","value":r["tp1"],"borderColor":"green","borderWidth":2,"label":{"enabled":True,"content":f'TP1'}},
                    ]
                }
            }
        }
        url=f"https://quickchart.io/chart?width=700&height=400&c={urllib.parse.quote(json.dumps(cfg))}"
        resp=requests.get(url,timeout=12)
        if resp.status_code==200 and len(resp.content)>4000:
            return resp.content
    except: pass
    return None

def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 🧠 LIVE',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]} AI',callback_data="CHK"),InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 20 SMART AI PERFECT - Trade {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY")])
    row=[]
    for c in FAST:
        row.append(InlineKeyboardButton(f'{c}',callback_data=f'C_{c}'))
        if len(row)==5:
            btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","🧠 V34 PERFECT"),BotCommand("scan","SCAN SMART"),BotCommand("daily","Daily")])
    except: pass

def bg_scan(chat_id):
    try:
        print(f"🧠 V34 PERFECT SCAN {len(FAST)}")
        raws=[]
        for code in FAST:
            r=analyze_single(code)
            if r:
                raws.append(r)
                print(f" OK {code} ADX {r['adx']:.0f} RSI {r['rsi']:.0f} PD {r['pd_pct']:.0f}% Volat {r['volatility']:.2f}% Vol {r['vol_pct']:.0f}%")
            time.sleep(0.06)
        print(f"FETCHED {len(raws)}/{len(FAST)}")
        if len(raws)==0:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"⚠️ Fetch fail 0/20 - Try 1m"},timeout=10)
            return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        avg_volat=sum(x["volatility"] for x in raws)/len(raws)
        mode="TREND" if avg_adx>=18 else "NORMAL" if avg_adx>=14 else "CHOPPY"
        learn=get_learn()
        cands=[]
        for r in raws:
            # HARD REJECT TRASH LIKE WLD -76%
            if r["vol_pct"] < -40: 
                print(f"  REJECT {r['code']} Vol {r['vol_pct']:.0f}% < -40% dead like WLD screenshot")
                continue
            if r["adx"] < 11:
                print(f"  REJECT {r['code']} ADX {r['adx']:.0f} <11 too weak")
                continue
            if r["rsi"]>78 or r["rsi"]<22: continue
            if r["dir"]=="BUY" and r["pd_pct"]>72: continue
            if r["dir"]=="SELL" and r["pd_pct"]<28: continue
            score,reasons,thoughts=ai_score_perfect(r, avg_adx, learn)
            # ONLY TAKE 65+ SCORE - NO 39/100
            if score < 65:
                print(f"  LOW SCORE {r['code']} {score}/100 <65 skip like WLD 39/100")
                continue
            trade=build_trade(r)
            trade["conf"]=int(score)
            trade["reason"]=" | ".join(reasons[:4])
            trade["ai_thought"]=" | ".join(thoughts) if thoughts else "Good balanced setup"
            trade["mode"]=mode+" PERFECT"
            cands.append(trade)
            print(f"  CAND {r['code']} {int(score)}/100 - {trade['ai_thought'][:60]}")
        if not cands:
            # Find best even if <65 to show why no trade
            all_scores=[]
            for r in raws:
                s,_,_ = ai_score_perfect(r, avg_adx, learn)
                all_scores.append((r["code"], s, r["vol_pct"], r["adx"], r["pd_pct"]))
            all_scores.sort(key=lambda x: x[1], reverse=True)
            best_code, best_score, best_vol, best_adx, best_pd = all_scores[0]
            msg=(f"🛡️ *No FAST quality trade now - Market slow*\n"
                 f"Checked {len(raws)}/20 FAST Avg ADX {avg_adx:.1f} Volat {avg_volat:.2f}% Mode {mode}\n"
                 f"Best was {best_code} SCORE {best_score}/100 Vol {best_vol:.0f}% ADX {best_adx:.0f} PD {best_pd:.0f}% - Too weak like WLD 39/100 screenshot\n"
                 f"Need: Score 65+ + Vol > -40% + ADX 11+ + PD 0-40% BUY 60-100% SELL + RSI 22-78 + Volat 1.0%+\n"
                 f"Try again in 15m - Fast coins resting, not like WLD Vol -76% dead")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"},timeout=10)
            return
        cands.sort(key=lambda x: x["conf"]+x["volatility"]*4 + x["vol_pct"]*0.1, reverse=True)
        best=cands[0]
        print(f"BEST PERFECT {best['code']} {best['dir']} {best['conf']} Volat {best['volatility']:.2f}% THOUGHT {best['ai_thought']}")
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN"},timeout=10)
            return
        r=best
        stake=1.0 if r["conf"]>=75 else 0.6
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(__import__('datetime').datetime.now()),"mode":r["mode"],"ai_thought":r["ai_thought"],"reason":r["reason"]})
        loss=stake*r["sl_pct"]*r["lev"]/100
        p1=stake*r["tp1_pct"]*r["lev"]/100
        p2=stake*r["tp2_pct"]*r["lev"]/100
        p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"🧠 *{r['mode']} SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY LONG 🚀 SMART' if r['dir']=='BUY' else '🔴 SELL SHORT 💥 SMART'} ${stake} {r['lev']}x\n"
             f"💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} Volat {r['volatility']:.2f}% FAST | {r['vol_txt']}\n"
             f"⚡ TP1 FAST {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f})\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f})\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f})\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f})\n"
             f"{r['mtf']}\n"
             f"🧠 *AI THOUGHT (like me):* {r['ai_thought']}\n"
             f"✅ *SCORE:* {r['reason']}\n"
             f"📊 Avg ADX {avg_adx:.1f} Volat {avg_volat:.2f}% | Best {len(cands)}/{len(raws)} PERFECT FAST - Will hit TP fast!")
        chart_bytes=get_light_chart(r)
        try:
            if chart_bytes:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"},files={"photo":("chart.png", chart_bytes, "image/png")},timeout=25)
            else:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}")
        import traceback; traceback.print_exc()

async def start(u,c):
    save_chat(u.message.chat.id)
    await u.message.reply_text(f"🧠 *V34 PERFECT SMART AI LIKE ME + LIGHT CHART*\n✅ Fixed WLD 39/100 screenshot: Now reject Vol < -40% (WLD -76% dead) + ADX <11 + Score <65 = No trade\n✅ Minimum 65/100 to trade - No more 39/100 trash\n✅ Need: Volat 1.0%+ + Vol > -40% + ADX 11+ + PD 0-40% BUY 60-100% SELL + RSI 22-78\n✅ FAST coins priority PEPE BONK WIF FLOKI BOME - High volat fast TP\n✅ Light chart quickchart.io 0MB - Still Live\n✅ AI Thought like me perfect",parse_mode="Markdown",reply_markup=kb())
async def scan_cmd(u,c):
    save_chat(u.message.chat.id)
    threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🧠 SCANNING 20 PERFECT SMART AI - Reject 39/100...")
async def daily_cmd(u,c):
    save_chat(u.message.chat.id)
    d=get_daily(); learn=get_learn()
    txt=f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L Trades {d['trades']}/3 ${d['pnl']:.2f}\n"
    for k,v in learn.items():
        wr=v["wins"]/(v["wins"]+v["loss"])*100 if (v["wins"]+v["loss"])>0 else 0
        txt+=f"{k}: {v['wins']}W/{v['loss']}L WR {wr:.0f}% "
    await u.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb())
async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="DAILY":
        d=get_daily()
        await q.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("No active",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"🧠 {act['coin']} {act['dir']} Now {fmt(price)} Entry {fmt(act['entry'])} P&L {pnl:.2f}%\n🧠 AI: {act.get('ai_thought','')}\n✅ {act.get('reason','')}",reply_markup=kb(act)); return
    if data=="CLS": clear_active(); await q.message.reply_text("✅ Closed",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("🧠 SCANNING 20 PERFECT..."); return
    if data.startswith("C_"):
        code=data[2:]; raw=analyze_single(code)
        if not raw: await q.message.reply_text(f"⚠️ Fetch fail {code}",reply_markup=kb()); return
        trade=build_trade(raw); trade["conf"]=75; trade["reason"]=f"Manual {code}"; trade["ai_thought"]=f"Manual {code} check"; trade["mode"]="MANUAL PERFECT"
        set_active({"status":"OPEN","coin":trade["code"],"dir":trade["dir"],"entry":trade["entry"],"sl":trade["sl"],"tp1":trade["tp1"],"tp2":trade["tp2"],"tp3":trade["tp3"],"conf":trade["conf"],"stake":1.0,"lev":trade["lev"],"time":str(__import__('datetime').datetime.now()),"mode":"MANUAL","ai_thought":trade["ai_thought"],"reason":trade["reason"]})
        txt=f"🧠 *V34 MANUAL {trade['conf']}/100 {trade['code']} {trade['dir']}* @ {fmt(trade['entry'])}"
        chart_bytes=get_light_chart(trade)
        if chart_bytes:
            await q.message.reply_photo(photo=chart_bytes,caption=txt,parse_mode="Markdown",reply_markup=kb(get_active()))
        else:
            await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb(get_active()))

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
                stake=act["stake"]; lev=act["lev"]; entry=act["entry"]; coin=act["coin"]
                if "TP" in hit:
                    tp=act["tp1"] if "TP1" in hit else act["tp2"] if "TP2" in hit else act["tp3"]
                    pct=abs(tp-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"🧠 {hit} SMART! {coin} +{pct:.0f}% +${pnl:.2f} FAST TP!"; update_daily("WIN",pnl,coin); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL SMART {coin} -{pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":msg},timeout=8)
                except: pass
        except: time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V34 PERFECT starting"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
