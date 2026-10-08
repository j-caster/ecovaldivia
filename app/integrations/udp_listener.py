"""Recepción UDP explícita y puente hacia el servicio de mediciones."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
import socket
from threading import Event

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import DispositivoIoT
from app.services.medicion_service import procesar_medicion
from app.integrations.udp_protocol import ErrorProtocolo, cargar_clave, validar_telemetria

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigUDP:
    dispositivo_identificador: str
    clave_hmac: bytes = field(repr=False)
    clave_aead: bytes = field(repr=False)
    host: str = "0.0.0.0"
    puerto: int = 4211

    @classmethod
    def desde_entorno(cls):
        identificador = os.environ.get("ECOV_UDP_DEVICE_ID", "").strip()
        if not identificador or len(identificador) > 100:
            raise ValueError("ECOV_UDP_DEVICE_ID debe identificar un dispositivo registrado.")
        try:
            puerto = int(os.environ.get("ECOV_UDP_PORT", "4211"))
        except ValueError:
            raise ValueError("ECOV_UDP_PORT debe ser un puerto entero válido.") from None
        if not 1 <= puerto <= 65535:
            raise ValueError("ECOV_UDP_PORT debe estar entre 1 y 65535.")
        return cls(identificador,
                   cargar_clave(os.environ.get("ECOV_UDP_HMAC_KEY_HEX"), "ECOV_UDP_HMAC_KEY_HEX"),
                   cargar_clave(os.environ.get("ECOV_UDP_AEAD_KEY_HEX"), "ECOV_UDP_AEAD_KEY_HEX"),
                   os.environ.get("ECOV_UDP_HOST", "0.0.0.0"), puerto)


def procesar_datagrama(paquete, ip_origen, config, fecha_recepcion=None):
    """Requiere app_context; cada datagrama usa estado recién leído de la BD."""
    try:
        dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
            DispositivoIoT.identificador == config.dispositivo_identificador))
        if dispositivo is None:
            logger.warning("Dispositivo desconocido; datagrama descartado.")
            return False
        datos = validar_telemetria(
            paquete, config.clave_hmac, config.clave_aead,
            dispositivo_identificador=dispositivo.identificador,
            ultimo_boot=dispositivo.ultimo_boot, ultimo_seq=dispositivo.ultimo_seq,
            ip_origen=ip_origen, fecha_recepcion=fecha_recepcion)
        medicion = procesar_medicion(datos)
        logger.info("Medición aceptada: persistida=%s seq=%s.", medicion.id is not None, medicion.seq)
        return True
    except ErrorProtocolo as error:
        mensajes = {"hmac": "HMAC inválido", "aead": "TAG/AEAD inválido",
                    "nonce": "Nonce incoherente", "replay": "Medición duplicada/replay rechazada",
                    "fisica": "Error de validación física"}
        logger.warning("%s; datagrama descartado.", mensajes.get(error.codigo, "Protocolo inválido"))
        return False
    except ValueError as error:
        if "duplicada" in str(error):
            logger.warning("Medición duplicada/replay rechazada.")
        else:
            logger.warning("Error de validación física o de dominio; datagrama descartado.")
        return False
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Error de base de datos; medición no guardada.")
        return False
    finally:
        # Descarta instantáneas antiguas y revierte cualquier transacción abierta.
        db.session.remove()


def escuchar(app, config, detener=None):
    detener = detener if detener is not None else Event()
    with app.app_context():
        try:
            dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
                DispositivoIoT.identificador == config.dispositivo_identificador))
            if dispositivo is None:
                logger.error("Dispositivo desconocido; listener no iniciado.")
                raise ValueError("Registra el dispositivo configurado antes de iniciar el worker.")
            logger.info("Dispositivo encontrado: registro=%s.", dispositivo.id)
        finally:
            db.session.remove()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receptor:
        receptor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receptor.settimeout(1.0)
        receptor.bind((config.host, config.puerto))
        logger.info("Listener UDP iniciado en %s:%s.", config.host, config.puerto)
        while not detener.is_set():
            try:
                paquete, direccion = receptor.recvfrom(2048)
            except socket.timeout:
                continue
            fecha = datetime.now(timezone.utc)
            with app.app_context():
                procesar_datagrama(paquete, direccion[0], config, fecha)
    logger.info("Listener UDP detenido.")
