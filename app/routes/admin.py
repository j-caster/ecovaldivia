from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import Horario, Material, PuntoMaterial, PuntoReciclaje
from app.services.admin_validation import validar_horario, validar_horarios_creacion, validar_material, validar_punto
from app.services.security import roles_required, validar_csrf

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


@admin_bp.before_request
@roles_required("administrador")
def proteger_admin():
    if request.method == "POST":
        validar_csrf()


def guardar(mensaje):
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Operación no permitida: registro duplicado o relación inválida.", "danger")
        return False
    except SQLAlchemyError:
        db.session.rollback()
        flash("No se pudo guardar la operación. Intenta nuevamente.", "danger")
        return False
    flash(mensaje, "success")
    return True


@admin_bp.get("")
@admin_bp.get("/")
def index():
    return render_template("admin.html")


@admin_bp.get("/puntos")
def puntos():
    registros = db.session.scalars(db.select(PuntoReciclaje).order_by(PuntoReciclaje.nombre)).all()
    return render_template("admin/puntos/lista.html", puntos=registros)


@admin_bp.route("/puntos/nuevo", methods=["GET", "POST"])
@admin_bp.route("/puntos/<int:punto_id>/editar", methods=["GET", "POST"])
def punto_formulario(punto_id=None):
    punto = db.get_or_404(PuntoReciclaje, punto_id) if punto_id else None
    if request.method == "POST":
        datos = request.form
        try:
            valores = validar_punto(datos)
        except ValueError as error:
            flash(str(error), "danger")
        else:
            nuevo = punto is None
            if nuevo:
                punto = PuntoReciclaje()
                db.session.add(punto)
            for campo, valor in valores.items():
                setattr(punto, campo, valor)
            if guardar("Punto creado." if nuevo else "Punto modificado."):
                return redirect(url_for("admin.punto_formulario", punto_id=punto.id))
    else:
        datos = {campo: getattr(punto, campo) for campo in ("nombre", "direccion", "latitud", "longitud")} if punto else {}
        datos["activo"] = "1" if punto is None or punto.activo else ""
    materiales = db.session.scalars(db.select(Material).order_by(Material.nombre)).all()
    return render_template("admin/puntos/formulario.html", punto=punto, datos=datos, materiales=materiales, dias=DIAS)


@admin_bp.post("/puntos/<int:punto_id>/estado")
def punto_estado(punto_id):
    punto = db.get_or_404(PuntoReciclaje, punto_id)
    punto.activo = not punto.activo
    guardar("Punto activado." if punto.activo else "Punto desactivado.")
    return redirect(url_for("admin.puntos"))


@admin_bp.get("/materiales")
def materiales():
    registros = db.session.scalars(db.select(Material).order_by(Material.nombre)).all()
    return render_template("admin/materiales/lista.html", materiales=registros)


@admin_bp.route("/materiales/nuevo", methods=["GET", "POST"])
@admin_bp.route("/materiales/<int:material_id>/editar", methods=["GET", "POST"])
def material_formulario(material_id=None):
    material = db.get_or_404(Material, material_id) if material_id else None
    if request.method == "POST":
        datos = request.form
        try:
            valores = validar_material(datos)
        except ValueError as error:
            flash(str(error), "danger")
        else:
            consulta = db.select(Material).where(Material.nombre == valores["nombre"])
            if material:
                consulta = consulta.where(Material.id != material.id)
            if db.session.scalar(consulta):
                flash("Ya existe un material con ese nombre.", "danger")
            else:
                nuevo = material is None
                if nuevo:
                    material = Material()
                    db.session.add(material)
                for campo, valor in valores.items():
                    setattr(material, campo, valor)
                if guardar("Material creado." if nuevo else "Material modificado."):
                    return redirect(url_for("admin.materiales"))
    else:
        datos = {"nombre": material.nombre, "instrucciones": material.instrucciones or ""} if material else {}
    return render_template("admin/materiales/formulario.html", material=material, datos=datos)


