import os, threading, requests, time, json, urllib.parse
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from datetime import date
from binance.client import Client
from binance.exceptions import BinanceAPIException

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_SECRET = os.getenv("BINANCE_SECRET","").strip()
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET","false").lower() == "true"
TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT","5"))

PORT = int(os.getenv("PORT","10000"))
app = Flask(__name__)
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_v40.json"
DAILY_FILE = f"{DATA_DIR}/daily_v40.json"
CHAT_FILE = f"{DATA_DIR}/chat_v40.json"
LEARN_FILE = f"{DATA_DIR}/learn_v40.json"
CACHE = {}; LOCK = threading.Lock()
HEADERS = {"User-Agent":"Mozilla/5.0"}

# --- BINANCE CLASSIC CLIENT ---
binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET:
    try:
        if BINANCE_TESTNET:
            binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=True)
            print("Client: Testnet Binance")
        else:
            binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET)
            print("Client: Real Binance (Classic Mode) ✅")
            # Test connection
            bal = binance_client.futures_account_balance()
            print(f"Futures Balance: {bal}")
    except Exception as e:
        print(f"Binance Client Error: {e}")
else:
    print("BINANCE_API_KEY missing - running signal only")

def setup_symbol_classic(symbol):
    if not binance_client: return
    try:
        binance_client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
    except: pass
    try:
        binance_client.futures_change_leverage(symbol=symbol, leverage=10)
    except Exception as e:
        print(f"Leverage {symbol}: {e}")

def place_real_order(symbol, direction, usdt_amount):
    if not binance_client:
        print("No binance client - skip real order")
        return None
    try:
        price_data = binance_client.futures_symbol_ticker(symbol=symbol)
        price = float(price_data['price'])
        # $5 margin * 10x = $50 notional
        qty = (usdt_amount * 10) / price
        # Round qty based on symbol precision - get info
        info = binance_client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                precision = int(s['quantityPrecision'])
                qty = round(qty, precision)
                break
        
        setup_symbol_classic(symbol)
        side = "BUY" if direction == "BUY" else "SELL"
        order = binance_client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=qty
        )
        print(f"REAL ORDER PLACED: {symbol} {side} Qty {qty} Price {price} OrderID {order['orderId']}")
        return order
    except Exception as e:
        print(f"REAL ORDER FAILED {symbol}: {e}")
        return None

def close_real_position(symbol, direction):
    if not binance_client: return
    try:
        # Close by opposite market order with reduceOnly
        pos = binance_client.futures_position_information(symbol=symbol)
        for p in pos:
            amt = float(p['positionAmt'])
            if amt != 0:
                side = "SELL" if amt > 0 else "BUY"
                qty = abs(amt)
                binance_client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='MARKET',
                    quantity=qty,
                    reduceOnly=True
                )
                print(f"REAL CLOSE: {symbol} {side} {qty}")
    except Exception as e:
        print(f"CLOSE FAILED {symbol}: {e}")

FAST = ["PEPE","BONK","WIF","FLOKI","BOME","SHIB","DOGE","TRUMP","FARTCOIN","ZEREBRO","WLD","HYPE","SUI","SOL","AVAX","TAO","ARB","OP","ENA","TIA","PENGU","POPCAT","MEW","MOODENG","GOAT","PNUT","ACT","BRETT","MOG","TURBO","1000PEPE","NEIRO","DOG","SPX","W","LADYS","WOJAK","MEME","PONKE","MYRO","WEN","TOSHI","CAT","BABYDOGE","NOT","DOGS","HMSTR","EIGEN","ZK","ZRO"]

CRYPTO = {}
for k in FAST:
    CRYPTO[k]=f"{k}USDT"
