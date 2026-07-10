import ccxt
import pandas as pd
import time
import numpy as np 
import os
import json
import schedule
from dotenv import load_dotenv
from telebot import TeleBot
from pathlib import Path
from ccxt.base.errors import NetworkError 


# 🔐 Cargar entorno y Telegram
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_GRUPO_VIP")
THREAD_ID = 9
bot = TeleBot(TOKEN)

# 🔁 Control de historial persistente
HISTORIAL_PATH = Path("historial_alertas.json")

def cargar_historial():
    if HISTORIAL_PATH.exists():
        with open(HISTORIAL_PATH, "r") as f:
            try: return json.load(f)
            except: return {}
    return {}

def guardar_historial(historial):
    with open(HISTORIAL_PATH, "w") as f:
        json.dump(historial, f, indent=2, default=str)

ultimos_patrones_enviados = cargar_historial()

# 📤 Función de envío a Telegram
def send_telegram_message(message):
    if message and message.strip():
        try:
            bot.send_message(CHAT_ID, message, message_thread_id=THREAD_ID, parse_mode='HTML')
        except Exception as e:
            print(f"❌ Error al enviar mensaje a Telegram: {e}")

# ===========================
# 🔹 Configuración de exchanges y pares
# ===========================
exchanges_liquidos = ["binance", "kraken", "bybit", "coinbase", "okx", "bitfinex", "kucoin", "gate", "bingx", "bitget", "mexc", "whitebit", "coinex", "deribit", "bitmex"]
pares_liquidos = ['ADA/USDT', 'BTC/USDT', 'ETH/USDT']

# ===========================
# 🔹 Función para obtener datos OHLCV
# ===========================
def obtener_datos(exchange_name, symbol, timeframe='1h', limit=200):
    try:
        exchange = getattr(ccxt, exchange_name)()
        exchange.timeout = 30000 
        exchange.load_markets()

        if symbol in exchange.markets:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volumen'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='ms')
            df['Exchange'] = exchange_name
            
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'exchange'] 
            return df
        else:
            return None
    except NetworkError:
        print(f"❌ Error de red/DNS al conectar con {exchange_name}. Saltando este exchange.")
        return None
    except Exception as e:
        return None

# ===========================
# 🔹 Consolidar datos multi-exchange
# ===========================
def consolidar_datos(symbol):
    dfs = [obtener_datos(exchange, symbol) for exchange in exchanges_liquidos]
    dfs = [df for df in dfs if df is not None and not df.empty]

    if dfs:
        df_global = pd.concat(dfs).groupby('timestamp').agg({
            'open': 'mean',
            'high': 'max',
            'low': 'min',
            'close': 'mean',
            'volume': 'sum'
        }).reset_index()
        
        df_global.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volumen']
        return df_global
    return None

# ===========================
# 🔹 Funciones de Análisis
# ===========================
def evaluar_contexto_patron(df, tipo="spring", n_contexto=4):
    if len(df) < n_contexto + 1:
        return {"confirmado": False} 

    contexto = df.iloc[-(n_contexto+1):-1]
    vol_actual = df['Volumen'].iloc[-1]
    rango_actual = df['High'].iloc[-1] - df['Low'].iloc[-1]
    vol_prom_prev = contexto['Volumen'].mean()
    rangos_previos = (contexto['High'] - contexto['Low']).mean()

    compresion_vol = vol_prom_prev < vol_actual * 0.6
    compresion_rango = rangos_previos < rango_actual * 0.7

    cierre_previo = contexto['Close'].iloc[-1]
    cierre_inicial = contexto['Close'].iloc[0]
    tendencia = "Lateral"
    if cierre_previo > cierre_inicial: tendencia = "Alcista"
    elif cierre_previo < cierre_inicial: tendencia = "Bajista"

    confirmado = False
    if tipo == "spring":
        confirmado = tendencia in ["Bajista", "Lateral"] and (compresion_vol or compresion_rango)
    elif tipo == "breakout":
        confirmado = tendencia == "Lateral" and compresion_vol and compresion_rango

    return {"compresion_volumen": compresion_vol, "compresion_rango": compresion_rango, "tendencia_previa": tendencia, "confirmado": confirmado}

