"""Extensiones compartidas, independientes de la factory y los modelos."""

import sqlite3

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Inicia sesión para acceder a esta página."


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, connection_record):
    """Activar claves foráneas en cada conexión SQLite."""
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
