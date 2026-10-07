import os
import secrets


class Config:
    """Configuración base de la aplicación."""

    TESTING = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///ecovaldivia.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Sin variable de entorno, clave temporal para desarrollo; cambia al reiniciar.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
