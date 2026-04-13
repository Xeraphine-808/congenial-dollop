import os
import sys
import time
import signal
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
C  = "\033[36m"   # cyan
G  = "\033[32m"   # verde
Y  = "\033[33m"   # amarillo
R  = "\033[31m"   # rojo
B  = "\033[1m"    # bold
RS = "\033[0m"    # reset

def clr():
    os.system("clear")

def info(msg):
    print(f"  {C}>{RS} {msg}", flush=True)
    log.info(msg)

def ok(msg):
    print(f"  {G}✔{RS}  {msg}", flush=True)
    log.info(msg)

def warn(msg):
    print(f"  {Y}⚠{RS}  {msg}", flush=True)
    log.warning(msg)

def err(msg):
    print(f"  {R}✖{RS}  {msg}", flush=True)
    log.error(msg)

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
proceso_mc: subprocess.Popen | None = None
_apagando = False

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
    ignorar = [
        "# mc_manager", "*.log", "logs/", "crash-reports/",
        "*.tmp", "*.lock", "__pycache__/", "playit.log", "manager.log",
    ]
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
        warn(f"Push falló (intento {i}/{MAX_REINTENTOS_PUSH})")
        if i < MAX_REINTENTOS_PUSH:
            time.sleep(8)
    return False

def hacer_backup(etiqueta="manual") -> bool:
    raiz = Path(__file__).parent.resolve()
    os.chdir(raiz)
    _git("add", ".")
    fecha = time.strftime("%Y-%m-%d %H:%M:%S")
    res = _git("commit", "-m", f"Backup {etiqueta}: {fecha}", capturar=True)
    if res.returncode == 0:
        info(f"Commit creado. Subiendo a GitHub...")
        if git_push_retry():
            ok("Backup subido correctamente.")
            return True
        else:
            err("No se pudo hacer push después de varios intentos.")
            return False
    else:
        info("Sin cambios nuevos — no se creó commit.")
        return True

# ─────────────────────────────────────────────
#  PLAYIT
# ─────────────────────────────────────────────
def run_playit():
    if not shutil.which("playit"):
        warn("'playit' no encontrado en PATH — sin tunnel.")
        return
    info("Iniciando Playit en segundo plano...")
    with open("playit.log", "w") as lf:
        subprocess.Popen(["playit"], stdout=lf, stderr=lf)
    ok("Playit corriendo → playit.log")

# ─────────────────────────────────────────────
#  BACKUP PERIÓDICO (hilo)
# ─────────────────────────────────────────────
def backup_loop():
    while not _apagando:
        time.sleep(INTERVALO_BACKUP)
        if _apagando:
            break
        log.info("Backup periódico automático...")
        hacer_backup("automático")

# ─────────────────────────────────────────────
#  SEÑAL Ctrl+C  →  solo detiene el servidor
# ─────────────────────────────────────────────
def _handler_shutdown(sig, frame):
    global _apagando
    # Si el servidor está corriendo, Ctrl+C lo detiene limpiamente
    if proceso_mc and proceso_mc.poll() is None:
        _apagando = True
        print(f"\n  {Y}[Ctrl+C]{RS} Deteniendo servidor...", flush=True)
        try:
            proceso_mc.stdin.write("stop\n")
            proceso_mc.stdin.flush()
            proceso_mc.wait(timeout=60)
        except Exception:
            proceso_mc.terminate()
    # No llamar sys.exit — dejar que main_loop() retome el menú

signal.signal(signal.SIGINT,  _handler_shutdown)
signal.signal(signal.SIGTERM, _handler_shutdown)

# ─────────────────────────────────────────────
#  SERVIDOR
# ─────────────────────────────────────────────
def iniciar_servidor():
    global proceso_mc, _apagando

    if not Path(JAVA_8).exists():
        err(f"Java 8 no encontrado en: {JAVA_8}")
        err("Instálalo con: sudo apt-get install -y openjdk-8-jdk")
        input(f"\n  {Y}Presiona Enter para volver al menú...{RS}")
        return

    srv = Path(CARPETA_SERVER)
    if not srv.exists():
        err(f"No existe la carpeta '{CARPETA_SERVER}'")
        input(f"\n  {Y}Presiona Enter para volver al menú...{RS}")
        return

    os.chdir(srv)
    jars = glob.glob("forge*.jar")
    if not jars:
        err("No se encontró ningún 'forge*.jar'")
        os.chdir("..")
        input(f"\n  {Y}Presiona Enter para volver al menú...{RS}")
        return

    jar_file = jars[0]

    # Playit
    run_playit()

    # Hilo de backup periódico
    _apagando = False
    hilo_backup = threading.Thread(target=backup_loop, daemon=True, name="backup")
    hilo_backup.start()

    # Limpiar pantalla antes de mostrar la consola de Minecraft
    clr()
    print(f"{B}{'─'*60}{RS}")
    print(f"  {G}{B}SERVIDOR MINECRAFT{RS}  {C}{jar_file}{RS}")
    print(f"  Escribe comandos aquí · Ctrl+C para detener")
    print(f"{B}{'─'*60}{RS}\n")

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
        stderr=sys.stdout,   # stderr también a stdout para no mezclar streams
        text=True,
        bufsize=1,
    )

    # Relay stdin usuario → servidor
    def relay_stdin():
        try:
            for linea in sys.stdin:
                if proceso_mc.poll() is not None:
                    break
                proceso_mc.stdin.write(linea)
                proceso_mc.stdin.flush()
        except (EOFError, OSError):
            pass

    hilo_stdin = threading.Thread(target=relay_stdin, daemon=True, name="stdin-relay")
    hilo_stdin.start()

    proceso_mc.wait()

    # Servidor cerrado → backup final
    _apagando = True
    raiz = Path(__file__).parent.resolve()
    os.chdir(raiz)

    print(f"\n{B}{'─'*60}{RS}")
    print(f"  {Y}Servidor detenido.{RS} Realizando backup final...")
    hacer_backup("FINAL")

    input(f"\n  {G}Presiona Enter para volver al menú...{RS}")

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
    print(f"  {B}[1]{RS}  Iniciar servidor")
    print(f"  {B}[2]{RS}  Hacer backup ahora")
    print(f"  {B}[0]{RS}  Salir")
    print()

def menu_backup():
    clr()
    print(f"\n  {B}── Backup manual ──{RS}\n")
    hacer_backup("manual")
    input(f"\n  {G}Presiona Enter para volver al menú...{RS}")

def main_loop():
    # Configuración inicial silenciosa
    setup_git()
    crear_gitignore()

    while True:
        dibujar_menu()
        try:
            opcion = input(f"  Elige una opción: ").strip()
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
        else:
            pass   # opción inválida → redibujar menú

if __name__ == "__main__":
    main_loop()