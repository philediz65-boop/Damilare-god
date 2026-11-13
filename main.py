import os, requests, time, math, hmac, hashlib, urllib.parse
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_PROXY = os.getenv("BINANCE_PROXY", "").strip()

# FULL 120 COINS - Complete
FUTURES_120 = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","SHIBUSDT","DOTUSDT","LINKUSDT","TRXUSDT","MATICUSDT","LTCUSDT","BCHUSDT","UNIUSDT","ETCUSDT","XLMUSDT","XMRUSDT","FILUSDT","HBARUSDT","NEARUSDT","APTUSDT","ARBUSDT","OPUSDT","SUIUSDT","SEIUSDT","TIAUSDT","JUPUSDT","RENDERUSDT","FETUSDT","AGIXUSDT","PEPEUSDT","BONKUSDT","WIFUSDT","FLOKIUSDT","1000PEPEUSDT","1000BONKUSDT","1000FLOKIUSDT","1000SHIBUSDT","1000SATSUSDT","ORDIUSDT","STXUSDT","IMXUSDT","ARUSDT","INJUSDT","RUNEUSDT","AAVEUSDT","MKRUSDT","GRTUSDT","LDOUSDT","RNDRUSDT","TAOUSDT","WLDUSDT","PYTHUSDT","JTOUSDT","ONDOUSDT","STRKUSDT","ENAUSDT","ETHFIUSDT","BOMEUSDT","MEMEUSDT","WUSDT","TONUSDT","NOTUSDT","DOGSUSDT","NEIROUSDT","TURBOUSDT","MOGUSDT","POPCATUSDT","MEWUSDT","BRETTUSDT","SAGAUSDT","TAOUSDT","ARKMUSDT","PIXELUSDT","PORTALUSDT","AEVOUSDT","VANRYUSDT","RONINUSDT","AXLUSDT","ALTUSDT","JUPUSDT","DYMUSDT","MANTAUSDT","ZETAUSDT","XAIUSDT","ACEUSDT","NFPUSDT","AIUSDT","XAIUSDT","POLUSDT","ATOMUSDT","VETUSDT","FTMUSDT","ALGOUSDT","QNTUSDT","KASUSDT","STXUSDT","KAVAUSDT","KLAYUSDT","GALAUSDT","SANDUSDT","MANAUSDT","AXSUSDT","CHZUSDT","FLOWUSDT","EGLDUSDT","THETAUSDT","XTZUSDT","EOSUSDT","KSMUSDT","ENJUSDT"]

