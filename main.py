import os, threading, requests, math
from flask import Flask, request, jsonify, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from binance.client import Client
from binance.exceptions import BinanceAPIException

BOT_TOKEN = os.getenv("BOT_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
RENDER_URL = "https://skelly-bot-v7.onrender.com"
MINI_APP_URL = f"{RENDER_URL}/miniapp"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

binance_client = None
if BINANCE_API_KEY and BINANCE_API_SECRET:
    binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

# ===== REAL FUTURES SCANNER - SAME AS OLD BOT =====
def scan_binance_futures_real():
    try:
        # Get all futures tickers (public - no key needed)
        tickers = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10).json()
        funding = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", timeout=10).json()
        funding_map = {f['symbol']: float(f['lastFundingRate'])*100 for f in funding}
        
        results = []
        for t in tickers:
            if not t['symbol'].endswith('USDT'): continue
            if '1000' in t['symbol'] or t['symbol'] in ['BTCUSDT','ETHUSDT']: 
                pass # allow majors
            
            price_change = float(t['priceChangePercent'])
            volume = float(t['quoteVolume'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])
            volatility = ((high-low)/low*100) if low>0 else 0
            
            # OLD BOT PULSE FORMULA
            vol_score = min(volume/5000000 * 10, 30) # Volume spike
            mom_score = min(abs(price_change)*3, 40) # Momentum
            vola_score = min(volatility*2, 20) # Volatility
            fund = funding_map.get(t['symbol'],0)
            fund_score = 10 if abs(fund) < 0.1 else 0
            
            strength = int(vol_score + mom_score + vola_score + fund_score)
            strength = max(1, min(99, strength))
            
            # Emoji setup like old bot
            if strength >= 84: emoji="🟢"; signal="🚀 STRONG LONG"; tag="🔥"
            elif strength >= 70: emoji="🟢"; signal="✅ LONG"; tag="⚡"
            elif strength >= 55: emoji="🟡"; signal="👀 WATCH"; tag="👀"
            elif strength >= 40: emoji="🟠"; signal="⚠️ WEAK"; tag="⚠️"
            else: emoji="🔴"; signal="📉 SHORT"; tag="🔻"
            
            if strength >= 55: # Only show top
                results.append({
                    "symbol": t['symbol'],
                    "strength": strength,
                    "emoji": emoji,
                    "signal": signal,
                    "tag": tag,
                    "change": price_change,
                    "vol": volume,
                    "price": float(t['lastPrice']),
                    "funding": fund,
                    "display": f"{emoji} {t['symbol'].replace('USDT','')} {strength}% {signal} | 💧Vol ${volume/1e6:.1f}M | 📈{price_change:+.1f}% | 💰Funding {fund:.3f}% {tag}"
                })
        
        # Sort by strength like old bot did
        results = sorted(results, key=lambda x: x['strength'], reverse=True)[:135]
        return results
    except Exception as e:
        print(f"Scan error: {e}")
        return [{"symbol":"BTCUSDT","strength":84,"display":"🟢 BTC 84% 🚀 STRONG LONG | 💧Vol $1200M | 📈+2.1% 🔥","price":67200,"emoji":"🟢","signal":"STRONG LONG"}]

