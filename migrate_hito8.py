"""Actualización aditiva e idempotente: python migrate_hito8.py.

Necesaria para bases existentes: create_all no agrega columnas a tablas creadas.
Reiniciar Flask/worker después para cargar los modelos y servicios nuevos.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def actualizar_confirmacion(engine):
    with engine.begin() as conexion:
        columnas = {c["name"] for c in inspect(conexion).get_columns("dispositivo_iot")}
        if "contador_lleno" not in columnas:
            conexion.execute(text(
                "ALTER TABLE dispositivo_iot ADD COLUMN contador_lleno INTEGER NOT NULL "
                "DEFAULT 0 CHECK (contador_lleno BETWEEN 0 AND 3)"))
        if "boot_confirmacion" not in columnas:
            conexion.execute(text(
                "ALTER TABLE dispositivo_iot ADD COLUMN boot_confirmacion VARCHAR(100)"))


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        actualizar_confirmacion(db.engine)
    print("Esquema Hito 8 actualizado sin eliminar datos.")