CRYPTO["1000PEPE"]="1000PEPEUSDT"
CRYPTO["FARTCOIN"]="FARTCOINUSDT"
CRYPTO["ZEREBRO"]="ZEREBROUSDT"
CRYPTO["PENGU"]="PENGUUSDT"
CRYPTO["POPCAT"]="POPCATUSDT"
CRYPTO["MEW"]="MEWUSDT"
CRYPTO["MOODENG"]="MOODENGUSDT"
CRYPTO["GOAT"]="GOATUSDT"
CRYPTO["PNUT"]="PNUTUSDT"
CRYPTO["ACT"]="ACTUSDT"
CRYPTO["BRETT"]="BRETTUSDT"
CRYPTO["MOG"]="MOGUSDT"
CRYPTO["TURBO"]="TURBOUSDT"
CRYPTO["NEIRO"]="NEIROUSDT"
CRYPTO["DOG"]="DOGUSDT"
CRYPTO["SPX"]="SPXUSDT"
CRYPTO["W"]="WUSDT"
CRYPTO["LADYS"]="LADYSUSDT"
CRYPTO["WOJAK"]="WOJAKUSDT"
CRYPTO["MEME"]="MEMEUSDT"
CRYPTO["PONKE"]="PONKEUSDT"
CRYPTO["MYRO"]="MYROUSDT"
CRYPTO["WEN"]="WENUSDT"
CRYPTO["TOSHI"]="TOSHIUSDT"
CRYPTO["CAT"]="CATUSDT"
CRYPTO["BABYDOGE"]="BABYDOGEUSDT"
CRYPTO["NOT"]="NOTUSDT"
CRYPTO["DOGS"]="DOGSUSDT"
CRYPTO["HMSTR"]="HMSTRUSDT"
CRYPTO["EIGEN"]="EIGENUSDT"
CRYPTO["ZK"]="ZKUSDT"
CRYPTO["ZRO"]="ZROUSDT"

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
def update_daily(res,pnl,coin=""):
    d=get_daily(); d["trades"]+=1
    if res=="WIN": d["wins"]+=1
    else: d["losses"]+=1
    d["pnl"]+=pnl; save_json(DAILY_FILE,d)
    learn=load_json(LEARN_FILE,{})
    if coin not in learn: learn[coin]={"wins":0,"loss":0,"pnl":0.0}
    if res=="WIN": learn[coin]["wins"]+=1
    else: learn[coin]["loss"]+=1
    learn[coin]["pnl"]+=pnl; save_json(LEARN_FILE,learn)
def get_learn(): return load_json(LEARN_FILE,{})
def get_active(): return load_json(ACTIVE_FILE,{})
def set_active(d): save_json(ACTIVE_FILE,d)
def clear_active(): save_json(ACTIVE_FILE,{})
def save_chat(cid): save_json(CHAT_FILE,{"id":cid})
def get_chat(): return load_json(CHAT_FILE,{}).get("id")

