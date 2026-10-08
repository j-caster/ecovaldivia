"""Comprobar layouts con Chrome instalado, sin dependencias ni datos reales.

Ejecutar: .venv/Scripts/python.exe tests/visual_check.py
Guarda capturas de escritorio/móvil en instance/visual-hito85b/.
"""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
import json
import mimetypes
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from flask import g
from app.extensions import db
from app.models import DispositivoIoT, EventoOperacional, Usuario
from app.services.medicion_service import procesar_medicion
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


CHECK = """<script>
window.addEventListener('load', () => {
  const resultado = {
    viewport: innerWidth,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    bootstrap: getComputedStyle(document.querySelector('.navbar')).display === 'flex',
    mapFits: !document.getElementById('mapa-publico') || document.getElementById('mapa-publico').getBoundingClientRect().right <= innerWidth
  };
  const boton = document.querySelector('.navbar-toggler');
  if (innerWidth < 992) {
    boton.click();
    setTimeout(() => {
      resultado.navWorks = boton.getAttribute('aria-expanded') === 'true';
      boton.click();
      document.body.setAttribute('data-visual-result', JSON.stringify(resultado));
    }, 450);
  } else document.body.setAttribute('data-visual-result', JSON.stringify(resultado));
});
</script>"""


def snapshots():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        cargar_datos()
        dispositivo = db.session.scalar(db.select(DispositivoIoT))
        for seq in range(3):
            procesar_medicion(dict(dispositivo_identificador=dispositivo.identificador,
                sensor1_cm=25, sensor2_cm=25, modo="AUTO", compuerta="CERRADA",
                fuente="REAL", boot="visual-test", seq=seq,
                fecha_recepcion=datetime.now(timezone.utc)))
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.rol == "administrador"))
        db.session.add(EventoOperacional(contenedor_id=dispositivo.contenedor_id,
            usuario_id=usuario.id, tipo="VACIADO", descripcion="Evento ilustrativo para comprobar el historial.",
            creado_en=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.session.commit()
        cliente = app.test_client()
        paginas = {}
        for nombre, ruta in (("publico", "/"), ("login", "/login")):
            paginas[nombre] = cliente.get(ruta).get_data(as_text=True)
        with cliente.session_transaction() as sesion:
            sesion["_user_id"] = str(usuario.id)
            sesion["_fresh"] = True
        g.pop("_login_user", None)
        for nombre, ruta in (("panel", "/panel"), ("admin", "/admin"),
                             ("alertas", "/operacion/alertas"), ("historial", "/operacion/historial")):
            respuesta = cliente.get(ruta)
            assert respuesta.status_code == 200
            paginas[nombre] = respuesta.get_data(as_text=True)
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
    return {"/" + nombre: contenido.replace("</body>", CHECK + "</body>").encode()
            for nombre, contenido in paginas.items()}


def main():
    browser = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not browser.exists():
        raise SystemExit("Chrome no disponible; comprobar breakpoints manualmente.")
    paginas = snapshots()
    salida = ROOT / "instance" / "visual-hito85b"
    salida.mkdir(parents=True, exist_ok=True)
    static = (ROOT / "app" / "static").resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            ruta = urlparse(self.path).path
            if ruta in paginas:
                cuerpo, mime = paginas[ruta], "text/html; charset=utf-8"
            elif ruta.startswith("/static/"):
                archivo = (static / ruta[len("/static/"):]).resolve()
                if not archivo.is_relative_to(static) or not archivo.is_file():
                    self.send_error(404)
                    return
                cuerpo, mime = archivo.read_bytes(), mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    proceso_browser = subprocess.Popen([str(browser), "--headless", "--disable-gpu",
        "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=9229",
        f"--user-data-dir={salida / 'browser-profile-cdp'}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(2)
        for ancho in (390, 768, 1366, 1920):
            for nombre in ("publico", "login", "panel", "admin", "alertas", "historial"):
                captura = str(salida / f"{nombre}-{ancho}.png") if ancho in (390, 1920) else ""
                proceso = subprocess.run(["node", str(ROOT / "tests/visual_browser.js"), "9229",
                    f"http://127.0.0.1:{server.server_port}/{nombre}", str(ancho), captura],
                    capture_output=True, timeout=40, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW)
                assert proceso.returncode == 0, proceso.stderr
                resultado = json.loads(proceso.stdout)
                assert resultado["viewport"] == ancho, f"Viewport incorrecto: {resultado}"
                assert resultado["bootstrap"], "No carg? Bootstrap desde CDN."
                assert not resultado["overflow"], f"Overflow horizontal: {nombre} {ancho}px"
                assert resultado["mapFits"], "Mapa fuera de pantalla."
                assert resultado.get("navWorks", True), "Navbar m?vil no abre."
                print(f"{nombre} {ancho}px: OK", flush=True)
    finally:
        proceso_browser.terminate()
        proceso_browser.wait(timeout=10)
        server.shutdown()
        server.server_close()
        hilo.join()


if __name__ == "__main__":
    main()
