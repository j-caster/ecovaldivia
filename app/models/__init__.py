"""Registrar y exponer los modelos base de EcoValdivia."""

from app.models.punto_reciclaje import PuntoReciclaje
from app.models.material import Material
from app.models.punto_material import PuntoMaterial
from app.models.horario import Horario
from app.models.contenedor import Contenedor
from app.models.usuario import Usuario
from app.models.dispositivo_iot import DispositivoIoT
from app.models.medicion import Medicion
from app.models.alerta import Alerta
from app.models.evento_operacional import EventoOperacional

__all__ = ["PuntoReciclaje", "Material", "PuntoMaterial", "Horario", "Contenedor", "Usuario", "DispositivoIoT", "Medicion", "Alerta", "EventoOperacional"]