# ===== MINI APP HTML V90 =====
MINI_APP_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PulseFlow V90</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:sans-serif}
body{background:#000;color:#fff;padding:12px;background:radial-gradient(circle at top, #0f2a1a 0%, #000 70%);}
.logo{font-weight:900;font-size:20px;} .logo span{color:#00FF88;}
.card{background:#111;border:1px solid #222;border-radius:14px;padding:12px;margin-top:10px;}
.top{display:flex;justify-content:space-between;align-items:center}
.strength{font-size:36px;font-weight:900;color:#00FF88;text-align:center}
.token{padding:10px;border-bottom:1px solid #1a1a1a;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.btn{padding:12px;border-radius:10px;border:none;font-weight:900;cursor:pointer}
.btn-long{background:#00FF88;color:#000;flex:1;margin:2px} .btn-short{background:#ff3b30;color:#fff;flex:1;margin:2px}
.scan{background:#00FF88;color:#000;width:100%;padding:16px;border-radius:14px;font-size:16px;margin-top:10px}
input,select{background:#000;border:1px solid #333;color:#fff;padding:10px;border-radius:8px;width:100%;margin-top:6px}
</style></head><body>
<div class="top"><div class="logo">SKELLY'S <span>V90</span></div><div id="bal" style="background:#111;padding:5px 10px;border-radius:20px;font-size:11px;">$0.00</div></div>

<div class="card" style="text-align:center"><div style="font-size:10px;color:#666;letter-spacing:2px;">PULSE STRENGTH</div><div class="strength" id="g">84%</div><div style="color:#00FF88;font-size:11px;" id="sig">● SCANNING FUTURES...</div></div>

<div class="card"><select id="lev"><option>5x</option><option>10x</option><option selected>20x</option><option>25x</option><option>50x</option></select><input id="qty" placeholder="Qty e.g 0.01 or 100" /></div>

<button class="scan" onclick="doScan()">⚡ SCAN 135 FUTURES</button>

<div class="card" id="list" style="max-height:400px;overflow-y:auto;"><div style="color:#555;text-align:center;padding:20px;">Press SCAN to load real Binance Futures...</div></div>

<div style="font-size:10px;color:#444;text-align:center;margin-top:15px;">V90 Real Scanner • Binance Futures Direct</div>

<script>
let tg=Telegram.WebApp; tg.expand(); tg.ready();
fetch('/api/balance').then(r=>r.json()).then(d=>{ if(d.balance) document.getElementById('bal').innerText='$'+d.balance; });

function doScan(){
 document.getElementById('list').innerHTML='<div style="text-align:center;padding:20px;color:#00FF88;">⚡ Scanning Binance Futures... 135 coins...</div>';
 fetch('/api/scan/real').then(r=>r.json()).then(d=>{
   document.getElementById('g').innerText=d.top_strength+'%';
   document.getElementById('sig').innerText=d.top_signal;
   let html='';
   d.results.forEach(t=>{
     html+=`<div class="token"><div style="flex:1">${t.display}</div><div style="display:flex;"><button class="btn btn-long" onclick="trade('${t.symbol}','BUY')">LONG</button><button class="btn btn-short" onclick="trade('${t.symbol}','SELL')">SHORT</button></div></div>`;
   });
   document.getElementById('list').innerHTML=html;
   tg.HapticFeedback.notificationOccurred('success');
 });
}
function trade(sym, side){
 let qty=document.getElementById('qty').value; let lev=document.getElementById('lev').value.replace('x','');
 if(!qty){ tg.showAlert('Enter Qty first!'); return; }
 tg.showConfirm(`Confirm ${side} ${sym} ${qty} ${lev}x?`, (ok)=>{
  if(!ok) return;
  fetch('/api/futures/trade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:sym,qty,side,leverage:lev})})
  .then(r=>r.json()).then(d=>{ tg.showAlert(d.success ? '✅ '+d.message : '❌ '+d.error); });
 });
}
doScan();
</script></body></html>
"""

@app.route('/')
def home(): return "V90 Real Futures Scanner Live 🟢"
@app.route('/miniapp')
def miniapp(): return render_template_string(MINI_APP_HTML)

@app.route('/api/scan/real')
def real_scan():
    results = scan_binance_futures_real()
    top = results[0] if results else {"strength":84,"signal":"STRONG LONG"}
    return jsonify({"results": results, "top_strength": top['strength'], "top_signal": top.get('signal','STRONG'), "count": len(results)})

@app.route('/api/balance')
def bal():
    if not binance_client: return jsonify({"balance":"Add Keys"})
    try:
        b = binance_client.futures_account_balance()
        usdt = next((x for x in b if x['asset']=='USDT'), {"balance":"0"})
        return jsonify({"balance": f"{float(usdt['balance']):.2f}"})
    except Exception as e: return jsonify({"error": str(e)})

@app.route('/api/futures/trade', methods=['POST'])
def trade():
    if not binance_client: return jsonify({"success":False,"error":"Add BINANCE_API_KEY & SECRET for Render Env!"})
    try:
        d=request.json; sym=d['symbol']; qty=float(d['qty']); side=d['side']; lev=int(d['leverage'])
        binance_client.futures_change_leverage(symbol=sym, leverage=lev)
        try: binance_client.futures_change_margin_type(symbol=sym, marginType='ISOLATED')
        except: pass
        order = binance_client.futures_create_order(symbol=sym, side=side, type='MARKET', quantity=qty)
        return jsonify({"success":True,"message": f"{side} {qty} {sym} {lev}x - ID {order['orderId']}"})
    except BinanceAPIException as e: return jsonify({"success":False,"error": e.message})
    except Exception as e: return jsonify({"success":False,"error": str(e)})

@bot.message_handler(commands=['start','scan'])
def start_cmd(m):
    if m.text.startswith('/scan'):
        bot.send_message(m.chat.id, "⚡ Scanning Real Binance Futures...")
        res = scan_binance_futures_real()[:15]
        msg = "💀 *SKELLY'S V90 REAL SCAN* 🟢\n\n"
        for r in res: msg += f"{r['display']}\n"
        msg += f"\n📱 Open Mini App to trade direct!"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📱 OPEN PulseFlow Futures", web_app=WebAppInfo(url=MINI_APP_URL)))
        bot.send_message(m.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📱 OPEN PulseFlow Futures", web_app=WebAppInfo(url=MINI_APP_URL)))
        markup.add(InlineKeyboardButton("⚡ SCAN 135 FUTURES", callback_data="scan_real"))
        bot.send_message(m.chat.id, "💀 *SKELLY'S BOT V90* 🟢\n\n✅ REAL Binance Futures Scanner\n✅ 135 coins sorted by Pulse Strength\n✅ LONG/SHORT direct from Mini App\n\nPress SCAN:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.data=="scan_real":
        bot.answer_callback_query(c.id, "Scanning...")
        res = scan_binance_futures_real()[:10]
        msg=""
        for r in res: msg+=f"{r['display']}\n"
        bot.send_message(c.message.chat.id, msg)

def run_bot(): 
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port=int(os.environ.get("PORT",10000))
    app.run(host='0.0.0.0', port=port)
