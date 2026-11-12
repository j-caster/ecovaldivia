from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import PuntoReciclaje, Usuario
from app.services.security import roles_required, validar_csrf
from app.services.camara_service import PUNTO_CON_CAMARA, camara_para_punto
from app.services.panel_service import INTERVALO_PANEL_SEGUNDOS, datos_panel
from app.services.fecha_service import fecha_chile

auth_bp = Blueprint("auth", __name__)
# Verificación equivalente para usernames desconocidos, sin revelar su existencia.
HASH_DESCONOCIDO = generate_password_hash("credencial-inexistente")


@login_manager.user_loader
def cargar_usuario(user_id):
    try:
        usuario = db.session.get(Usuario, int(user_id))
    except (ValueError, TypeError):
        return None
    return usuario if usuario and usuario.is_active else None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validar_csrf()
    if current_user.is_authenticated:
        return redirect(url_for("auth.panel"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == username))
        valido = usuario.verificar_password(password) if usuario else check_password_hash(HASH_DESCONOCIDO, password)
        if usuario and valido and usuario.is_active:
            session.clear()
            login_user(usuario)
            return redirect(url_for("auth.panel"))
        flash("Credenciales inválidas o cuenta no disponible.", "danger")
    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    validar_csrf()
    logout_user()
    session.clear()
    return redirect(url_for("public.index"))


@auth_bp.get("/panel")
@roles_required("operador", "administrador")
def panel():
    punto_camara = db.session.scalar(
        db.select(PuntoReciclaje).where(PuntoReciclaje.nombre == PUNTO_CON_CAMARA)
    )
    camara = camara_para_punto(punto_camara) if punto_camara else None
    return render_template("panel.html", contenedores=datos_panel(), camara=camara,
                           intervalo_panel_ms=INTERVALO_PANEL_SEGUNDOS * 1000)


@auth_bp.get("/panel/datos")
@roles_required("operador", "administrador")
def panel_datos():
    contenedores = datos_panel()
    fechas_locales = {c["ultima_actualizacion"]: fecha_chile(c["ultima_actualizacion"])
                     for c in contenedores if c["ultima_actualizacion"]}
    respuesta = jsonify(contenedores=contenedores, fechas_locales=fechas_locales)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@auth_bp.get("/api/camara/<int:punto_id>")
@roles_required("operador", "administrador")
def camara(punto_id):
    """Datos de la cámara en vivo de un punto, solo para operadores/admin."""
    punto = db.session.get(PuntoReciclaje, punto_id)
    if punto is None:
        return jsonify(ok=False, error="punto_no_encontrado"), 404

    datos_camara = camara_para_punto(punto)
    if datos_camara is None:
        return jsonify(ok=False, error="punto_sin_camara"), 404

    return jsonify(ok=True, **datos_camara)
