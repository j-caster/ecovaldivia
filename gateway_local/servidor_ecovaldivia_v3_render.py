from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from datetime import datetime
from pathlib import Path
from threading import Thread, Lock
from queue import Queue, Empty, Full

import base64
import hashlib
import hmac
import json
import secrets
import socket
import time
import ssl

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.exceptions import InvalidTag

import firebase_admin
from firebase_admin import credentials, firestore

from render_bridge import RenderBridge

from secrets_config import (
    UDP_HMAC_KEY_HEX,
    UDP_AEAD_KEY_HEX,
    WEB_USER,
    WEB_PASSWORD_HASH,
)


# ======================================================
# CONFIGURACION GENERAL
# ======================================================

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

CERT_DIR = BASE_DIR / "certs"

CERT_FILE = (
    CERT_DIR /
    "server_cert.pem"
)

KEY_FILE = (
    CERT_DIR /
    "server_key.pem"
)

ARCHIVO_MEDICIONES = BASE_DIR / "mediciones.txt"

# ======================================================
# FIREBASE / CLOUD FIRESTORE
# ======================================================

FIREBASE_CREDENCIAL = (
    BASE_DIR /
    "firebase" /
    "serviceAccountKey.json"
)

# Documento que representará el estado actual del prototipo.
FIREBASE_COLECCION_CONTENEDORES = "contenedores"
FIREBASE_ID_CONTENEDOR = "eco_valdivia_01"

# La telemetría local llega aproximadamente cada 2 segundos,
# pero no necesitamos escribir cada paquete en Firestore.
# Cinco segundos mantiene una visualización fluida y reduce
# el consumo de escrituras del plan gratuito.
FIREBASE_INTERVALO_ESTADO = 5.0

HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8443

UDP_HOST = "0.0.0.0"
UDP_PUERTO_PYTHON = 4211
UDP_PUERTO_ARDUINO = 4210

TIEMPO_OFFLINE = 5


# ======================================================
# SEGURIDAD UDP V2.7B
# ======================================================

try:
    UDP_HMAC_KEY = bytes.fromhex(
        UDP_HMAC_KEY_HEX
    )

except ValueError:
    raise SystemExit(
        "ERROR: UDP_HMAC_KEY_HEX debe contener solo caracteres hexadecimales."
    )


if len(UDP_HMAC_KEY) != 32:
    raise SystemExit(
        "ERROR: UDP_HMAC_KEY_HEX debe representar exactamente 32 bytes "
        "(64 caracteres hexadecimales)."
    )


try:
    UDP_AEAD_KEY = bytes.fromhex(
        UDP_AEAD_KEY_HEX
    )

except ValueError:
    raise SystemExit(
        "ERROR: UDP_AEAD_KEY_HEX debe contener solo caracteres hexadecimales."
    )


if len(UDP_AEAD_KEY) != 32:
    raise SystemExit(
        "ERROR: UDP_AEAD_KEY_HEX debe representar exactamente 32 bytes "
        "(64 caracteres hexadecimales)."
    )


AAD_CMD = b"ECO-VALDIVIA-V27B|CMD"
AAD_TEL = b"ECO-VALDIVIA-V27B|TEL"

# Ocho bytes aleatorios nuevos en cada arranque del servidor.
# Se combinan con CTR para formar nonces de 12 bytes.
PREFIJO_NONCE_CMD = secrets.token_bytes(8)


# ======================================================
# SEGURIDAD WEB
# ======================================================

SESSION_COOKIE_NAME = "eco_session"

# Sesion expira tras 30 minutos SIN actividad.
SESSION_TIMEOUT = 30 * 60

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_BLOCK_SECONDS = 60

# HTTPS activo: la cookie de sesion debe enviarse solo por TLS.
COOKIE_SECURE = True


# ======================================================
# ESTADO DEL SISTEMA
# ======================================================

comando_actual = "AUTO"

ultima_medicion = {}
arduino_ip = None
arduino_boot = None

ultimo_seq = None
ultimo_ctr_aceptado = 0
contador_comando = 0

ultima_telemetria = 0.0

# BOOT anteriores observados durante esta ejecucion de Python.
# Si reaparece uno antiguo, se trata como posible replay.
boots_anteriores = set()

estado_lock = Lock()

# Estado de la integración con Firebase.
firebase_db = None
firebase_disponible = False
firebase_cola = Queue(maxsize=1)
ultimo_encolado_firebase = 0.0

# Copia V3: puente HTTPS independiente de la escritura en Firestore.
# Sin variables ECOV_RENDER_* el servidor conserva el comportamiento V2.7B.
render_bridge = RenderBridge()


# ======================================================
# FIREBASE
# ======================================================

