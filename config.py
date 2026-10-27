import os
import secrets


def _booleano(nombre, por_defecto=False):
    """Leer un booleano del entorno aceptando 1/true/sí/yes/on."""
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def _url_basedatos():
    """Cadena de conexión: SQLite local o la que entregue el hosting (Render)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///ecovaldivia.db"
    # Render y otros hostings entregan postgres://, que SQLAlchemy 2 ya no acepta.
    return url.replace("postgres://", "postgresql://", 1)


class Config:
    """Configuración base de la aplicación."""

    TESTING = False
    SQLALCHEMY_DATABASE_URI = _url_basedatos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Sin variable de entorno, clave temporal para desarrollo; cambia al reiniciar.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # En producción con HTTPS: definir SESSION_COOKIE_SECURE=1 para que la cookie
    # de sesión viaje solo por conexiones cifradas.
    SESSION_COOKIE_SECURE = _booleano("SESSION_COOKIE_SECURE")
    # El gateway UDP local envía telemetría validada a este endpoint HTTPS.
    # Ambos valores se configuran por entorno; nunca se guardan en Git.
    IOT_INGEST_TOKEN = os.environ.get("ECOV_IOT_INGEST_TOKEN", "")
    IOT_INGEST_DEVICE_ID = os.environ.get("ECOV_IOT_INGEST_DEVICE_ID", "")
