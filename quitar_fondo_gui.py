#!/usr/bin/env python3
"""
QuitaFondo — Interfaz grafica para quitar el fondo de imagenes (rembg)
Con splash publicitario y banner, siguiendo el mismo patron que R&A Downloader
"""

import os
import io
import json
import sys
import threading
import webbrowser
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from rembg import remove
from PIL import Image

EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".webp")


def get_app_dir():
    """Carpeta donde vive el script (o el .exe cuando se empaquete con PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

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
    SPLASH_W = 460
    SPLASH_H = 280

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
    text_block.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(text_block, text=msg_title, bg=COLOR_BG, fg=COLOR_MAGENTA,
              font=("Segoe UI", 24, "bold"), anchor="center").pack(pady=(0, 8))
    tk.Label(text_block, text=msg_text, bg=COLOR_BG, fg=COLOR_WHITE,
              font=("Segoe UI", 15), anchor="center").pack(pady=(0, 6))
    tk.Label(text_block, text=msg_sub, bg=COLOR_BG, fg=COLOR_MUTED,
              font=("Segoe UI", 10), wraplength=380, justify="center",
              anchor="center").pack()

    footer = tk.Frame(splash, bg=COLOR_BG)
    footer.pack(side="bottom", fill="x", pady=10)

    countdown_var = tk.StringVar(value=f"Iniciando en {splash_seconds}...")
    tk.Label(footer, textvariable=countdown_var, bg=COLOR_BG, fg=COLOR_MUTED,
              font=("Segoe UI", 9)).pack(side="left", padx=14)

    def close():
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
        if t > 0:
            countdown_var.set(f"Iniciando en {t}...")
            splash.after(1000, tick, t - 1)
        else:
            close()

    tick(splash_seconds)


class QuitarFondoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("R&A QuitaFondo — Quitar Fondo de Imágenes")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.modo = tk.StringVar(value="archivo")
        self.ruta_entrada = tk.StringVar()
        self.carpeta_salida = tk.StringVar()
        self._config = LOCAL_CONFIG.copy()

        self._ico_path = os.path.join(get_app_dir(), "pixcut.ico")
        try:
            self.wm_iconbitmap(self._ico_path)
        except Exception as e:
            print(f"DEBUG iconbitmap error: {e}")

        self.attributes("-alpha", 0.0)
        self.withdraw()

        self._construir_interfaz()
        self._center_window(600, 620)

        threading.Thread(target=self._load_config_and_splash, daemon=True).start()

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _load_config_and_splash(self):
        config = load_config()
        self.after(0, self._show_splash, config)

    def _show_splash(self, config):
        self._config = config
        show_splash(self, config, on_close=self._after_splash)

    def _after_splash(self):
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

        send_metric(metrics_url, banner_id, "app_abierta")

        self.attributes("-alpha", 0.0)
        self.deiconify()

        def fade_in(alpha=0.0):
            if alpha >= 1.0:
                self.attributes("-alpha", 1.0)
            else:
                self.attributes("-alpha", alpha)
                self.after(20, fade_in, alpha + 0.05)
        fade_in()

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

        self.boton_procesar = tk.Button(
            self, text="Quitar fondo", command=self.iniciar_proceso,
            bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"), height=2,
        )
        self.boton_procesar.pack(fill="x", padx=20, pady=(10, 6))

        self.barra_progreso = ttk.Progressbar(self, mode="determinate")
        self.barra_progreso.pack(fill="x", padx=20, pady=(0, 6))

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

    def _actualizar_modo(self):
        self.ruta_entrada.set("")
        if self.modo.get() == "archivo":
            self.label_entrada.config(text="Imagen:")
            self.boton_procesar.config(text="Quitar fondo")
        else:
            self.label_entrada.config(text="Carpeta de entrada:")
            self.boton_procesar.config(text="Quitar fondo a todas las imágenes")

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

    def escribir_log(self, texto):
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

        hilo = threading.Thread(target=self._procesar_imagenes, args=(carpeta_base, salida, archivos, modo))
        hilo.start()

    def _procesar_imagenes(self, carpeta_base, salida, archivos, modo):
        for i, nombre in enumerate(archivos, start=1):
            ruta_entrada = os.path.join(carpeta_base, nombre)
            nombre_salida = os.path.splitext(nombre)[0] + "_sin_fondo.png"
            ruta_salida = os.path.join(salida, nombre_salida)

            self.escribir_log(f"Procesando: {nombre}...")
            try:
                imagen = Image.open(ruta_entrada)
                resultado = remove(imagen)
                resultado.save(ruta_salida)
                self.escribir_log(f"  -> Guardado: {nombre_salida}")
            except Exception as e:
                self.escribir_log(f"  -> ERROR con {nombre}: {e}")

            self.barra_progreso.config(value=i)

        self.escribir_log("\n✅ Proceso terminado.")
        texto_boton = "Quitar fondo" if modo == "archivo" else "Quitar fondo a todas las imágenes"
        self.boton_procesar.config(state="normal", text=texto_boton)
        messagebox.showinfo("Listo", "¡Proceso finalizado!")


if __name__ == "__main__":
    app = QuitarFondoApp()
    app.mainloop()