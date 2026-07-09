import pandas as pd
import ccxt
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackContext, CommandHandler, CallbackQueryHandler

# ==============================================================================
# 0. CONFIGURACIÓN DE ENTORNO Y EXCHANGES (CCXT FUTUROS)
# ==============================================================================
load_dotenv()
TOKEN_TELEGRAM = os.getenv('TELEGRAM_TOKEN')

EXCHANGES_CONFIG = ['binance', 'bybit', 'bitget', 'okx', 'phemex']
exchanges_conectados = {}

for name in EXCHANGES_CONFIG:
    try:
        # Añadimos 'headers' para simular un navegador
        exchanges_conectados[name] = getattr(ccxt, name)({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        })
    except Exception as e:
        print(f"⚠️ No se pudo inicializar {name}: {e}")

# ==============================================================================
# 1. MOTOR DE CÁLCULO UNIFICADO MULTI-EXCHANGE
# ==============================================================================
def obtener_datos_historicos_unificados(simbolo, timeframe='4h', lookback_velas=18):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    df_final = None

    for name, exchange in exchanges_conectados.items():
        try:
            exchange.load_markets()
            market = exchange.market(symbol_ccxt)
            contract_size = float(market.get('contractSize', 1.0))
            
            ohlcv = exchange.fetch_ohlcv(symbol_ccxt, timeframe=timeframe, limit=lookback_velas)
            if not ohlcv or len(ohlcv) < 2:
                continue
                
            df_temp = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume_Raw'])
            df_temp['Timestamp'] = pd.to_datetime(df_temp['Timestamp'], unit='ms')
            
            df_temp[f'Volume_{name}'] = df_temp['Volume_Raw'] * contract_size * df_temp['Close']
            df_temp = df_temp[['Timestamp', f'Volume_{name}', 'Close']]
            
            if df_final is None:
                df_final = df_temp
            else:
                df_final = pd.merge(df_final, df_temp, on='Timestamp', how='outer')
        except Exception:
            continue

    if df_final is None or df_final.empty:
        return pd.DataFrame()

    df_final.sort_values('Timestamp', inplace=True)
    df_final.drop_duplicates(subset=['Timestamp'], keep='last', inplace=True)

    col_closes = [c for c in df_final.columns if 'Close' in c]
    df_final['Close'] = df_final[col_closes].mean(axis=1)

    col_volumenes = [c for c in df_final.columns if 'Volume_' in c]
    df_final[col_volumenes] = df_final[col_volumenes].fillna(0)
    df_final['Volume'] = df_final[col_volumenes].sum(axis=1)

    df_final['Volatilidad'] = df_final['Close'].pct_change().rolling(window=6).std().fillna(df_final['Close'].pct_change().std())
    df_final.rename(columns={'Timestamp': 'Close time'}, inplace=True)
    return df_final[['Close time', 'Close', 'Volume', 'Volatilidad']].reset_index(drop=True)


def obtener_interes_abierto_actual(simbolo):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    oi_total = 0.0
    con_data = 0

    for name, exchange in exchanges_conectados.items():
        try:
            info = exchange.fetch_open_interest(symbol_ccxt)
            if not info:
                continue
            if isinstance(info, list) and len(info) > 0:
                val = float(info[-1].get('openInterest', 0) or info[-1].get('info', {}).get('openInterest', 0))
            else:
                val = float(info.get('openInterest', 0) or info.get('info', {}).get('openInterest', 0))
            
            if val > 0:
                oi_total += val
                con_data += 1
        except Exception:
            continue
    return oi_total if con_data > 0 else None


def obtener_promedio_interes_abierto_mejorado(simbolo, timeframe='4h'):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    valores_interes = []

    for name, exchange in exchanges_conectados.items():
        try:
            if hasattr(exchange, 'fetch_open_interest_history'):
                hist = exchange.fetch_open_interest_history(symbol_ccxt, timeframe=timeframe, limit=18)
                for entry in hist:
                    val = float(entry.get('openInterest', 0) or entry.get('info', {}).get('sumOpenInterest', 0))
                    if val > 0:
                        valores_interes.append(val)
        except Exception:
            continue

    return sum(valores_interes[-7:-1]) / len(valores_interes[-7:-1]) if len(valores_interes) >= 7 else None


