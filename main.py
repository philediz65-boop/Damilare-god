import os
import threading
import logging
from flask import Flask
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Setup
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

app = Flask(__name__)

@app.route('/')
def home():
    return "SKELLY V7.1 FIX SERVICE UNAVAILABLE - MENU COLOURED GOD 90% LIVE - Virginia"

@app.route('/health')
def health():
    return "OK"

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚡ FAST 18 MENU", callback_data="fast18")],
        [InlineKeyboardButton("📊 Check Chart", callback_data="chart")],
        [InlineKeyboardButton("🆘 Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 *SKELLY V7.1 IS LIVE - Virginia Fix* 🔥\n\n"
        "Service Unavailable don fix! Bot don dey Live.\n\n"
        "Select menu below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "fast18":
        await query.edit_message_text("⚡ FAST 18 Menu don load! Bot dey work 100% for Virginia!")
    elif query.data == "chart":
        await query.edit_message_text("📊 Chart feature go come back after we stabilize Live status.")
    elif query.data == "help":
        await query.edit_message_text("🆘 Help: Type /start again if bot sleep. Render free tier dey sleep after 50s.")

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def run_bot():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set in Environment!")
        return
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    print("Bot polling started...")
    application.run_polling()

if __name__ == "__main__":
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    # Start bot in main thread
    run_bot()
