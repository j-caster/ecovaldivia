import logging
import time

from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db

logger = logging.getLogger(__name__)

app = create_app()


def _inicializar():
    """Crear tablas y cargar datos de demostración (idempotente).

    En Render el plan gratuito no ofrece Shell, por lo que la aplicación se
    inicializa sola al arrancar: crea el esquema si falta y agrega solo los
    registros de demostración ausentes.
    """
    with app.app_context():
        db.create_all()
        from seed import cargar_datos  # import tardío: no ejecuta el main de seed.py
        cargar_datos()
        from seed import cargar_dispositivos
        cargar_dispositivos()


for intento in range(10):
    try:
        _inicializar()
    except OperationalError:
        if intento == 9:
            raise
        logger.warning("Base de datos no disponible; reintentando en 3 s...")
        time.sleep(3)
    else:
        break

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
