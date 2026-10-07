"""Extensiones compartidas, independientes de la factory y los modelos."""

import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, connection_record):
    """Activar claves foráneas en cada conexión SQLite."""
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