def iniciar_firebase():

    global firebase_db
    global firebase_disponible

    if not FIREBASE_CREDENCIAL.exists():
        print(
            "[FIREBASE] No se encontro la credencial:"
        )
        print(
            FIREBASE_CREDENCIAL
        )
        print(
            "[FIREBASE] El servidor continuara sin nube."
        )
        return False

    try:

        try:
            firebase_admin.get_app()
        except ValueError:
            credencial = credentials.Certificate(
                str(FIREBASE_CREDENCIAL)
            )
            firebase_admin.initialize_app(
                credencial
            )

        firebase_db = firestore.client()
        firebase_disponible = True

        print(
            "[FIREBASE] Cloud Firestore inicializado correctamente."
        )
        print(
            "[FIREBASE] Estado remoto: "
            f"{FIREBASE_COLECCION_CONTENEDORES}/"
            f"{FIREBASE_ID_CONTENEDOR}"
        )

        return True

    except Exception as error:

        firebase_disponible = False

        print(
            "[FIREBASE] No se pudo inicializar:"
        )
        print(
            error
        )
        print(
            "[FIREBASE] El servidor local seguira funcionando."
        )

        return False


def _numero_float(valor):

    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _numero_entero(valor):

    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def construir_estado_firebase(datos, ip_origen):

    return {
        "dispositivo": FIREBASE_ID_CONTENEDOR,
        "sensor1_cm": _numero_float(datos.get("S1_CM")),
        "sensor2_cm": _numero_float(datos.get("S2_CM")),
        "modo": datos.get("MODO", "-"),
        "compuerta": datos.get("COMPUERTA", "-"),
        "fuente": datos.get("FUENTE", "-"),
        "boot": datos.get("BOOT", "-"),
        "seq": _numero_entero(datos.get("SEQ")),
        "id_medicion": _numero_entero(datos.get("ID")),
        "ultimo_ctr": _numero_entero(datos.get("LAST_CMD_CTR")),
        "arduino_ip": str(ip_origen),
        "conectado": True,
        "seguridad_udp": "ChaCha20-Poly1305 + HMAC-SHA256 + CTR",
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP,
    }


def encolar_estado_firebase(datos, ip_origen):

    global ultimo_encolado_firebase

    if not firebase_disponible:
        return

    ahora = time.time()

    if (
        ahora - ultimo_encolado_firebase
        < FIREBASE_INTERVALO_ESTADO
    ):
        return

    ultimo_encolado_firebase = ahora

    estado = construir_estado_firebase(
        datos,
        ip_origen
    )

    # Solo nos interesa conservar el estado mas reciente
    # si Firebase se demora o Internet falla temporalmente.
    try:
        if firebase_cola.full():
            firebase_cola.get_nowait()
            firebase_cola.task_done()
    except Empty:
        pass

    try:
        firebase_cola.put_nowait(
            estado
        )
    except Full:
        pass


def trabajador_firebase():

    while True:

        try:
            estado = firebase_cola.get(
                timeout=1
            )
        except Empty:
            continue

        try:
            (
                firebase_db
                .collection(FIREBASE_COLECCION_CONTENEDORES)
                .document(FIREBASE_ID_CONTENEDOR)
                .set(
                    estado,
                    merge=True
                )
            )

            print(
                "[FIREBASE] Estado actualizado "
                f"(SEQ={estado.get('seq')})."
            )

        except Exception as error:

            print(
                "[FIREBASE] Error al escribir en Firestore:"
            )
            print(
                error
            )

        finally:
            firebase_cola.task_done()


# ======================================================
# SESIONES
# ======================================================

sesiones = {}
sesiones_lock = Lock()

intentos_login = {}
bloqueos_login = {}
login_lock = Lock()


# ======================================================
# UDP
# ======================================================

udp_socket = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

udp_socket.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

udp_socket.bind(
    (
        UDP_HOST,
        UDP_PUERTO_PYTHON
    )
)


# ======================================================
# HMAC / PROTOCOLO UDP V2.7A
# ======================================================

