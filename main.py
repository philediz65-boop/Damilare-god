import os, requests, time, hmac, hashlib, urllib.parse, threading
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
BINANCE_API_KEY = (os.getenv("BINANCE_API_KEY") or "").strip()
BINANCE_API_SECRET = (os.getenv("BINANCE_API_SECRET") or "").strip()
BINANCE_PROXY = (os.getenv("BINANCE_PROXY") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_URL") or "").strip()

SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","NEARUSDT","ARBUSDT","OPUSDT","SUIUSDT","APTUSDT","TAOUSDT","FETUSDT","RENDERUSDT","WIFUSDT","PEPEUSDT","BONKUSDT","SHIBUSDT","UNIUSDT","AAVEUSDT","INJUSDT","SEIUSDT","JUPUSDT","ONDOUSDT","ENAUSDT","TONUSDT","ATOMUSDT","FILUSDT","ETCUSDT","TRXUSDT","HBARUSDT","MATICUSDT","POLUSDT"]

def tg(msg):
    try:
        url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(e)

def get_k(sym, interval, limit=100):
    try:
        base = "https://fapi.binance.com"
        if BINANCE_PROXY:
            base = BINANCE_PROXY.rstrip('/')
        url = base + "/fapi/v1/klines?symbol=" + sym + "&interval=" + interval + "&limit=" + str(limit)
        r = requests.get(url, timeout=8)
        j = r.json()
        if isinstance(j, list):
            return j
        return None
    except:
        return None

def b_balance():
    try:
        base = "https://fapi.binance.com"
        if BINANCE_PROXY:
            base = BINANCE_PROXY.rstrip('/')
        ts = int(time.time()*1000)
        q = urllib.parse.urlencode({"timestamp": ts})
        sig = hmac.new(BINANCE_API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
        url = base + "/fapi/v2/balance?" + q + "&signature=" + sig
        r = requests.get(url, headers={"X-MBX-APIKEY": BINANCE_API_KEY}, timeout=10)
        d = r.json()
        if isinstance(d, list):
            for b in d:
                if b.get('asset') == 'USDT':
                    return float(b.get('balance', 0))
        return 0.0
    except:
        return 0.0

def trend_4h_6h(sym):
    k4 = get_k(sym, "4h", 200)
    k6 = get_k(sym, "6h", 200)
    if not k4 or not k6 or len(k4) < 50:
        return None
    c4 = [float(x[4]) for x in k4]
    c6 = [float(x[4]) for x in k6]
    e50_4 = sum(c4[-50:]) / 50
    e200_4 = sum(c4[-200:]) / 200 if len(c4) >= 200 else sum(c4) / len(c4)
    e50_6 = sum(c6[-50:]) / 50
    e200_6 = sum(c6[-200:]) / 200 if len(c6) >= 200 else sum(c6) / len(c6)
    t4 = "BUY" if e50_4 > e200_4 else "SELL"
    t6 = "BUY" if e50_6 > e200_6 else "SELL"
    if t4 == t6:
        return t4
    return None

def secret_entry(sym, trend):
    k1 = get_k(sym, "1h", 100)
    if not k1 or len(k1) < 30:
        return False, "No data"
    highs = [float(x[2]) for x in k1]
    lows = [float(x[3]) for x in k1]
    closes = [float(x[4]) for x in k1]
    prev_high = max(highs[-21:-1])
    prev_low = min(lows[-21:-1])
    curr_close = closes[-1]
    sweep_bull = lows[-2] < prev_low and curr_close > prev_low
    sweep_bear = highs[-2] > prev_high and curr_close < prev_high
    bos_bull = curr_close > prev_high
    bos_bear = curr_close < prev_low
    fvg = False
    if lows[-1] > highs[-3]:
        fvg = True
    if highs[-1] < lows[-3]:
        fvg = True
    if trend == "BUY":
        if not sweep_bull:
            return False, "No Liquidity Sweep"
        if not bos_bull:
            return False, "No BOS Bull"
        if not fvg:
            return False, "No FVG"
        return True, "Sweep Low + BOS + FVG"
    else:
        if not sweep_bear:
            return False, "No Liquidity Sweep"
        if not bos_bear:
            return False, "No BOS Bear"
        if not fvg:
            return False, "No FVG"
        return True, "Sweep High + BOS + FVG"

def do_scan():
    try:
        bal = b_balance()
        bal_txt = "Bal $" + str(round(bal,2)) if bal>0 else "Bal $0 Demo"
        tg("SCAN V96 SECRET\n40 coins | 4H+6H\n" + bal_txt + "\nLev 3x Risk 0.5%\nSweep+BOS+FVG only")
        found = 0
        for sym in SYMBOLS:
            try:
                trend = trend_4h_6h(sym)
                if not trend:
                    continue
                ok, reason = secret_entry(sym, trend)
                if ok:
                    found += 1
                    k = get_k(sym, "1h", 2)
                    price = float(k[-1][4]) if k else 0
                    risk = bal * 0.005 if bal>0 else 5
                    tg("ENTRY FOUND\n\nCoin " + sym + "\nTrend " + trend + " 4H+6H\nReason " + reason + "\nPrice " + str(price) + "\nSL 6% TP1 1.5% 50% BE TP2 3% TP3 5%\nLEV 3x Size $" + str(round(risk,2)) + "\n" + bal_txt)
                    if found >= 2:
                        break
            except:
                continue
        if found == 0:
            tg("No secret setup yet - Patient = profit\n" + bal_txt)
    except Exception as e:
        tg("Scan error but alive: " + str(e))

@app.route("/")
def home():
    return "V96 FIXED Running - Go /setwebhook"

@app.route("/setwebhook")
def sethook():
    if not RENDER_URL:
        return "Set RENDER_EXTERNAL_URL env = https://your-app.onrender.com"
    hook = RENDER_URL.rstrip('/') + "/" + BOT_TOKEN
    api = "https://api.telegram.org/bot" + BOT_TOKEN + "/setWebhook?url=" + hook
    r = requests.get(api, timeout=10)
    tg("Webhook set! Type /start")
    return "OK " + r.text + " -> " + hook

@app.route("/scan")
def scan_page():
    threading.Thread(target=do_scan).start()
    return "Scan started"

# FIXED WEBHOOK - No f-string cutting
@app.route("/webhook", methods=["POST"])
def webhook_fixed():
    try:
        data = request.get_json(silent=True)
        if not data:
            return "ok"
        msg = data.get("message", {})
        txt = msg.get("text", "")
        if "/start" in txt or "/scan" in txt:
            threading.Thread(target=lambda: tg("Got /start! Scanning...")).start()
            threading.Thread(target=do_scan).start()
        return "ok"
    except:
        return "ok"

@app.route("/<token>", methods=["POST"])
def webhook_token(token):
    if token != BOT_TOKEN:
        return "ok"
    try:
        data = request.get_json(silent=True)
        if not data:
            return "ok"
        msg = data.get("message", {})
        txt = msg.get("text", "")
        cid = str(msg.get("chat", {}).get("id", "")).strip()
        if CHAT_ID and cid != CHAT_ID:
            try:
                url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
                requests.post(url, data={"chat_id": cid, "text": "Your ID " + cid + " Set as CHAT_ID env. Current " + CHAT_ID}, timeout=5)
            except:
                pass
            return "ok"
        if "/start" in txt or "/scan" in txt:
            threading.Thread(target=lambda: tg("Got /start! Scanning...")).start()
            threading.Thread(target=do_scan).start()
        return "ok"
    except:
        return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
