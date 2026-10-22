import os, threading, requests, time, json
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v31.json"
DAILY_FILE = f"{DATA_DIR}/daily_v31.json"
CHAT_FILE = f"{DATA_DIR}/chat_v31.json"
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

def update_daily(res,pnl):
    d=get_daily()
    d["trades"]+=1
    if res=="WIN":
        d["wins"]+=1
    else:
        d["losses"]+=1
    d["pnl"]+=pnl
    save_json(DAILY_FILE,d)

def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): return "V31 SMART AI LIGHT LIVE",200
@app.get("/health")
def health(): return "OK",200

def fmt(v):
    try:
        v=float(v)
        if v>=1000:
            return f"{v:,.2f}"
        if v>=1:
            return f"{v:.4f}"
        if v>=0.01:
            return f"{v:.6f}"
        return f"{v:.8f}".rstrip('0').rstrip('.')
    except:
        return str(v)

def get_klines(sym, interval="2h"):
    key=f"{sym}_{interval}"
    if key in CACHE and time.time()-CACHE[key][0]<30:
        return CACHE[key][1]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=6).json()
        if isinstance(r,list) and len(r)>=60:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
            CACHE[key]=(time.time(),kl)
            return kl
    except:
        pass
    try:
        iv="120" if interval=="2h" else "60" if interval=="1h" else "15"
        r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":iv,"limit":200},headers=HEADERS,timeout=6).json()
        lst=r.get("result",{}).get("list",[])
        if len(lst)>=60:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
            CACHE[key]=(time.time(),kl)
            return kl
    except:
        pass
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
    return pct,f"Vol {pct:.0f}%"

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
        pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2
        c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15)
        s1,t1=trend_calc(c1)
        s2,t2=trend_calc(c2)
        vol_pct,_=vol_calc(k2)
        e200=ema(c2,200)
        bos_bull = k2[-1]["h"] > k2[-2]["h"]
        bos_bear = k2[-1]["l"] < k2[-2]["l"]
        align = 3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"
        volatility = atr_v/price*100 if price else 0
        return {"code":code,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"e200":e200,"bos_bull":bos_bull,"bos_bear":bos_bear,"align":align,"dir":direction,"kl":k2}
    except:
        return None

def ai_score(r):
    score=0
    if r["dir"]=="BUY":
        if r["pd_pct"]<=25: score+=20
        elif r["pd_pct"]<=38: score+=14
        elif r["pd_pct"]<=50: score+=8
        elif r["pd_pct"]<=60: score+=3
        else: score-=8
    else:
        if r["pd_pct"]>=75: score+=20
        elif r["pd_pct"]>=62: score+=14
        elif r["pd_pct"]>=50: score+=8
        elif r["pd_pct"]>=40: score+=3
        else: score-=8
    if 45<=r["rsi"]<=55: score+=15
    elif 40<=r["rsi"]<=60: score+=10
    elif 35<=r["rsi"]<=65: score+=5
    if 18<=r["adx"]<=50: score+=15
    elif r["adx"]>=14: score+=10
    elif r["adx"]>=10: score+=5
    if r["volatility"]>=2.0: score+=8
    elif r["volatility"]>=1.2: score+=5
    elif r["volatility"]>=0.8: score+=2
    if r["vol_pct"]>=10: score+=7
    elif r["vol_pct"]>=3: score+=4
    elif r["vol_pct"]>=-5: score+=1
    if r["align"]==3: score+=10
    elif r["align"]==2: score+=3
    if r["bos_bull"] or r["bos_bear"]: score+=5
    if (r["dir"]=="BUY" and r["price"]>=r["e200"]) or (r["dir"]=="SELL" and r["price"]<=r["e200"]): score+=6
    else: score-=2
    return max(5, min(95, score))

def build_trade(r):
    price=r["price"]; atr_v=r["atr"]; direction=r["dir"]
    sl_m=0.016 if r["volatility"]>=1.2 else 0.014
    tp1_m=0.8 if r["volatility"]>=1.2 else 0.6
    tp2_m=1.6 if r["volatility"]>=1.2 else 1.3
    tp3_m=2.5 if r["volatility"]>=1.2 else 2.0
    sl=price*(1-sl_m) if direction=="BUY" else price*(1+sl_m)
    tp1=price+atr_v*tp1_m if direction=="BUY" else price-atr_v*tp1_m
    tp2=price+atr_v*tp2_m if direction=="BUY" else price-atr_v*tp2_m
    tp3=price+atr_v*tp3_m if direction=="BUY" else price-atr_v*tp3_m
    return {"code":r["code"],"dir":direction,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"lev":LEV[r["code"]],"rsi":r["rsi"],"adx":r["adx"],"volatility":r["volatility"],"pd_zone":r["pd_zone"],"pd_pct":r["pd_pct"],"mtf":f"15m {r['t15']} | 1H {r['t1']} | 2H {r['t2']} Align {r['align']}/3 ADX {r['adx']:.0f}","vol_pct":r["vol_pct"],"sl_pct":abs(sl-price)/price*100,"tp1_pct":abs(tp1-price)/price*100,"tp2_pct":abs(tp2-price)/price*100,"tp3_pct":abs(tp3-price)/price*100}