def obtener_funding_rate(simbolo):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    for name in ['binance', 'bybit', 'okx']:
        try:
            exchange = exchanges_conectados.get(name)
            if exchange:
                data = exchange.fetch_funding_rate(symbol_ccxt)
                return float(data['fundingRate'])
        except Exception:
            continue
    return None


def obtener_delta_ordenes(simbolo):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    exchange = exchanges_conectados.get('binance') or exchanges_conectados.get('bybit')
    try:
        book = exchange.fetch_order_book(symbol_ccxt, limit=1000)
        bids = sum(float(order[1]) for order in book["bids"][:500])
        asks = sum(float(order[1]) for order in book["asks"][:500])
        return bids - asks
    except Exception:
        return 0.0


def obtener_order_book(simbolo):
    cripto_base = simbolo.replace('USDT', '')
    symbol_ccxt = f"{cripto_base}/USDT:USDT"
    exchange = exchanges_conectados.get('binance') or exchanges_conectados.get('bybit')
    try:
        book = exchange.fetch_order_book(symbol_ccxt, limit=1000)
        bids = sum(float(order[1]) for order in book["bids"][:100])
        asks = sum(float(order[1]) for order in book["asks"][:100])
        return bids, asks
    except Exception:
        return 0.0, 0.0

# ==============================================================================
# 2. FILTRADO PROFESIONAL Y CLASIFICACIÓN DE FASES RECOBRADA
# ==============================================================================
def determinar_fase_mercado(simbolo, df, precio_actual, interes_actual, promedio_interes, volumen_actual, promedio_volumen, funding_rate, promedio_volatilidad):
    df['Momentum'] = df['Close'].diff(10)  
    df['Cambio_Momentum'] = df['Momentum'].diff(1)  

    if df['Momentum'].iloc[-1] > 0 and df['Cambio_Momentum'].iloc[-1] > 0:
        tendencia_precio = "📈 Subida fuerte"
    elif df['Momentum'].iloc[-1] > 0 and df['Cambio_Momentum'].iloc[-1] < 0:
        tendencia_precio = "⚠️ Subida desacelerando"
    elif df['Momentum'].iloc[-1] < 0 and df['Cambio_Momentum'].iloc[-1] < 0:
        tendencia_precio = "📉 Bajada fuerte"
    else:
        tendencia_precio = "⚠️ Bajada desacelerando"

    tendencia_interes = "📈 Aumento" if interes_actual > promedio_interes else "📉 Disminución"
    tendencia_volumen = "📈 Aumento" if volumen_actual > promedio_volumen else "📉 Disminución"

    delta_ordenes = obtener_delta_ordenes(simbolo)
    bids, asks = obtener_order_book(simbolo)
    if bids is None or asks is None: bids, asks = 0.0, 0.0  

    desalineacion_funding = None
    if funding_rate > 0 and (tendencia_precio == "📉 Bajada fuerte" or tendencia_precio == "⚠️ Bajada desacelerando") and delta_ordenes > 0 and interes_actual > promedio_interes and asks > bids:
        desalineacion_funding = "⚠️ **✅ Absorción institucional basada en presión de órdenes y aumento de interés abierto**"
    elif funding_rate < 0 and (tendencia_precio == "📈 Subida fuerte" or tendencia_precio == "⚠️ Subida desacelerando") and delta_ordenes < 0 and interes_actual > promedio_interes and bids > asks:
        desalineacion_funding = "⚠️ **✅ Manipulación de liquidez basada en presión de órdenes y aumento de interés abierto**"
       
    cambio_interes = ((interes_actual - promedio_interes) / promedio_interes) * 100 if promedio_interes else 0.0
    cambio_volumen = ((volumen_actual - promedio_volumen) / promedio_volumen) * 100 if promedio_volumen else 0.0

    mensaje = f"""
——————————————————————————————————————————————————
🔹 Análisis de Mercado para {simbolo} 4H
🔸 Precio Actual: {precio_actual:.5f} ({tendencia_precio})
🔸 Interés Abierto Actual: {interes_actual:.2f} ({tendencia_interes}, {cambio_interes:.2f}%)
🔸 Volumen Actual: {volumen_actual:.2f} ({tendencia_volumen}, {cambio_volumen:.2f}%)
🔸 Funding Rate: {funding_rate:.5f} ({'🟢 Positivo' if funding_rate > 0 else '🔴 Negativo'})
🔸 Volatilidad Promedio (6 periodos): {promedio_volatilidad:.5f}
"""

    if desalineacion_funding:
        mensaje += f"\n{desalineacion_funding}\n"

    # 1. EXPANSIONES
    if tendencia_precio == "📈 Subida fuerte" and tendencia_interes == "📈 Aumento" and tendencia_volumen == "📈 Aumento":
        mensaje += "\n🔥 **Expansión Alcista**: Fuerte presión compradora, posiciones largas agresivas impulsando la ruptura."
    elif tendencia_precio == "📉 Bajada fuerte" and tendencia_interes == "📈 Aumento" and tendencia_volumen == "📈 Aumento":
        mensaje += "\n🔻 **Expansión Bajista**: Fuerte presión vendedora, posiciones cortas agresivas barriendo las órdenes." 

    # 2. ABSORCIÓN PROFESIONAL (Tu lógica de verdad de mercado corregida)
    elif tendencia_precio == "⚠️ Bajada desacelerando" and tendencia_interes == "📈 Aumento" and tendencia_volumen == "📉 Disminución":
        mensaje += "\n🛡️ **Absorción de Compras (Oferta Seca)**: Los shorts minoristas intentan vender tarde, pero las instituciones están absorbiendo todo con órdenes límite de compra. El piso aguanta."
    elif tendencia_precio == "⚠️ Subida desacelerando" and tendencia_interes == "📈 Aumento" and tendencia_volumen == "📉 Disminución":
        mensaje += "\n⚠️ **Absorción de Ventas (Demanda Seca)**: Los longs rezagados compran tarde, pero las órdenes límite de venta institucionales están bloqueando la subida. Techo fuerte."

    # 3. DISTRIBUCIONES
    elif tendencia_precio == "⚠️ Bajada desacelerando" and tendencia_interes == "📉 Disminución" and tendencia_volumen == "📈 Aumento":
        mensaje += "\n🔻 **Distribución Bajista**: Cierre masivo de posiciones largas (Long Squeeze de stop-loss), debilidad en soporte."
    elif tendencia_precio == "⚠️ Subida desacelerando" and tendencia_interes == "📉 Disminución" and tendencia_volumen == "📈 Aumento":
        mensaje += "\n🔻 **Distribución Alcista**: Cierre masivo de posiciones cortas (Short Squeeze forzado), compras obligadas impulsando el precio momentáneamente."

    # 4. REVERSIONES
    elif tendencia_precio == "⚠️ Bajada desacelerando" and tendencia_interes == "📉 Disminución" and tendencia_volumen == "📉 Disminución":
        mensaje += "\n🔄 **Posible Reversión Alcista**: La caída se queda sin gasolina ni contratos nuevos. Atento a giros si entra volumen comprador."
    elif tendencia_precio == "⚠️ Subida desacelerando" and tendencia_interes == "📉 Disminución" and tendencia_volumen == "📉 Disminución":
        fancy = "\n🔄 **Posible Reversión Bajista**: La subida pierde fuerza y los contratos se cierran. Agotamiento comprador."
        mensaje += fancy
    
    # 5. CONSOLIDACIONES GENERALES
    elif tendencia_volumen == "📉 Disminución" and tendencia_interes == "📈 Aumento":
        mensaje += "\n📊 **Consolidación**: Baja participación en mercado abierto, pero acumulando bloques antes de una ruptura."
    else:
        mensaje += "\n⚖️ **Mercado en Equilibrio**: Sin presión dominante de compradores o vendedores en las órdenes."

    mensaje += "\n——————————————————————————————————————————————————"
    return mensaje.strip()

