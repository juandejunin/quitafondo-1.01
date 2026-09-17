import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from rembg import remove
from PIL import Image

EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".webp")


class QuitarFondoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quitar Fondo de Imágenes")
        self.root.geometry("560x420")
        self.root.resizable(False, False)

        self.carpeta_entrada = tk.StringVar()
        self.carpeta_salida = tk.StringVar()

        self._construir_interfaz()

    def _construir_interfaz(self):
        padding = {"padx": 10, "pady": 6}

        # --- Carpeta de entrada ---
        frame_entrada = tk.Frame(self.root)
        frame_entrada.pack(fill="x", **padding)

        tk.Label(frame_entrada, text="Carpeta de entrada:", width=16, anchor="w").pack(side="left")
        tk.Entry(frame_entrada, textvariable=self.carpeta_entrada).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frame_entrada, text="Elegir...", command=self.elegir_entrada).pack(side="left")

        # --- Carpeta de salida ---
        frame_salida = tk.Frame(self.root)
        frame_salida.pack(fill="x", **padding)

        tk.Label(frame_salida, text="Carpeta de salida:", width=16, anchor="w").pack(side="left")
        tk.Entry(frame_salida, textvariable=self.carpeta_salida).pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(frame_salida, text="Elegir...", command=self.elegir_salida).pack(side="left")

        # --- Botón procesar ---
        self.boton_procesar = tk.Button(
            self.root,
            text="Quitar fondo a todas las imágenes",
            command=self.iniciar_proceso,
            bg="#2e7d32",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            height=2,
        )
        self.boton_procesar.pack(fill="x", padx=10, pady=(10, 6))

        # --- Barra de progreso ---
        self.barra_progreso = ttk.Progressbar(self.root, mode="determinate")
        self.barra_progreso.pack(fill="x", padx=10, pady=(0, 6))

        # --- Log de texto ---
        tk.Label(self.root, text="Registro:", anchor="w").pack(fill="x", padx=10)
        self.log = tk.Text(self.root, height=12, state="disabled", bg="#f5f5f5")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def elegir_entrada(self):
        ruta = filedialog.askdirectory(title="Seleccionar carpeta con imágenes")
        if ruta:
            self.carpeta_entrada.set(ruta)

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
        entrada = self.carpeta_entrada.get().strip()
        salida = self.carpeta_salida.get().strip()

        if not entrada or not os.path.isdir(entrada):
            messagebox.showwarning("Falta carpeta", "Elegí una carpeta de entrada válida.")
            return
        if not salida:
            messagebox.showwarning("Falta carpeta", "Elegí una carpeta de salida válida.")
            return

        os.makedirs(salida, exist_ok=True)

        archivos = [f for f in os.listdir(entrada) if f.lower().endswith(EXTENSIONES_VALIDAS)]
        if not archivos:
            messagebox.showinfo("Sin imágenes", "No se encontraron imágenes en la carpeta elegida.")
            return

        self.boton_procesar.config(state="disabled", text="Procesando...")
        self.barra_progreso.config(maximum=len(archivos), value=0)

        # Procesar en un hilo aparte para no congelar la ventana
        hilo = threading.Thread(target=self._procesar_imagenes, args=(entrada, salida, archivos))
        hilo.start()

    def _procesar_imagenes(self, entrada, salida, archivos):
        for i, nombre in enumerate(archivos, start=1):
            ruta_entrada = os.path.join(entrada, nombre)
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
        self.boton_procesar.config(state="normal", text="Quitar fondo a todas las imágenes")
        messagebox.showinfo("Listo", "¡Se procesaron todas las imágenes!")


if __name__ == "__main__":
    root = tk.Tk()
    app = QuitarFondoApp(root)
    root.mainloop()