import os
import sys
import time
import signal
import select
import threading
import subprocess
import glob
import shutil
import logging
from pathlib import Path

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
MEMORIA             = "4G"
CARPETA_SERVER      = "servidor_minecraft"
INTERVALO_BACKUP    = 1800
JAVA_8              = "/usr/lib/jvm/java-8-openjdk-amd64/bin/java"
GIT_BRANCH          = "main"
MAX_REINTENTOS_PUSH = 3

# ─────────────────────────────────────────────
#  LOGGING  →  solo al archivo
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
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
proceso_mc: subprocess.Popen | None = None
_servidor_corriendo = False

# ─────────────────────────────────────────────
#  GIT
# ─────────────────────────────────────────────
def _git(*args, capturar=False):
    kwargs = dict(capture_output=True, text=True) if capturar else dict(
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return subprocess.run(["git", *args], **kwargs)

def setup_git():
    _git("config", "--global", "user.email", "codespace@example.com")
    _git("config", "--global", "user.name",  "Codespace Backup")

def crear_gitignore():
    ignorar = ["# mc_manager", "*.log", "logs/", "crash-reports/",
               "*.tmp", "*.lock", "__pycache__/", "playit.log", "manager.log"]
    ruta = Path(".gitignore")
    actual = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    nuevas = [l for l in ignorar if l not in actual]
    if nuevas:
        with ruta.open("a", encoding="utf-8") as f:
            f.write("\n".join([""] + nuevas) + "\n")

def git_push_retry() -> bool:
    for i in range(1, MAX_REINTENTOS_PUSH + 1):
        res = _git("push", "origin", GIT_BRANCH, capturar=True)
        if res.returncode == 0:
            return True
        warn(f"Push falló (intento {i}/{MAX_REINTENTOS_PUSH}): {res.stderr.strip()}")
        if i < MAX_REINTENTOS_PUSH:
            time.sleep(8)
    return False

def hacer_backup(etiqueta="manual"):
    raiz = Path(__file__).parent.resolve()
    os.chdir(raiz)
    _git("add", ".")
    fecha = time.strftime("%Y-%m-%d %H:%M:%S")
    res = _git("commit", "-m", f"Backup {etiqueta}: {fecha}", capturar=True)
    if res.returncode == 0:
        info("Commit creado. Subiendo a GitHub...")
        if git_push_retry():
            ok("Backup subido correctamente.")
        else:
            err("No se pudo hacer push.")
    else:
        info("Sin cambios nuevos — no se creó commit.")

# ─────────────────────────────────────────────
#  PLAYIT
# ─────────────────────────────────────────────
def run_playit():
    if not shutil.which("playit"):
        warn("'playit' no encontrado en PATH — sin tunnel.")
        return False
    # Matar instancia previa si existe
    subprocess.run(["pkill", "-f", "playit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    with open("playit.log", "w") as lf:
        subprocess.Popen(["playit"], stdout=lf, stderr=lf,
                         start_new_session=True)
    ok("Playit iniciado → playit.log")
    return True

# ─────────────────────────────────────────────
#  BACKUP PERIÓDICO
# ─────────────────────────────────────────────
_stop_backup = threading.Event()

def backup_loop():
    while not _stop_backup.wait(timeout=INTERVALO_BACKUP):
        log.info("Backup periódico...")
        hacer_backup("automático")
        # Regresar a la carpeta del servidor si sigue corriendo
        srv = Path(__file__).parent.resolve() / CARPETA_SERVER
        if srv.exists() and _servidor_corriendo:
            os.chdir(srv)

# ─────────────────────────────────────────────
#  SERVIDOR
# ─────────────────────────────────────────────
def detener_servidor():
    """Envía 'stop' al servidor y espera que cierre."""
    global proceso_mc
    if proceso_mc and proceso_mc.poll() is None:
        try:
            proceso_mc.stdin.write("stop\n")
            proceso_mc.stdin.flush()
            proceso_mc.wait(timeout=60)
        except Exception:
            proceso_mc.terminate()
            proceso_mc.wait()

# Ctrl+C mientras el servidor corre → solo detiene el servidor
def _ctrlc_servidor(sig, frame):
    print(f"\n  {Y}[Ctrl+C detectado]{RS} Deteniendo servidor...", flush=True)
    detener_servidor()

def iniciar_servidor():
    global proceso_mc, _servidor_corriendo

    if not Path(JAVA_8).exists():
        err(f"Java 8 no encontrado: {JAVA_8}")
        err("Instálalo: sudo apt-get install -y openjdk-8-jdk")
        input(f"\n  {Y}Enter para volver al menú...{RS}")
        return

    srv = Path(CARPETA_SERVER)
    if not srv.exists():
        err(f"Carpeta '{CARPETA_SERVER}' no existe.")
        input(f"\n  {Y}Enter para volver al menú...{RS}")
        return

    os.chdir(srv)
    jars = glob.glob("forge*.jar")
    if not jars:
        err("No se encontró 'forge*.jar'")
        os.chdir("..")
        input(f"\n  {Y}Enter para volver al menú...{RS}")
        return

    jar_file = jars[0]
    run_playit()

    # Iniciar hilo de backup periódico
    _stop_backup.clear()
    hilo_backup = threading.Thread(target=backup_loop, daemon=True, name="backup")
    hilo_backup.start()

    _servidor_corriendo = True

    # Registrar Ctrl+C para esta sesión
    signal.signal(signal.SIGINT, _ctrlc_servidor)

    clr()
    print(f"\n  {B}{G}SERVIDOR MINECRAFT{RS}  {C}{jar_file}{RS}")
    print(f"  {Y}Ctrl+C{RS} para detener el servidor\n")
    print("─" * 50, flush=True)

    comando = [
        JAVA_8,
        f"-Xmx{MEMORIA}", f"-Xms{MEMORIA}",
        "-Djava.awt.headless=true",
        "-jar", jar_file, "nogui",
    ]

    proceso_mc = subprocess.Popen(
        comando,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=sys.stdout,
        text=True,
        bufsize=1,
    )

    # Relay stdin → servidor usando select para no bloquear señales
    def relay_stdin():
        fd = sys.stdin.fileno()
        while proceso_mc.poll() is None:
            try:
                r, _, _ = select.select([fd], [], [], 0.2)
                if r:
                    linea = sys.stdin.readline()
                    if not linea:
                        break
                    proceso_mc.stdin.write(linea)
                    proceso_mc.stdin.flush()
            except (OSError, ValueError):
                break

    hilo_stdin = threading.Thread(target=relay_stdin, daemon=True, name="stdin-relay")
    hilo_stdin.start()

    proceso_mc.wait()

    # Servidor cerrado
    _servidor_corriendo = False
    _stop_backup.set()

    raiz = Path(__file__).parent.resolve()
    os.chdir(raiz)

    print("\n" + "─" * 50)
    print(f"\n  {Y}Servidor detenido.{RS} Realizando backup final...\n")
    hacer_backup("FINAL")

    # Restaurar Ctrl+C al comportamiento del menú
    signal.signal(signal.SIGINT, _ctrlc_menu)

    input(f"\n  {G}Enter para volver al menú...{RS}")

# ─────────────────────────────────────────────
#  Ctrl+C en el menú → salir limpio
# ─────────────────────────────────────────────
def _ctrlc_menu(sig, frame):
    clr()
    print(f"\n  {G}👋  ¡Hasta luego!{RS}\n")
    sys.exit(0)

signal.signal(signal.SIGINT, _ctrlc_menu)

# ─────────────────────────────────────────────
#  MENÚ
# ─────────────────────────────────────────────
def dibujar_menu():
    clr()
    print()
    print(f"  {B}{C}╔══════════════════════════════════╗{RS}")
    print(f"  {B}{C}║   🎮  MC Server Manager          ║{RS}")
    print(f"  {B}{C}╚══════════════════════════════════╝{RS}")
    print()
    print(f"  {B}[1]{RS}  Iniciar servidor  {C}(+ Playit){RS}")
    print(f"  {B}[2]{RS}  Hacer backup ahora")
    print(f"  {B}[0]{RS}  Salir")
    print()

def menu_backup():
    clr()
    print(f"\n  {B}── Backup manual ──{RS}\n")
    hacer_backup("manual")
    input(f"\n  {G}Enter para volver al menú...{RS}")

def main_loop():
    setup_git()
    crear_gitignore()

    while True:
        dibujar_menu()
        try:
            opcion = input(f"  Opción: ").strip()
        except (EOFError, KeyboardInterrupt):
            opcion = "0"

        if opcion == "1":
            iniciar_servidor()
        elif opcion == "2":
            menu_backup()
        elif opcion == "0":
            clr()
            print(f"\n  {G}👋  ¡Hasta luego!{RS}\n")
            sys.exit(0)

if __name__ == "__main__":
    main_loop()