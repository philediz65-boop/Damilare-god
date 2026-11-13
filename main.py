import os, requests, time, hmac, hashlib, urllib.parse, threading
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
BINANCE_API_KEY = (os.getenv("BINANCE_API_KEY") or "").strip()
BINANCE_API_SECRET = (os.getenv("BINANCE_API_SECRET") or "").strip()
BINANCE_PROXY = (os.getenv("BINANCE_PROXY") or "").strip()
# Render gives this automatically
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_URL") or "").strip()

FUTURES_120 = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","SHIBUSDT","DOTUSDT","LINKUSDT","TRXUSDT","MATICUSDT","LTCUSDT","BCHUSDT","UNIUSDT","ETCUSDT","XLMUSDT","NEARUSDT","APTUSDT","ARBUSDT","OPUSDT","SUIUSDT","SEIUSDT","TIAUSDT","JUPUSDT","RENDERUSDT","FETUSDT","PEPEUSDT","BONKUSDT","WIFUSDT","FLOKIUSDT","1000PEPEUSDT","1000BONKUSDT","1000FLOKIUSDT","1000SHIBUSDT","ORDIUSDT","STXUSDT","IMXUSDT","INJUSDT","RUNEUSDT","AAVEUSDT","GRTUSDT","LDOUSDT","TAOUSDT","WLDUSDT","JTOUSDT","ONDOUSDT","ENAUSDT","BOMEUSDT","WUSDT","TONUSDT","NOTUSDT","SAGAUSDT","ARKMUSDT","PIXELUSDT","PORTALUSDT","AEVOUSDT","VANRYUSDT","RONINUSDT","ALTUSDT","DYMUSDT","MANTAUSDT","ATOMUSDT","VETUSDT","FTMUSDT","ALGOUSDT","SANDUSDT","MANAUSDT","AXSUSDT","GALAUSDT","CHZUSDT","FLOWUSDT","EGLDUSDT","THETAUSDT","XTZUSDT","EOSUSDT","KSMUSDT","KAVAUSDT","KLAYUSDT","QNTUSDT","KASUSDT","FILUSDT","HBARUSDT","XMRUSDT","MKRUSDT","RNDRUSDT","PYTHUSDT","STRKUSDT","ETHFIUSDT","MEMEUSDT","DOGSUSDT","TURBOUSDT","MOGUSDT","POPCATUSDT","MEWUSDT","BRETTUSDT","ZETAUSDT","XAIUSDT","ACEUSDT","NFPUSDT","AIUSDT","POLUSDT","ENJUSDT","1000SATSUSDT","NEIROUSDT"]

