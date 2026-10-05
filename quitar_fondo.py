#!/usr/bin/env python3
"""
QuitaFondo — Interfaz grafica para quitar el fondo de imagenes (rembg)
Con splash publicitario y banner, siguiendo el mismo patron que R&A Downloader
"""

import os
import io
import json
import sys
import time
import ctypes
import logging
import platform
import tempfile
import threading
import webbrowser
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageFile

# Tolerar imagenes truncadas (ej: descarga del banner cortada por conexion lenta)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ── Proteccion para ejecutables empaquetados con --windowed ───────────────────
# Sin consola, sys.stdout/stderr pueden ser None y cualquier print() explota
# con "NoneType object has no attribute 'write'". Esto lo evita.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".webp")

# ── Logging a archivo, independiente de la interfaz ────────────────────────────
# Si la ventana se congela, esto nos permite ver igual qué pasó paso a paso.
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "RyA_QuitaFondo")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "log.txt")

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("quitafondo")


def obtener_ram_total_gb():
    """RAM total del sistema en GB, usando la API de Windows via ctypes (sin dependencias extra)."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        return None


def log_info_hardware():
    """Registra las características del equipo al iniciar, para poder diagnosticar
    después si algo tarda o se cuelga en un equipo puntual."""
    try:
        ram_gb = obtener_ram_total_gb()
        info = (
            f"Sistema: {platform.system()} {platform.release()} ({platform.version()}) | "
            f"CPU: {platform.processor() or 'desconocida'} | "
            f"Núcleos lógicos: {os.cpu_count()} | "
            f"RAM total: {ram_gb if ram_gb is not None else 'desconocida'} GB | "
            f"Python: {platform.python_version()} | "
            f"Ejecutable empaquetado: {getattr(sys, 'frozen', False)}"
        )
        logger.info(info)
        return {"ram_gb": ram_gb, "nucleos": os.cpu_count()}
    except Exception as e:
        logger.info(f"No se pudo obtener info de hardware: {e}")
        return {"ram_gb": None, "nucleos": os.cpu_count()}


def get_app_dir():
    """Carpeta donde vive el script (o el .exe cuando se empaquete con PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """Ruta a un recurso empaquetado (ej: el .ico), tanto en desarrollo como
    dentro del .exe compilado con --onefile (PyInstaller extrae los datos
    agregados con --add-data a una carpeta temporal apuntada por sys._MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# ── Nombre interno de esta app (para diferenciar metricas) ───────────────────
APP_ID = "quitar_fondo"

# ── Configuracion local (fallback si no hay internet) ─────────────────────────
LOCAL_CONFIG = {
    "app": {
        "splash_seconds": 5,
    },
    "splash": {
        "title": "R&A QuitaFondo",
        "text": "Gratis, pero el café no ☕",
        "sub": "Podés ayudar opcionalmente durante el uso de la app",
    },
    "banner": {
        "id": "default",
        "text": "Apoyá el proyecto",
        "text2": "Hacé clic para saber más ▶",
        "url": "",
        "metrics_url": "",
        "show_image": False,
        "image_url": "",
    },
}

CONFIG_URL = "https://juandejunin.github.io/quitar-fondo-ads/config.json"

# ── Colores splash ────────────────────────────────────────────────────────────
COLOR_BG      = "#0a0a0a"
COLOR_MAGENTA = "#cc44cc"
COLOR_WHITE   = "#ffffff"
COLOR_MUTED   = "#888888"
COLOR_BTN_ON  = "#cc44cc"

# ── Colores app principal ─────────────────────────────────────────────────────
BG        = "#1a1a1a"
BG2       = "#242424"
BG3       = "#2e2e2e"
ACCENT    = "#cc44cc"
TEXT      = "#f0f0f0"
TEXT2     = "#999999"
BORDER    = "#3a3a3a"
FONT      = ("Helvetica", 12)
FONT_SM   = ("Helvetica", 10)


def load_config():
    """Carga config remota con fallback local. Mergea seccion por seccion."""
    try:
        with urllib.request.urlopen(CONFIG_URL, timeout=3) as r:
            remote = json.loads(r.read().decode("utf-8"))
        return {
            "app":    {**LOCAL_CONFIG["app"],    **remote.get("app",    {})},
            "splash": {**LOCAL_CONFIG["splash"], **remote.get("splash", {})},
            "banner": {**LOCAL_CONFIG["banner"], **remote.get("banner", {})},
        }
    except Exception as e:
        print(f"DEBUG load_config error: {e}")
        return {k: v.copy() for k, v in LOCAL_CONFIG.items()}


_region_cache = None


def obtener_region_aprox():
    """Pais/region aproximados segun la IP publica (no GPS, no datos exactos).
    Se cachea en memoria para no consultarlo mas de una vez por sesion."""
    global _region_cache
    if _region_cache is not None:
        return _region_cache

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # Intento 1: ipapi.co
    try:
        req = urllib.request.Request("https://ipapi.co/json/", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        pais = data.get("country_name", "")
        region = data.get("region", "")
        if pais or region:
            _region_cache = f"{pais} - {region}".strip(" -")
            return _region_cache
    except Exception as e:
        print(f"DEBUG ipapi.co error: {e}")

    # Intento 2 (respaldo): ipinfo.io
    try:
        req = urllib.request.Request("https://ipinfo.io/json", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        pais = data.get("country", "")
        region = data.get("region", "")
        _region_cache = f"{pais} - {region}".strip(" -")
        return _region_cache
    except Exception as e:
        print(f"DEBUG ipinfo.io error: {e}")

    _region_cache = ""
    return _region_cache


def send_metric(metrics_url, banner_id, event):
    """Envia metrica al servidor en hilo separado. Falla silenciosamente."""
    if not metrics_url:
        return

    def _post():
        try:
            payload = json.dumps({
                "app": APP_ID,
                "banner_id": banner_id,
                "event": event,
                "region": obtener_region_aprox(),
            }).encode("utf-8")
            req = urllib.request.Request(
                metrics_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


def load_banner_image(url, width, height):
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = resp.read()
        from PIL import ImageTk
        img = Image.open(io.BytesIO(data)).convert("RGBA").resize(
            (width, height), Image.LANCZOS
        )
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"DEBUG error cargando imagen de banner: {e}")
        return None


def load_gif_frames(url, size):
    """Descarga un GIF animado y devuelve una lista de (PhotoImage, delay_ms)."""
    if not url:
        return []
    try:
        from PIL import ImageTk
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = resp.read()
        gif = Image.open(io.BytesIO(data))
        frames = []
        try:
            while True:
                delay = gif.info.get("duration", 80)
                frame = gif.copy().convert("RGBA").resize((size, size), Image.LANCZOS)
                frames.append((ImageTk.PhotoImage(frame), delay))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        return frames
    except Exception as e:
        print(f"DEBUG error cargando gif de banner: {e}")
        return []


# ── Splash ────────────────────────────────────────────────────────────────────

def show_splash(root, config, on_close):
    """Muestra el splash como una ventana flotante ENCIMA de la ventana principal,
    que ya está visible en ese momento (ver _mostrar_app_y_splash). El splash ya
    no bloquea la aparición de la app: es solo un overlay temporal.

    Devuelve un dict de referencias (labels + barra de progreso + estado) para
    que, si llega la configuración remota mientras el splash sigue abierto,
    se puedan actualizar sus textos en caliente (ver _aplicar_config_remota)."""
    SPLASH_W = 460
    SPLASH_H = 300

    splash_seconds = config.get("app", {}).get("splash_seconds", 5)
    msg_title = config.get("splash", {}).get("title", "R&A QuitaFondo")
    msg_text  = config.get("splash", {}).get("text", "Gratis, pero el café no ☕")
    msg_sub   = config.get("splash", {}).get("sub", "Podés ayudar opcionalmente durante el uso de la app")

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg=COLOR_BG)
    splash.grab_set()

    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = (sw - SPLASH_W) // 2
    y = (sh - SPLASH_H) // 2
    splash.geometry(f"{SPLASH_W}x{SPLASH_H}+{x}+{y}")

    text_block = tk.Frame(splash, bg=COLOR_BG)
    text_block.place(relx=0.5, rely=0.42, anchor="center")

    title_label = tk.Label(text_block, text=msg_title, bg=COLOR_BG, fg=COLOR_MAGENTA,
              font=("Segoe UI", 24, "bold"), anchor="center")
    title_label.pack(pady=(0, 8))
    text_label = tk.Label(text_block, text=msg_text, bg=COLOR_BG, fg=COLOR_WHITE,
              font=("Segoe UI", 15), anchor="center")
    text_label.pack(pady=(0, 6))
    sub_label = tk.Label(text_block, text=msg_sub, bg=COLOR_BG, fg=COLOR_MUTED,
              font=("Segoe UI", 10), wraplength=380, justify="center",
              anchor="center")
    sub_label.pack(pady=(0, 10))

    # Barra de progreso indeterminada: no mide un avance real (la carga de
    # configuración remota no tiene un "porcentaje"), pero deja claro que algo
    # sigue trabajando en segundo plano en vez de parecer colgado.
    progreso = ttk.Progressbar(text_block, mode="indeterminate", length=260)
    progreso.pack(pady=(0, 4))
    progreso.start(12)

    footer = tk.Frame(splash, bg=COLOR_BG)
    footer.pack(side="bottom", fill="x", pady=10)

    countdown_var = tk.StringVar(value=f"Iniciando en {splash_seconds}...")
    tk.Label(footer, textvariable=countdown_var, bg=COLOR_BG, fg=COLOR_MUTED,
              font=("Segoe UI", 9)).pack(side="left", padx=14)

    estado = {"cerrado": False}

    def close():
        if estado["cerrado"]:
            return
        estado["cerrado"] = True
        progreso.stop()

        def fade(alpha=1.0):
            if alpha <= 0:
                splash.destroy()
                on_close()
            else:
                splash.attributes("-alpha", alpha)
                splash.after(30, fade, alpha - 0.05)
        fade()

    tk.Button(footer, text="Continuar", command=close, bg=COLOR_BTN_ON, fg=COLOR_WHITE,
               relief="flat", padx=18, pady=6, cursor="hand2").pack(side="right", padx=14)

    def tick(t):
        if estado["cerrado"]:
            return
        if t > 0:
            countdown_var.set(f"Iniciando en {t}...")
            splash.after(1000, tick, t - 1)
        else:
            close()

    tick(splash_seconds)

    return {
        "estado": estado,
        "title_label": title_label,
        "text_label": text_label,
        "sub_label": sub_label,
    }


class QuitarFondoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("R&A QuitaFondo — Quitar Fondo de Imágenes")
        self.configure(bg=BG)
        self.resizable(False, False)

        logger.info("=" * 60)
        logger.info("Iniciando R&A QuitaFondo...")
        self._hw_info = log_info_hardware()
        self._session = None  # se crea en el primer uso, ver _obtener_session()

        self.modo = tk.StringVar(value="archivo")
        self.ruta_entrada = tk.StringVar()
        self.carpeta_salida = tk.StringVar()
        self._config = LOCAL_CONFIG.copy()

        self._ico_path = resource_path("pixcut.ico")
        try:
            self.wm_iconbitmap(self._ico_path)
        except Exception as e:
            logger.info(f"iconbitmap error: {e}")

        self._construir_interfaz()
        self._center_window(600, 620)

        # La ventana se muestra YA, con la interfaz completa y funcional —
        # no espera a la configuración remota ni al splash. El splash (si
        # corresponde) aparece encima como un overlay, y la config/banner
        # remotos se completan en segundo plano sin bloquear nada de esto.
        self._mostrar_app_y_splash()

        # La preparación de la IA (import de rembg/onnxruntime + modelo) ya
        # no espera al primer click: arranca sola apenas se ve la ventana,
        # en paralelo con el splash/config. El botón queda deshabilitado y
        # el overlay de preparación visible hasta que esté todo listo.
        self._preparar_ia_en_segundo_plano()

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _mostrar_app_y_splash(self):
        """Arranca el splash de inmediato con la config local (sin esperar red)
        y, en paralelo, dispara la descarga de la config remota en un hilo
        aparte. Antes, todo esto pasaba en secuencia (bajar config → recién
        mostrar splash → recién mostrar la ventana principal), que era la
        causa real de la demora al abrir."""
        self._config = {k: v.copy() for k, v in LOCAL_CONFIG.items()}
        self.banner_label.config(text="Cargando...")
        self.banner_label2.config(text="")

        self._splash_refs = show_splash(self, self._config, on_close=self._al_cerrar_splash)

        threading.Thread(target=self._cargar_config_remota, daemon=True).start()

    def _cargar_config_remota(self):
        config = load_config()
        self.after(0, self._aplicar_config_remota, config)

    def _aplicar_config_remota(self, config):
        self._config = config

        # Si el splash todavía está en pantalla, refrescamos sus textos con
        # los valores remotos (si el usuario ya le dio "Continuar", no hay
        # nada que actualizar ahí y seguimos directo al banner).
        refs = getattr(self, "_splash_refs", None)
        if refs and not refs["estado"]["cerrado"]:
            splash_cfg = config.get("splash", {})
            refs["title_label"].config(text=splash_cfg.get("title", LOCAL_CONFIG["splash"]["title"]))
            refs["text_label"].config(text=splash_cfg.get("text", LOCAL_CONFIG["splash"]["text"]))
            refs["sub_label"].config(text=splash_cfg.get("sub", LOCAL_CONFIG["splash"]["sub"]))

        self._configurar_banner()

    def _al_cerrar_splash(self):
        # El banner ya se configura por su cuenta en cuanto llega la config
        # remota (o con el texto por defecto si todavía no llegó); acá no
        # queda nada bloqueante por hacer.
        pass

    def _configurar_banner(self):
        banner = self._config.get("banner", {})
        text = banner.get("text", LOCAL_CONFIG["banner"]["text"])
        text2 = banner.get("text2", LOCAL_CONFIG["banner"]["text2"])
        url = banner.get("url", "")
        metrics_url = banner.get("metrics_url", "")
        banner_id = banner.get("id", "default")
        show_image = banner.get("show_image", False)
        image_url = banner.get("image_url", "")

        self.banner_label.config(text=text)
        self.banner_label2.config(text=text2)

        def _on_click(e):
            if url:
                send_metric(metrics_url, banner_id, "click")
                webbrowser.open(url)

        widgets = (self.banner_frame, self.banner_label, self.banner_label2)
        for w in widgets:
            w.unbind("<Button-1>")
            w.bind("<Button-1>", _on_click)

        gif_url = self._config.get("splash", {}).get("gif_url", "")

        if gif_url:
            def _load_gif():
                frames = load_gif_frames(gif_url, 70)
                if frames:
                    self.after(0, self._animate_banner_gif, frames)
            threading.Thread(target=_load_gif, daemon=True).start()
        elif show_image and image_url:
            def _load_img():
                img = load_banner_image(image_url, 70, 70)
                if img:
                    self.after(0, self._set_banner_image, img)
            threading.Thread(target=_load_img, daemon=True).start()

        # Con la config local (fallback) metrics_url viene vacío, así que
        # send_metric no hace nada hasta que llegue la config remota real.
        send_metric(metrics_url, banner_id, "app_abierta")

    def _set_banner_image(self, img):
        self.banner_img_label.config(image=img)
        self.banner_img_label.image = img

    def _animate_banner_gif(self, frames, idx=0):
        if not frames or not self.banner_img_label.winfo_exists():
            return
        photo, delay = frames[idx]
        self.banner_img_label.config(image=photo)
        self.banner_img_label.image = photo
        self.after(delay, self._animate_banner_gif, frames, (idx + 1) % len(frames))

    def _construir_interfaz(self):
        padding = {"padx": 20, "pady": 6}

        header = tk.Frame(self, bg=BG, pady=12)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="R&A QuitaFondo", bg=BG, fg=ACCENT,
                  font=("Helvetica", 18, "bold")).pack(side="left")
        tk.Label(header, text="powered by Ritmo & Algoritmo", bg=BG, fg=TEXT2,
                  font=FONT_SM).pack(side="left", padx=10, pady=4)

        frame_modo = tk.Frame(self, bg=BG)
        frame_modo.pack(fill="x", **padding)
        tk.Label(frame_modo, text="¿Qué querés procesar?", bg=BG, fg=TEXT, anchor="w").pack(side="left")
        tk.Radiobutton(frame_modo, text="Un archivo", variable=self.modo, value="archivo",
                        command=self._actualizar_modo, bg=BG, fg=TEXT, selectcolor=BG3,
                        activebackground=BG).pack(side="left", padx=(10, 0))
        tk.Radiobutton(frame_modo, text="Una carpeta", variable=self.modo, value="carpeta",
                        command=self._actualizar_modo, bg=BG, fg=TEXT, selectcolor=BG3,
                        activebackground=BG).pack(side="left")

        frame_entrada = tk.Frame(self, bg=BG)
        frame_entrada.pack(fill="x", **padding)
        self.label_entrada = tk.Label(frame_entrada, text="Imagen:", width=16, anchor="w", bg=BG, fg=TEXT)
        self.label_entrada.pack(side="left")
        tk.Entry(frame_entrada, textvariable=self.ruta_entrada, bg=BG3, fg=TEXT,
                  insertbackground=TEXT, relief="flat").pack(side="left", fill="x", expand=True, padx=5, ipady=4)
        self.boton_entrada = tk.Button(frame_entrada, text="Elegir...", command=self.elegir_entrada)
        self.boton_entrada.pack(side="left")

        frame_salida = tk.Frame(self, bg=BG)
        frame_salida.pack(fill="x", **padding)
        tk.Label(frame_salida, text="Carpeta de salida:", width=16, anchor="w", bg=BG, fg=TEXT).pack(side="left")
        tk.Entry(frame_salida, textvariable=self.carpeta_salida, bg=BG3, fg=TEXT,
                  insertbackground=TEXT, relief="flat").pack(side="left", fill="x", expand=True, padx=5, ipady=4)
        tk.Button(frame_salida, text="Elegir...", command=self.elegir_salida).pack(side="left")
        tk.Button(frame_salida, text="Abrir carpeta", command=self.abrir_carpeta_salida).pack(side="left", padx=(5, 0))

        self.boton_procesar = tk.Button(
            self, text="Preparando IA...", command=self.iniciar_proceso,
            bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"), height=2,
            state="disabled",
        )
        self.boton_procesar.pack(fill="x", padx=20, pady=(10, 6))

        self.barra_progreso = ttk.Progressbar(self, mode="determinate")
        self.barra_progreso.pack(fill="x", padx=20, pady=(0, 2))

        self.label_tiempo = tk.Label(self, text="", bg=BG, fg=TEXT2, font=FONT_SM, anchor="w")
        self.label_tiempo.pack(fill="x", padx=20, pady=(0, 4))

        # --- Banner publicitario ---
        self.banner_frame = tk.Frame(self, bg="#ffffff", cursor="hand2", height=80)
        self.banner_frame.pack(fill="x", padx=20, pady=(4, 6))
        self.banner_frame.pack_propagate(False)

        inner = tk.Frame(self.banner_frame, bg="#ffffff", cursor="hand2")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self.banner_img_label = tk.Label(inner, bg="#ffffff", cursor="hand2")
        self.banner_img_label.pack(side="left", padx=(0, 10))

        text_col = tk.Frame(inner, bg="#ffffff", cursor="hand2")
        text_col.pack(side="left")
        self.banner_label = tk.Label(text_col, text="", bg="#ffffff", fg="#6a0080",
                                       font=("Segoe UI", 11), cursor="hand2",
                                       wraplength=420, justify="left", anchor="w")
        self.banner_label.pack(anchor="w")
        self.banner_label2 = tk.Label(text_col, text="", bg="#ffffff", fg="#9933aa",
                                        font=("Segoe UI", 11), cursor="hand2",
                                        wraplength=420, justify="left", anchor="w")
        self.banner_label2.pack(anchor="w")

        tk.Label(self, text="Registro:", bg=BG, fg=TEXT, anchor="w").pack(fill="x", padx=20)
        self.log = tk.Text(self, height=10, state="disabled", bg="#f5f5f5")
        self.log.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        # --- Overlay de preparación inicial ---
        # Tapa toda la ventana (se crea al final, así queda arriba de todo lo
        # demás) mientras se cargan rembg/onnxruntime y el modelo de IA. Es la
        # "pantalla única" que pedía Juan: aparece sola al abrir la app, y
        # desaparece sola apenas todo está listo para procesar imágenes.
        self.overlay_preparacion = tk.Frame(self, bg=BG)
        self.overlay_preparacion.place(relx=0, rely=0, relwidth=1, relheight=1)

        centro_prep = tk.Frame(self.overlay_preparacion, bg=BG)
        centro_prep.place(relx=0.5, rely=0.42, anchor="center")

        tk.Label(centro_prep, text="Preparando todo por primera vez", bg=BG, fg=ACCENT,
                  font=("Helvetica", 16, "bold")).pack(pady=(0, 12))

        self.label_estado_prep = tk.Label(centro_prep, text="Iniciando...", bg=BG, fg=TEXT,
                                            font=("Helvetica", 13), wraplength=440, justify="center")
        self.label_estado_prep.pack(pady=(0, 16))

        self.progreso_prep = ttk.Progressbar(centro_prep, mode="indeterminate", length=280)
        self.progreso_prep.pack(pady=(0, 16))

        tk.Label(centro_prep,
                  text="Esto solo pasa una vez: si hay que descargar el modelo de IA\n"
                       "puede tardar varios minutos según tu conexión. Las próximas\n"
                       "veces la app arranca lista para usar al instante.",
                  bg=BG, fg=TEXT2, font=("Helvetica", 11), justify="center").pack()

        self.boton_reintentar_prep = tk.Button(
            centro_prep, text="Reintentar", command=self._preparar_ia_en_segundo_plano,
            bg=ACCENT, fg="white", relief="flat", padx=16, pady=6, cursor="hand2",
        )
        # No se muestra hasta que haga falta (ver _preparacion_fallida).

    def _texto_boton(self):
        return "Quitar fondo" if self.modo.get() == "archivo" else "Quitar fondo a todas las imágenes"

    def _preparar_ia_en_segundo_plano(self):
        """Arranca (o reintenta) la carga de rembg/onnxruntime + el modelo de
        IA en un hilo de fondo, apenas se abre la app — ya no se espera al
        primer click de 'Quitar fondo'. Mientras tanto, el overlay de
        preparación tapa la ventana y el botón queda deshabilitado."""
        self.boton_reintentar_prep.pack_forget()
        self.label_estado_prep.config(text="Iniciando...")
        self.progreso_prep.start(12)
        if not self.overlay_preparacion.winfo_ismapped():
            self.overlay_preparacion.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.boton_procesar.config(state="disabled", text="Preparando IA...")

        threading.Thread(target=self._cargar_ia_inicial, daemon=True).start()

    def _cargar_ia_inicial(self):
        try:
            t0 = time.time()
            from rembg import remove  # noqa: F401 (warm-up: deja el módulo cacheado)
            logger.info(f"Import de 'remove' (preparación inicial) listo en {time.time() - t0:.1f}s")
            self._obtener_session()
        except Exception as e:
            logger.exception("Fallo preparando la IA al iniciar")
            self.after(0, self._preparacion_fallida, str(e))
            return
        self.after(0, self._preparacion_lista)

    def _preparacion_lista(self):
        self.progreso_prep.stop()
        self.overlay_preparacion.place_forget()
        self.boton_procesar.config(state="normal", text=self._texto_boton())
        self.escribir_log("✅ IA lista. Ya podés quitar fondos.")

    def _preparacion_fallida(self, mensaje_error):
        self.progreso_prep.stop()
        self.label_estado_prep.config(
            text=f"✘ No se pudo preparar la IA:\n{mensaje_error}\n\n"
                 "Revisá tu conexión a internet y probá de nuevo."
        )
        self.boton_reintentar_prep.pack(pady=(14, 0))
        self.escribir_log(f"✘ ERROR preparando la IA al iniciar: {mensaje_error}")

    def _actualizar_modo(self):
        self.ruta_entrada.set("")
        if self.modo.get() == "archivo":
            self.label_entrada.config(text="Imagen:")
        else:
            self.label_entrada.config(text="Carpeta de entrada:")
        # Si el botón está deshabilitado (preparando IA o procesando), no le
        # pisamos el texto — eso lo maneja quien lo deshabilitó.
        if str(self.boton_procesar["state"]) != "disabled":
            self.boton_procesar.config(text=self._texto_boton())

    def elegir_entrada(self):
        if self.modo.get() == "archivo":
            ruta = filedialog.askopenfilename(
                title="Seleccionar imagen",
                filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.webp")]
            )
        else:
            ruta = filedialog.askdirectory(title="Seleccionar carpeta con imágenes")
        if ruta:
            self.ruta_entrada.set(ruta)

    def elegir_salida(self):
        ruta = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if ruta:
            self.carpeta_salida.set(ruta)

    def abrir_carpeta_salida(self):
        ruta = self.carpeta_salida.get().strip()
        if not ruta or not os.path.isdir(ruta):
            messagebox.showwarning("Carpeta no definida", "Elegí primero una carpeta de salida válida.")
            return
        try:
            os.startfile(ruta)
        except Exception as e:
            logger.exception("Fallo abriendo la carpeta de salida")
            messagebox.showerror("Error", f"No se pudo abrir la carpeta:\n{e}")

    def escribir_log(self, texto):
        """Seguro para llamar desde cualquier hilo: si no estamos en el hilo
        principal de Tkinter, reprograma la actualización real vía self.after
        en vez de tocar el widget directamente (Tkinter no es thread-safe)."""
        logger.info(texto)
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self._escribir_log_ui, texto)
        else:
            self._escribir_log_ui(texto)

    def _escribir_log_ui(self, texto):
        self.log.config(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def iniciar_proceso(self):
        entrada = self.ruta_entrada.get().strip()
        salida = self.carpeta_salida.get().strip()
        modo = self.modo.get()

        if not entrada:
            mensaje = "Elegí una imagen." if modo == "archivo" else "Elegí una carpeta de entrada."
            messagebox.showwarning("Falta selección", mensaje)
            return
        if not salida:
            messagebox.showwarning("Falta carpeta", "Elegí una carpeta de salida válida.")
            return

        os.makedirs(salida, exist_ok=True)

        if modo == "archivo":
            if not os.path.isfile(entrada):
                messagebox.showwarning("Archivo inválido", "El archivo elegido no existe.")
                return
            archivos = [os.path.basename(entrada)]
            carpeta_base = os.path.dirname(entrada)
        else:
            if not os.path.isdir(entrada):
                messagebox.showwarning("Carpeta inválida", "La carpeta elegida no existe.")
                return
            archivos = [f for f in os.listdir(entrada) if f.lower().endswith(EXTENSIONES_VALIDAS)]
            carpeta_base = entrada
            if not archivos:
                messagebox.showinfo("Sin imágenes", "No se encontraron imágenes en la carpeta elegida.")
                return

        self.boton_procesar.config(state="disabled", text="Procesando...")
        self.barra_progreso.config(maximum=len(archivos), value=0)
        self.label_tiempo.config(text="")

        hilo = threading.Thread(target=self._procesar_imagenes, args=(carpeta_base, salida, archivos, modo), daemon=True)
        hilo.start()

    def _obtener_session(self):
        """Crea (o reutiliza) la sesion de rembg. Separado de remove() para poder
        medir y loguear la descarga/carga del modelo por separado de la inferencia.

        El import de rembg (y de onnxruntime, que carga internamente) se hace
        recien aca, no al tope del archivo: es lo que tarda varios segundos en
        cargar sus DLLs, y en un .exe recien compilado ademas el antivirus de
        Windows suele escanear cada DLL la primera vez que se usa. Ahora esto
        arranca solo al abrir la app (ver _preparar_ia_en_segundo_plano), así
        que para cuando el usuario puede tocar 'Quitar fondo' ya está listo."""
        if self._session is not None:
            return self._session

        self._actualizar_estado_preparacion("Cargando librería de IA (rembg)...")
        t_import = time.time()
        from rembg import new_session
        logger.info(f"Import de rembg listo en {time.time() - t_import:.1f}s")

        ya_descargado = os.path.isdir(os.path.join(os.path.expanduser("~"), ".u2net"))
        self._actualizar_estado_preparacion(
            "Descargando modelo de IA (primera vez, puede tardar varios\n"
            "minutos según tu conexión)..."
            if not ya_descargado else
            "Cargando modelo de IA en memoria..."
        )
        t0 = time.time()
        self._session = new_session("u2net")
        logger.info(f"Sesion de rembg lista en {time.time() - t0:.1f}s")
        return self._session

    def _actualizar_estado_preparacion(self, texto):
        """Escribe el mensaje en el registro Y, si el overlay de preparación
        sigue visible, también lo muestra ahí en grande (más visible que una
        línea perdida en el log)."""
        texto_log = texto.replace("\n", " ")
        self.escribir_log(texto_log)

        def _actualizar_label():
            if self.overlay_preparacion.winfo_ismapped():
                self.label_estado_prep.config(text=texto)

        if threading.current_thread() is not threading.main_thread():
            self.after(0, _actualizar_label)
        else:
            _actualizar_label()

    def _actualizar_progreso_ui(self, i, texto_tiempo):
        self.barra_progreso.config(value=i)
        self.label_tiempo.config(text=texto_tiempo)

    def _procesar_imagenes(self, carpeta_base, salida, archivos, modo):
        total = len(archivos)
        self.escribir_log(f"Se van a procesar {total} imagen(es).\n")
        logger.info(f"Núcleos: {self._hw_info.get('nucleos')} | RAM total: {self._hw_info.get('ram_gb')} GB")

        duraciones = []

        # El import de 'remove' (y el de new_session dentro de _obtener_session)
        # van DENTRO de este try/except a propósito: si rembg/onnxruntime no se
        # pudo empaquetar bien en el .exe, antes esto moría en silencio en este
        # hilo de fondo (sin consola, sin log, sin aviso) y la ventana quedaba
        # trabada en "Procesando..." para siempre. Ahora cualquier falla queda
        # registrada y el botón se libera con un mensaje de error.
        try:
            t_import = time.time()
            from rembg import remove
            logger.info(f"Import de 'remove' listo en {time.time() - t_import:.1f}s")
            self._obtener_session()
        except Exception as e:
            self.escribir_log(f"✘ ERROR cargando la IA (rembg/onnxruntime): {e}")
            logger.exception("Fallo al importar rembg o cargar el modelo")
            self.after(0, self._finalizar_proceso, modo)
            self.after(0, lambda: messagebox.showerror("Error", f"No se pudo cargar la IA:\n{e}"))
            return

        for i, nombre in enumerate(archivos, start=1):
            ruta_entrada = os.path.join(carpeta_base, nombre)
            nombre_salida = os.path.splitext(nombre)[0] + "_sin_fondo.png"
            ruta_salida = os.path.join(salida, nombre_salida)

            self.escribir_log(f"[{i}/{total}] {nombre}")
            t_inicio = time.time()

            # Heartbeat: mientras remove() esta trabajando, avisamos cada 10s
            # que seguimos vivos (para diferenciar "lento" de "colgado").
            detener_heartbeat = threading.Event()

            def heartbeat(nombre=nombre, inicio=t_inicio, detener=detener_heartbeat):
                segundos = 10
                while not detener.wait(segundos):
                    transcurrido = time.time() - inicio
                    self.escribir_log(f"    ...sigue procesando {nombre} ({transcurrido:.0f}s transcurridos)")

            hilo_heartbeat = threading.Thread(target=heartbeat, daemon=True)

            try:
                self.escribir_log("  • Abriendo imagen...")
                imagen = Image.open(ruta_entrada)

                self.escribir_log("  • Quitando fondo con IA (puede tardar varios segundos)...")
                hilo_heartbeat.start()
                resultado = remove(imagen, session=self._session)
                detener_heartbeat.set()

                self.escribir_log("  • Guardando resultado...")
                resultado.save(ruta_salida)

                duracion = time.time() - t_inicio
                duraciones.append(duracion)
                self.escribir_log(f"  ✔ Listo: {nombre_salida}  ({duracion:.1f}s)\n")
            except Exception as e:
                detener_heartbeat.set()
                self.escribir_log(f"  ✘ ERROR con {nombre}: {e}\n")
                logger.exception(f"Fallo procesando {nombre}")

            restantes = total - i
            promedio = sum(duraciones) / len(duraciones) if duraciones else 0
            texto_tiempo = f"Promedio: {promedio:.1f}s/imagen · restante estimado: {promedio * restantes:.0f}s" if restantes and promedio else ""
            self.after(0, self._actualizar_progreso_ui, i, texto_tiempo)

        self.escribir_log("✅ Proceso terminado.")
        self.after(0, self._finalizar_proceso, modo)
        self.after(0, lambda: messagebox.showinfo("Listo", "¡Proceso finalizado!"))

    def _finalizar_proceso(self, modo):
        self.boton_procesar.config(state="normal", text=self._texto_boton())


if __name__ == "__main__":
    app = QuitarFondoApp()
    app.mainloop()