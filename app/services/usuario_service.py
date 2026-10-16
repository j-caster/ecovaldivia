"""Validación de cuentas administradas, independiente de la integración IoT."""

from app.extensions import db
from app.models import Usuario


def validar_usuario(datos, usuario, administrador_id):
    nombre = datos.get("nombre", "").strip()
    username = datos.get("username", "").strip()
    rol = datos.get("rol", "")
    activo = datos.get("activo") == "1"
    password = datos.get("password", "")
    if not nombre or len(nombre) > 150:
        raise ValueError("Ingresa un nombre de hasta 150 caracteres.")
    if not username or len(username) > 100 or any(c.isspace() for c in username):
        raise ValueError("Ingresa un username de hasta 100 caracteres, sin espacios.")
    if rol not in ("operador", "administrador"):
        raise ValueError("Selecciona un rol válido.")
    if datos.get("activo", "") not in ("", "1"):
        raise ValueError("Estado de usuario inválido.")
    if (usuario is None or password) and (len(password) < 8 or len(password) > 128 or not password.strip()):
        raise ValueError("La contraseña debe tener entre 8 y 128 caracteres.")
    if password != datos.get("password_confirmacion", ""):
        raise ValueError("Las contraseñas no coinciden.")
    consulta = db.select(Usuario).where(Usuario.username == username)
    if usuario:
        consulta = consulta.where(Usuario.id != usuario.id)
    if db.session.scalar(consulta):
        raise ValueError("Ya existe un usuario con ese username.")
    if usuario and usuario.id == administrador_id and (not activo or rol != "administrador"):
        raise ValueError("No puedes desactivar tu cuenta ni quitar tu propio rol de administrador.")
    if usuario and usuario.activo and usuario.rol == "administrador" and (not activo or rol != "administrador"):
        otro = db.session.scalar(db.select(Usuario.id).where(
            Usuario.id != usuario.id, Usuario.activo.is_(True), Usuario.rol == "administrador"))
        if otro is None:
            raise ValueError("Debe existir al menos un administrador activo.")
    return {"nombre": nombre, "username": username, "rol": rol, "activo": activo}, password
