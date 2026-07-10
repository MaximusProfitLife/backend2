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

# Pares a analizar
PARES = ["BTC/USDT", "ETH/USDT"]

def get_volume_data():
    """Obtiene volumen y precios para BTC y ETH consolidado"""
    consolidated_data = {}
    prices = {} # Para la conversión a USD
    
    for ex_id in ["binance", "bybit", "okx", "bitget"]: # Exchanges principales para robustez
        try:
            exchange = getattr(ccxt, ex_id)({'timeout': 10000, 'enableRateLimit': True})
            for symbol in PARES:
                # Ajuste nombre para bitmex si fuera necesario
                exch_symbol = "BTC/USD" if (ex_id == 'bitmex' and "BTC" in symbol) else symbol
                ohlcv = exchange.fetch_ohlcv(exch_symbol, timeframe="1h", limit=720)
                
                # Volúmenes
                vols = [candle[5] for candle in ohlcv]
                consolidated_data.setdefault(symbol, []).append(vols)
                
                # Precio de cierre para convertir a USD
                if ex_id == "binance":
                    prices[symbol] = [candle[4] for candle in ohlcv]
        except: continue
    return consolidated_data, prices

def generar_foto_y_enviar(df_plot, tipo_alerta, valor_actual):
    plt.style.use('dark_background')
    # Configuración de los dos gráficos
    fig, (ax, ax_bar) = plt.subplots(2, 1, figsize=(12, 9), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # 1. Gráfico de Rendimiento (Lógica de Bandas de Desviación)
    ax.fill_between(range(len(df_plot)), df_plot["lower"], df_plot["upper"], color="gray", alpha=0.15)
    ax.plot(range(len(df_plot)), df_plot["vol_returns"], color="#a85cfc", label="Rendimiento (%)", linewidth=1)
    ax.plot(range(len(df_plot)), df_plot["upper"], color="#00ff88", linestyle="--", alpha=0.7)
    ax.plot(range(len(df_plot)), df_plot["lower"], color="#ff3333", linestyle="--", alpha=0.7)
    ax.scatter(len(df_plot)-1, valor_actual, color="magenta", s=100, zorder=5)
    ax.set_title(f"ALERTA MAXIMUS | {tipo_alerta} | BTC+ETH", color='yellow', fontweight='bold')
    ax.grid(alpha=0.1)

    # 2. Gráfico de Volumen en USD
    ax_bar.bar(range(len(df_plot)), df_plot["Volume_USD"], color="blue", alpha=0.7)
    ax_bar.set_ylabel("Millones USD")
    ax_bar.grid(axis="y", alpha=0.2)
    
    path = "alerta_volumen.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close()

    with open(path, 'rb') as f:
        caption = f"🚨 **ANOMALÍA DETECTADA**\n\nTipo: `{tipo_alerta}`\nValor: `{valor_actual:.4f}`\nActivos: BTC/ETH Consolidado"
        bot.send_photo(CHAT_ID, f, caption=caption, message_thread_id=THREAD_ID, parse_mode='Markdown')
    if os.path.exists(path): os.remove(path)

def correr_volumen():
    while True:
        try:
            data, prices = get_volume_data()
            if not data: continue
            
            # Consolidar Volumen en USD
            total_vol_usd = 0
            for symbol in PARES:
                vols_array = np.array(data[symbol]).mean(axis=0) # Promedio entre exchanges
                total_vol_usd += (vols_array * np.array(prices[symbol])) / 1_000_000
            
            df = pd.DataFrame(total_vol_usd, columns=["Volume_USD"])
            df["vol_returns"] = df["Volume_USD"].pct_change()
            
            # Cálculo de bandas (Ventana 200)
            ventana = 200
            df["mean_ret"] = df["vol_returns"].rolling(window=ventana).mean()
            df["std_ret"] = df["vol_returns"].rolling(window=ventana).std()
            df["upper"] = df["mean_ret"] + (2 * df["std_ret"])
            df["lower"] = df["mean_ret"] - (2 * df["std_ret"])
            df = df.dropna()

            # Lógica de disparo (aquí iría tu check de alertas...)
            # ... (código de disparo igual al anterior) ...
            
            time.sleep(300)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == '__main__':
    correr_volumen()