# ==============================================================================
# 3. INTERFAZ ASÍNCRONA PARA TELEGRAM (MÓDULO DE COMANDO Y GRUPO)
# ==============================================================================
THREAD_ID = 9  # ID del hilo donde el bot debe responder obligatoriamente

async def iniciar(update: Update, context: CallbackContext):
    if update.message.chat.type in ["group", "supergroup"] and update.message.message_thread_id != THREAD_ID:
        return  
    await update.message.reply_text("📝 MAXIMUS PRO MULTI-EXCHANGE\nEscribe el par que deseas analizar (Ejemplo: BTC o BTCUSDT):")

async def analizar_par_telegram(update: Update, context: CallbackContext):
    if update.message.chat.type in ["group", "supergroup"] and update.message.message_thread_id != THREAD_ID:
        return  

    input_usuario = update.message.text.upper().strip()
    
    # Limpieza del string de entrada
    simbolo = input_usuario if 'USDT' in input_usuario else f"{input_usuario}USDT"

    if not re.match(r"^[A-Z0-9-_.]{1,20}$", simbolo):
        await update.message.reply_text(f"❌ El símbolo '{input_usuario}' no contiene un formato de ticker válido.")
        return

    espera_msg = await update.message.reply_text(f"⏳ Analizando flujos unificados agregados para {simbolo}...")

    try:
        # Petición al pool unificado utilizando la ventana estática de 18 velas
        df = obtener_datos_historicos_unificados(simbolo, timeframe='4h', lookback_velas=18)
        
        if df.empty or len(df) < 12:
            await espera_msg.edit_text(f"❌ Error: El par unificado de futuros para {simbolo} no se encuentra disponible o no retornó histórico.")
            return

        precio_actual = df['Close'].iloc[-1]
        volumen_actual = df['Volume'].iloc[-1]
        
        promedio_volumen = df['Volume'].iloc[:-1].tail(6).mean()
        promedio_volatilidad = df['Volatilidad'].iloc[:-1].tail(6).mean()
        
        interes_abierto_actual = obtener_interes_abierto_actual(simbolo)
        promedio_interes_abierto = obtener_promedio_interes_abierto_mejorado(simbolo, timeframe='4h')
        funding_rate = obtener_funding_rate(simbolo)

        # Tratar nulos de exchanges secundarios para no colapsar la respuesta
        if interes_abierto_actual is None or interes_abierto_actual == 0.0:
            try:
                symbol_ccxt_fallback = f"{input_usuario.replace('USDT','')}/USDT:USDT"
                interes_abierto_actual = float(exchanges_conectados['binance'].fetch_open_interest(symbol_ccxt_fallback)['openInterest'])
            except:
                interes_abierto_actual = 1.0

        if promedio_interes_abierto is None or promedio_interes_abierto == 0.0:
            promedio_interes_abierto = interes_abierto_actual

        if funding_rate is None:
            funding_rate = 0.0001

        # Generar diagnóstico real por Order Flow
        resultado_diagnostico = determinar_fase_mercado(
            simbolo, df, precio_actual,
            interes_abierto_actual, promedio_interes_abierto,
            volumen_actual, promedio_volumen,
            funding_rate, promedio_volatilidad
        )

        teclado = [[InlineKeyboardButton("🔄 Analizar otro par", callback_data="analizar_otro")]]
        reply_markup = InlineKeyboardMarkup(teclado)

        # Enviar respuesta final formateada en Markdown
        await espera_msg.delete()
        await update.message.reply_text(f"```text\n{resultado_diagnostico}\n```", parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as e:
        await espera_msg.edit_text(f"❌ Error crítico procesando la consulta en el pool de exchanges: {e}")

async def manejar_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "analizar_otro":
        await query.message.reply_text("📝 Escribe el nuevo par que deseas analizar:")

# ==============================================================================
# 4. ORQUESTADOR DE INICIO DEL BOT (CORREGIDO PARA PYTHON 3.13+)
# ==============================================================================
import asyncio

async def main():
    if not TOKEN_TELEGRAM:
        print("❌ Error crítico: Falta la variable TELEGRAM_TOKEN en el archivo .env")
        return

    print("🤖 Inicializando Bot de Telegram Maximus Pro (Pool Multi-Exchange)...")
    
    # Construimos la aplicación de forma nativa
    app = Application.builder().token(TOKEN_TELEGRAM).build()

    # Registramos tus manejadores exactos
    app.add_handler(CommandHandler("analisis", iniciar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analizar_par_telegram))
    app.add_handler(CallbackQueryHandler(manejar_callback))

    print("🚀 Bot en línea recibiendo peticiones en Telegram. Presiona Ctrl+C para apagar.")
    
    # El bloque 'async with' fuerza la inicialización interna del ExtBot de manera segura
    async with app:
        await app.initialize()
        await app.start()
        # Inicializa y procesa las actualizaciones por polling directamente en el loop activo
        await app.updater.start_polling()
        
        # Mantiene el bot vivo de forma asíncrona hasta recibir un KeyboardInterrupt
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            print("\n🛑 Apagando el bot de forma segura...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

def correr_bot1():
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Bot 1 finalizado.")
        


