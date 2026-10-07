"""Registrar y exponer los modelos base de EcoValdivia."""

from app.models.punto_reciclaje import PuntoReciclaje
from app.models.material import Material
from app.models.punto_material import PuntoMaterial
from app.models.horario import Horario
from app.models.contenedor import Contenedor

__all__ = ["PuntoReciclaje", "Material", "PuntoMaterial", "Horario", "Contenedor"]
