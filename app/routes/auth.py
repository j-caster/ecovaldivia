from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import Usuario
from app.services.security import roles_required, validar_csrf

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
    return render_template("panel.html")
