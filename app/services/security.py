"""Autorización por rol y protección de formularios de sesión."""

from functools import wraps
import secrets

from flask import abort, request, session
from flask_login import current_user, login_required


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_active or current_user.rol not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validar_csrf():
    esperado = session.get("csrf_token")
    recibido = request.form.get("csrf_token", "")
    if not esperado or not secrets.compare_digest(esperado, recibido):
        abort(400, description="Formulario vencido o inválido. Recarga la página.")
