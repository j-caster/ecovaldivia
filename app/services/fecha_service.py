"""Presentación de fechas UTC en hora local de Chile, sin alterar su origen."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONA_CHILE = ZoneInfo("America/Santiago")


def fecha_chile(valor, sin_fecha="Sin datos"):
    if valor is None:
        return sin_fecha
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(ZONA_CHILE).strftime("%d-%m-%Y %H:%M:%S")