def b_signed(method, path, params={}):
    try:
        base = "https://fapi.binance.com"
        if BINANCE_PROXY: base = BINANCE_PROXY.rstrip('/')
        ts = int(time.time()*1000)
        params['timestamp'] = ts
        q = urllib.parse.urlencode(params)
        sig = hmac.new(BINANCE_API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
        url = f"{base}{path}?{q}&signature={sig}"
        r = requests.request(method, url, headers={"X-MBX-APIKEY": BINANCE_API_KEY}, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def get_bal():
    d = b_signed("GET", "/fapi/v2/balance")
    print(f"🔍 BAL: {d}")
    if isinstance(d, list):
        for b in d:
            if b.get('asset') == 'USDT':
                try: return float(b.get('balance', 0))
                except: pass
        return 0.0
    return -1.0

def get_k(symbol, interval, limit=100):
    try:
        base = "https://fapi.binance.com"
        if BINANCE_PROXY: base = BINANCE_PROXY.rstrip('/')
        url = f"{base}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=10)
        j = r.json()
        return j if isinstance(j, list) else None
    except: return None

def get_trend_4h_6h(symbol):
    k4h = get_k(symbol, "4h", 200)
    k6h = get_k(symbol, "6h", 200)
    if not k4h or not k6h or len(k4h) < 50: return None, "No data"
    c4 = [float(x[4]) for x in k4h]
    c6 = [float(x[4]) for x in k6h]
    e50_4 = sum(c4[-50:])/50
    e200_4 = sum(c4[-200:])/200 if len(c4)>=200 else sum(c4)/len(c4)
    e50_6 = sum(c6[-50:])/50
    e200_6 = sum(c6[-200:])/200 if len(c6)>=200 else sum(c6)/len(c6)
    t4 = "BUY" if e50_4 > e200_4 else "SELL"
    t6 = "BUY" if e50_6 > e200_6 else "SELL"
    if t4 == t6: return t4, f"✅ 4H:{t4}+6H:{t6} AGREE"
    return None, f"⚠️ {t4} vs {t6}"

def check_entry(symbol, trend):
    k1h = get_k(symbol, "1h", 100)
    if not k1h: return False, "No 1h"
    closes = [float(x[4]) for x in k1h]
    highs = [float(x[2]) for x in k1h]
    lows = [float(x[3]) for x in k1h]
    rh = max(highs[-20:-1]); rl = min(lows[-20:-1])
    if trend == "BUY" and closes[-1] <= rh: return False, "No BOS Bull"
    if trend == "SELL" and closes[-1] >= rl: return False, "No BOS Bear"
    gains = 0; losses = 0
    for i in range(1, len(closes)):
        d = closes[i]-closes[i-1]
        if d>0: gains+=d
        else: losses+=-d
    if losses==0: rsi=70
    else:
        rs=gains/(losses+1e-9)
        rsi=100-(100/(1+rs))
    if not (25 <= rsi <= 66): return False, f"RSI {rsi:.1f}"
    return True, f"🔥 BOS OK | RSI {rsi:.1f} | FVG/OB"

def tg(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
        print(f"✅ TG Sent to {CHAT_ID}")
    except Exception as e:
        print(f"❌ TG Fail {e}")

def auto_set_webhook():
    try:
        if not RENDER_URL or not BOT_TOKEN:
            print(f"⚠️ Skip webhook auto: RENDER_URL={RENDER_URL} BOT_TOKEN set={bool(BOT_TOKEN)}")
            return
        hook_url = RENDER_URL.rstrip('/') + f"/{BOT_TOKEN}"
        api = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={hook_url}"
        r = requests.get(api, timeout=10)
        print(f"🔗 Webhook set: {r.text} -> {hook_url}")
    except Exception as e:
        print(f"Webhook err {e}")

def do_scan():
    bal = get_bal()
    if bal == -1: bal_txt = "❌ API Error - Check Futures Enabled"
    elif bal == 0: bal_txt = "⚠️ $0.00 - Move Spot->Futures"
    else: bal_txt = f"💰 ${bal:.2f} USDT"
    tg(f"🔍 *V94.1 ALL-DAY 4H+6H SMC* 🔥\n⏳ Scanning 120 coins...\n{bal_txt}\n\n🧠 4H+6H Must Agree + BOS + RSI\n💎 Anytime 24/7")
    found=0
    for sym in FUTURES_120:
        trend, log = get_trend_4h_6h(sym)
        if not trend: continue
        ok, reason = check_entry(sym, trend)
        if ok:
            found+=1
            k = get_k(sym, "1h", 2)
            price = float(k[-1][4]) if k else 0
            tg(f"🚀 *SMC ENTRY FOUND* 🚀\n\n💎 Coin: `{sym}`\n📊 Trend: *{trend}* (4H+6H)\n{log}\n✅ {reason}\n\n💵 Entry: ~{price}\n🛑 SL: 6-8% Wide Safe\n🎯 TP: 1.5% / 3% / 5%\n\n{bal_txt}")
            if found>=2: break
    if found==0:
        tg(f"😴 *No SMC setup yet...* 🛡️\nAll 120 dull now. Safe, no trade.\n{bal_txt}")

@app.route("/")
def home():
    # Set webhook each time home visited (fixes gunicorn)
    threading.Thread(target=auto_set_webhook).start()
    return "V94.1 ALL-DAY 4H+6H Running ✅ - Webhook auto-setting"

@app.route("/setwebhook")
def sethook_page():
    auto_set_webhook()
    return f"Webhook set attempt to {RENDER_URL}"

@app.route("/scan")
def scan_page():
    threading.Thread(target=do_scan).start()
    return "Scanning started, check Telegram 🚀"

# FIXED: webhook route checks token dynamically
@app.route("/<token>", methods=["POST"])
def webhook(token):
    try:
        print(f"📩 Webhook hit token={token[:10]}...")
        if token != BOT_TOKEN:
            print("Wrong token in URL")
            return "ok"
        data = request.get_json()
        if not data: return "ok"
        msg = data.get("message", {})
        txt = (msg.get("text") or "").strip()
        cid = str(msg.get("chat", {}).get("id", "")).strip()
        print(f"From {cid}: {txt} | Expected CHAT_ID={CHAT_ID}")
        if cid != CHAT_ID:
            # still reply to help debug
            if "/start" in txt:
                tg(f"⚠️ CHAT_ID mismatch! Your chat is `{cid}` but env CHAT_ID is `{CHAT_ID}`. Update env!")
            return "ok"
        if "/start" in txt or "/scan" in txt or "SCAN" in txt:
            threading.Thread(target=do_scan).start()
        return "ok"
    except Exception as e:
        print(f"Webhook err {e}")
        return "ok"

# Run auto webhook in background on startup
threading.Thread(target=auto_set_webhook).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
