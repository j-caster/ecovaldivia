"""Datos operacionales mínimos, compartidos por HTML y JSON."""

from datetime import datetime, timezone

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Contenedor

UMBRAL_ONLINE_SEGUNDOS = 15
INTERVALO_PANEL_SEGUNDOS = 5


def conectividad(dispositivo, ahora=None):
    if dispositivo is None or dispositivo.ultima_actualizacion is None:
        return "OFFLINE"
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is not None:
        ahora = ahora.astimezone(timezone.utc).replace(tzinfo=None)
    antiguedad = (ahora - dispositivo.ultima_actualizacion).total_seconds()
    return "ONLINE" if antiguedad <= UMBRAL_ONLINE_SEGUNDOS else "OFFLINE"


def datos_panel():
    ahora = datetime.now(timezone.utc)
    contenedores = db.session.scalars(db.select(Contenedor).where(
        Contenedor.activo.is_(True)).options(
        selectinload(Contenedor.punto), selectinload(Contenedor.dispositivos),
        selectinload(Contenedor.alertas)).order_by(Contenedor.codigo)).all()
    resultado = []
    for contenedor in contenedores:
        dispositivo = next((d for d in contenedor.dispositivos if d.activo), None)
        alerta = next((a for a in contenedor.alertas if a.activa), None)
        fecha = contenedor.ultima_actualizacion
        resultado.append(dict(
            codigo=contenedor.codigo, punto=contenedor.punto.nombre,
            porcentaje=contenedor.porcentaje_llenado, estado=contenedor.estado,
            modo=dispositivo.modo_actual if dispositivo else None,
            compuerta=dispositivo.compuerta_actual if dispositivo else None,
            ultima_actualizacion=fecha.isoformat() + "Z" if fecha else None,
            alerta=alerta.mensaje if alerta else None,
            conectividad=conectividad(dispositivo, ahora)))
    return resultado
