"""Validación y persistencia de mediciones, independiente de su transporte.

Las fechas se almacenan en UTC sin zona para mantener compatibilidad con SQLite.
procesar_medicion confirma la transacción; el llamador debe usar una sesión
sin otras modificaciones pendientes.
"""

from datetime import datetime, timezone
from ipaddress import ip_address
from math import isfinite
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import DispositivoIoT, Medicion
from app.services.operacion_service import asegurar_alerta_llenado

DISTANCIA_VACIO_CM = 175
DISTANCIA_LLENO_CM = 25
UMBRAL_MEDIO = 50
UMBRAL_CASI_LLENO = 80
MODOS = ("AUTO", "MANUAL")
COMPUERTAS = ("ABIERTA", "CERRADA")
FUENTES = ("REAL", "SIMULACION")
INTERVALO_PERSISTENCIA_SEGUNDOS = 60


def debe_persistir_medicion(ultima, valores, dispositivo):
    if ultima is None:
        return True
    return (
        valores["estado_calculado"] != dispositivo.contenedor.estado
        or valores["modo"] != dispositivo.modo_actual
        or valores["compuerta"] != dispositivo.compuerta_actual
        or valores["boot"] != dispositivo.ultimo_boot
        or (valores["recibida_en"] - ultima.recibida_en).total_seconds()
        >= INTERVALO_PERSISTENCIA_SEGUNDOS
    )


def numero_positivo(valor, campo):
    try:
        if isinstance(valor, bool):
            raise ValueError
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{campo} debe ser numérico y positivo.") from None
    if not isfinite(numero) or numero <= 0:
        raise ValueError(f"{campo} debe ser numérico, finito y positivo.")
    return numero


def entero_no_negativo(valor, campo):
    # No truncar flotantes ni aceptar booleanos como enteros.
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ValueError(f"{campo} debe ser un entero no negativo.")
    try:
        numero = int(valor)
    except ValueError:
        raise ValueError(f"{campo} debe ser un entero no negativo.") from None
    if not 0 <= numero <= 9223372036854775807:
        raise ValueError(f"{campo} debe ser un entero no negativo de 64 bits.")
    return numero


def texto(valor, campo, limite, requerido=True):
    if valor is None and not requerido:
        return None
    if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > limite:
        raise ValueError(f"{campo} debe ser texto de 1 a {limite} caracteres.")
    return valor.strip()


def calcular_llenado(sensor1_cm, sensor2_cm):
    """Retornar porcentaje y estado a partir del promedio de dos distancias."""
    s1 = numero_positivo(sensor1_cm, "sensor1_cm")
    s2 = numero_positivo(sensor2_cm, "sensor2_cm")
    distancia = s1 / 2 + s2 / 2
    porcentaje = max(0.0, min(100.0, (DISTANCIA_VACIO_CM - distancia)
                             / (DISTANCIA_VACIO_CM - DISTANCIA_LLENO_CM) * 100))
    if porcentaje == 100:
        estado = "Lleno"
    elif porcentaje >= UMBRAL_CASI_LLENO:
        estado = "Casi lleno"
    elif porcentaje >= UMBRAL_MEDIO:
        estado = "Medio"
    else:
        estado = "Disponible"
    return porcentaje, estado


def procesar_medicion(datos):
    """Procesar siempre; muestrear historial y confirmar estado/alertas juntos.

    Retorna una Medicion con id si se persistió o un objeto transitorio con
    id=None si solo se actualizó el estado actual. No contiene una fila histórica
    en este último caso; los consumidores no deben agregarlo a la sesión.
    """
    identificador = texto(datos.get("dispositivo_identificador"), "dispositivo_identificador", 100)
    valores = {campo: numero_positivo(datos.get(campo), campo)
               for campo in ("sensor1_cm", "sensor2_cm")}
    for campo, permitidos in (("modo", MODOS), ("compuerta", COMPUERTAS), ("fuente", FUENTES)):
        valor = datos.get(campo)
        if valor not in permitidos:
            raise ValueError(f"{campo} debe ser uno de: {', '.join(permitidos)}.")
        valores[campo] = valor
    boot = datos.get("boot")
    if valores["fuente"] == "SIMULACION" and boot in (None, ""):
        boot = f"sim-{uuid4().hex}"
    valores["boot"] = texto(boot, "boot", 100)
    valores["seq"] = entero_no_negativo(datos.get("seq"), "seq")
    ctr = datos.get("last_cmd_ctr")
    valores["last_cmd_ctr"] = entero_no_negativo(ctr, "last_cmd_ctr") if ctr is not None else None
    externo = datos.get("medicion_externa_id")
    if isinstance(externo, int) and not isinstance(externo, bool):
        externo = str(externo)
    valores["medicion_externa_id"] = texto(externo, "medicion_externa_id", 100, requerido=False)
    ip = datos.get("ip_origen")
    try:
        valores["ip_origen"] = str(ip_address(ip)) if ip is not None else None
    except ValueError:
        raise ValueError("ip_origen debe ser una dirección IP válida.") from None
    fecha = datos.get("fecha_recepcion")
    if fecha is None:
        fecha = datetime.now(timezone.utc)
    if not isinstance(fecha, datetime):
        raise ValueError("fecha_recepcion debe ser datetime.")
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    valores["recibida_en"] = fecha
    valores["porcentaje_llenado"], valores["estado_calculado"] = calcular_llenado(
        valores["sensor1_cm"], valores["sensor2_cm"])

    dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
        DispositivoIoT.identificador == identificador))
    if dispositivo is None or not dispositivo.activo or not dispositivo.contenedor.activo:
        raise ValueError("Dispositivo inexistente, inactivo o asociado a un contenedor inactivo.")
    if (dispositivo.ultimo_boot == valores["boot"] and dispositivo.ultimo_seq is not None
            and valores["seq"] <= dispositivo.ultimo_seq):
        raise ValueError("Medición duplicada/replay para dispositivo, boot y seq.")
    duplicado = db.session.scalar(db.select(Medicion.id).where(
        Medicion.dispositivo_id == dispositivo.id,
        Medicion.boot == valores["boot"], Medicion.seq == valores["seq"]))
    if duplicado is not None:
        raise ValueError("Medición duplicada para dispositivo, boot y seq.")
    ultima = db.session.scalar(db.select(Medicion).where(
        Medicion.dispositivo_id == dispositivo.id).order_by(Medicion.id.desc()).limit(1))
    persistir = debe_persistir_medicion(ultima, valores, dispositivo)
    medicion = Medicion(dispositivo_id=dispositivo.id, **valores)
    try:
        if persistir:
            db.session.add(medicion)
        dispositivo.modo_actual = medicion.modo
        dispositivo.compuerta_actual = medicion.compuerta
        dispositivo.ultima_ip = medicion.ip_origen
        dispositivo.ultimo_boot = medicion.boot
        dispositivo.ultimo_seq = medicion.seq
        dispositivo.ultima_actualizacion = fecha
        dispositivo.contenedor.porcentaje_llenado = medicion.porcentaje_llenado
        dispositivo.contenedor.estado = medicion.estado_calculado
        dispositivo.contenedor.ultima_actualizacion = fecha
        asegurar_alerta_llenado(dispositivo.contenedor, fecha)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError("Medición duplicada o incompatible con las restricciones de persistencia.") from None
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return medicion