@admin_bp.post("/puntos/<int:punto_id>/materiales")
def asociar_material(punto_id):
    db.get_or_404(PuntoReciclaje, punto_id)
    material_id = request.form.get("material_id", type=int)
    if material_id is None or db.session.get(Material, material_id) is None:
        flash("Selecciona un material válido.", "danger")
    elif db.session.get(PuntoMaterial, (punto_id, material_id)):
        flash("El material ya está asociado al punto.", "warning")
    else:
        db.session.add(PuntoMaterial(punto_id=punto_id, material_id=material_id))
        guardar("Material asociado al punto.")
    return redirect(url_for("admin.punto_formulario", punto_id=punto_id))


@admin_bp.post("/puntos/<int:punto_id>/materiales/<int:material_id>/quitar")
def quitar_material(punto_id, material_id):
    db.get_or_404(PuntoReciclaje, punto_id)
    asociacion = db.get_or_404(PuntoMaterial, (punto_id, material_id))
    db.session.delete(asociacion)
    guardar("Asociación quitada; el material se conserva.")
    return redirect(url_for("admin.punto_formulario", punto_id=punto_id))


@admin_bp.route("/puntos/<int:punto_id>/horarios/nuevo", methods=["GET", "POST"])
@admin_bp.route("/puntos/<int:punto_id>/horarios/<int:horario_id>/editar", methods=["GET", "POST"])
def horario_formulario(punto_id, horario_id=None):
    punto = db.get_or_404(PuntoReciclaje, punto_id)
    horario = db.first_or_404(db.select(Horario).where(Horario.id == horario_id, Horario.punto_id == punto_id)) if horario_id else None
    if request.method == "POST":
        datos = request.form
        try:
            valores = [validar_horario(datos)] if horario else validar_horarios_creacion(datos)
        except ValueError as error:
            flash(str(error), "danger")
        else:
            existentes = db.session.scalars(db.select(Horario).where(Horario.punto_id == punto_id)).all()
            claves = {(h.dia_semana, h.hora_inicio, h.hora_fin) for h in existentes if h is not horario}
            if horario:
                valor = valores[0]
                if (valor["dia_semana"], valor["hora_inicio"], valor["hora_fin"]) in claves:
                    flash("Ya existe un horario idéntico para este punto y día.", "warning")
                else:
                    for campo, valor_campo in valor.items():
                        setattr(horario, campo, valor_campo)
                    if guardar("Horario modificado."):
                        return redirect(url_for("admin.punto_formulario", punto_id=punto_id))
            else:
                nuevos = [valor for valor in valores if (valor["dia_semana"], valor["hora_inicio"], valor["hora_fin"]) not in claves]
                omitidos = len(valores) - len(nuevos)
                if nuevos:
                    db.session.add_all([Horario(punto_id=punto_id, **valor) for valor in nuevos])
                    if guardar(f"Horarios creados: {len(nuevos)}. Duplicados omitidos: {omitidos}."):
                        return redirect(url_for("admin.punto_formulario", punto_id=punto_id))
                else:
                    flash("No se crearon horarios: todos los seleccionados ya existen.", "warning")
    else:
        datos = {"dia_semana": str(horario.dia_semana), "hora_inicio": horario.hora_inicio.isoformat(), "hora_fin": horario.hora_fin.isoformat()} if horario else {}
    dias_seleccionados = request.form.getlist("dia_semana") if request.method == "POST" else []
    return render_template("admin/horarios/formulario.html", punto=punto, horario=horario, datos=datos, dias=DIAS, dias_seleccionados=dias_seleccionados)


@admin_bp.post("/puntos/<int:punto_id>/horarios/<int:horario_id>/eliminar")
def eliminar_horario(punto_id, horario_id):
    horario = db.first_or_404(db.select(Horario).where(Horario.id == horario_id, Horario.punto_id == punto_id))
    db.session.delete(horario)
    guardar("Horario eliminado.")
    return redirect(url_for("admin.punto_formulario", punto_id=punto_id))
