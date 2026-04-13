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
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
INTERVALO_BACKUP    = 1800  # 30 minutos
GIT_BRANCH          = "main"
MAX_REINTENTOS_PUSH = 3

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("manager.log", encoding="utf-8")],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  COLORES ANSI
# ─────────────────────────────────────────────
C  = "\033[36m"
G  = "\033[32m"
Y  = "\033[33m"
R  = "\033[31m"
B  = "\033[1m"
RS = "\033[0m"

def clr():    os.system("clear")
def info(m):  print(f"  {C}>{RS} {m}", flush=True);  log.info(m)
def ok(m):    print(f"  {G}✔{RS}  {m}", flush=True); log.info(m)
def warn(m):  print(f"  {Y}⚠{RS}  {m}", flush=True); log.warning(m)
def err(m):   print(f"  {R}✖{RS}  {m}", flush=True); log.error(m)

# ─────────────────────────────────────────────
#  GIT & BACKUPS
# ─────────────────────────────────────────────
def _git(*args, capturar=False):
    kwargs = dict(capture_output=True, text=True) if capturar else dict(
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return subprocess.run(["git", *args], **kwargs)

def setup_git():
    _git("config", "--global", "user.email", "codespace@example.com")
    _git("config", "--global", "user.name",  "Codespace Backup")

def git_push_retry() -> bool:
    for i in range(1, MAX_REINTENTOS_PUSH + 1):
        res = _git("push", "origin", GIT_BRANCH, capturar=True)
        if res.returncode == 0:
            return True
        warn(f"Push falló (intento {i}/{MAX_REINTENTOS_PUSH})")
        if i < MAX_REINTENTOS_PUSH:
            time.sleep(5)
    return False

def hacer_backup(etiqueta="manual"):
    info(f"Iniciando backup ({etiqueta})...")
    _git("add", ".")
    fecha = time.strftime("%Y-%m-%d %H:%M:%S")
    res = _git("commit", "-m", f"Backup {etiqueta}: {fecha}", capturar=True)
    if res.returncode == 0:
        if git_push_retry():
            ok(f"Backup '{etiqueta}' completado con éxito.")
        else:
            err("Error al subir el backup a GitHub.")
    else:
        info("Nada nuevo para respaldar.")

# ─────────────────────────────────────────────
#  PLAYIT
# ─────────────────────────────────────────────
def run_playit():
    if not shutil.which("playit"):
        err("'playit' no instalado. Instálalo primero.")
        return
    
    # Matar procesos previos
    subprocess.run(["pkill", "-f", "playit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        with open("playit.log", "w") as lf:
            subprocess.Popen(["playit"], stdout=lf, stderr=lf, start_new_session=True)
        ok("Servicio Playit activado (Segundo plano).")
    except Exception as e:
        err(f"No se pudo iniciar Playit: {e}")

# ─────────────────────────────────────────────
#  HILO DE BACKUP AUTOMÁTICO
# ─────────────────────────────────────────────
def backup_loop():
    while True:
        time.sleep(INTERVALO_BACKUP)
        hacer_backup("automático")

# ─────────────────────────────────────────────
#  MENÚ PRINCIPAL
# ─────────────────────────────────────────────
def dibujar_menu():
    clr()
    print()
    print(f"  {B}{C}╔══════════════════════════════════╗{RS}")
    print(f"  {B}{C}║    🛠️  Utility Manager MC        ║{RS}")
    print(f"  {B}{C}╚══════════════════════════════════╝{RS}")
    print()
    print(f"  {B}[1]{RS}  Activar Playit")
    print(f"  {B}[2]{RS}  Realizar Backup Manual")
    print(f"  {B}[0]{RS}  Salir")
    print()

def _ctrlc_handler(sig, frame):
    print(f"\n\n  {G}👋 Saliendo de forma segura...{RS}\n")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, _ctrlc_handler)
    setup_git()
    
    # Iniciar backup automático en segundo plano
    hilo_auto = threading.Thread(target=backup_loop, daemon=True)
    hilo_auto.start()

    while True:
        dibujar_menu()
        try:
            opcion = input(f"  Opción: ").strip()
        except (EOFError, KeyboardInterrupt):
            _ctrlc_handler(None, None)

        if opcion == "1":
            run_playit()
            input(f"\n  {Y}Presiona Enter para continuar...{RS}")
        elif opcion == "2":
            hacer_backup("manual")
            input(f"\n  {Y}Presiona Enter para continuar...{RS}")
        elif opcion == "0":
            _ctrlc_handler(None, None)

if __name__ == "__main__":
    main()