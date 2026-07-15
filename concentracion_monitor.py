import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import os
import time
import asyncio
import json
from datetime import datetime
from telegram import Bot
from dotenv import load_dotenv

# 🔹 Configuración
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN_DONA')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID_GRUPO_VIP')
bot = Bot(token=TELEGRAM_TOKEN)

# 📂 Archivo para persistencia de memoria (Nombre solicitado)
DB_FILE = "concentracion_monitor.json"

def cargar_memoria():
    """Carga los datos del archivo JSON si existe."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_memoria(memoria):
    """Guarda la memoria actual en el archivo JSON."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

# 🔹 MEMORIA INICIAL (Persistente)
memoria_alertas = cargar_memoria()

# 🔹 LISTA DE EXCHANGES
exchanges = {
    'binance': ccxt.binance(),
    'coinbase': ccxt.coinbase(),
    'kraken': ccxt.kraken(),
    'okx': ccxt.okx(),
    'bybit': ccxt.bybit(),
    'bingx': ccxt.bingx(),
    'bitget': ccxt.bitget(),
    'mexc': ccxt.mexc(),
    'gate': ccxt.gate(),
    'kucoin': ccxt.kucoin(),
    'whitebit': ccxt.htx(),
    'coinex': ccxt.htx(),
    'deribit': ccxt.htx(),
    'bitmex': ccxt.htx()
}

symbol = 'BTC/USDT'
timeframes = {'1h': 720, '4h': 720, '1d': 365, '1w': 300}

def generar_grafico_estilo_original(df, tf, top_volumen):
    plt.style.use('dark_background')
    plt.figure(figsize=(14, 6))
    
    plt.plot(df['timestamp'], df['close'], label='Precio de Cierre', color='#3498db', lw=1.5)

    for precio in top_volumen.index:
        plt.axhline(precio, color='red', linestyle='--', alpha=0.6)
        plt.text(df['timestamp'].iloc[-1], precio, f' {precio:.2f}', 
                 color='red', va='center', ha='left', fontsize=9, fontweight='bold')

    # MARCA DE AGUA PROFESIONAL
    plt.gcf().text(0.5, 0.45, "MaximusProftLife", fontsize=60, color='white', 
                    alpha=0.1, ha='center', va='center', rotation=25, weight='bold')

    plt.title(f'{symbol} - {tf} | Zonas de Alta Concentración (Multi-Exchange)', color='yellow')
    plt.xlabel('Tiempo')
    plt.ylabel('Precio')
    plt.grid(True, alpha=0.15)
    plt.tight_layout()
    
    path = f"concentracion_{tf}.png"
    plt.savefig(path, facecolor='#0d1117')
    plt.close()
    return path

async def procesar_analisis():
    global memoria_alertas
    ahora = datetime.now()
    fecha_hoy = ahora.strftime('%Y-%m-%d')

    for tf, limit in timeframes.items():
        temp_data = []
        for name, exchange in exchanges.items():
            try:
                if name == 'coinbase' and tf in ['4h', '1w']: continue
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
                if not ohlcv: continue
                df_temp = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df_temp['timestamp'] = pd.to_datetime(df_temp['timestamp'], unit='ms')
                temp_data.append(df_temp[['timestamp', 'close', 'volume']])
            except: continue

        if temp_data:
            df_combined = pd.concat(temp_data).groupby('timestamp').agg({'close': 'mean', 'volume': 'sum'}).reset_index()
            vol_por_precio = df_combined.groupby('close')['volume'].sum().sort_values(ascending=False)
            top_volumen = vol_por_precio.head(5)
            precio_actual = df_combined['close'].iloc[-1]

            for zona_precio in top_volumen.index:
                if abs(precio_actual - zona_precio) < (precio_actual * 0.004):
                    zona_key = str(round(float(zona_precio), 1)) 
                    ultima_zona = memoria_alertas.get(tf, {}).get('zona')
                    ultima_fecha = memoria_alertas.get(tf, {}).get('fecha')
                    
                    if zona_key != str(ultima_zona) or fecha_hoy != ultima_fecha:
                        memoria_alertas[tf] = {'zona': zona_key, 'fecha': fecha_hoy}
                        guardar_memoria(memoria_alertas)
                        
                        foto_path = generar_grafico_estilo_original(df_combined, tf, top_volumen)
                        msg = (f"🎯 **ZONA DE INTERÉS ALCANZADA ({tf})**\n\n"
                               f"💵 Precio Actual: `{precio_actual:.2f}`\n"
                               f"📊 Punto de Volumen: `{zona_precio:.2f}`\n\n"
                               f"🛰 _Monitor Permanente Maximus_")
                        
                        try:
                            with open(foto_path, 'rb') as f:
                                await bot.send_photo(TELEGRAM_CHAT_ID, f, caption=msg, 
                                                     message_thread_id=9, parse_mode='Markdown')
                            print(f"✅ Alerta Enviada [{tf}]: Zona {zona_key}")
                        finally:
                            if os.path.exists(foto_path): os.remove(foto_path)
                        break
                    else:
                        print(f"😴 {tf} ya alertado para {zona_key} hoy.")
                        break

async def ciclo_principal():
    print(f"🚀 Monitor Maximus iniciado. Memoria física: {DB_FILE}")
    while True:
        await procesar_analisis()
        await asyncio.sleep(900)

# ... (aquí va todo tu código anterior) ...

def correr_concentracion():
    try:
        asyncio.run(ciclo_principal())
    except KeyboardInterrupt:
        print("🛑 Monitor de concentración apagado.")

# ESTO ES LO QUE DEBES PEGAR AL FINAL:
if __name__ == '__main__':
    print("🚀 MONITOR DE CONCENTRACIÓN ACTIVADO")
    correr_concentracion()