@app.get("/")
def home(): 
    status = "REAL CONNECTED" if binance_client else "SIGNAL ONLY"
    return f"V40 REAL CLASSIC {status} LIVE",200
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
    if key in CACHE and time.time()-CACHE[key][0]<50:
        return CACHE[key][1]
    kl=None
    okx_inst_list = []
    if sym == "1000PEPEUSDT":
        okx_inst_list = ["1000PEPE-USDT-SWAP", "1000PEPE-USDT", "PEPE-USDT-SWAP"]
    else:
        okx_inst_list = [sym.replace("USDT","-USDT-SWAP"), sym.replace("USDT","-USDT")]
    try:
        r=requests.get("https://fapi.binance.com/fapi/v1/klines",params={"symbol":sym,"interval":interval,"limit":200},headers=HEADERS,timeout=7).json()
        if isinstance(r,list) and len(r)>=50:
            kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in r]
    except: pass
    if not kl:
        try:
            iv="120" if interval=="2h" else "60" if interval=="1h" else "15"
            r=requests.get("https://api.bybit.com/v5/market/kline",params={"category":"linear","symbol":sym,"interval":iv,"limit":200},headers=HEADERS,timeout=7).json()
            lst=r.get("result",{}).get("list",[])
            if len(lst)>=50:
                kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
        except: pass
    if not kl:
        try:
            iv="2H" if interval=="2h" else "1H" if interval=="1h" else "15m"
            for inst in okx_inst_list:
                try:
                    r=requests.get("https://www.okx.com/api/v5/market/candles",params={"instId":inst,"bar":iv,"limit":"200"},headers=HEADERS,timeout=7).json()
                    lst=r.get("data",[])
                    if len(lst)>=50:
                        kl=[{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in lst[::-1]]
                        if kl: break
                except: continue
        except: pass
    if kl:
        CACHE[key]=(time.time(),kl)
        return kl
    return CACHE.get(key,(0,[]))[1] if key in CACHE else []

def get_price(sym):
    for url,params in [
        ("https://fapi.binance.com/fapi/v1/ticker/price",{"symbol":sym}),
        ("https://api.bybit.com/v5/market/tickers",{"category":"linear","symbol":sym}),
    ]:
        try:
            r=requests.get(url,params=params,headers=HEADERS,timeout=5).json()
            if "price" in r:
                p=float(r["price"])
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
    if pr>e20>e50: return 50,"⬆️ UPTREND"
    if pr>e20: return 20,"↗️ WEAK UP"
    if pr<e20<e50: return -50,"⬇️ DOWNTREND"
    if pr<e20: return -20,"↘️ WEAK DOWN"
    return 0,"➡️ SIDEWAYS"
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
        if abs(price-c2[-1])/c2[-1]>0.08: price=c2[-1]
        rsi_v=rsi_calc(c2); atr_v=atr_calc(k2); adx_v=adx_calc(k2); pd_zone,pd_pct=pd_calc(k2)
        c15=[k["c"] for k in k15] if k15 else c2; c1=[k["c"] for k in k1] if k1 else c2
        s15,t15=trend_calc(c15); s1,t1=trend_calc(c1); s2,t2=trend_calc(c2)
        vol_pct,vol_txt=vol_calc(k2); e200=ema(c2,200)
        bos_bull=k2[-1]["h"]>k2[-2]["h"]; bos_bear=k2[-1]["l"]<k2[-2]["l"]
        align=3 if (s15>0 and s1>0 and s2>0) or (s15<0 and s1<0 and s2<0) else 2 if (s1>0 and s2>0) or (s1<0 and s2<0) else 1
        direction="BUY" if s2>=0 else "SELL"; volatility=atr_v/price*100 if price else 0
        return {"code":code,"price":price,"rsi":rsi_v,"adx":adx_v,"atr":atr_v,"volatility":volatility,"pd_zone":pd_zone,"pd_pct":pd_pct,"t15":t15,"t1":t1,"t2":t2,"vol_pct":vol_pct,"vol_txt":vol_txt,"e200":e200,"bos_bull":bos_bull,"bos_bear":bos_bear,"align":align,"dir":direction,"kl":k2,"closes":c2}
    except: return None

def ai_score_perfect(r, market_adx, learn):
    score=0; reasons=[]; thoughts=[]
    if r["dir"]=="BUY":
        if r["pd_pct"]<=28: score+=20; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% +20"); thoughts.append(f"Discount {r['pd_pct']:.0f}% perfect buy")
        elif r["pd_pct"]<=40: score+=14; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% +14")
        elif r["pd_pct"]<=50: score+=7; reasons.append(f"EQUIL {r['pd_pct']:.0f}% +7")
        elif r["pd_pct"]<=58: score+=2; reasons.append(f"EQUIL HIGH {r['pd_pct']:.0f}% +2")
        else: score-=10; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% -10")
    else:
        if r["pd_pct"]>=72: score+=20; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% +20"); thoughts.append(f"Premium {r['pd_pct']:.0f}% perfect sell")
        elif r["pd_pct"]>=60: score+=14; reasons.append(f"PREMIUM {r['pd_pct']:.0f}% +14")
        elif r["pd_pct"]>=50: score+=7; reasons.append(f"EQUIL {r['pd_pct']:.0f}% +7")
        elif r["pd_pct"]>=42: score+=2; reasons.append(f"EQUIL LOW {r['pd_pct']:.0f}% +2")
        else: score-=10; reasons.append(f"DISCOUNT {r['pd_pct']:.0f}% -10")
    if 44<=r["rsi"]<=56: score+=15; reasons.append(f"RSI {r['rsi']:.0f} PERFECT +15"); thoughts.append(f"RSI {r['rsi']:.0f} perfect")
    elif 40<=r["rsi"]<=60: score+=10; reasons.append(f"RSI {r['rsi']:.0f} +10")
    elif 36<=r["rsi"]<=66: score+=4; reasons.append(f"RSI {r['rsi']:.0f} +4")
    else: score-=5; reasons.append(f"RSI {r['rsi']:.0f} -5")
    if 18<=r["adx"]<=50: score+=15; reasons.append(f"ADX {r['adx']:.0f} STRONG +15"); thoughts.append(f"ADX {r['adx']:.0f} strong fast")
    elif r["adx"]>=14: score+=9; reasons.append(f"ADX {r['adx']:.0f} +9")
    elif r["adx"]>=11: score+=3; reasons.append(f"ADX {r['adx']:.0f} +3")
    else: score-=5; reasons.append(f"ADX {r['adx']:.0f} WEAK -5")
    vs=0
    if r["volatility"]>=2.2: vs+=10; reasons.append(f"Volat {r['volatility']:.2f}% HIGH +10"); thoughts.append(f"High volat {r['volatility']:.2f}% fast TP")
    elif r["volatility"]>=1.3: vs+=6; reasons.append(f"Volat {r['volatility']:.2f}% +6")
    elif r["volatility"]>=1.0: vs+=2; reasons.append(f"Volat {r['volatility']:.2f}% +2")
    else: vs-=5; reasons.append(f"Volat {r['volatility']:.2f}% LOW -5")
    if r["vol_pct"]>=15: vs+=10; reasons.append(f"Vol {r['vol_pct']:.0f}% 🔥🔥 +10")
    elif r["vol_pct"]>=5: vs+=6; reasons.append(f"Vol {r['vol_pct']:.0f}% 🔥 +6")
    elif r["vol_pct"]>=-10: vs+=2; reasons.append(f"Vol {r['vol_pct']:.0f}% +2")
    elif r["vol_pct"]>=-30: vs-=2; reasons.append(f"Vol {r['vol_pct']:.0f}% LOW -2")
    else: vs-=10; reasons.append(f"Vol {r['vol_pct']:.0f}% DEAD -10")
    score+=vs
    a_s=0
    if r["align"]==3: a_s+=10; reasons.append(f"Align 3/3 +10"); thoughts.append(f"All TF agree")
    elif r["align"]==2: a_s+=4; reasons.append(f"Align 2/3 +4")
    else: a_s-=3; reasons.append(f"Align 1/3 -3")
    if r["bos_bull"] or r["bos_bear"]: a_s+=5; reasons.append(f"BOS +5")
    score+=a_s
    if (r["dir"]=="BUY" and r["price"]>=r["e200"]) or (r["dir"]=="SELL" and r["price"]<=r["e200"]): score+=6; reasons.append(f"EMA200 +6")
    else: score-=4; reasons.append(f"EMA200 -4")
    if r["code"] in learn:
        tot=learn[r["code"]]["wins"]+learn[r["code"]]["loss"]
        if tot>0:
            wr=learn[r["code"]]["wins"]/tot
            if wr>=0.6: score+=5; reasons.append(f"LEARN WR {wr*100:.0f}% +5")
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
        closes=r["closes"][-50:]; e20=ema_series(closes,20)[-50:]
        entry_line=[r["entry"]]*50; sl_line=[r["sl"]]*50; tp1_line=[r["tp1"]]*50
        labels=[str(i) for i in range(50)]
        cfg={"type":"line","data":{"labels":labels,"datasets":[{"label":r["code"],"data":closes,"borderColor":"black","fill":False,"pointRadius":0,"borderWidth":2},{"label":"EMA20","data":e20,"borderColor":"#2196F3","fill":False,"pointRadius":0,"borderWidth":1},{"label":"Entry","data":entry_line,"borderColor":"blue","borderDash":[5,5],"fill":False,"pointRadius":0,"borderWidth":1},{"label":"SL","data":sl_line,"borderColor":"red","borderDash":[5,5],"fill":False,"pointRadius":0,"borderWidth":1},{"label":"TP1","data":tp1_line,"borderColor":"green","borderDash":[5,5],"fill":False,"pointRadius":0,"borderWidth":1}]},"options":{"title":{"display":True,"text":f'{r["code"]} FUTURES {r["dir"]} SCORE {r["conf"]}/100'}}}
        url=f"https://quickchart.io/chart?width=700&height=400&c={urllib.parse.quote(json.dumps(cfg))}"
        resp=requests.get(url,timeout=12)
        if resp.status_code==200 and len(resp.content)>4000: return resp.content
    except: pass
    return None

def kb(active=None):
    daily=get_daily(); btns=[]
    if active and active.get("status")=="OPEN":
        btns.append([InlineKeyboardButton(f'{"🟢 BUY" if active["dir"]=="BUY" else "🔴 SELL"} {active["coin"]} {active["conf"]}/100 🧠 LIVE',callback_data="MON")])
        btns.append([InlineKeyboardButton(f'👀 {active["coin"]} AI',callback_data="CHK"),InlineKeyboardButton(f'❌ Close',callback_data="CLS")])
    else:
        btns.append([InlineKeyboardButton(f'🧠 SCAN 50/50 REAL FUTURES - Trade {daily["trades"]+1}/3 🚀',callback_data="SCAN")])
    btns.append([InlineKeyboardButton(f'📊 Daily {daily["wins"]}W/{daily["losses"]}L ${daily["pnl"]:.2f}',callback_data="DAILY")])
    row=[]
    for c in FAST[:20]:
        row.append(InlineKeyboardButton(f'{c}',callback_data=f'C_{c}'))
        if len(row)==5: btns.append(row); row=[]
    if row: btns.append(row)
    btns.append([InlineKeyboardButton(f'➕ FUTURES 50: {", ".join(FAST[20:])}',callback_data="MORE")])
    return InlineKeyboardMarkup(btns)

async def setup_menu(app):
    try: await app.bot.set_my_commands([BotCommand("start","🧠 V40 REAL"),BotCommand("scan","SCAN REAL"),BotCommand("daily","Daily")])
    except: pass

def bg_scan(chat_id):
    try:
        print(f"🧠 V40 REAL CLASSIC SCAN")
        raws=[]; fails=[]
        for code in FAST:
            r=analyze_single(code)
            if r:
                raws.append(r)
            else:
                fails.append(code)
            time.sleep(0.03)
        print(f"FETCHED {len(raws)}/{len(FAST)}")
        if len(raws)==0:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Fetch fail 0/50"},timeout=10)
            return
        avg_adx=sum(x["adx"] for x in raws)/len(raws); avg_volat=sum(x["volatility"] for x in raws)/len(raws)
        mode="TREND" if avg_adx>=18 else "NORMAL" if avg_adx>=14 else "CHOPPY"
        learn=get_learn(); cands=[]
        for r in raws:
            if r["vol_pct"] < -40: continue
            if r["adx"] < 11: continue
            if r["rsi"]>78 or r["rsi"]<22: continue
            if r["dir"]=="BUY" and r["pd_pct"]>72: continue
            if r["dir"]=="SELL" and r["pd_pct"]<28: continue
            score,reasons,thoughts=ai_score_perfect(r, avg_adx, learn)
            if score < 65: continue
            trade=build_trade(r); trade["conf"]=int(score); trade["reason"]=" | ".join(reasons[:4]); trade["ai_thought"]=" | ".join(thoughts) if thoughts else "Good setup"; trade["mode"]=mode+" REAL CLASSIC"; cands.append(trade)
        if not cands:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"🛡️ No quality trade now - Market slow"},timeout=10)
            return
        cands.sort(key=lambda x: x["conf"]+x["volatility"]*4, reverse=True)
        best=cands[0]
        if get_active().get("status")=="OPEN":
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Active {get_active().get('coin')} OPEN"},timeout=10)
            return
        
        # --- PLACE REAL BINANCE ORDER ---
        real_symbol = CRYPTO[best["code"]]
        print(f"Attempting REAL order {real_symbol} {best['dir']} ${TRADE_AMOUNT_USDT}")
        order_res = place_real_order(real_symbol, best["dir"], TRADE_AMOUNT_USDT)
        if binance_client and not order_res:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Real order failed for {real_symbol} - Check Binance balance. Need at least $10 in Futures wallet."},timeout=10)
            return

        r=best; stake=1.0 if r["conf"]>=75 else 0.6
        set_active({"status":"OPEN","coin":r["code"],"symbol":real_symbol,"dir":r["dir"],"entry":r["entry"],"sl":r["sl"],"tp1":r["tp1"],"tp2":r["tp2"],"tp3":r["tp3"],"conf":r["conf"],"stake":TRADE_AMOUNT_USDT,"lev":r["lev"],"time":str(__import__('datetime').datetime.now()),"mode":r["mode"],"ai_thought":r["ai_thought"],"reason":r["reason"]})
        loss=stake*r["sl_pct"]*r["lev"]/100; p1=stake*r["tp1_pct"]*r["lev"]/100; p2=stake*r["tp2_pct"]*r["lev"]/100; p3=stake*r["tp3_pct"]*r["lev"]/100
        txt=(f"🧠 *REAL CLASSIC SCORE {r['conf']}/100 {r['code']} FUTURES Trade {get_daily()['trades']+1}/3* {'🟢 BUY 🚀 REAL' if r['dir']=='BUY' else '🔴 SELL 💥 REAL'} ${stake} {r['lev']}x\n💰 @ {fmt(r['entry'])} | {r['pd_zone']} {r['pd_pct']:.0f}% ADX {r['adx']:.0f} RSI {r['rsi']:.0f} Volat {r['volatility']:.2f}% | {r['vol_txt']}\n⚡ TP1 {fmt(r['tp1'])} (+{r['tp1_pct']*r['lev']:.0f}% ${p1:.2f})\n🎯 TP2 {fmt(r['tp2'])} (+{r['tp2_pct']*r['lev']:.0f}% ${p2:.2f})\n🚀 TP3 {fmt(r['tp3'])} (+{r['tp3_pct']*r['lev']:.0f}% ${p3:.2f})\n🛑 SL {fmt(r['sl'])} (-{r['sl_pct']*r['lev']:.0f}% -${loss:.2f})\n{r['mtf']}\n🧠 *AI:* {r['ai_thought']}\n✅ *SCORE:* {r['reason']}\n{'✅ REAL ORDER PLACED ON BINANCE!' if order_res else '⚠️ Signal only - Binance not connected'}")
        chart_bytes=get_light_chart(r)
        try:
            if chart_bytes: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data={"chat_id":chat_id,"caption":txt,"parse_mode":"Markdown"},files={"photo":("chart.png", chart_bytes, "image/png")},timeout=25)
            else: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
        except: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":txt,"parse_mode":"Markdown"},timeout=10)
    except Exception as e:
        print(f"SCAN ERR {e}"); import traceback; traceback.print_exc()
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat_id,"text":f"⚠️ Scan error {e}"},timeout=10)
        except: pass

