"""Actualización aditiva e idempotente: python migrate_hito10.py.

Necesaria para bases existentes: create_all no agrega columnas a tablas ya creadas.
Agrega `contenedor.material_id` para indicar qué material recibe cada contenedor.
Reiniciar Flask/worker después para cargar los modelos y servicios nuevos.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def actualizar_material_contenedor(engine):
    with engine.begin() as conexion:
        columnas = {c["name"] for c in inspect(conexion).get_columns("contenedor")}
        if "material_id" not in columnas:
            # La columna es opcional, por lo que las filas existentes quedan sin material.
            conexion.execute(text(
                "ALTER TABLE contenedor ADD COLUMN material_id INTEGER REFERENCES material(id)"))


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        actualizar_material_contenedor(db.engine)
    print("Esquema Hito 10 actualizado sin eliminar datos.")
