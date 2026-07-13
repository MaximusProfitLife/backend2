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
DB_FILE = "volumen_monitor.json"

# Lista completa de exchanges y pares
EXCHANGES_IDS = [
    "binance", "kraken", "bybit", "coinbase", "okx", 
    "bitfinex", "kucoin", "gate", "bingx", "bitget", "htx",
    "mexc", "whitebit", "coinex", "deribit", "bitmex", "phemex"
]
PARES = ["BTC/USDT", "ETH/USDT"]

def cargar_memoria():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def guardar_memoria(memoria):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4)

memoria = cargar_memoria()
estado_cero = memoria.get("estado_cero")
ultima_alerta_anomalia = memoria.get("ultima_alerta_anomalia", 0)

def get_volume_data():
    consolidated_data = {}
    prices = {}
    for ex_id in EXCHANGES_IDS:
        try:
            exchange = getattr(ccxt, ex_id)({'timeout': 10000, 'enableRateLimit': True})
            for symbol in PARES:
                # Ajuste de nombre para exchanges con nomenclatura específica
                exch_symbol = "BTC/USD" if (ex_id == 'bitmex' and "BTC" in symbol) else symbol
                ohlcv = exchange.fetch_ohlcv(exch_symbol, timeframe="1h", limit=720)
                
                vols = [candle[5] for candle in ohlcv]
                consolidated_data.setdefault(symbol, []).append(vols)
                
                # Usamos Binance como referencia de precio para la conversión a USD
                if ex_id == "binance":
                    prices[symbol] = [candle[4] for candle in ohlcv]
        except: continue
    return consolidated_data, prices

def generar_foto_y_enviar(df_plot, tipo_alerta, valor_actual):
    plt.style.use('dark_background')
    fig, (ax, ax_bar) = plt.subplots(2, 1, figsize=(12, 9), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # 1. Gráfico de Rendimiento
    ax.fill_between(range(len(df_plot)), df_plot["lower"], df_plot["upper"], color="gray", alpha=0.15)
    ax.plot(range(len(df_plot)), df_plot["vol_returns"], color="#a85cfc", linewidth=1)
    ax.plot(range(len(df_plot)), df_plot["upper"], color="#00ff88", linestyle="--", alpha=0.7)
    ax.plot(range(len(df_plot)), df_plot["lower"], color="#ff3333", linestyle="--", alpha=0.7)
    ax.scatter(len(df_plot)-1, valor_actual, color="magenta", s=150, edgecolors='white', zorder=5)
    ax.set_title(f"ALERTA MAXIMUS | {tipo_alerta}", color='yellow', fontweight='bold')
    ax.grid(alpha=0.1)

    # 2. Gráfico de Volumen en USD
    ax_bar.bar(range(len(df_plot)), df_plot["Volume_USD"], color="blue", alpha=0.7)
    ax_bar.set_ylabel("Millones USD")
    ax_bar.grid(axis="y", alpha=0.2)
    
    path = "alerta_volumen.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close()

    pares_str = ", ".join(PARES)
    with open(path, 'rb') as f:
        caption = f"🚨 ANOMALÍA DETECTADA\n\nTipo: `{tipo_alerta}`\nValor: `{valor_actual:.4f}`\nActivos: `{pares_str}`"
        bot.send_photo(CHAT_ID, f, caption=caption, message_thread_id=THREAD_ID, parse_mode='Markdown')
    if os.path.exists(path): os.remove(path)

def correr_volumen():
    global estado_cero, ultima_alerta_anomalia
    while True:
        try:
            data, prices = get_volume_data()
            if not data: 
                time.sleep(60)
                continue
            
            total_vol_usd = 0
            for symbol in PARES:
                if symbol in data and symbol in prices:
                    vols_array = np.array(data[symbol]).mean(axis=0)
                    total_vol_usd += (vols_array * np.array(prices[symbol])) / 1_000_000
            
            df = pd.DataFrame(total_vol_usd, columns=["Volume_USD"])
            df["vol_returns"] = df["Volume_USD"].pct_change()
            df = df.dropna()

            # --- ESTA ES LA VALIDACIÓN QUE TE FALTA ---
            if df.empty:
                print("DataFrame vacío, esperando más datos...")
                time.sleep(60)
                continue
            # ------------------------------------------

            actual = df["vol_returns"].iloc[-1]
            timestamp_actual = time.time()
            disparar = False
            tipo = ""

            # ... (tu lógica de disparar sigue igual)
            if actual > df["upper"].iloc[-1] or actual < df["lower"].iloc[-1]:
                if (timestamp_actual - ultima_alerta_anomalia) > 14400:
                    disparar = True
                    tipo = "ANOMALÍA (BANDAS)"
                    ultima_alerta_anomalia = timestamp_actual
            else:
                if actual > 0 and estado_cero != "ARRIBA":
                    disparar = True
                    tipo = "CRUCE CERO (Entrando VOL)"
                    estado_cero = "ARRIBA"
                elif actual < 0 and estado_cero != "ABAJO":
                    disparar = True
                    tipo = "CRUCE CERO (Saliendo VOL)"
                    estado_cero = "ABAJO"

            if disparar:
                guardar_memoria({"estado_cero": estado_cero, "ultima_alerta_anomalia": ultima_alerta_anomalia})
                generar_foto_y_enviar(df, tipo, actual)
                time.sleep(60)
            else:
                time.sleep(300)
        except Exception as e:
            print(f"Error en bucle: {e}")
            time.sleep(60)

if __name__ == '__main__':
    correr_volumen()
