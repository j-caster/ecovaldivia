"""Alertas sobre estado procesado y registro transaccional de vaciados."""

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Alerta, Contenedor, EventoOperacional, Usuario

ESTADO_TRAS_VACIADO = "Vaciado pendiente de lectura"


def asegurar_alerta_llenado(contenedor, fecha):
    """No confirma transacciones. Punto de extensión para futura confirmación.

    Actualmente EcoValdivia no dispone de una capa independiente de consistencia;
    se utiliza el estado calculado por el servicio, sin añadir otro algoritmo.
    """
    if contenedor.estado != "Lleno":
        return None
    alerta = db.session.scalar(db.select(Alerta).where(
        Alerta.contenedor_id == contenedor.id, Alerta.tipo == "LLENO", Alerta.activa.is_(True)))
    if alerta is None:
        alerta = Alerta(contenedor_id=contenedor.id, tipo="LLENO",
                        mensaje="Contenedor lleno. Requiere vaciado.", activa=True, creada_en=fecha)
        db.session.add(alerta)
    return alerta


def registrar_vaciado(contenedor_id, usuario_id):
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or usuario.rol not in ("operador", "administrador"):
        raise ValueError("El vaciado requiere un operador o administrador activo.")
    contenedor = db.session.get(Contenedor, contenedor_id)
    if contenedor is None:
        raise ValueError("Contenedor inexistente.")
    fecha = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        alertas = db.session.scalars(db.select(Alerta).where(
            Alerta.contenedor_id == contenedor.id, Alerta.tipo == "LLENO", Alerta.activa.is_(True))).all()
        for alerta in alertas:
            alerta.activa = False
            alerta.cerrada_en = fecha
        evento = EventoOperacional(
            contenedor_id=contenedor.id, usuario_id=usuario.id, tipo="VACIADO", creado_en=fecha,
            descripcion=f"Vaciado registrado. Alertas LLENO cerradas: {len(alertas)}. "
                        "Pendiente de nueva lectura física; no se generó una medición.")
        db.session.add(evento)
        contenedor.estado = ESTADO_TRAS_VACIADO
        contenedor.porcentaje_llenado = None
        contenedor.ultima_actualizacion = fecha
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return evento
