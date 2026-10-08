"""Paquetes sintéticos con claves ficticias; nunca usa claves del entorno."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib
import os
import socket
from threading import Event, Thread
import unittest
from unittest.mock import patch, MagicMock

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import DispositivoIoT, Medicion
from app.integrations.udp_protocol import AAD_TELEMETRIA, ErrorProtocolo, validar_telemetria
from app.integrations.udp_listener import ConfigUDP, escuchar, procesar_datagrama
from config import Config
from seed import cargar_datos

HMAC_TEST = bytes(range(32))
AEAD_TEST = bytes(range(32, 64))
BOOT_TEST = "0123456789ABCDEF"


def paquete(boot=BOOT_TEST, seq=1, nonce=None, tag_invalido=False, **campos):
    datos = dict(TYPE="TEL", BOOT=boot, SEQ=str(seq), ID="42", S1_CM="75.5",
                 S2_CM="124.5", MODO="AUTO", COMPUERTA="CERRADA",
                 FUENTE="LOCAL", LAST_CMD_CTR="2")
    datos.update(campos)
    nonce = nonce or bytes.fromhex(boot) + seq.to_bytes(4, "big")
    plano = ";".join(f"{k}={v}" for k, v in datos.items())
    cifrado = ChaCha20Poly1305(AEAD_TEST).encrypt(nonce, plano.encode(), AAD_TELEMETRIA)
    tag = bytes(16) if tag_invalido else cifrado[-16:]
    sobre = f"V=2;DIR=TEL;NONCE={nonce.hex()};CT={cifrado[:-16].hex()};TAG={tag.hex()}"
    return firmar(sobre)


def firmar(sobre):
    firma = hmac.new(HMAC_TEST, sobre.encode(), hashlib.sha256).hexdigest()
    return f"{sobre};SIG={firma}".encode()


class ProtocoloTests(unittest.TestCase):
    def validar(self, mensaje, **estado):
        return validar_telemetria(mensaje, HMAC_TEST, AEAD_TEST,
                                 dispositivo_identificador="DEMO-IOT-01",
                                 ip_origen="192.0.2.10", **estado)

    def test_hmac_nonce_y_normalizacion_validos(self):
        datos = self.validar(paquete(MODO="manual", COMPUERTA="abierta"))
        self.assertEqual(datos["sensor1_cm"], 75.5)
        self.assertEqual(datos["sensor2_cm"], 124.5)
        self.assertEqual(datos["seq"], 1)
        self.assertEqual(datos["last_cmd_ctr"], 2)
        self.assertEqual(datos["medicion_externa_id"], "42")
        self.assertEqual(datos["fuente"], "REAL")
        self.assertEqual(datos["modo"], "MANUAL")
        self.assertEqual(datos["compuerta"], "ABIERTA")
        self.assertEqual(datos["fecha_recepcion"].tzinfo, timezone.utc)

    def test_hmac_invalido(self):
        mensaje = paquete()
        mensaje = mensaje[:-1] + (b"0" if mensaje[-1:] != b"0" else b"1")
        with self.assertRaises(ErrorProtocolo) as error:
            self.validar(mensaje)
        self.assertEqual(error.exception.codigo, "hmac")

    def test_tag_invalido(self):
        with self.assertRaises(ErrorProtocolo) as error:
            self.validar(paquete(tag_invalido=True))
        self.assertEqual(error.exception.codigo, "aead")

    def test_nonce_incoherente_con_tag_valido(self):
        with self.assertRaises(ErrorProtocolo) as error:
            self.validar(paquete(nonce=bytes(12)))
        self.assertEqual(error.exception.codigo, "nonce")

    def test_seq_repetido_o_anterior(self):
        for seq in (0, 1):
            with self.subTest(seq=seq), self.assertRaises(ErrorProtocolo) as error:
                self.validar(paquete(seq=seq), ultimo_boot=BOOT_TEST, ultimo_seq=1)
            self.assertEqual(error.exception.codigo, "replay")

    def test_boot_nuevo_y_salto_seq(self):
        nuevo = "FEDCBA9876543210"
        self.assertEqual(self.validar(paquete(boot=nuevo, seq=0), ultimo_boot=BOOT_TEST,
                                     ultimo_seq=100)["boot"], nuevo)
        self.assertEqual(self.validar(paquete(seq=10), ultimo_boot=BOOT_TEST,
                                     ultimo_seq=1)["seq"], 10)

    def test_sobre_invalido_y_campos_duplicados(self):
        sobre = paquete().decode().split(";SIG=")[0]
        for invalido in (sobre.replace("V=2", "V=3"), sobre.replace("DIR=TEL", "DIR=CMD"),
                         sobre + ";V=2", sobre.replace("NONCE=", "NONCE=00")):
            with self.subTest(invalido=invalido[:30]), self.assertRaises(ErrorProtocolo):
                self.validar(firmar(invalido))

    def test_importar_no_abre_socket(self):
        with patch("socket.socket") as constructor:
            importlib.reload(importlib.import_module("app.integrations.udp_listener"))
            importlib.reload(importlib.import_module("udp_worker"))
            constructor.assert_not_called()

    def test_configuracion_claves_y_puerto(self):
        entorno = dict(ECOV_UDP_DEVICE_ID="DEMO-IOT-01", ECOV_UDP_HMAC_KEY_HEX=HMAC_TEST.hex(),
                       ECOV_UDP_AEAD_KEY_HEX=AEAD_TEST.hex())
        with patch.dict(os.environ, entorno, clear=True):
            config = ConfigUDP.desde_entorno()
            self.assertEqual(config.puerto, 4211)
            self.assertNotIn(HMAC_TEST.hex(), repr(config))
        for variable in ("ECOV_UDP_HMAC_KEY_HEX", "ECOV_UDP_AEAD_KEY_HEX", "ECOV_UDP_PORT", "ECOV_UDP_DEVICE_ID"):
            with patch.dict(os.environ, {**entorno, variable: ""}, clear=True), self.assertRaises(ValueError):
                ConfigUDP.desde_entorno()


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class IntegracionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        cargar_datos()
        self.config = ConfigUDP("DEMO-IOT-01", HMAC_TEST, AEAD_TEST)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def recibir(self, mensaje, config=None):
        return procesar_datagrama(mensaje, "192.0.2.10", config or self.config)

    def test_persistencia_replay_y_reinicio(self):
        self.assertTrue(self.recibir(paquete()))
        dispositivo = db.session.scalar(db.select(DispositivoIoT))
        self.assertEqual((dispositivo.ultimo_boot, dispositivo.ultimo_seq), (BOOT_TEST, 1))
        self.assertEqual(dispositivo.contenedor.porcentaje_llenado, 50)
        db.session.remove()  # Simula otra sesión / reinicio del worker.
        self.assertFalse(self.recibir(paquete()))
        self.assertFalse(self.recibir(paquete(seq=0)))
        self.assertTrue(self.recibir(paquete(boot="FEDCBA9876543210", seq=0)))
        # Cambio al BOOT original: restricción única todavía rechaza la repetición.
        self.assertFalse(self.recibir(paquete()))
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Medicion)), 2)

    def test_dispositivo_desconocido(self):
        config = ConfigUDP("no-existe", HMAC_TEST, AEAD_TEST)
        self.assertFalse(self.recibir(paquete(), config))

    def test_muestreo_no_rompe_antireplay_persistente(self):
        fecha = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        self.assertTrue(procesar_datagrama(paquete(), "192.0.2.10", self.config, fecha))
        self.assertTrue(procesar_datagrama(paquete(seq=2), "192.0.2.10", self.config, fecha + timedelta(seconds=2)))
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Medicion)), 1)
        db.session.remove()
        self.assertFalse(procesar_datagrama(paquete(seq=2), "192.0.2.10", self.config, fecha + timedelta(seconds=4)))
        self.assertEqual(db.session.scalar(db.select(DispositivoIoT)).ultimo_seq, 2)

    def test_validacion_fisica_no_avanza_seq(self):
        for valor in ("-1", "nan", "inf", "abc"):
            self.assertFalse(self.recibir(paquete(S1_CM=valor)))
        self.assertIsNone(db.session.scalar(db.select(DispositivoIoT)).ultimo_seq)
        self.assertTrue(self.recibir(paquete()))

    def test_error_bd_y_reintento(self):
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            self.assertFalse(self.recibir(paquete()))
        self.assertIsNone(db.session.scalar(db.select(DispositivoIoT)).ultimo_seq)
        self.assertTrue(self.recibir(paquete()))

    def test_socket_configuracion_y_cierre_limpio(self):
        detener = Event()
        detener.set()
        receptor = MagicMock()
        with patch("app.integrations.udp_listener.socket.socket") as constructor:
            constructor.return_value.__enter__.return_value = receptor
            escuchar(self.app, self.config, detener)
            receptor.bind.assert_called_once_with(("0.0.0.0", 4211))
            receptor.settimeout.assert_called_once_with(1.0)
            receptor.setsockopt.assert_called_once()
            receptor.recvfrom.assert_not_called()
            constructor.return_value.__exit__.assert_called_once()

    def test_listener_loopback_con_datagrama_real(self):
        detener, listo, procesado = Event(), Event(), Event()
        resultado, errores, puerto = [], [], []
        socket_real = socket.socket

        class ReceptorPrueba(socket_real):
            def bind(self, direccion):
                super().bind(direccion)
                puerto.append(self.getsockname()[1])
                listo.set()

        def recibir(*args):
            resultado.append(procesar_datagrama(*args))
            detener.set()
            procesado.set()

        def ejecutar():
            try:
                escuchar(self.app, ConfigUDP("DEMO-IOT-01", HMAC_TEST, AEAD_TEST, "127.0.0.1", 0), detener)
            except Exception as error:
                errores.append(error)
                listo.set()
                procesado.set()

        # Sin lecturas concurrentes sobre SQLite en memoria; consultar al terminar.
        db.session.remove()
        with patch("app.integrations.udp_listener.socket.socket", ReceptorPrueba), \
                patch("app.integrations.udp_listener.procesar_datagrama", side_effect=recibir):
            hilo = Thread(target=ejecutar, daemon=True)
            hilo.start()
            try:
                self.assertTrue(listo.wait(5), "El listener no abrió su socket.")
                self.assertFalse(errores)
                with socket_real(socket.AF_INET, socket.SOCK_DGRAM) as emisor:
                    emisor.sendto(paquete(S1_CM="25", S2_CM="25"), ("127.0.0.1", puerto[0]))
                self.assertTrue(procesado.wait(5), "El listener no procesó el datagrama.")
            finally:
                detener.set()
                hilo.join(3)
        self.assertFalse(hilo.is_alive())
        self.assertFalse(errores)
        self.assertEqual(resultado, [True])
        self.assertEqual(db.session.scalar(db.select(DispositivoIoT)).ultimo_seq, 1)
        self.assertEqual(db.session.scalar(db.select(Medicion)).porcentaje_llenado, 100)


if __name__ == "__main__":
    unittest.main()
