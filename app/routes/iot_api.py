"""Recepción HTTPS de mediciones autenticadas procedentes del gateway local.

El Arduino nunca se conecta directamente aquí: el gateway valida primero el
datagrama UDP cifrado y remite únicamente los datos normalizados mediante TLS.
"""

import hmac
import logging

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.services.medicion_service import procesar_medicion

logger = logging.getLogger(__name__)
iot_api_bp = Blueprint("iot_api", __name__, url_prefix="/api/iot")


@iot_api_bp.post("/lecturas")
def recibir_lectura():
    """Actualizar el contenedor existente sin saltarse las reglas de dominio."""
    token_esperado = current_app.config.get("IOT_INGEST_TOKEN", "")
    dispositivo_esperado = current_app.config.get("IOT_INGEST_DEVICE_ID", "")
    if not token_esperado or not dispositivo_esperado or len(token_esperado) < 32:
        return jsonify(error="Integración IoT no configurada."), 503

    cabecera = request.headers.get("Authorization", "")
    if not cabecera.startswith("Bearer "):
        return jsonify(error="No autorizado."), 401
    token_recibido = cabecera.removeprefix("Bearer ")
    if not hmac.compare_digest(token_esperado, token_recibido):
        return jsonify(error="No autorizado."), 401

    if request.content_length is not None and request.content_length > 4096:
        return jsonify(error="Carga demasiado grande."), 413
    if not request.is_json:
        return jsonify(error="Se requiere application/json."), 415
    entrada = request.get_json(silent=True)
    if not isinstance(entrada, dict):
        return jsonify(error="Se requiere un objeto JSON."), 400
    if entrada.get("dispositivo_identificador") != dispositivo_esperado:
        return jsonify(error="Identificador de dispositivo no autorizado."), 403

    # La fuente REAL no depende de un valor controlado por el cliente.
    campos = (
        "sensor1_cm", "sensor2_cm", "modo", "compuerta", "boot", "seq",
        "last_cmd_ctr", "medicion_externa_id", "ip_origen",
    )
    datos = {campo: entrada.get(campo) for campo in campos}
    datos["dispositivo_identificador"] = dispositivo_esperado
    datos["fuente"] = "REAL"

    try:
        medicion = procesar_medicion(datos)
    except ValueError as error:
        # Replay o reenvío repetido: respuesta explícita y sin efectos laterales.
        mensaje = str(error)
        if "duplicada" in mensaje or "replay" in mensaje:
            return jsonify(error="Medición repetida."), 409
        return jsonify(error=mensaje), 422
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("No se pudo persistir una medición IoT.")
        return jsonify(error="Error al guardar la medición."), 503

    return jsonify(
        aceptada=True,
        persistida=medicion.id is not None,
        estado=medicion.estado_calculado,
        porcentaje_llenado=round(medicion.porcentaje_llenado, 1),
    ), 200
