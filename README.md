# R&A QuitaFondo

Aplicación de escritorio para **quitar el fondo de imágenes** con inteligencia artificial, de forma sencilla y sin conocimientos técnicos. Funciona con una interfaz gráfica: eliges una imagen (o una carpeta entera), eliges dónde guardar el resultado y listo.

Usa [rembg](https://github.com/danielgatis/rembg) con el modelo `u2net`, y el procesamiento de tus imágenes se hace **en tu propio equipo**.

## Características

- Quita el fondo de **una imagen** o de **todas las imágenes de una carpeta**.
- Formatos de entrada: `.jpg`, `.jpeg`, `.png` y `.webp`.
- El resultado se guarda como PNG transparente con el sufijo `_sin_fondo` (por ejemplo, `foto_sin_fondo.png`).
- Pantalla de preparación al iniciar: carga la IA en segundo plano para que no esperes en tu primer uso.
- Barra de progreso, tiempo promedio por imagen y tiempo restante estimado.
- Botón **Abrir carpeta** para ver directamente dónde se guardaron los resultados.
- Registro de actividad dentro de la app y en un archivo de log para diagnosticar problemas.

## Descarga

Descarga el ejecutable `QuitaFondo.exe` desde la sección [Releases](../../releases) del repositorio. No necesitas instalar Python.

> **Primer inicio:** la app descarga el modelo de IA (unos cientos de MB), por lo que necesitas conexión a internet y puede tardar varios minutos según tu conexión. Esto solo ocurre una vez; en los siguientes inicios la app arranca lista para usar.

## Uso

1. Abre `QuitaFondo.exe` y espera a que termine la preparación inicial.
2. Elige el modo: **Un archivo** o **Una carpeta**.
3. Selecciona la imagen o carpeta de entrada.
4. Selecciona la carpeta de salida.
5. Pulsa **Quitar fondo**.
6. Cuando termine, usa **Abrir carpeta** para ver los resultados.

## Ejecutar desde el código fuente

Requisitos: Windows y Python 3.10 o superior (Tkinter viene incluido con Python).

```bash
git clone <URL-DEL-REPOSITORIO>
cd <carpeta-del-repositorio>
pip install rembg onnxruntime pillow pymatting
python quitar_fondo.py
```

## Compilar el ejecutable

Con [PyInstaller](https://pyinstaller.org/) instalado (`pip install pyinstaller`):

```bash
pyinstaller --onefile --windowed --icon=pixcut.ico --add-data "pixcut.ico;." --collect-all onnxruntime --collect-all rembg --copy-metadata pymatting --name QuitaFondo quitar_fondo.py
```

El ejecutable queda en `dist/QuitaFondo.exe`.

## Archivos de la aplicación

| Qué | Dónde |
|---|---|
| Modelo de IA descargado | `%USERPROFILE%\.u2net` |
| Log de la aplicación | `%LOCALAPPDATA%\RyA_QuitaFondo\log.txt` |

Si algo falla o la app se queda esperando, el archivo de log indica qué pasó paso a paso.

## Privacidad

- Tus imágenes **no se suben a ningún servidor**: se procesan localmente.
- La app consulta una configuración remota para mostrar el mensaje de bienvenida y el banner de apoyo al proyecto. Si no hay conexión, usa valores locales y funciona igual.
- Para métricas básicas de uso del banner (apertura de la app y clics) puede enviar el identificador de la app y una **región aproximada** calculada a partir de la IP pública. No se envían imágenes ni nombres de archivo.

## Apoya el proyecto

R&A QuitaFondo es gratuita. Si te resulta útil, puedes apoyar el proyecto desde el banner dentro de la app.

## Créditos

- [rembg](https://github.com/danielgatis/rembg) y el modelo [U²-Net](https://github.com/xuebinqin/U-2-Net) para la eliminación de fondos.
- Desarrollado por **Ritmo & Algoritmo**.