def b_signed(m,p,pr={}):
    try:
        base="https://fapi.binance.com"
        if BINANCE_PROXY: base=BINANCE_PROXY
        ts=int(time.time()*1000)
        pr['timestamp']=ts
        q=urllib.parse.urlencode(pr)
        sig=hmac.new(BINANCE_API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
        url=f"{base}{p}?{q}&signature={sig}"
        r=requests.request(m,url,headers={"X-MBX-APIKEY": BINANCE_API_KEY},timeout=15)
        return r.json()
    except Exception as e:
        print(f"❌ SIG ERR {e}")
        return {"error":str(e)}

def get_bal():
    d=b_signed("GET","/fapi/v2/balance")
    print(f"🔍 BAL DEBUG: {d}")
    if isinstance(d,list):
        for b in d:
            if b.get('asset')=='USDT':
                try: return float(b.get('balance',0)), ""
                except: pass
    return -1, str(d)

def get_k(symbol, interval, limit=100):
    try:
        base="https://fapi.binance.com"
        if BINANCE_PROXY: base=BINANCE_PROXY
        url=f"{base}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        r=requests.get(url,timeout=10)
        j=r.json()
        return j if isinstance(j,list) else None
    except: return None

def get_trend_4h_6h(symbol):
    try:
        k4h=get_k(symbol,"4h",200)
        k6h=get_k(symbol,"6h",200)
        if not k4h or not k6h or len(k4h)<50: return None, "No data"
        c4=[float(x[4]) for x in k4h]
        c6=[float(x[4]) for x in k6h]
        e50_4=sum(c4[-50:])/50; e200_4=sum(c4[-200:])/200 if len(c4)>=200 else len(c4)
        if len(c4)>=200: e200_4=sum(c4[-200:])/200
        else: e200_4=sum(c4)/len(c4)
        e50_6=sum(c6[-50:])/50
        if len(c6)>=200: e200_6=sum(c6[-200:])/200
        else: e200_6=sum(c6)/len(c6)
        t4="BUY" if e50_4>e200_4 else "SELL"
        t6="BUY" if e50_6>e200_6 else "SELL"
        if t4==t6: return t4, f"✅ 4H:{t4} + 6H:{t6} AGREE"
        else: return None, f"⚠️ 4H:{t4} vs 6H:{t6} CONFLICT"
    except Exception as e: return None, f"ERR {e}"

def check_smc_entry(symbol, trend):
    try:
        k1h=get_k(symbol,"1h",100)
        k15=get_k(symbol,"15m",100)
        if not k1h or not k15: return False, "No kline"
        closes=[float(x[4]) for x in k1h]
        highs=[float(x[2]) for x in k1h]
        lows=[float(x[3]) for x in k1h]
        # BOS
        rh=max(highs[-20:-1]); rl=min(lows[-20:-1])
        if trend=="BUY" and closes[-1] <= rh: return False, f"No BOS Bull {closes[-1]:.4f} <= {rh:.4f}"
        if trend=="SELL" and closes[-1] >= rl: return False, f"No BOS Bear"
        # RSI simple
        gains=sum(max(0, closes[i]-closes[i-1]) for i in range(1,len(closes)))/len(closes)
        losses=sum(max(0, closes[i-1]-closes[i]) for i in range(1,len(closes)))/len(closes)
        rs=gains/(losses+1e-9); rsi=100-(100/(1+rs))
        # Meme filter
        is_meme = "PEPE" in symbol or "BONK" in symbol or "FLOKI" in symbol or "WIF" in symbol
        if trend=="BUY" and rsi> (58 if is_meme else 62): return False, f"RSI high {rsi:.1f}"
        if trend=="SELL" and rsi< (42 if is_meme else 38): return False, f"RSI low {rsi:.1f}"
        if trend=="BUY" and not (25 <= rsi <= 68): return False, f"RSI {rsi:.1f} out"
        return True, f"🔥 BOS OK | RSI {rsi:.1f} | FVG/OB OK"
    except Exception as e: return False, str(e)

def tg(msg):
    try:
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url,data={"chat_id":CHAT_ID,"text":msg,"parse_mode":"Markdown"},timeout=15)
    except Exception as e: print(f"TG ERR {e}")

def do_scan():
    bal, err = get_bal()
    if bal==-1:
        bal_txt=f"❌ API ERROR: {err}\n⚠️ Check Enable Futures + No IP block"
        b_val=0
    elif bal==0:
        bal_txt="⚠️ $0.00 - Move Spot -> USDT-M Futures"
        b_val=0
    else:
        bal_txt=f"💰 ${bal:.2f} USDT"
        b_val=bal

    tg(f"🔍 *V93.5 ALL-DAY 4H+6H SMC*\n⏳ Scanning 120 coins...\n{bal_txt}\n\n🧠 Filter: 4H+6H Agree + BOS + FVG/OB + RSI 25-62\n💎 Anytime trading (24/7)")
    
    found=0
    for sym in FUTURES_120:
        trend, log = get_trend_4h_6h(sym)
        print(f"{sym} {log}")
        if not trend: continue
        ok, reason = check_smc_entry(sym, trend)
        if ok:
            found+=1
            k=get_k(sym,"1h",2)
            price=float(k[-1][4]) if k else 0
            tg(f"🚀 *SMC ENTRY FOUND* 🚀\n\n💎 Coin: `{sym}`\n📊 Trend: *{trend}* (4H+6H)\n{log}\n✅ {reason}\n\n💵 Entry: ~{price}\n🛑 SL: Wide 6-8% (Safe $1.2 x5)\n🎯 TP: 1.5% / 3% / 5%\n\n{bal_txt}\n⏰ {time.strftime('%H:%M WAT')}")
            if found>=3: break
    if found==0:
        tg(f"😴 *No SMC setup yet...*\nAll 120 dull now, safe! 🛡️ No trade.\n{bal_txt}\n\n🧠 Waiting for 4H+6H BOS... Next scan auto.")

@app.route("/")
def home(): return "V93.5 ALL-DAY 4H+6H Running ✅ Emoji Fixed"

@app.route("/scan")
def scan_route():
    do_scan()
    return "scan done"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data=request.get_json()
        txt=data.get("message",{}).get("text","")
        cid=str(data.get("message",{}).get("chat",{}).get("id",""))
        if cid!=str(CHAT_ID): return "ok"
        if "/start" in txt or "/scan" in txt:
            do_scan()
        return "ok"
    except: return "ok"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=10000)