def firmar_udp(contenido):

    return hmac.new(
        UDP_HMAC_KEY,
        contenido.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()


def separar_firma_udp(mensaje):

    marcador = ";SIG="

    posicion = mensaje.rfind(
        marcador
    )

    if posicion < 0:
        return None, None

    contenido = mensaje[:posicion]

    firma = mensaje[
        posicion + len(marcador):
    ].strip().upper()

    if len(firma) != 64:
        return None, None

    return contenido, firma


def verificar_firma_udp(mensaje):

    contenido, firma_recibida = separar_firma_udp(
        mensaje
    )

    if contenido is None:
        return None

    firma_esperada = firmar_udp(
        contenido
    )

    if not hmac.compare_digest(
        firma_recibida,
        firma_esperada
    ):
        return None

    return contenido



def bytes_hex(texto, longitud=None):

    try:
        datos = bytes.fromhex(
            texto
        )

    except (
        TypeError,
        ValueError
    ):
        return None

    if (
        longitud is not None
        and
        len(datos) != longitud
    ):
        return None

    return datos


def cifrar_aead(texto_plano, nonce, aad):

    resultado = ChaCha20Poly1305(
        UDP_AEAD_KEY
    ).encrypt(
        nonce,
        texto_plano.encode("utf-8"),
        aad
    )

    ciphertext = resultado[:-16]
    tag = resultado[-16:]

    return (
        ciphertext.hex().upper(),
        tag.hex().upper()
    )


def descifrar_aead(
    cipher_hex,
    tag_hex,
    nonce,
    aad
):

    ciphertext = bytes_hex(
        cipher_hex
    )

    tag = bytes_hex(
        tag_hex,
        16
    )

    if (
        ciphertext is None
        or
        tag is None
        or
        len(ciphertext) == 0
        or
        len(ciphertext) > 256
    ):
        return None

    try:

        plano = ChaCha20Poly1305(
            UDP_AEAD_KEY
        ).decrypt(
            nonce,
            ciphertext + tag,
            aad
        )

    except InvalidTag:
        return None

    try:
        return plano.decode(
            "utf-8",
            errors="strict"
        )

    except UnicodeDecodeError:
        return None


def crear_nonce_comando(ctr):

    if not (
        0 <= ctr <= 0xFFFFFFFF
    ):
        raise ValueError(
            "CTR fuera del rango de 32 bits."
        )

    return (
        PREFIJO_NONCE_CMD
        +
        ctr.to_bytes(
            4,
            "big"
        )
    )


def nonce_telemetria_esperado(
    boot,
    seq
):

    try:

        boot_bytes = bytes.fromhex(
            boot
        )

    except ValueError:
        return None

    if (
        len(boot_bytes) != 8
        or
        not (
            0 <= seq <= 0xFFFFFFFF
        )
    ):
        return None

    return (
        boot_bytes
        +
        seq.to_bytes(
            4,
            "big"
        )
    )


def boot_valido(boot):

    if len(boot) != 16:
        return False

    try:
        int(boot, 16)
        return True

    except ValueError:
        return False


def entero_no_negativo(texto):

    try:
        valor = int(texto)

    except (
        TypeError,
        ValueError
    ):
        return None

    if valor < 0:
        return None

    return valor


# ======================================================
# HASH DE CONTRASEÑA
# ======================================================

def verificar_password(password, hash_guardado):

    try:
        partes = hash_guardado.split("$")

        if len(partes) != 4:
            return False

        algoritmo = partes[0]
        iteraciones = int(partes[1])

        salt = base64.urlsafe_b64decode(
            partes[2].encode("ascii")
        )

        esperado = base64.urlsafe_b64decode(
            partes[3].encode("ascii")
        )

        if algoritmo != "pbkdf2_sha256":
            return False

        calculado = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iteraciones,
            dklen=len(esperado)
        )

        return hmac.compare_digest(
            calculado,
            esperado
        )

    except Exception:
        return False


# ======================================================
# SESIONES WEB
# ======================================================

def crear_sesion(usuario):

    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    ahora = time.time()

    with sesiones_lock:

        sesiones[session_id] = {
            "usuario": usuario,
            "csrf": csrf_token,
            "creada": ahora,
            "ultima_actividad": ahora
        }

    return session_id, csrf_token


def obtener_sesion(session_id):

    if not session_id:
        return None

    ahora = time.time()

    with sesiones_lock:

        sesion = sesiones.get(
            session_id
        )

        if not sesion:
            return None

        if (
            ahora - sesion["ultima_actividad"]
            > SESSION_TIMEOUT
        ):

            sesiones.pop(
                session_id,
                None
            )

            return None

        sesion["ultima_actividad"] = ahora

        return dict(
            sesion
        )


def destruir_sesion(session_id):

    if not session_id:
        return

    with sesiones_lock:

        sesiones.pop(
            session_id,
            None
        )


# ======================================================
# LIMITACION DE LOGIN
# ======================================================

def segundos_bloqueo(ip):

    ahora = time.time()

    with login_lock:

        hasta = bloqueos_login.get(
            ip,
            0
        )

        if hasta <= ahora:

            bloqueos_login.pop(
                ip,
                None
            )

            return 0

        return int(
            hasta - ahora
        ) + 1


def registrar_login_fallido(ip):

    ahora = time.time()

    with login_lock:

        historial = intentos_login.get(
            ip,
            []
        )

        historial = [
            instante
            for instante in historial
            if ahora - instante <= LOGIN_WINDOW_SECONDS
        ]

        historial.append(
            ahora
        )

        if len(historial) >= MAX_LOGIN_ATTEMPTS:

            bloqueos_login[ip] = (
                ahora + LOGIN_BLOCK_SECONDS
            )

            historial = []

        intentos_login[ip] = historial


