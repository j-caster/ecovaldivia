from flask import Blueprint, flash, redirect, render_template, request, url_for, abort
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Alerta, Contenedor, EventoOperacional
from app.services.operacion_service import registrar_vaciado
from app.services.security import roles_required, validar_csrf

operacion_bp = Blueprint("operacion", __name__, url_prefix="/operacion")


@operacion_bp.before_request
@roles_required("operador", "administrador")
def proteger_operacion():
    if request.method == "POST":
        validar_csrf()


@operacion_bp.get("/alertas")
def alertas():
    filtro = request.args.get("estado", "todas")
    if filtro not in ("todas", "activas"):
        abort(400, description="Filtro de alertas inválido.")
    total_activas = db.session.scalar(db.select(db.func.count()).select_from(Alerta).where(Alerta.activa.is_(True)))
    consulta = db.select(Alerta).options(
        joinedload(Alerta.contenedor).joinedload(Contenedor.punto)).order_by(
        Alerta.activa.desc(), Alerta.creada_en.desc(), Alerta.id.desc())
    if filtro == "activas":
        consulta = consulta.where(Alerta.activa.is_(True))
    pagina = db.paginate(consulta, per_page=50)
    contenedores = db.session.scalars(db.select(Contenedor).where(
        Contenedor.activo.is_(True)).order_by(Contenedor.codigo)).all()
    return render_template("operacion/alertas.html", pagina=pagina, contenedores=contenedores,
                           total_activas=total_activas, filtro=filtro)


@operacion_bp.post("/contenedores/<int:contenedor_id>/vaciado")
def vaciado(contenedor_id):
    db.get_or_404(Contenedor, contenedor_id)
    try:
        registrar_vaciado(contenedor_id, current_user.id)
    except ValueError as error:
        flash(str(error), "danger")
    except SQLAlchemyError:
        flash("No se pudo registrar el vaciado. Intenta nuevamente.", "danger")
    else:
        flash("Vaciado registrado. Alertas cerradas; pendiente de nueva lectura.", "success")
    return redirect(url_for("operacion.alertas"))


@operacion_bp.get("/historial")
def historial():
    pagina = db.paginate(db.select(EventoOperacional).options(
        joinedload(EventoOperacional.contenedor), joinedload(EventoOperacional.usuario)).order_by(
        EventoOperacional.creado_en.desc(), EventoOperacional.id.desc()), per_page=50)
    return render_template("operacion/historial.html", pagina=pagina)
