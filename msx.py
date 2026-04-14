import os
import sys
import time
import signal
import threading
import subprocess
import logging
import shutil
from pathlib import Path

# ─────────────────────────────────────────────
#  CONFIGURACIÓN (Ajusta esto)
# ─────────────────────────────────────────────
JAR_NAME          = "server.jar"  # Nombre de tu archivo .jar
RAM_INICIAL       = "2G"
RAM_MAXIMA        = "4G"
INTERVALO_BACKUP  = 1800          # 30 minutos
GIT_BRANCH        = "main"
MAX_REINTENTOS_PUSH = 3

# ─────────────────────────────────────────────
#  LOGGING Y ESTILOS
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("manager.log", encoding="utf-8")],
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
#  GIT & BACKUPS
# ─────────────────────────────────────────────
def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)

def setup_git():
    _git("config", "--global", "user.email", "mc-manager@example.com")
    _git("config", "--global", "user.name", "MC Server Manager")

def hacer_backup(etiqueta="manual"):
    if not os.path.exists(".git"):
        err("No hay un repositorio Git inicializado aquí.")
        return

    info(f"Iniciando backup ({etiqueta})...")
    # Si el server está abierto, avisamos por log
    if esta_corriendo("minecraft"):
        warn("El servidor está activo. El backup podría capturar archivos temporales.")

    _git("add", ".")
    fecha = time.strftime("%Y-%m-%d %H:%M:%S")
    res = _git("commit", "-m", f"Backup {etiqueta}: {fecha}")
    
    if "nothing to commit" in res.stdout:
        info("Nada nuevo para respaldar.")
        return

    for i in range(1, MAX_REINTENTOS_PUSH + 1):
        res_push = _git("push", "origin", GIT_BRANCH)
        if res_push.returncode == 0:
            ok(f"Backup '{etiqueta}' subido a GitHub.")
            return
        warn(f"Reintento push {i}/{MAX_REINTENTOS_PUSH}...")
        time.sleep(5)
    err("No se pudo subir el backup tras varios intentos.")

# ─────────────────────────────────────────────
#  ACCIONES DE ARRANQUE
# ─────────────────────────────────────────────
def run_playit():
    if esta_corriendo("playit"):
        warn("Playit ya está en ejecución.")
        return

    if not shutil.which("playit"):
        err("Comando 'playit' no encontrado.")
        return

    try:
        log_file = open("playit.log", "a")
        procesos["playit"] = subprocess.Popen(
            ["playit"], stdout=log_file, stderr=log_file, preexec_fn=os.setpgrp
        )
        ok("Playit iniciado en segundo plano (Log: playit.log).")
    except Exception as e:
        err(f"Error al iniciar Playit: {e}")

def run_minecraft():
    if esta_corriendo("minecraft"):
        warn("El servidor de Minecraft ya está abierto.")
        return

    if not os.path.exists(JAR_NAME):
        err(f"No se encuentra {JAR_NAME}")
        return

    cmd = ["java", f"-Xms{RAM_INICIAL}", f"-Xmx{RAM_MAXIMA}", "-jar", JAR_NAME, "nogui"]
    
    try:
        info("Iniciando Minecraft... (Usa Ctrl+C para volver al menú, el server seguirá vivo)")
        # Iniciamos el proceso
        procesos["minecraft"] = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        # Esperamos un poco para ver si crashea al inicio
        time.sleep(2)
        if esta_corriendo("minecraft"):
            ok("Servidor de Minecraft en línea.")
    except Exception as e:
        err(f"Error al iniciar Minecraft: {e}")

# ─────────────────────────────────────────────
#  HILOS
# ─────────────────────────────────────────────
def backup_loop():
    while True:
        time.sleep(INTERVALO_BACKUP)
        hacer_backup("automático")

# ─────────────────────────────────────────────
#  INTERFAZ
# ─────────────────────────────────────────────
def menu():
    os.system("clear")
    print(f"""
  {B}{C}╔════════════════════════════════════════╗{RS}
  {B}{C}║      ⛏️  MINECRAFT SERVER MANAGER       ║{RS}
  {B}{C}╚════════════════════════════════════════╝{RS}
  
  {B}[1]{RS} Iniciar Servidor Minecraft {f'({G}ONLINE{RS})' if esta_corriendo("minecraft") else f'({R}OFFLINE{RS})'}
  {B}[2]{RS} Iniciar Playit Tunnel      {f'({G}ONLINE{RS})' if esta_corriendo("playit") else f'({R}OFFLINE{RS})'}
  {B}[3]{RS} Realizar Backup Manual
  {B}[4]{RS} Ver Logs de Minecraft (Escribir comandos)
  
  {B}[0]{RS} Salir y apagar todo
    """)

def main():
    setup_git()
    threading.Thread(target=backup_loop, daemon=True).start()

    while True:
        menu()
        opcion = input(f"  {B}Selecciona una opción:{RS} ").strip()

        if opcion == "1":
            run_minecraft()
        elif opcion == "2":
            run_playit()
        elif opcion == "3":
            hacer_backup("manual")
        elif opcion == "4":
            if esta_corriendo("minecraft"):
                info("Entrando a la consola. Para salir al menú usa Ctrl+C.")
                try:
                    procesos["minecraft"].wait()
                except KeyboardInterrupt:
                    info("Regresando al menú... (El servidor sigue activo)")
            else:
                err("El servidor no está corriendo.")
        elif opcion == "0":
            confirmar = input(f"  {Y}¿Apagar servidor y salir? (s/n):{RS} ")
            if confirmar.lower() == 's':
                if esta_corriendo("minecraft"):
                    info("Cerrando Minecraft de forma segura...")
                    procesos["minecraft"].terminate()
                if esta_corriendo("playit"):
                    procesos["playit"].terminate()
                sys.exit(0)
        
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)