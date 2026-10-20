import os, re, threading, requests, time, io, json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from datetime import datetime, date

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))
app = Flask(__name__)
CACHE = {}
LOCK = threading.Lock()
DATA_DIR = "/data" if os.path.exists("/data") else "/tmp"
ACTIVE_FILE = f"{DATA_DIR}/active_trade_v18.json"
DAILY_FILE = f"{DATA_DIR}/daily_stats_v18.json"
CHAT_FILE = f"{DATA_DIR}/last_chat_id.json"
BACKUP_FILE = "./active_backup.json"
GLOBAL_ACTIVE = {}
GLOBAL_CHAT_ID = None
HEADERS = {"User-Agent": "Mozilla/5.0"}

DEFAULT_STAKE = 1.0
REDUCED_STAKE = 0.5
CHOPPY_STAKE = 0.5
DEFAULT_LEV = 15
MEME_LEV = 10
MEME_COINS = {"WIF", "PEPE", "BONK", "FLOKI", "BOME", "SHIB", "NOT", "FARTCOIN", "ZEREBRO", "BR", "PONS", "TRUMP"}

def get_lev(c):
    return MEME_LEV if c in MEME_COINS else DEFAULT_LEV

MIN_VOL_PCT = 8
MIN_ADX = 12
MIN_SCORE = 30
MIN_ADAPTIVE = 25
MIN_CHOPPY = 20
GOD_MODE_SCORE = 75
MAX_DAILY_LOSS = 2
MAX_PREM = 82
MIN_DISC = 18

print(f"💀 V18.7 QUICK TP 57 COINS {DATA_DIR} 👌")

# ==================== PERSISTENCE ====================
def load_json(p, d):
    try:
        if os.path.exists(p):
            with open(p, 'r') as f:
                return json.load(f)
        alt = p.replace("/data", "/tmp") if "/data" in p else p.replace("/tmp", "/data")
        if os.path.exists(alt):
            with open(alt, 'r') as f:
                return json.load(f)
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return d

def save_json(p, data):
    try:
        with LOCK:
            with open(p, 'w') as f:
                json.dump(data, f)
            with open(BACKUP_FILE, 'w') as f2:
                json.dump(data, f2)
    except Exception:
        pass

def get_daily():
    d = load_json(DAILY_FILE, {})
    today = str(date.today())
    if d.get("date") != today:
        d = {"date": today, "wins": 0, "losses": 0, "trades": 0, "pnl": 0.0, "last_result": ""}
        save_json(DAILY_FILE, d)
    return d

def update_daily(result, pnl, coin=""):
    d = get_daily()
    d["trades"] += 1
    if result == "WIN":
        d["wins"] += 1
        d["last_result"] = "WIN"
    else:
        d["losses"] += 1
        d["last_result"] = "LOSS"
    d["pnl"] += pnl
    save_json(DAILY_FILE, d)
    return d

def get_active():
    global GLOBAL_ACTIVE
    if GLOBAL_ACTIVE and GLOBAL_ACTIVE.get("status") == "OPEN":
        return GLOBAL_ACTIVE
    fa = load_json(ACTIVE_FILE, {})
    if fa and fa.get("status") == "OPEN":
        GLOBAL_ACTIVE = fa
        return fa
    return {}

def set_active(data):
    global GLOBAL_ACTIVE
    GLOBAL_ACTIVE = data
    save_json(ACTIVE_FILE, data)

def clear_active():
    global GLOBAL_ACTIVE
    GLOBAL_ACTIVE = {}
    save_json(ACTIVE_FILE, {})

def save_chat_id(cid):
    global GLOBAL_CHAT_ID
    GLOBAL_CHAT_ID = cid
    save_json(CHAT_FILE, {"chat_id": cid})

def get_chat_id():
    global GLOBAL_CHAT_ID
    if GLOBAL_CHAT_ID:
        return GLOBAL_CHAT_ID
    d = load_json(CHAT_FILE, {})
    cid = d.get("chat_id")
    if cid:
        GLOBAL_CHAT_ID = cid
    return cid

# ==================== COINS ====================
CRYPTO = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT", "ADA": "ADAUSDT", "AVAX": "AVAXUSDT", "LINK": "LINKUSDT", "TRX": "TRXUSDT",
    "DOT": "DOTUSDT", "MATIC": "MATICUSDT", "LTC": "LTCUSDT", "BCH": "BCHUSDT", "UNI": "UNIUSDT",
    "ATOM": "ATOMUSDT", "ETC": "ETCUSDT", "FIL": "FILUSDT", "PEPE": "PEPEUSDT", "BONK": "BONKUSDT",
    "SHIB": "SHIBUSDT", "FLOKI": "FLOKIUSDT", "WIF": "WIFUSDT", "BOME": "BOMEUSDT", "SUI": "SUIUSDT",
    "ARB": "ARBUSDT", "OP": "OPUSDT", "APT": "APTUSDT", "TAO": "TAOUSDT", "NOT": "NOTUSDT",
    "PAXG": "PAXGUSDT", "JUP": "JUPUSDT", "ENA": "ENAUSDT", "FARTCOIN": "FARTCOINUSDT",
    "TIA": "TIAUSDT", "AVAIL": "AVAILUSDT", "DYM": "DYMUSDT", "ALT": "ALTUSDT", "EIGEN": "EIGENUSDT",
    "STRK": "STRKUSDT", "SAGA": "SAGAUSDT", "MANTA": "MANTAUSDT", "GTC": "GTCUSDT",
    "WLD": "WLDUSDT", "ZEREBRO": "ZEREBROUSDT", "ASTER": "ASTERUSDT", "XAUT": "XAUTUSDT",
    "HBAR": "HBARUSDT", "ONDO": "ONDOUSDT", "VVV": "VVVUSDT", "BR": "BRUSDT", "TRUMP": "TRUMPUSDT",
    "PONS": "PONSUSDT", "HYPE": "HYPEUSDT", "QNT": "QNTUSDT", "NEAR": "NEARUSDT", "MNT": "MNTUSDT"
}

FAST_LIST = ["WLD", "ZEREBRO", "TRUMP", "HYPE", "ONDO", "APT", "ENA", "NEAR", "BTC", "ETH", "SOL",
             "XRP", "AVAX", "LINK", "SUI", "LTC", "UNI", "QNT", "HBAR", "DOGE", "DOT", "ARB", "OP",
             "TAO", "PEPE", "BONK", "FLOKI", "WIF", "SHIB", "BNB", "ADA", "MATIC", "ASTER", "VVV", "BR"][:35]

SLOW_LIST = ["BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "TRX", "DOT", "MATIC", "LTC", "BCH", "UNI",
             "ATOM", "ETC", "FIL", "PAXG", "WLD", "ONDO", "APT", "