async def start(u,c):
    save_chat(u.message.chat.id)
    bal_text = ""
    if binance_client:
        try:
            bals = binance_client.futures_account_balance()
            usdt_bal = [b for b in bals if b['asset']=='USDT']
            if usdt_bal:
                bal_text = f"\n💰 Futures Balance: ${float(usdt_bal[0]['balance']):.2f} USDT\nAPI: Connected ✅\nMode: REAL CLASSIC ${TRADE_AMOUNT_USDT} per trade"
        except Exception as e:
            bal_text = f"\n⚠️ API Error: {e}"
    else:
        bal_text = "\n⚠️ Binance not connected - Signal only"
    await u.message.reply_text(f"🧠 *V40 REAL CLASSIC LIVE*{bal_text}\n✅ 50 coins futures classic 10x isolated\nUse /scan to trade real money",parse_mode="Markdown",reply_markup=kb())

async def scan_cmd(u,c):
    save_chat(u.message.chat.id); threading.Thread(target=bg_scan,args=(u.message.chat.id,),daemon=True).start()
    await u.message.reply_text("🧠 SCANNING 50 REAL FUTURES - Placing real order if found...")

async def daily_cmd(u,c):
    save_chat(u.message.chat.id); d=get_daily()
    await u.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L Trades {d['trades']}/3 ${d['pnl']:.2f}",parse_mode="Markdown",reply_markup=kb())

