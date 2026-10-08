"""Serialización pública del resultado ya filtrado, sin consultas adicionales."""

from math import isfinite


def coordenada_valida(valor, limite):
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if isfinite(numero) and -limite <= numero <= limite else None


def datos_mapa_publico(puntos):
    datos = []
    for punto in puntos:
        latitud = coordenada_valida(punto.latitud, 90)
        longitud = coordenada_valida(punto.longitud, 180)
        if latitud is None or longitud is None:
            latitud = longitud = None
        datos.append({
            "punto_id": punto.id, "nombre": punto.nombre, "direccion": punto.direccion,
            "latitud": latitud, "longitud": longitud,
            "materiales": sorted(material.nombre for material in punto.materiales),
            "contenedores": [{
                "codigo": contenedor.codigo, "estado": contenedor.estado,
                "porcentaje_llenado": contenedor.porcentaje_llenado,
                "ultima_actualizacion": (contenedor.ultima_actualizacion.isoformat() + "Z"
                                          if contenedor.ultima_actualizacion else None),
            } for contenedor in sorted(punto.contenedores, key=lambda c: c.codigo) if contenedor.activo],
        })
    return datos
