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

def get_volume_data():
    consolidated_data = {}
    prices = {}
    for ex_id in EXCHANGES_IDS:
        try:
            exchange = getattr(ccxt, ex_id)({'timeout': 10000, 'enableRateLimit': True})
            for symbol in PARES:
                exch_symbol = "BTC/USD" if (ex_id == 'bitmex' and "BTC" in symbol) else symbol
                ohlcv = exchange.fetch_ohlcv(exch_symbol, timeframe="1h", limit=720)
                vols = [candle[5] for candle in ohlcv]
                consolidated_data.setdefault(symbol, []).append(vols)
                if ex_id == "binance":
                    prices[symbol] = [candle[4] for candle in ohlcv]
        except: continue
    return consolidated_data, prices

def generar_foto_y_enviar(df, tipo_alerta, valor_actual):
    plt.style.use('dark_background')
    fig, (ax, ax_bar) = plt.subplots(2, 1, figsize=(12, 9), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    
    # Gráfico 1: Rendimiento
    ax.fill_between(range(len(df)), df["lower"], df["upper"], color="gray", alpha=0.15)
    ax.plot(df["vol_returns"].values, color="#a85cfc", linewidth=1)
    ax.plot(df["upper"].values, color="#00ff88", linestyle="--", alpha=0.7)
    ax.plot(df["lower"].values, color="#ff3333", linestyle="--", alpha=0.7)
    ax.set_title(f"ALERTA MAXIMUS | {tipo_alerta}", color='yellow', fontweight='bold')
    
    # Gráfico 2: Volumen USD
    ax_bar.bar(range(len(df)), df["Volume_USD"], color="blue", alpha=0.7)
    ax_bar.set_ylabel("Millones USD")
    
    path = "alerta_volumen.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close(fig)

    with open(path, 'rb') as f:
        caption = f"🚨 **ANOMALÍA DETECTADA**\n\nTipo: `{tipo_alerta}`\nValor: `{valor_actual:.4f}`"
        bot.send_photo(CHAT_ID, f, caption=caption, message_thread_id=THREAD_ID, parse_mode='Markdown')
    if os.path.exists(path): os.remove(path)

def correr_volumen():
    memoria = cargar_memoria()
    ultima_alerta_tiempo = memoria.get("ultima_alerta_tiempo", 0)
    ultima_alerta_tipo = memoria.get("ultima_alerta_tipo", "")
    estado_cero = memoria.get("estado_cero", "NEUTRAL")
    
    print("🚀 MONITOR DE VOLUMEN INTELIGENTE ACTIVADO")
    
    while True:
        try:
            data, prices = get_volume_data()
            if not data: 
                time.sleep(60); continue
            
            # --- CÁLCULO DE DATOS ---
            total_vol_usd = None
            for symbol in PARES:
                if symbol in data and symbol in prices:
                    vols_avg = np.mean(data[symbol], axis=0)
                    if total_vol_usd is None: total_vol_usd = (vols_avg * np.array(prices[symbol])) / 1_000_000
                    else: total_vol_usd += (vols_avg * np.array(prices[symbol])) / 1_000_000
            
            df = pd.DataFrame(total_vol_usd, columns=["Volume_USD"])
            df["vol_returns"] = df["Volume_USD"].pct_change()
            
            ventana = 200
            df["mean_ret"] = df["vol_returns"].rolling(window=ventana).mean()
            df["std_ret"] = df["vol_returns"].rolling(window=ventana).std()
            df["upper"] = df["mean_ret"] + (2 * df["std_ret"])
            df["lower"] = df["mean_ret"] - (2 * df["std_ret"])
            df = df.dropna()

            actual = df["vol_returns"].iloc[-1]
            tiempo_actual = time.time()
            
            # --- LÓGICA DE DETECCIÓN ---
            candidato_tipo = ""
            
            # 1. ¿Es Anomalía?
            if (actual > df["upper"].iloc[-1] or actual < df["lower"].iloc[-1]):
                candidato_tipo = "ANOMALÍA (BANDAS)"
            
            # 2. ¿Es Cruce? (Independiente de la anomalía)
            elif actual > 0 and estado_cero != "ARRIBA":
                candidato_tipo = "CRUCE CERO (ARRIBA)"
                estado_cero = "ARRIBA"
            elif actual < 0 and estado_cero != "ABAJO":
                candidato_tipo = "CRUCE CERO (ABAJO)"
                estado_cero = "ABAJO"

            # --- FILTRO INTELIGENTE ---
            # Disparamos si:
            # 1. Hay un candidato.
            # 2. El tipo de alerta cambió (ej: de Cruce a Anomalía) O pasaron 4 horas.
            if candidato_tipo != "":
                if (candidato_tipo != ultima_alerta_tipo) or (tiempo_actual - ultima_alerta_tiempo > 14400):
                    
                    print(f"🎯 Alerta enviada: {candidato_tipo}")
                    generar_foto_y_enviar(df, candidato_tipo, actual)
                    
                    ultima_alerta_tiempo = tiempo_actual
                    ultima_alerta_tipo = candidato_tipo
                    
                    guardar_memoria({
                        "ultima_alerta_tiempo": ultima_alerta_tiempo,
                        "ultima_alerta_tipo": ultima_alerta_tipo,
                        "estado_cero": estado_cero
                    })
            
            time.sleep(300)
            
        except Exception as e:
            print(f"⚠️ Error en bucle: {e}")
            time.sleep(60)

if __name__ == '__main__':
    correr_volumen()
