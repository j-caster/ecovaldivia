"""Descargar las librerías de CDN a app/static/vendor para servirlas localmente.

Uso: python descargar_librerias.py

Solo necesita internet al ejecutarse. Después, la interfaz no depende de CDN:
funciona igual sobre HTTP local y sobre HTTPS en un hosting como Render.
Las teselas del mapa (OpenStreetMap) siguen requiriendo conexión: son datos, no librerías.
"""

import re
from pathlib import Path
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parent
VENDOR = RAIZ / "app" / "static" / "vendor"

BOOTSTRAP = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist"
LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist"
FUENTES_CSS = ("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700"
               "&family=Fraunces:wght@400;600;700&display=swap")
# Sin un agente moderno, Google Fonts devuelve TTF en lugar de WOFF2.
AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

ARCHIVOS = [
    (f"{BOOTSTRAP}/css/bootstrap.min.css", "bootstrap/bootstrap.min.css"),
    (f"{BOOTSTRAP}/js/bootstrap.bundle.min.js", "bootstrap/bootstrap.bundle.min.js"),
    (f"{LEAFLET}/leaflet.css", "leaflet/leaflet.css"),
    (f"{LEAFLET}/leaflet.js", "leaflet/leaflet.js"),
]
ARCHIVOS += [
    (f"{LEAFLET}/images/{nombre}", f"leaflet/images/{nombre}") for nombre in (
        "layers.png", "layers-2x.png", "marker-icon.png", "marker-icon-2x.png",
        "marker-shadow.png")
]


def descargar(url, destino):
    """Guardar una URL en disco y devolver su contenido como texto si es de texto."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    peticion = Request(url, headers={"User-Agent": AGENTE})
    with urlopen(peticion, timeout=60) as respuesta:
        contenido = respuesta.read()
    destino.write_bytes(contenido)
    print(f"  {destino.relative_to(VENDOR)}  ({len(contenido) // 1024} KB)")
    return contenido.decode("utf-8") if destino.suffix == ".css" else ""


def descargar_fuentes():
    """Traer el CSS de Google Fonts y sus WOFF2 para no depender de fonts.googleapis.com."""
    destino_css = VENDOR / "fuentes" / "fuentes.css"
    print("Fuentes web:")
    css = descargar(FUENTES_CSS, destino_css)
    for url in sorted(set(re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", css))):
        nombre = url.rsplit("/", 1)[-1]
        descargar(url, VENDOR / "fuentes" / nombre)
        css = css.replace(url, nombre)
    destino_css.write_text(css, encoding="utf-8")


if __name__ == "__main__":
    print(f"Descargando librerías en {VENDOR} ...")
    for url, relativo in ARCHIVOS:
        descargar(url, VENDOR / relativo)
    descargar_fuentes()
    print("Listo. Las plantillas ya pueden usar static/vendor sin depender de CDN.")
