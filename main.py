import os
import interes_bot
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Ecosistema de Análisis de Interés Abierto Activo"

def arrancar_interes_bot():
    # Lanzamos el motor de interés que es asíncrono
    interes_bot.correr_bot1()

if __name__ == "__main__":
    print("🚀 INICIANDO BOT DE ANÁLISIS DE FLUJO DE ÓRDENES...")
    
    # Lanzar el hilo del bot
    hilo_bot = threading.Thread(target=arrancar_interes_bot, daemon=True)
    hilo_bot.start()
    
    # Iniciar servidor Flask para Zeabur
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