def limpiar_intentos_login(ip):

    with login_lock:

        intentos_login.pop(
            ip,
            None
        )

        bloqueos_login.pop(
            ip,
            None
        )


# ======================================================
# PARSEO UDP
# ======================================================

def parsear_datos(texto):

    datos = {}

    for parte in texto.split(";"):

        if "=" not in parte:
            continue

        clave, valor = parte.split(
            "=",
            1
        )

        datos[
            clave.strip()
        ] = valor.strip()

    return datos


# ======================================================
# LOG
# ======================================================

def guardar_medicion(datos):

    fecha = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    bloque_txt = (
        "\n"
        "========================================\n"
        f"Fecha/hora : {fecha}\n"
        f"BOOT       : {datos.get('BOOT', '-')}\n"
        f"SEQ        : {datos.get('SEQ', '-')}\n"
        f"ID         : {datos.get('ID', '-')}\n"
        f"Sensor 1   : {datos.get('S1_CM', '-')} cm\n"
        f"Sensor 2   : {datos.get('S2_CM', '-')} cm\n"
        f"Modo       : {datos.get('MODO', '-')}\n"
        f"Compuerta  : {datos.get('COMPUERTA', '-')}\n"
        f"Fuente     : {datos.get('FUENTE', '-')}\n"
        f"Ult. CTR   : {datos.get('LAST_CMD_CTR', '-')}\n"
        "Seguridad  : ChaCha20-Poly1305 + HMAC-SHA256\n"
        "========================================\n"
    )

    with ARCHIVO_MEDICIONES.open(
        "a",
        encoding="utf-8"
    ) as archivo:

        archivo.write(
            bloque_txt
        )

    print(
        bloque_txt
    )

# ======================================================
# RECEPTOR UDP
# ======================================================

def receptor_udp():

    global ultima_medicion
    global arduino_ip
    global arduino_boot

    global ultimo_seq
    global ultimo_ctr_aceptado
    global contador_comando

    global ultima_telemetria

    print(
        f"[UDP] Escuchando telemetria V2.7B cifrada "
        f"en puerto {UDP_PUERTO_PYTHON}"
    )

    while True:

        try:

            datos_raw, direccion = (
                udp_socket.recvfrom(2048)
            )

            texto = datos_raw.decode(
                "utf-8",
                errors="strict"
            ).strip()

            # ==========================================
            # 1) HMAC DEL SOBRE EXTERIOR
            # ==========================================

            sobre = verificar_firma_udp(
                texto
            )

            if sobre is None:

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: HMAC exterior invalido."
                )

                continue


            exterior = parsear_datos(
                sobre
            )


            if (
                exterior.get("V") != "2"
                or
                exterior.get("DIR") != "TEL"
            ):

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: sobre V2.7B invalido."
                )

                continue


            nonce = bytes_hex(
                exterior.get(
                    "NONCE",
                    ""
                ),
                12
            )


            if nonce is None:

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: NONCE invalido."
                )

                continue


            # ==========================================
            # 2) DESCIFRAR + VALIDAR POLY1305
            # ==========================================

            contenido = descifrar_aead(
                exterior.get(
                    "CT",
                    ""
                ),
                exterior.get(
                    "TAG",
                    ""
                ),
                nonce,
                AAD_TEL
            )


            if contenido is None:

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: cifrado/TAG invalido."
                )

                continue


            datos = parsear_datos(
                contenido
            )


            if datos.get("TYPE") != "TEL":

                print(
                    "[SEGURIDAD UDP] "
                    "Paquete rechazado: TYPE interno invalido."
                )

                continue


            boot = datos.get(
                "BOOT",
                ""
            ).upper()


            seq_num = entero_no_negativo(
                datos.get("SEQ")
            )


            ultimo_ctr_arduino = entero_no_negativo(
                datos.get("LAST_CMD_CTR")
            )


            if (
                not boot_valido(boot)
                or
                seq_num is None
                or
                ultimo_ctr_arduino is None
            ):

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: campos de seguridad invalidos."
                )

                continue


            # El NONCE de telemetria debe corresponder
            # exactamente a BOOT + SEQ.
            nonce_esperado = (
                nonce_telemetria_esperado(
                    boot,
                    seq_num
                )
            )


            if (
                nonce_esperado is None
                or
                not hmac.compare_digest(
                    nonce,
                    nonce_esperado
                )
            ):

                print(
                    "[SEGURIDAD UDP] "
                    "Telemetria rechazada: NONCE/BOOT/SEQ no coinciden."
                )

                continue


            ip_origen = direccion[0]


            with estado_lock:

                # ======================================
                # BOOT / REINICIO DE ARDUINO
                # ======================================

                if arduino_boot is None:

                    arduino_boot = boot
                    ultimo_seq = None

                    contador_comando = max(
                        contador_comando,
                        ultimo_ctr_arduino
                    )

                    print(
                        "[UDP] BOOT Arduino aprendido:",
                        arduino_boot
                    )

                elif boot != arduino_boot:

                    if boot in boots_anteriores:

                        print(
                            "[SEGURIDAD UDP] "
                            "Telemetria rechazada: BOOT antiguo/replay."
                        )

                        continue

                    boots_anteriores.add(
                        arduino_boot
                    )

                    print(
                        "[UDP] Reinicio Arduino detectado:",
                        arduino_boot,
                        "->",
                        boot
                    )

                    arduino_boot = boot
                    ultimo_seq = None

                    contador_comando = (
                        ultimo_ctr_arduino
                    )

                # ======================================
                # ANTI-REPLAY DE TELEMETRIA
                # ======================================

                if (
                    ultimo_seq is not None
                    and
                    seq_num <= ultimo_seq
                ):

                    print(
                        "[SEGURIDAD UDP] "
                        "Telemetria repetida/antigua rechazada:",
                        seq_num
                    )

                    continue


                if (
                    ultimo_seq is not None
                    and
                    seq_num != ultimo_seq + 1
                ):

                    print(
                        "[AVISO] Salto de SEQ:",
                        ultimo_seq,
                        "->",
                        seq_num
                    )


                ultimo_seq = seq_num


                ultimo_ctr_aceptado = max(
                    ultimo_ctr_aceptado,
                    ultimo_ctr_arduino
                )


                contador_comando = max(
                    contador_comando,
                    ultimo_ctr_arduino
                )


                arduino_ip = ip_origen

                ultima_medicion = dict(
                    datos
                )

                ultima_telemetria = (
                    time.time()
                )


            guardar_medicion(
                datos
            )

            # Firebase se ejecuta de forma desacoplada del
            # receptor UDP. Si Internet falla, Arduino y el
            # servidor local siguen funcionando normalmente.
            encolar_estado_firebase(
                datos,
                ip_origen
            )

            # El worker HTTPS corre en otro hilo. No bloquea las mediciones,
            # el control físico ni la comunicación UDP existente.
            render_bridge.encolar(datos, ip_origen)


        except UnicodeDecodeError:

            print(
                "[SEGURIDAD UDP] "
                "Datagrama no UTF-8 rechazado."
            )


        except Exception as error:

            print(
                "[UDP] Error:",
                error
            )

            time.sleep(1)

