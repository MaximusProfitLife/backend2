import os
import subprocess
import sys
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Ecosistema MaximusProftLife Activo"

# Lista de scripts a ejecutar
scripts = [
    "VOL_monitor.py",
    "concentracion_monitor.py",
    "patrones_liquidez_2.py",
    "interes-bot.py"
]

def ejecutar_script(nombre_script):
    """Ejecuta un script de Python como un proceso independiente."""
    print(f"🚀 Lanzando {nombre_script}...")
    subprocess.run([sys.executable, nombre_script])

if __name__ == "__main__":
    print("🚀 INICIANDO ORQUESTADOR DE BOTS...")
    
    # Lanzar cada bot en un hilo separado para que no bloqueen el servidor Flask
    for script in scripts:
        hilo = Thread(target=ejecutar_script, args=(script,), daemon=True)
        hilo.start()
    
    # Iniciar servidor Flask (necesario para mantener el contenedor encendido en Railway/Zeabur)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