async def btn_handler(u,c):
    q=u.callback_query; await q.answer(); data=q.data
    if data=="MORE": await q.message.reply_text(f"50 FUTURES: {', '.join(FAST)}",reply_markup=kb(get_active())); return
    if data=="DAILY": d=get_daily(); await q.message.reply_text(f"📊 Daily {d['date']} {d['wins']}W/{d['losses']}L ${d['pnl']:.2f}",reply_markup=kb(get_active())); return
    if data in ["MON","CHK"]:
        act=get_active()
        if not act.get("status")=="OPEN": await q.message.reply_text("No active",reply_markup=kb()); return
        price=get_price(CRYPTO[act["coin"]]) or act["entry"]
        pnl=(price-act["entry"])/act["entry"]*100*act["lev"] if act["dir"]=="BUY" else (act["entry"]-price)/act["entry"]*100*act["lev"]
        await q.message.reply_text(f"🧠 {act['coin']} REAL {act['dir']} Now {fmt(price)} P&L {pnl:.2f}%\n🧠 AI: {act.get('ai_thought','')}\n✅ {act.get('reason','')}",reply_markup=kb(act)); return
    if data=="CLS": 
        act=get_active()
        if act.get("symbol"): close_real_position(act["symbol"], act["dir"])
        clear_active(); await q.message.reply_text("✅ Closed - Real position closed too",reply_markup=kb()); return
    if data=="SCAN": threading.Thread(target=bg_scan,args=(q.message.chat.id,),daemon=True).start(); await q.message.reply_text("🧠 SCANNING REAL..."); return
    if data.startswith("C_"):
        code=data[2:]; raw=analyze_single(code)
        if not raw: await q.message.reply_text(f"⚠️ Fetch fail {code}",reply_markup=kb()); return
        trade=build_trade(raw); trade["conf"]=75; trade["reason"]=f"Manual {code} REAL"; trade["ai_thought"]=f"Manual {code}"; trade["mode"]="MANUAL REAL"
        # Place real order for manual too
        real_symbol = CRYPTO[code]
        order_res = place_real_order(real_symbol, trade["dir"], TRADE_AMOUNT_USDT)
        set_active({"status":"OPEN","coin":trade["code"],"symbol":real_symbol,"dir":trade["dir"],"entry":trade["entry"],"sl":trade["sl"],"tp1":trade["tp1"],"tp2":trade["tp2"],"tp3":trade["tp3"],"conf":trade["conf"],"stake":TRADE_AMOUNT_USDT,"lev":trade["lev"],"time":str(__import__('datetime').datetime.now()),"mode":"MANUAL","ai_thought":trade["ai_thought"],"reason":trade["reason"]})
        txt=f"🧠 *V40 MANUAL REAL {trade['conf']}/100 {trade['code']} {trade['dir']}* @ {fmt(trade['entry'])} {'✅ REAL ORDER' if order_res else '⚠️ Signal'}"
        chart_bytes=get_light_chart(trade)
        if chart_bytes: await q.message.reply_photo(photo=chart_bytes,caption=txt,parse_mode="Markdown",reply_markup=kb(get_active()))
        else: await q.message.reply_text(txt,parse_mode="Markdown",reply_markup=kb(get_active()))

