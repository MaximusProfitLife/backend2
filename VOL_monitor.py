import ccxt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import time
import os
import json
from telebot import TeleBot
from dotenv import load_dotenv

# 🔹 CONFIGURACIÓN
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID_GRUPO_VIP')
bot = TeleBot(TELEGRAM_TOKEN)
THREAD_ID = 9
DB_FILE = "volumen_monitor_btc.json"
SYMBOL = "BTC/USDT"

EXCHANGES_IDS = [
    "binance", "kraken", "bybit", "coinbase", "okx", 
    "bitfinex", "kucoin", "gate", "bingx", "bitget", "htx",
    "mexc", "whitebit", "coinex", "deribit", "bitmex", "phemex"
]

def cargar_memoria():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {"ultima_alerta_tiempo": 0, "ultima_alerta_tipo": "", "estado_cero": "NEUTRAL"}
    return {"ultima_alerta_tiempo": 0, "ultima_alerta_tipo": "", "estado_cero": "NEUTRAL"}

def guardar_memoria(memoria):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4)

def get_volume_data():
    all_volumes = []
    price_data = None
    for ex_id in EXCHANGES_IDS:
        try:
            exchange = getattr(ccxt, ex_id)({'timeout': 5000, 'enableRateLimit': True})
            exch_symbol = "BTC/USD" if (ex_id == 'bitmex') else SYMBOL
            ohlcv = exchange.fetch_ohlcv(exch_symbol, timeframe="1h", limit=720)
            if len(ohlcv) < 720: continue
            
            all_volumes.append([candle[5] for candle in ohlcv])
            if ex_id == "binance" and price_data is None:
                price_data = [candle[4] for candle in ohlcv]
        except: continue
    
    if not all_volumes or price_data is None: return None, None
    return np.mean(all_volumes, axis=0), price_data

def generar_foto_y_enviar(df, tipo_alerta, valor_actual):
    plt.style.use('dark_background')
    fig, (ax, ax_bar) = plt.subplots(2, 1, figsize=(12, 9), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    ax.fill_between(range(len(df)), df["lower"], df["upper"], color="gray", alpha=0.15)
    ax.plot(df["vol_returns"].values, color="#a85cfc", linewidth=1)
    ax.plot(df["upper"].values, color="#00ff88", linestyle="--", alpha=0.7)
    ax.plot(df["lower"].values, color="#ff3333", linestyle="--", alpha=0.7)
    ax.set_title(f"ALERTA BTC | {tipo_alerta}", color='yellow', fontweight='bold')
    
    ax_bar.bar(range(len(df)), df["Volume_USD"], color="blue", alpha=0.7)
    ax_bar.set_ylabel("Millones USD")
    
    path = "alerta_btc.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close(fig)

    with open(path, 'rb') as f:
        caption = f"🚨 **ANOMALÍA BTC DETECTADA**\n\nTipo: `{tipo_alerta}`\nValor: `{valor_actual:.4f}`"
        bot.send_photo(CHAT_ID, f, caption=caption, message_thread_id=THREAD_ID, parse_mode='Markdown')
    if os.path.exists(path): os.remove(path)

def correr_volumen():
    memoria = cargar_memoria()
    print("🚀 MONITOR BTC ACTIVADO")
    
    while True:
        try:
            vols, prices = get_volume_data()
            if vols is None: time.sleep(60); continue
            
            vol_usd = (vols * np.array(prices)) / 1_000_000
            df = pd.DataFrame(vol_usd, columns=["Volume_USD"])
            df["vol_returns"] = df["Volume_USD"].pct_change()
            
            ventana = 200
            df["mean_ret"] = df["vol_returns"].rolling(window=ventana).mean()
            df["std_ret"] = df["vol_returns"].rolling(window=ventana).std()
            df["upper"] = df["mean_ret"] + (2 * df["std_ret"])
            df["lower"] = df["mean_ret"] - (2 * df["std_ret"])
            df = df.dropna()

            actual = df["vol_returns"].iloc[-1]
            tiempo_actual = time.time()
            candidato_tipo = ""
            
            # Lógica de detección única para BTC
            if (actual > df["upper"].iloc[-1] or actual < df["lower"].iloc[-1]):
                candidato_tipo = "ANOMALÍA (BANDAS)"
            elif actual > 0 and memoria["estado_cero"] != "ARRIBA":
                candidato_tipo = "CRUCE CERO (ARRIBA)"
                memoria["estado_cero"] = "ARRIBA"
            elif actual < 0 and memoria["estado_cero"] != "ABAJO":
                candidato_tipo = "CRUCE CERO (ABAJO)"
                memoria["estado_cero"] = "ABAJO"

            # Filtro anti-spam
            if candidato_tipo != "":
                if (candidato_tipo != memoria["ultima_alerta_tipo"]) or (tiempo_actual - memoria["ultima_alerta_tiempo"] > 14400):
                    print(f"🎯 Alerta BTC: {candidato_tipo}")
                    generar_foto_y_enviar(df, candidato_tipo, actual)
                    
                    memoria.update({
                        "ultima_alerta_tiempo": tiempo_actual,
                        "ultima_alerta_tipo": candidato_tipo
                    })
                    guardar_memoria(memoria)
            
            time.sleep(300)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(60)

if __name__ == '__main__':
    correr_volumen()
