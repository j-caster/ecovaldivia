"""Puente no bloqueante entre el gateway UDP probado y EcoValdivia en Render.

No gestiona UDP ni lee las claves del Arduino. Recibe exclusivamente telemetría
que el servidor Python existente ya autenticó y descifró correctamente.
"""

import json
import os
from queue import Empty, Full, Queue
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def construir_lectura(datos, ip_origen, dispositivo_identificador):
    """Traducir los campos UDP V2.7B al servicio de mediciones de Flask."""
    medicion_externa = datos.get("ID")
    return {
        "dispositivo_identificador": dispositivo_identificador,
        "sensor1_cm": datos.get("S1_CM"),
        "sensor2_cm": datos.get("S2_CM"),
        "modo": datos.get("MODO"),
        "compuerta": datos.get("COMPUERTA"),
        "boot": datos.get("BOOT"),
        "seq": datos.get("SEQ"),
        "last_cmd_ctr": datos.get("LAST_CMD_CTR"),
        "medicion_externa_id": str(medicion_externa) if medicion_externa is not None else None,
        "ip_origen": str(ip_origen),
    }


class RenderBridge:
    def __init__(self):
        self.url = os.environ.get("ECOV_RENDER_INGEST_URL", "").strip()
        self.token = os.environ.get("ECOV_RENDER_INGEST_TOKEN", "").strip()
        self.dispositivo = os.environ.get("ECOV_RENDER_DEVICE_ID", "").strip()
        try:
            self.intervalo = max(1.0, float(os.environ.get("ECOV_RENDER_INTERVALO", "5")))
        except ValueError:
            self.intervalo = 5.0
        self._cola = Queue(maxsize=1)
        self._ultimo_envio = 0.0
        self._activo = False

    def iniciar(self):
        """Habilitar envío solo con configuración completa y transporte seguro."""
        if not any((self.url, self.token, self.dispositivo)):
            print("[RENDER] Integración desactivada; Firebase continúa funcionando.")
            return False
        partes = urlparse(self.url)
        local_http = partes.scheme == "http" and partes.hostname in {"127.0.0.1", "localhost"}
        if not (partes.scheme == "https" or local_http) or not partes.netloc:
            print("[RENDER] Configuración inválida: HTTPS obligatorio fuera de localhost.")
            return False
        if (not self.token or len(self.token) < 32 or not self.dispositivo
                or not self.url.endswith("/api/iot/lecturas")):
            print("[RENDER] Faltan token, dispositivo o endpoint válido; envío desactivado.")
            return False
        self._activo = True
        Thread(target=self._trabajador, daemon=True, name="EcoValdiviaRenderBridge").start()
        print("[RENDER] Puente HTTPS listo; el UDP y Firebase se mantienen independientes.")
        return True

    def encolar(self, datos, ip_origen):
        """No esperar la red: procesar el siguiente paquete UDP inmediatamente."""
        if not self._activo:
            return
        ahora = time.monotonic()
        if ahora - self._ultimo_envio < self.intervalo:
            return
        self._ultimo_envio = ahora
        lectura = construir_lectura(datos, ip_origen, self.dispositivo)
        try:
            if self._cola.full():
                self._cola.get_nowait()
                self._cola.task_done()
        except Empty:
            pass
        try:
            self._cola.put_nowait(lectura)
        except Full:
            pass

    def _trabajador(self):
        while True:
            lectura = self._cola.get()
            try:
                codigo = self._enviar(lectura)
                if codigo == 200:
                    print(f"[RENDER] Medición aceptada (SEQ={lectura.get('seq')}).")
                else:
                    print(f"[RENDER] Respuesta inesperada: HTTP {codigo}.")
            except HTTPError as error:
                if error.code == 409:
                    print("[RENDER] Lectura repetida; el servidor ya la recibió.")
                else:
                    print(f"[RENDER] HTTP {error.code}; revisar configuración o medición.")
            except (URLError, TimeoutError, OSError, ValueError) as error:
                # Evitar mostrar token, URL con parámetros u otros secretos.
                print(f"[RENDER] Error temporal de comunicación ({type(error).__name__}).")
            finally:
                self._cola.task_done()

    def _enviar(self, lectura):
        """Una solicitud HTTPS; separada para pruebas sin conexión externa."""
        peticion = Request(
            self.url,
            data=json.dumps(lectura, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(peticion, timeout=8) as respuesta:
            return respuesta.status