def monitor():
    while True:
        try:
            time.sleep(30); act=get_active()
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
                # Close real binance position
                if act.get("symbol"):
                    close_real_position(act["symbol"], act["dir"])
                stake=act["stake"]; lev=act["lev"]; entry=act["entry"]; coin=act["coin"]
                if "TP" in hit:
                    tp=act["tp1"] if "TP1" in hit else act["tp2"] if "TP2" in hit else act["tp3"]
                    pct=abs(tp-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"🧠 {hit} REAL! {coin} +{pct:.0f}% +${pnl:.2f} Closed on Binance!"; update_daily("WIN",pnl,coin); clear_active()
                else:
                    pct=abs(act["sl"]-entry)/entry*100*lev; pnl=stake*pct/100
                    msg=f"💀 SL REAL {coin} -{pct:.0f}% -${pnl:.2f} Closed"; update_daily("LOSS",-pnl,coin); clear_active()
                try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":chat,"text":msg},timeout=8)
                except: pass
        except: time.sleep(10)

def run_flask(): app.run(host="0.0.0.0",port=PORT)
def run_bot():
    if not BOT_TOKEN: print("BOT_TOKEN missing"); return
    a=ApplicationBuilder().token(BOT_TOKEN).post_init(setup_menu).build()
    a.add_handler(CommandHandler("start",start)); a.add_handler(CommandHandler("scan",scan_cmd)); a.add_handler(CommandHandler("daily",daily_cmd))
    a.add_handler(CallbackQueryHandler(btn_handler))
    print("V40 REAL CLASSIC starting"); a.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    threading.Thread(target=run_flask,daemon=True).start()
    threading.Thread(target=monitor,daemon=True).start()
    run_bot()
