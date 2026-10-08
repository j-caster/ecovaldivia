"""Worker independiente: python udp_worker.py. No arranca al importar."""

import logging
import signal
from threading import Event

from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.integrations.udp_listener import ConfigUDP, escuchar


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    detener = Event()
    signal.signal(signal.SIGINT, lambda *_: detener.set())
    signal.signal(signal.SIGTERM, lambda *_: detener.set())
    try:
        config = ConfigUDP.desde_entorno()
        escuchar(create_app(), config, detener)
    except ValueError as error:
        logging.error("Configuración UDP inválida: %s", error)
        return 1
    except SQLAlchemyError:
        logging.error("Error de base de datos al iniciar el worker UDP.")
        return 1
    except OSError:
        logging.error("Error de socket UDP; comprueba host, puerto y disponibilidad.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