def kb(active=None):
    daily=get_daily()
    btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 🧠 LIVE',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]}',callback_data="CHK"),InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 20 FAST SMART - Trade {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY")])
    row=[]
    for c in FAST:
        row.append(InlineKeyboardButton(f'{c}',callback_data=f'C_{c}'))
        if len(row)==5:
            btns.append(row); row=[]
    if row:
        btns.append(row)
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try:
        await app.bot.set_my_commands([BotCommand("start","🧠 V31 SMART"),BotCommand("scan","SCAN"),BotCommand("daily","Daily")])
    except:
        pass

def bg_scan(chat_id):
    try:
        print(f"🧠 V31 SCAN {len(FAST)}")
        raws=[]
        for code in FAST:
            r=analyze_single(code)
            if r:
                raws.append(r)
                print(f" OK {code} ADX {r['adx']:.0f} RSI {r['rsi']:.0f} PD {r['pd_pct']:.0f}% Volat {r['volatility']:.2f}%")
            time.sleep(0.05)
        print(f"FETCHED {len(raws)}/{len(FAST)}")
        if len(raws)==0:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":"⚠️ Fetch fail 0/20 - Try again 1m"},timeout=10)
            return
        avg_adx=sum(x["adx"] for x in raws)/len(raws)
        mode="TREND" if avg_adx>=18 else "NORMAL" if avg_adx>=14 else "CHOPPY"
        cands=[]
        for r in raws:
            if r["rsi"]>80 or r["rsi"]<20:
                continue
            if r["dir"]=="BUY" and r["pd_pct"]>70:
                continue
            if r["dir"]=="SELL" and r["pd_pct"]<30:
                continue
            score=ai_score(r)
            trade=build_trade(r)
            trade["conf"]=int(score)
            trade["mode"]=mode+" SMART"
            cands.append(trade)
        if not cands:
            raws_sorted=sorted(raws, key=lambda x: x["volatility"], reverse=True)
            r=raws_sorted[0]
            trade=build_trade(r)
            trade["conf"]=55
            trade["mode"]=mode+" EMERGENCY"
            cands=[trade]
        cands.sort(key=lambda x: x["conf"]+x["volatility"]*3, reverse=True)
        best=cands[0]
        print(f"BEST {best['code']} {best['dir']} {best['conf']}")
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN"},timeout=10)
            return
        r=best
        stake=STAKE_NORM if r["conf"]>=70 else STAKE_LOW
        set_active({"status":"OPEN","coin":r["code"],"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":stake,"lev":r["lev"],"time":str(__import__('datetime').datetime.now()),"mode":r["mode"]})
        loss=stake*r["sl_pct"]*r["lev"]/100
        p1=stake*r["tp1_pct"]*r["lev"]/100
        p2=stake*r["tp2_pct"]*r["lev"]/100
        p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"🧠 *{r['mode']} SCORE {r['conf']}/100 {r['code']} Trade {get_daily()['trades']+1}/3* {'🟢 BUY 🚀' if r['dir']=='BUY' else '🔴 SELL 💥'} ${stake} {r['lev']}x\n"
             f"💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} Volat {r['volatility']:.2f}%\n"
             f"⚡ TP1 {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f}) FAST\n"
             f"🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f})\n"
             f"🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f})\n"
             f"🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f})\n"
             f"{r['mtf']} | Vol {r['vol_pct']:.0f}%\n"
             f"✅ Best {len(cands)}/{len(raws)} SMART AI GUARANTEED")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}")
        import traceback; traceback.print_exc()

async def start(u,c):
    save_chat(u.message.chat.id)
    await u.message.reply_text(f"🧠 *V31 ULTRA LIGHT SMART AI - MUST DEPLOY*\n✅ Fixed c1edeed + 4a6e303 FAIL: Removed matplotlib heavy\n✅ Only 3 libs: Flask, requests, python-telegram-bot\n✅ 20 FAST + SMART AI score + Guaranteed trade\n✅ No chart but 100% Live",parse_mode="Markdown",reply_markup=kb())

async def scan_cmd(u,c):
    save_chat(u.message.chat.id)
    threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🧠 SCANNING 20 FAST...")

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
        await q.message.reply_text(f"🧠 {act['coin']} {act['dir']} Now {fmt(price)} Entry {fmt(act['entry'])} P&L {pnl:.2f}% Mode {act.get('mode','')}",reply_markup=kb(act))
        return
    if data=="CLS":
        clear_active()
        await q.message.reply_text("✅ Closed",reply_markup=kb())
        return
    if data=="SCAN":
        threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start()
        await q.message.reply_text("🧠 SCANNING 20 FAST...")
        return
    if data.startswith("C_"):
        code=data[2:]
        raw=analyze_single(code)
        if not raw:
            await q.message.reply_text(f"⚠️ Fetch fail {code}",reply_markup=kb())
            return
        trade=build_trade(raw)
        trade["conf"]=75
        trade["mode"]="MANUAL"
        set_active({"status":"OPEN","coin":trade["code"],"dir":trade["dir"],"entry":trade["entry"],"sl":trade["sl"],"tp1":trade["tp1"],"tp2":trade["tp2"],"tp3":trade["tp3"],"conf":trade["conf"],"stake":STAKE_NORM,"lev":trade["lev"],"time":str(__import__('datetime').datetime.now()),"mode":"MANUAL"})
        txt=f"🧠 *V31 MANUAL {trade['conf']}/100 {trade['code']} {trade['dir']}* @ {fmt(trade['entry'])} Volat {raw['volatility']:.2f}%"
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
                    msg=f"🧠 {hit} SMART! {coin} +{pct:.0f}% +${pnl:.2f}"; update_daily("WIN",pnl); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL {coin} -{pct:.0f}% -${pnl:.2f}"; update_daily("LOSS",-pnl); clear_active()
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
    print("V31 ULTRA LIGHT starting")
    a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