def detectar_patrones_real_time(df):
    # Analizamos df.iloc[-2] que es la VELA CERRADA
    df_cerrada = df.iloc[-2].copy()
    df_previa = df.iloc[-3].copy()
    
    if len(df) < 50:
        return {"Timestamp": df_cerrada['Timestamp'], "Close": df_cerrada['Close'], "Patrón de Liquidez": "Error: Datos Insuficientes", "Intencion": "Neutral"}
        
    contexto_spring = evaluar_contexto_patron(df.iloc[:-1], tipo="spring")
    contexto_breakout = evaluar_contexto_patron(df.iloc[:-1], tipo="breakout")
    
    promedio_vol_50 = df['Volumen'].iloc[:-1].rolling(50).mean().iloc[-1]
    promedio_vol_20 = df['Volumen'].iloc[:-1].rolling(20).mean().iloc[-1]
    
    patron_liquidez = "Sin Patrón"
    intencion = "Neutral"

    # Barrido Alcista
    if df_cerrada['Low'] < df_previa['Low'] and df_cerrada['Close'] > df_cerrada['Open']:
        patron_liquidez = "Barrido de Liquidez Alcista"; intencion = "Compra Institucional"

    # Barrido Bajista
    elif df_cerrada['High'] > df_previa['High'] and df_cerrada['Close'] < df_cerrada['Open']:
        patron_liquidez = "Barrido de Liquidez Bajista"; intencion = "Venta Institucional"

    # Bloque de Órdenes
    elif df_cerrada['Volumen'] > promedio_vol_50 * 3:
        patron_liquidez = "Bloque de Órdenes Institucional"; intencion = "Compra" if df_cerrada['Close'] > df_cerrada['Open'] else "Venta"

    # Absorción de Liquidez
    elif df_cerrada['Volumen'] > promedio_vol_20 * 2:
        if df_cerrada['Close'] == df_cerrada['High']:
            patron_liquidez = "Absorción de Liquidez en Resistencia"; intencion = "Venta Institucional"
        elif df_cerrada['Close'] == df_cerrada['Low']:
            patron_liquidez = "Absorción de Liquidez en Soporte"; intencion = "Compra Institucional"

    # SPRING / SHAKEOUT
    wick_inferior = df_cerrada['Close'] - df_cerrada['Low']
    cuerpo = abs(df_cerrada['Close'] - df_cerrada['Open'])

    if (df_cerrada['Low'] < df_previa['Low'] and df_cerrada['Close'] > df_cerrada['Open'] and 
        wick_inferior > cuerpo and df_cerrada['Volumen'] > promedio_vol_50 * 2 and contexto_spring['confirmado']):
        patron_liquidez = "Spring / Shakeout Detectado"; intencion = "Acumulación Profesional"

    # FALLO DE BREAKOUT
    elif (df_cerrada['High'] > df_previa['High'] and df_cerrada['Close'] < df_previa['High'] and 
          df_cerrada['Volumen'] > promedio_vol_50 * 1.5 and contexto_breakout['confirmado']):
        patron_liquidez = "Fallo de Breakout en Resistencia"; intencion = "Venta Institucional"
    elif (df_cerrada['Low'] < df_previa['Low'] and df_cerrada['Close'] > df_previa['Low'] and 
          df_cerrada['Volumen'] > promedio_vol_50 * 1.5 and contexto_breakout['confirmado']):
        patron_liquidez = "Fallo de Breakout en Soporte"; intencion = "Compra Institucional"

    return {"Timestamp": df_cerrada['Timestamp'], "Close": df_cerrada['Close'], "Patrón de Liquidez": patron_liquidez, "Intencion": intencion}

def imprimir_resultados(symbol, resultado):
    if resultado['Patrón de Liquidez'] != "Sin Patrón":
        clave_evento = f"{symbol}-{resultado['Patrón de Liquidez']}-{str(resultado['Timestamp'])}"
        if ultimos_patrones_enviados.get(symbol) != clave_evento:
            ultimos_patrones_enviados[symbol] = clave_evento
            guardar_historial(ultimos_patrones_enviados)

            mensaje = (f"🟢 <b>Alerta de Liquidez (Vela Cerrada)</b>\n"
                       f"<b>Par:</b> {symbol}\n"
                       f"<b>Timestamp:</b> {resultado['Timestamp']}\n"
                       f"<b>Close:</b> {resultado['Close']:.2f} USDT\n"
                       f"<b>Patrón:</b> {resultado['Patrón de Liquidez']}\n"
                       f"<b>Intención:</b> {resultado['Intencion']}")
            send_telegram_message(mensaje)

    print(f"📊 {symbol} | {resultado['Timestamp']} | {resultado['Patrón de Liquidez']} | {resultado['Intencion']}")

# ===========================
# 🔹 Ejecución principal
# ===========================
def ejecutar_analisis():
    print(f"--- INICIANDO ANÁLISIS DE VELAS CERRADAS ({time.strftime('%H:%M:%S')}) ---")
    for symbol in pares_liquidos:
        df_global = consolidar_datos(symbol)
        
        if df_global is not None:
            resultado_rt = detectar_patrones_real_time(df_global)
            imprimir_resultados(symbol, resultado_rt)
        else:
            print(f"--- No se pudieron consolidar suficientes datos para {symbol}. Saltando. ---")

def correr_liquidez():
    # Ejecuta el análisis una vez al arrancar
    ejecutar_analisis()
    # Programa el resto
    schedule.every().hour.at(":01").do(ejecutar_analisis)
    while True:
        schedule.run_pending()
        time.sleep(10)

# ESTO VA AQUÍ, FUERA DE LA FUNCIÓN Y SIN ESPACIOS A LA IZQUIERDA:
if __name__ == '__main__':
    print("🚀 MONITOR DE LIQUIDEZ ACTIVADO")
    correr_liquidez()
        
        

