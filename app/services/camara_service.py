"""Servicio que expone la cámara en vivo asociada a un punto de reciclaje.

Los navegadores no reproducen RTSP de forma nativa, por lo que este servicio
solo entrega los datos de conexión. La conversión a WebRTC la realiza un
servidor go2rtc local (http://localhost:1984) que el operador mantiene
corriendo; el frontend compone el iframe con el identificador del stream.

Las credenciales RTSP se leen desde variables de entorno (ver .env.example)
y nunca se guardan en el repositorio.
"""

import os

# Punto de demostración que dispone de cámara.
PUNTO_CON_CAMARA = "Demostración — Las Ánimas"

# Identificador del stream configurado en go2rtc.
STREAM_SRC_POR_DEFECTO = "las_animas"

# Origen del servidor de streaming (go2rtc). En local es localhost:1984; en
# producción debe apuntar a una URL pública (túnel/proxy) que alcance go2rtc.
STREAM_HOST_POR_DEFECTO = "http://localhost:1984"


def camara_para_punto(punto):
    """Devuelve los datos de la cámara del punto, o None si no dispone de una.

    `punto` es una instancia de PuntoReciclaje. Solo el punto de demostración
    tiene cámara y únicamente cuando la URL RTSP está configurada en el entorno.
    """
    if punto.nombre != PUNTO_CON_CAMARA:
        return None

    rtsp_url = os.environ.get("ECOV_CAMARA_RTSP_URL")
    if not rtsp_url:
        return None

    return {
        "punto_id": punto.id,
        "nombre": punto.nombre,
        "rtsp_url": rtsp_url,
        "stream_src": os.environ.get(
            "ECOV_CAMARA_STREAM_SRC",
            STREAM_SRC_POR_DEFECTO,
        ),
        "stream_host": os.environ.get(
            "ECOV_CAMARA_STREAM_HOST",
            STREAM_HOST_POR_DEFECTO,
        ).rstrip("/"),
    }