# ======================================================
# EMISOR UDP
# ======================================================

def emisor_comandos():

    global contador_comando

    while True:

        time.sleep(1)

        with estado_lock:

            ip = arduino_ip
            boot = arduino_boot
            comando = comando_actual

            if (
                not ip
                or
                not boot
            ):
                continue


            # Cada heartbeat usa un contador nuevo.
            contador_comando += 1
            ctr = contador_comando


        if ctr > 0xFFFFFFFF:

            print(
                "[SEGURIDAD UDP] "
                "CTR agotado. Reinicia el servidor/Arduino."
            )

            continue


        contenido = (
            f"TYPE=CMD;"
            f"BOOT={boot};"
            f"CTR={ctr};"
            f"CMD={comando}"
        )


        try:

            nonce = crear_nonce_comando(
                ctr
            )


            cipher_hex, tag_hex = (
                cifrar_aead(
                    contenido,
                    nonce,
                    AAD_CMD
                )
            )


            sobre = (
                "V=2;"
                "DIR=CMD;"
                f"NONCE={nonce.hex().upper()};"
                f"CT={cipher_hex};"
                f"TAG={tag_hex}"
            )


            mensaje = (
                f"{sobre};"
                f"SIG={firmar_udp(sobre)}"
            )


            udp_socket.sendto(
                mensaje.encode("utf-8"),
                (
                    ip,
                    UDP_PUERTO_ARDUINO
                )
            )


        except Exception as error:

            print(
                "[UDP] Error enviando comando:",
                error
            )

# ======================================================
# SERVIDOR HTTP
# ======================================================

