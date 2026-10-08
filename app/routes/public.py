from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Material, PuntoReciclaje
from app.services.mapa_publico_service import datos_mapa_publico

public_bp = Blueprint("public", __name__)


def consultar_puntos_publicos():
    """Compartir exactamente el filtro entre HTML y actualización JSON."""
    materiales = db.session.scalars(db.select(Material).order_by(Material.nombre)).all()
    valor = request.args.get("material", "").strip()
    material_id = None
    error_filtro = None
    if valor:
        try:
            material_id = int(valor)
        except ValueError:
            error_filtro = "El material seleccionado no es válido."
        else:
            if material_id not in {material.id for material in materiales}:
                error_filtro = "El material seleccionado no existe."

    consulta = db.select(PuntoReciclaje).where(PuntoReciclaje.activo.is_(True)).options(
        selectinload(PuntoReciclaje.materiales),
        selectinload(PuntoReciclaje.horarios),
        selectinload(PuntoReciclaje.contenedores),
    ).order_by(PuntoReciclaje.nombre)
    if material_id is not None:
        consulta = consulta.where(PuntoReciclaje.materiales.any(Material.id == material_id))
    puntos = [] if error_filtro else db.session.scalars(consulta).all()
    return puntos, materiales, material_id, error_filtro


@public_bp.route("/")
def index():
    puntos, materiales, material_id, error_filtro = consultar_puntos_publicos()
    return render_template(
        "index.html", puntos=puntos, materiales=materiales, puntos_mapa=datos_mapa_publico(puntos),
        material_id=material_id, error_filtro=error_filtro,
        dias_semana=("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"),
    )


@public_bp.get("/public/datos")
def datos():
    puntos, _, _, _ = consultar_puntos_publicos()
    respuesta = jsonify(puntos=datos_mapa_publico(puntos))
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
