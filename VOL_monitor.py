import ccxt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
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

# 📂 Archivo para persistencia de memoria
DB_FILE = "volumen_monitor.json"

def cargar_memoria():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_memoria(memoria):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4)

# 🔹 MEMORIA INICIAL
memoria = cargar_memoria()
estado_cero = memoria.get("estado_cero")  # "ARRIBA" o "ABAJO"
ultima_alerta_anomalia = memoria.get("ultima_alerta_anomalia", 0)

exchanges_ids = [
    "binance", "kraken", "bybit", "coinbase", "okx", 
    "bitfinex", "kucoin", "gate", "bingx", "bitget", "htx",
    "mexc", "whitebit", "coinex", "deribit", "bitmex", "phemex"
]

SYMBOL_DEFAULT = "BTC/USDT"

def get_volume_data():
    volumes_dict = {}
    for ex_id in exchanges_ids:
        try:
            exchange = getattr(ccxt, ex_id)({'timeout': 10000, 'enableRateLimit': True})
            symbol = "BTC/USD" if ex_id == 'bitmex' else SYMBOL_DEFAULT
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=720)
            volumes_dict[ex_id] = [candle[5] for candle in ohlcv]
        except: continue
    return volumes_dict

def generar_foto_y_enviar(df_plot, tipo_alerta, valor_actual):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 7))
    
    ax.fill_between(range(len(df_plot)), df_plot["lower"], df_plot["upper"], color="gray", alpha=0.15)
    ax.plot(range(len(df_plot)), df_plot["vol_returns"], color="#a85cfc", label="Rendimiento Volumen (%)", linewidth=1)
    ax.plot(range(len(df_plot)), df_plot["upper"], color="#00ff88", linestyle="--", alpha=0.7)
    ax.plot(range(len(df_plot)), df_plot["lower"], color="#ff3333", linestyle="--", alpha=0.7)
    ax.axhline(0, color='white', linewidth=0.8, alpha=0.5)

    ax.scatter(len(df_plot)-1, valor_actual, color="magenta", s=150, edgecolors='white', zorder=5)

    # MARCA DE AGUA
    fig.text(0.5, 0.5, "MaximusProftLife", fontsize=60, color='white', 
             alpha=0.1, ha='center', va='center', rotation=25, weight='bold')

    ax.set_title(f"ALERTA MAXIMUS - 1H\n{tipo_alerta}", color='yellow', fontweight='bold')
    ax.grid(alpha=0.1)
    
    path = "alerta_volumen.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close()

    with open(path, 'rb') as f:
        caption = f"🚨 **ALERTA DE VOLUMEN**\n\nTipo: `{tipo_alerta}`\nValor: `{valor_actual:.4f}`\n🛰 _Sistema Multi-Exchange_"
        bot.send_photo(CHAT_ID, f, caption=caption, message_thread_id=THREAD_ID, parse_mode='Markdown')
    
    if os.path.exists(path): os.remove(path)

print(f"🚀 MONITOR INTELIGENTE ACTIVADO - Usando {DB_FILE}")

def correr_volumen():
    global estado_cero, ultima_alerta_anomalia
    print(f"🚀 MONITOR DE VOLUMEN ACTIVADO")
    
    while True:
        try:
            # 1. Recuperamos los datos primero
            data = get_volume_data()
            if not data:
                time.sleep(30)
                continue
            
            # 2. Construimos el DataFrame y procesamos (Todo esto va DENTRO del try)
            df = pd.DataFrame.from_dict(data, orient="index").T
            df["Volume_Consolidado"] = df.mean(axis=1)
            df["vol_returns"] = df["Volume_Consolidado"].pct_change()
            
            ventana = 200
            df["mean_ret"] = df["vol_returns"].rolling(window=ventana).mean()
            df["std_ret"] = df["vol_returns"].rolling(window=ventana).std()
            df["upper"] = df["mean_ret"] + (2 * df["std_ret"])
            df["lower"] = df["mean_ret"] - (2 * df["std_ret"])
            
            df = df.dropna()
            if df.empty: continue

            actual = df["vol_returns"].iloc[-1]
            timestamp_actual = time.time()

            disparar = False
            tipo = ""

            # Lógica de señales
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
                guardar_memoria({
                    "estado_cero": estado_cero,
                    "ultima_alerta_anomalia": ultima_alerta_anomalia
                })
                print(f"🎯 Alerta Única Detectada: {tipo}. Enviando...")
                generar_foto_y_enviar(df, tipo, actual)
                time.sleep(60)
            else:
                print(f"😴 Mercado Estable / Notificado [{time.strftime('%H:%M')}]")
                time.sleep(300)

        except Exception as e:
            print(f"⚠️ Error en bucle de volumen: {e}")
            time.sleep(60)

# ESTO VA FUERA DE TODO, SIN NINGUNA SANGRÍA (ALINEADO A LA IZQUIERDA)
if __name__ == '__main__':
    print(f"🚀 MONITOR INTELIGENTE ACTIVADO - Usando {DB_FILE}")
    correr_volumen()