class EcoHandler(BaseHTTPRequestHandler):

    def log_message(
        self,
        format,
        *args
    ):
        return


    # --------------------------------------------------
    # CABECERAS DE SEGURIDAD
    # --------------------------------------------------

    def cabeceras_seguridad(self):

        self.send_header(
            "X-Content-Type-Options",
            "nosniff"
        )

        self.send_header(
            "X-Frame-Options",
            "DENY"
        )

        self.send_header(
            "Referrer-Policy",
            "no-referrer"
        )

        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()"
        )

        self.send_header(
            "Cross-Origin-Opener-Policy",
            "same-origin"
        )

        self.send_header(
            "Cross-Origin-Resource-Policy",
            "same-origin"
        )

        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )


    # --------------------------------------------------
    # RESPUESTAS
    # --------------------------------------------------

    def responder(
        self,
        codigo,
        contenido=b"",
        tipo="text/plain; charset=utf-8",
        cabeceras_extra=None
    ):

        if isinstance(
            contenido,
            str
        ):
            contenido = contenido.encode(
                "utf-8"
            )

        self.send_response(
            codigo
        )

        self.cabeceras_seguridad()

        self.send_header(
            "Content-Type",
            tipo
        )

        self.send_header(
            "Content-Length",
            str(len(contenido))
        )

        if cabeceras_extra:

            for nombre, valor in cabeceras_extra.items():

                self.send_header(
                    nombre,
                    valor
                )

        self.end_headers()

        if contenido:

            try:

                self.wfile.write(
                    contenido
                )

            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError
            ):
                pass


    def responder_json(
        self,
        codigo,
        datos,
        cabeceras_extra=None
    ):

        contenido = json.dumps(
            datos,
            ensure_ascii=False
        )

        self.responder(
            codigo,
            contenido,
            "application/json; charset=utf-8",
            cabeceras_extra
        )


    def redirigir(
        self,
        destino
    ):

        self.send_response(
            303
        )

        self.cabeceras_seguridad()

        self.send_header(
            "Location",
            destino
        )

        self.send_header(
            "Content-Length",
            "0"
        )

        self.end_headers()


    # --------------------------------------------------
    # COOKIE DE SESION
    # --------------------------------------------------

    def cookie_sesion(
        self,
        session_id
    ):

        cookie = (
            f"{SESSION_COOKIE_NAME}="
            f"{session_id}; "
            "Path=/; "
            "HttpOnly; "
            "SameSite=Strict"
        )

        if COOKIE_SECURE:

            cookie += "; Secure"

        return cookie


    def cookie_borrar_sesion(self):

        cookie = (
            f"{SESSION_COOKIE_NAME}=; "
            "Path=/; "
            "HttpOnly; "
            "SameSite=Strict; "
            "Max-Age=0"
        )

        if COOKIE_SECURE:
            cookie += "; Secure"

        return cookie


    # --------------------------------------------------
    # OBTENER SESION
    # --------------------------------------------------

    def obtener_session_id(self):

        cabecera_cookie = self.headers.get(
            "Cookie"
        )

        if not cabecera_cookie:
            return None

        try:

            cookie = SimpleCookie()
            cookie.load(
                cabecera_cookie
            )

            item = cookie.get(
                SESSION_COOKIE_NAME
            )

            if not item:
                return None

            return item.value

        except Exception:
            return None


    def sesion_actual(self):

        session_id = self.obtener_session_id()

        sesion = obtener_sesion(
            session_id
        )

        return (
            session_id,
            sesion
        )


    # --------------------------------------------------
    # CSRF
    # --------------------------------------------------

    def csrf_valido(
        self,
        sesion
    ):

        recibido = self.headers.get(
            "X-CSRF-Token",
            ""
        )

        esperado = sesion.get(
            "csrf",
            ""
        )

        return (
            bool(recibido)
            and
            hmac.compare_digest(
                recibido,
                esperado
            )
        )


    # --------------------------------------------------
    # ARCHIVOS ESTATICOS
    # --------------------------------------------------

    def servir_archivo(
        self,
        nombre,
        tipo
    ):

        ruta = WEB_DIR / nombre

        if not ruta.exists():

            self.responder(
                404,
                "Archivo no encontrado"
            )

            return

        self.responder(
            200,
            ruta.read_bytes(),
            tipo
        )


    # ==================================================
    # GET
    # ==================================================

    def do_GET(self):

        # ----------------------------------------------
        # LOGIN
        # ----------------------------------------------

        if self.path == "/login":

            _, sesion = self.sesion_actual()

            if sesion:

                self.redirigir(
                    "/"
                )

                return

            self.servir_archivo(
                "login.html",
                "text/html; charset=utf-8"
            )

            return


        # ----------------------------------------------
        # ARCHIVOS PUBLICOS
        # ----------------------------------------------

        if self.path == "/login.css":

            self.servir_archivo(
                "login.css",
                "text/css; charset=utf-8"
            )

            return


        if self.path == "/login.js":

            self.servir_archivo(
                "login.js",
                "application/javascript; charset=utf-8"
            )

            return


        if self.path == "/styles.css":

            self.servir_archivo(
                "styles.css",
                "text/css; charset=utf-8"
            )

            return


        if self.path == "/app.js":

            self.servir_archivo(
                "app.js",
                "application/javascript; charset=utf-8"
            )

            return


        # ----------------------------------------------
        # PANEL PRINCIPAL
        # ----------------------------------------------

        if self.path == "/":

            _, sesion = self.sesion_actual()

            if not sesion:

                self.redirigir(
                    "/login"
                )

                return

            self.servir_archivo(
                "index.html",
                "text/html; charset=utf-8"
            )

            return


        # ----------------------------------------------
        # API ESTADO
        # ----------------------------------------------

        if self.path == "/api/estado":

            _, sesion = self.sesion_actual()

            if not sesion:

                self.responder_json(
                    401,
                    {
                        "ok": False,
                        "error": "sesion_no_valida"
                    }
                )

                return

            with estado_lock:

                medicion = dict(
                    ultima_medicion
                )

                ip = arduino_ip
                comando = comando_actual
                ultima = ultima_telemetria

            ahora = time.time()

            segundos = (
                ahora - ultima
                if ultima > 0
                else None
            )

            online = (
                segundos is not None
                and
                segundos <= TIEMPO_OFFLINE
            )

            if ultima > 0:

                fecha_ultima = datetime.fromtimestamp(
                    ultima
                ).strftime(
                    "%H:%M:%S"
                )

            else:

                fecha_ultima = "-"

            respuesta = {

                "ok": True,

                "usuario":
                    sesion["usuario"],

                "csrf_token":
                    sesion["csrf"],

                "comando":
                    comando,

                "arduino_ip":
                    ip if ip else "-",

                "online":
                    online,

                "segundos_sin_datos":
                    round(segundos, 1)
                    if segundos is not None
                    else None,

                "ultima_actualizacion":
                    fecha_ultima,

                "seq":
                    medicion.get(
                        "SEQ",
                        "-"
                    ),

                "id":
                    medicion.get(
                        "ID",
                        "-"
                    ),

                "sensor1":
                    medicion.get(
                        "S1_CM",
                        "-"
                    ),

                "sensor2":
                    medicion.get(
                        "S2_CM",
                        "-"
                    ),

                "modo":
                    medicion.get(
                        "MODO",
                        "-"
                    ),

                "compuerta":
                    medicion.get(
                        "COMPUERTA",
                        "-"
                    ),

                "fuente":
                    medicion.get(
                        "FUENTE",
                        "-"
                    )
            }

            self.responder_json(
                200,
                respuesta
            )

            return


        if self.path == "/favicon.ico":

            self.responder(
                204,
                b""
            )

            return


        self.responder(
            404,
            "No encontrado"
        )


    # ==================================================
    # POST
    # ==================================================

    def do_POST(self):

        global comando_actual

        # ----------------------------------------------
        # LOGIN
        # ----------------------------------------------

        if self.path == "/login":

            ip_cliente = self.client_address[0]

            restante = segundos_bloqueo(
                ip_cliente
            )

            if restante > 0:

                self.responder_json(
                    429,
                    {
                        "ok": False,
                        "error": "demasiados_intentos",
                        "retry_after": restante
                    }
                )

                return

            datos = self.leer_json(
                maximo=4096
            )

            if datos is None:

                self.responder_json(
                    400,
                    {
                        "ok": False,
                        "error": "peticion_invalida"
                    }
                )

                return

            usuario = str(
                datos.get(
                    "usuario",
                    ""
                )
            )

            password = str(
                datos.get(
                    "password",
                    ""
                )
            )

            usuario_correcto = (
                hmac.compare_digest(
                    usuario,
                    WEB_USER
                )
            )

            password_correcto = verificar_password(
                password,
                WEB_PASSWORD_HASH
            )

            if not (
                usuario_correcto
                and
                password_correcto
            ):

                registrar_login_fallido(
                    ip_cliente
                )

                self.responder_json(
                    401,
                    {
                        "ok": False,
                        "error": "credenciales_invalidas"
                    }
                )

                return

            limpiar_intentos_login(
                ip_cliente
            )

            session_id, _ = crear_sesion(
                WEB_USER
            )

            print(
                "[SEGURIDAD WEB] "
                f"Sesion iniciada desde {ip_cliente}"
            )

            self.responder_json(
                200,
                {
                    "ok": True
                },
                {
                    "Set-Cookie":
                        self.cookie_sesion(
                            session_id
                        )
                }
            )

            return


        # ----------------------------------------------
        # TODAS LAS RUTAS SIGUIENTES REQUIEREN SESION
        # ----------------------------------------------

        session_id, sesion = self.sesion_actual()

        if not sesion:

            self.responder_json(
                401,
                {
                    "ok": False,
                    "error": "sesion_no_valida"
                }
            )

            return


        # ----------------------------------------------
        # LOGOUT
        # ----------------------------------------------

        if self.path == "/logout":

            if not self.csrf_valido(
                sesion
            ):

                self.responder_json(
                    403,
                    {
                        "ok": False,
                        "error": "csrf_invalido"
                    }
                )

                return

            destruir_sesion(
                session_id
            )

            print(
                "[SEGURIDAD WEB] "
                "Sesion cerrada."
            )

            self.responder_json(
                200,
                {
                    "ok": True
                },
                {
                    "Set-Cookie":
                        self.cookie_borrar_sesion()
                }
            )

            return


        # ----------------------------------------------
        # COMANDO
        # ----------------------------------------------

        if self.path == "/api/comando":

            if not self.csrf_valido(
                sesion
            ):

                self.responder_json(
                    403,
                    {
                        "ok": False,
                        "error": "csrf_invalido"
                    }
                )

                return

            datos = self.leer_json(
                maximo=1024
            )

            if datos is None:

                self.responder_json(
                    400,
                    {
                        "ok": False,
                        "error": "json_invalido"
                    }
                )

                return

            comando = str(
                datos.get(
                    "comando",
                    ""
                )
            ).upper()

            if comando not in (
                "AUTO",
                "CERRAR",
                "ABRIR"
            ):

                self.responder_json(
                    400,
                    {
                        "ok": False,
                        "error": "comando_invalido"
                    }
                )

                return

            with estado_lock:

                comando_actual = comando

            print(
                "[CONTROL]",
                comando
            )

            self.responder_json(
                200,
                {
                    "ok": True,
                    "comando": comando
                }
            )

            return


        self.responder_json(
            404,
            {
                "ok": False,
                "error": "no_encontrado"
            }
        )


    # --------------------------------------------------
    # LEER JSON
    # --------------------------------------------------

    def leer_json(
        self,
        maximo
    ):

        try:

            longitud = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

        except ValueError:

            return None

        if (
            longitud <= 0
            or
            longitud > maximo
        ):

            return None

        try:

            cuerpo = self.rfile.read(
                longitud
            )

            return json.loads(
                cuerpo.decode(
                    "utf-8"
                )
            )

        except Exception:

            return None


