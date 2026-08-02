import os
import subprocess
import sys
import time
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Ecosistema MaximusProftLife Activo"

scripts = [
    "VOL_monitor.py",
    "concentracion_monitor.py",
    "patrones_liquidez_2.py"
]

def ejecutar_script(nombre_script):
    """Supervisor que mantiene el bot vivo reiniciándolo si muere."""
    while True:
        print(f"🚀 Lanzando proceso: {nombre_script}")
        # Popen inicia el bot
        proceso = subprocess.Popen([sys.executable, nombre_script])
        
        # .wait() bloquea este hilo hasta que el script se cierre (crashee o finalice)
        proceso.wait()
        
        print(f"⚠️ El script {nombre_script} se detuvo. Reiniciando en 10 segundos...")
        time.sleep(10) # Espera un poco antes de intentar reabrirlo para no saturar la CPU

if __name__ == "__main__":
    print("🚀 INICIANDO ORQUESTADOR DE BOTS...")
    
    for script in scripts:
        hilo = Thread(target=ejecutar_script, args=(script,), daemon=True)
        hilo.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
