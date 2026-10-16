"""Validación de formularios administrativos, independiente de HTML."""

from datetime import time
from math import isfinite


def texto(datos, campo, etiqueta, limite=None):
    valor = datos.get(campo, "").strip()
    if not valor:
        raise ValueError(f"{etiqueta} es obligatorio.")
    if limite and len(valor) > limite:
        raise ValueError(f"{etiqueta} admite hasta {limite} caracteres.")
    return valor


def validar_punto(datos):
    resultado = {
        "nombre": texto(datos, "nombre", "El nombre", 150),
        "direccion": texto(datos, "direccion", "La dirección", 255),
        "activo": datos.get("activo") == "1",
    }
    for campo, limite in (("latitud", 90), ("longitud", 180)):
        try:
            valor = float(datos.get(campo, ""))
        except (ValueError, TypeError):
            raise ValueError(f"{campo.capitalize()} debe ser un número válido.") from None
        if not isfinite(valor) or not -limite <= valor <= limite:
            raise ValueError(f"{campo.capitalize()} debe estar entre {-limite} y {limite}.")
        resultado[campo] = valor
    return resultado


def validar_material(datos):
    return {
        "nombre": texto(datos, "nombre", "El nombre", 100),
        "instrucciones": texto(datos, "instrucciones", "Las instrucciones"),
    }


def validar_contenedor(datos):
    """Validar el contenedor y el identificador del dispositivo IoT que lo reporta.

    El identificador lo escribe el administrador y debe ser único en el sistema.
    """
    resultado = {
        "codigo": texto(datos, "codigo", "El código del contenedor", 100),
        "identificador": texto(datos, "identificador", "El identificador del dispositivo IoT", 100),
        "activo": datos.get("activo", "1") == "1",
    }
    material = (datos.get("material_id") or "").strip()
    if material:
        try:
            resultado["material_id"] = int(material)
        except (ValueError, TypeError):
            raise ValueError("El material seleccionado no es válido.") from None
    else:
        resultado["material_id"] = None
    return resultado


def validar_horario(datos):
    try:
        dia = int(datos.get("dia_semana", ""))
        inicio = time.fromisoformat(datos.get("hora_inicio", ""))
        fin = time.fromisoformat(datos.get("hora_fin", ""))
    except (ValueError, TypeError):
        raise ValueError("Completa un día y horas válidos.") from None
    if dia not in range(7):
        raise ValueError("El día debe estar entre lunes y domingo.")
    if inicio.tzinfo or fin.tzinfo or inicio >= fin:
        raise ValueError("La hora de inicio debe ser menor que la hora de fin.")
    return {"dia_semana": dia, "hora_inicio": inicio, "hora_fin": fin}


def validar_horarios_creacion(datos):
    dias = datos.getlist("dia_semana")
    if not dias:
        raise ValueError("Selecciona al menos un día de la semana.")
    # Validar todo el lote antes de agregar registros a la sesión.
    horarios = [validar_horario({
        "dia_semana": dia,
        "hora_inicio": datos.get("hora_inicio", ""),
        "hora_fin": datos.get("hora_fin", ""),
    }) for dia in dias]
    return list({horario["dia_semana"]: horario for horario in horarios}.values())