# ======================================================
# MAIN
# ======================================================

if __name__ == "__main__":

    print()
    print("Directorio del servidor:")
    print(BASE_DIR)

    print()
    print("Carpeta web:")
    print(WEB_DIR)

    print()
    print(
        "index.html existe:",
        (WEB_DIR / "index.html").exists()
    )

    print(
        "login.html existe:",
        (WEB_DIR / "login.html").exists()
    )

    print(
        "styles.css existe:",
        (WEB_DIR / "styles.css").exists()
    )

    print(
        "app.js existe:",
        (WEB_DIR / "app.js").exists()
    )

    print()

    # Inicializar Firebase antes de crear su hilo.
    # Si falla, no se detiene el servidor local.
    firebase_activo = iniciar_firebase()

    if firebase_activo:
        hilo_firebase = Thread(
            target=trabajador_firebase,
            daemon=True
        )
        hilo_firebase.start()

    # El acceso a Render es opcional y no impide iniciar el servidor.
    render_bridge.iniciar()

    hilo_udp = Thread(
        target=receptor_udp,
        daemon=True
    )

    hilo_udp.start()

    hilo_comandos = Thread(
        target=emisor_comandos,
        daemon=True
    )

    hilo_comandos.start()

    # ======================================================
# VERIFICAR CERTIFICADOS
# ======================================================

