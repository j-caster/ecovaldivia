"""Protocolo de telemetría V27B, sin transporte ni persistencia."""

from datetime import datetime, timezone
import hashlib
import hmac
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

AAD_TELEMETRIA = b"ECO-VALDIVIA-V27B|TEL"


class ErrorProtocolo(ValueError):
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(mensaje)


def decodificar_hex(valor, longitud=None, codigo="sobre"):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9a-fA-F]+", valor) or len(valor) % 2:
        raise ErrorProtocolo(codigo, "Campo hexadecimal inválido.")
    resultado = bytes.fromhex(valor)
    if longitud is not None and len(resultado) != longitud:
        raise ErrorProtocolo(codigo, "Longitud hexadecimal inválida.")
    return resultado


def cargar_clave(valor, nombre):
    try:
        return decodificar_hex(valor, 32)
    except ErrorProtocolo:
        raise ValueError(f"{nombre} debe representar exactamente 32 bytes hexadecimales.") from None


def parsear_campos(texto):
    campos = {}
    for parte in texto.split(";"):
        if not parte:  # Compatible con separador final.
            continue
        if "=" not in parte:
            raise ErrorProtocolo("sobre", "Campo sin separador.")
        clave, valor = (p.strip() for p in parte.split("=", 1))
        if not clave or clave in campos:
            raise ErrorProtocolo("sobre", "Campo vacío o repetido.")
        campos[clave] = valor
    return campos


def entero(valor, campo):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]+", valor):
        raise ErrorProtocolo("contenido", f"{campo} debe ser entero no negativo.")
    numero = int(valor)
    if numero > 0xFFFFFFFF:
        raise ErrorProtocolo("contenido", f"{campo} excede 32 bits.")
    return numero


def validar_telemetria(paquete, clave_hmac, clave_aead, *, dispositivo_identificador,
                       ultimo_boot=None, ultimo_seq=None, ip_origen=None,
                       fecha_recepcion=None):
    """Validar usando una instantánea persistente suministrada por el llamador.

    No modifica el estado: solo una persistencia exitosa debe avanzar BOOT/SEQ.
    Un BOOT distinto se acepta como reinicio según el alcance de este protocolo.
    """
    if len(clave_hmac) != 32 or len(clave_aead) != 32:
        raise ValueError("Las claves UDP deben tener 32 bytes.")
    try:
        texto = paquete.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        raise ErrorProtocolo("sobre", "Datagrama no UTF-8.") from None
    contenido, marcador, firma = texto.rpartition(";SIG=")
    if not marcador:
        raise ErrorProtocolo("hmac", "HMAC ausente.")
    firma_bytes = decodificar_hex(firma, 32, "hmac")
    esperada = hmac.new(clave_hmac, contenido.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(firma_bytes, esperada):
        raise ErrorProtocolo("hmac", "HMAC inválido.")
    exterior = parsear_campos(contenido)
    if set(exterior) != {"V", "DIR", "NONCE", "CT", "TAG"} or exterior["V"] != "2" or exterior["DIR"] != "TEL":
        raise ErrorProtocolo("sobre", "Sobre de telemetría inválido.")
    nonce = decodificar_hex(exterior["NONCE"], 12, "nonce")
    cipher = decodificar_hex(exterior["CT"], codigo="aead")
    tag = decodificar_hex(exterior["TAG"], 16, "aead")
    if not 1 <= len(cipher) <= 256:
        raise ErrorProtocolo("aead", "Longitud de contenido cifrado inválida.")
    try:
        plano = ChaCha20Poly1305(clave_aead).decrypt(nonce, cipher + tag, AAD_TELEMETRIA)
    except InvalidTag:
        raise ErrorProtocolo("aead", "TAG/AEAD inválido.") from None
    try:
        datos = parsear_campos(plano.decode("utf-8", errors="strict"))
    except UnicodeDecodeError:
        raise ErrorProtocolo("contenido", "Contenido no UTF-8.") from None
    requeridos = {"TYPE", "BOOT", "SEQ", "ID", "S1_CM", "S2_CM", "MODO", "COMPUERTA", "FUENTE", "LAST_CMD_CTR"}
    if not requeridos.issubset(datos) or datos["TYPE"] != "TEL" or not datos["ID"] or not datos["FUENTE"]:
        raise ErrorProtocolo("contenido", "Contenido de telemetría incompleto o inválido.")
    boot = datos["BOOT"].upper()
    boot_bytes = decodificar_hex(boot, 8, "nonce")
    seq = entero(datos["SEQ"], "SEQ")
    if not hmac.compare_digest(nonce, boot_bytes + seq.to_bytes(4, "big")):
        raise ErrorProtocolo("nonce", "Nonce incoherente con BOOT/SEQ.")
    if ultimo_boot is not None and boot == ultimo_boot.upper() and ultimo_seq is not None and seq <= ultimo_seq:
        raise ErrorProtocolo("replay", "Medición duplicada/replay rechazada.")
    try:
        sensores = {"sensor1_cm": float(datos["S1_CM"]), "sensor2_cm": float(datos["S2_CM"])}
    except (ValueError, OverflowError):
        raise ErrorProtocolo("fisica", "Sensores no numéricos.") from None
    modo, compuerta = datos["MODO"].upper(), datos["COMPUERTA"].upper()
    if modo not in ("AUTO", "MANUAL") or compuerta not in ("ABIERTA", "CERRADA"):
        raise ErrorProtocolo("contenido", "Modo o compuerta inválidos.")
    # FUENTE del firmware describe el origen operacional; el dominio clasifica
    # toda telemetría autenticada de este adaptador como REAL.
    return dict(dispositivo_identificador=dispositivo_identificador,
                medicion_externa_id=datos["ID"], **sensores, modo=modo,
                compuerta=compuerta, fuente="REAL", boot=boot, seq=seq,
                last_cmd_ctr=entero(datos["LAST_CMD_CTR"], "LAST_CMD_CTR"),
                ip_origen=ip_origen,
                fecha_recepcion=fecha_recepcion or datetime.now(timezone.utc))
