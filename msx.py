import os
import sys
import time
import json
import signal
import threading
import subprocess
import logging
import shutil
from pathlib import Path

# ─────────────────────────────────────────────
#  CONFIGURACIÓN BASADA EN TU ESTRUCTURA
# ─────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.absolute()
SERVER_DIR     = BASE_DIR / "servidor_minecraft"
CONFIG_FILE    = BASE_DIR / "configuracion.json"

# Valores por defecto (se sobreescriben si existen en configuracion.json)
CONFIG = {
    "jar_name": "forge-1.12.2-14.23.5.2860.jar",
    "ram_min": "4G",
    "ram_max": "6G",
    "backup_interval": 1800
}

# Cargar configuracion.json si existe
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE, 'r') as f:
            CONFIG.update(json.load(f))
    except Exception as e:
        print(f"Error cargando configuracion.json: {e}")

# ─────────────────────────────────────────────
#  LOGGING Y ESTILOS
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(BASE_DIR / "manager.log", encoding="utf-8")],
)
log = logging.getLogger(__name__)

C, G, Y, R, B, RS = "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"

def info(m):  print(f"  {C}>{RS} {m}"); log.info(m)
def ok(m):    print(f"  {G}✔{RS}  {m}"); log.info(m)
def warn(m):  print(f"  {Y}⚠{RS}  {m}"); log.warning(m)
def err(m):   print(f"  {R}✖{RS}  {m}"); log.error(m)

# ─────────────────────────────────────────────
#  CONTROL DE PROCESOS
# ─────────────────────────────────────────────
procesos = {"minecraft": None, "playit": None}

def esta_corriendo(nombre):
    proc = procesos.get(nombre)
    return proc is not None and proc.poll() is None

# ─────────────────────────────────────────────
#  GIT & BACKUPS (Desde la raíz del proyecto)
# ─────────────────────────────────────────────
def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=BASE_DIR)

def hacer_backup(etiqueta="manual"):
    info(f"Iniciando backup ({etiqueta})...")
    _git("add", ".")
    fecha = time.strftime("%Y-%m-%d %H:%M:%S")
    res = _git("commit", "-m", f"Backup {etiqueta}: {fecha}")
    
    if "nothing to commit" in res.stdout:
        info("Nada nuevo para respaldar.")
        return

    _git("push", "origin", "main")
    ok(f"Backup '{etiqueta}' completado.")

# ─────────────────────────────────────────────
#  ACCIONES DE ARRANQUE
# ─────────────────────────────────────────────
def run_playit():
    if esta_corriendo("playit"):
        warn("Playit ya está activo.")
        return

    try:
        # Playit suele generar archivos en el directorio donde se ejecuta
        log_file = open(BASE_DIR / "playit.log", "a")
        procesos["playit"] = subprocess.Popen(
            ["playit"], stdout=log_file, stderr=log_file, cwd=BASE_DIR
        )
        ok("Playit iniciado (Ver playit.log).")
    except Exception as e:
        err(f"Error con Playit: {e}")

def run_minecraft():
    if esta_corriendo("minecraft"):
        warn("El servidor ya está abierto.")
        return

    jar_path = SERVER_DIR / CONFIG["jar_name"]
    if not jar_path.exists():
        err(f"No se encuentra el archivo {CONFIG['jar_name']} en {SERVER_DIR}")
        return

    # IMPORTANTE: Ejecutamos el comando DENTRO de la carpeta del servidor
    cmd = [
        "java", 
        f"-Xms{CONFIG['ram_min']}", 
        f"-Xmx{CONFIG['ram_max']}", 
        "-jar", CONFIG["jar_name"], 
        "nogui"
    ]
    
    try:
        info(f"Lanzando {CONFIG['jar_name']}...")
        procesos["minecraft"] = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            cwd=SERVER_DIR  # Esto evita que los mundos se creen en la raíz
        )
        ok("Servidor de Minecraft arrancando.")
    except Exception as e:
        err(f"Error al iniciar Minecraft: {e}")

# ─────────────────────────────────────────────
#  INTERFAZ
# ─────────────────────────────────────────────
def menu():
    os.system("clear")
    print(f"""
  {B}{C}📂 DIRECTORIO:{RS} {BASE_DIR.name}
  {B}{C}╚════════════════════════════════════════╝{RS}
  
  {B}[1]{RS} Iniciar Servidor {f'({G}ONLINE{RS})' if esta_corriendo("minecraft") else f'({R}OFFLINE{RS})'}
  {B}[2]{RS} Iniciar Playit   {f'({G}ONLINE{RS})' if esta_corriendo("playit") else f'({R}OFFLINE{RS})'}
  {B}[3]{RS} Backup Manual
  {B}[4]{RS} Consola Minecraft (Ctrl+C para volver)
  
  {B}[0]{RS} Salir y apagar todo
    """)

def main():
    threading.Thread(target=lambda: (time.sleep(CONFIG["backup_interval"]), hacer_backup("auto")), daemon=True).start()

    while True:
        menu()
        opcion = input(f"  {B}Selección:{RS} ").strip()

        if opcion == "1":
            run_minecraft()
        elif opcion == "2":
            run_playit()
        elif opcion == "3":
            hacer_backup()
        elif opcion == "4":
            if esta_corriendo("minecraft"):
                try: procesos["minecraft"].wait()
                except KeyboardInterrupt: pass
            else:
                err("El servidor no está iniciado.")
        elif opcion == "0":
            if esta_corriendo("minecraft"): procesos["minecraft"].terminate()
            if esta_corriendo("playit"): procesos["playit"].terminate()
            break
        time.sleep(1)

if __name__ == "__main__":
    main()