if not CERT_FILE.exists():

    print(
        "ERROR: No existe:"
    )

    print(
        CERT_FILE
    )

    raise SystemExit(1)


if not KEY_FILE.exists():

    print(
        "ERROR: No existe:"
    )

    print(
        KEY_FILE
    )

    raise SystemExit(1)


# ======================================================
# CREAR SERVIDOR HTTP
# ======================================================

servidor_http = ThreadingHTTPServer(
    (
        HTTP_HOST,
        HTTP_PORT
    ),
    EcoHandler
)


# ======================================================
# CONFIGURAR TLS
# ======================================================

contexto_tls = ssl.SSLContext(
    ssl.PROTOCOL_TLS_SERVER
)


contexto_tls.minimum_version = (
    ssl.TLSVersion.TLSv1_2
)


contexto_tls.load_cert_chain(
    certfile=str(
        CERT_FILE
    ),

    keyfile=str(
        KEY_FILE
    )
)


# ======================================================
# CONVERTIR SOCKET A HTTPS
# ======================================================

servidor_http.socket = (
    contexto_tls.wrap_socket(
        servidor_http.socket,
        server_side=True)
    )

print ("========================================")

print(
        " ECO VALDIVIA V2.7B"
    )

print(
        " HTTPS + TLS + SESIONES + UDP CIFRADO"
    )

print(
        " UDP CHACHA20-POLY1305 + HMAC + ANTI-REPLAY"
    )

print(
        "========================================"
    )

print()

print(
        "Panel:"
    )

print(
        "https://127.0.0.1:8443"
    )

print()

try:

    servidor_http.serve_forever()

except KeyboardInterrupt:

    print(
            "\nServidor detenido."
        )

finally:

    servidor_http.server_close()
    udp_socket.close()
