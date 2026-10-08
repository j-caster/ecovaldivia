"""Confirmación persistente, panel protegido e integración con telemetría."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Alerta, Contenedor, DispositivoIoT, Medicion, Usuario
from app.services.confirmacion_service import confirmar_llenado
from app.services.medicion_service import procesar_medicion
from app.services.operacion_service import registrar_vaciado
from app.services.panel_service import conectividad
from config import Config
from migrate_hito8 import actualizar_confirmacion
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class PanelConfirmacionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.contexto = self.app.app_context()
        self.contexto.push()
        db.create_all()
        cargar_datos()
        self.client = self.app.test_client()
        self.fecha = datetime.now(timezone.utc)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.contexto.pop()

    def dispositivo(self):
        return db.session.scalar(db.select(DispositivoIoT).where(
            DispositivoIoT.identificador == "DEMO-IOT-01"))

    def lectura(self, seq, distancia=32.5, boot="BOOT-1", **cambios):
        datos = dict(dispositivo_identificador="DEMO-IOT-01", sensor1_cm=distancia,
                     sensor2_cm=distancia, fuente="REAL", modo="AUTO", compuerta="CERRADA",
                     boot=boot, seq=seq, fecha_recepcion=self.fecha + timedelta(seconds=seq))
        datos.update(cambios)
        return procesar_medicion(datos)

    def cantidad(self, modelo):
        return db.session.scalar(db.select(db.func.count()).select_from(modelo))

    def login(self, username, password):
        self.client.get("/login")
        with self.client.session_transaction() as sesion:
            token = sesion["csrf_token"]
        return self.client.post("/login", data={"username": username, "password": password, "csrf_token": token})

    def test_tres_lecturas_y_segunda_no_persistida(self):
        self.lectura(0)
        self.assertEqual(self.dispositivo().contador_lleno, 1)
        self.assertEqual(self.dispositivo().contenedor.estado, "Casi lleno")
        self.assertEqual(self.cantidad(Alerta), 0)
        db.session.remove()  # Una nueva sesión no pierde la confirmación.
        segunda = self.lectura(1)
        self.assertIsNone(segunda.id)
        self.assertEqual(self.dispositivo().contador_lleno, 2)
        self.assertEqual(self.cantidad(Alerta), 0)
        self.assertEqual(self.dispositivo().ultimo_seq, 1)
        tercera = self.lectura(2)
        self.assertIsNotNone(tercera.id)
        self.assertEqual(self.dispositivo().contenedor.estado, "Lleno")
        self.assertEqual(self.dispositivo().contenedor.porcentaje_llenado, 95)
        self.assertEqual(self.cantidad(Alerta), 1)
        self.assertEqual(self.cantidad(Medicion), 2)
        self.lectura(3)
        self.assertEqual(self.dispositivo().contador_lleno, 3)
        self.assertEqual(self.cantidad(Alerta), 1)

    def test_lectura_bajo_umbral_reinicia(self):
        self.lectura(0)
        self.lectura(1)
        self.lectura(2, distancia=34)
        self.assertEqual(self.dispositivo().contador_lleno, 0)
        self.lectura(3)
        self.lectura(4)
        self.assertEqual(self.cantidad(Alerta), 0)
        self.lectura(5)
        self.assertEqual(self.cantidad(Alerta), 1)

    def test_boot_nuevo_reinicia(self):
        self.lectura(0)
        self.lectura(1)
        self.lectura(0, boot="BOOT-2")
        self.assertEqual(self.dispositivo().contador_lleno, 1)
        self.assertEqual(self.dispositivo().boot_confirmacion, "BOOT-2")
        self.assertEqual(self.cantidad(Alerta), 0)
        self.lectura(1, boot="BOOT-2")
        self.lectura(2, boot="BOOT-2")
        self.assertEqual(self.cantidad(Alerta), 1)

    def test_vaciado_reinicia_y_necesita_tres_lecturas_nuevas(self):
        for seq in range(3):
            self.lectura(seq)
        dispositivo = self.dispositivo()
        operador = db.session.scalar(db.select(Usuario).where(Usuario.rol == "operador"))
        registrar_vaciado(dispositivo.contenedor_id, operador.id)
        self.assertEqual(dispositivo.contador_lleno, 0)
        self.assertIsNone(dispositivo.boot_confirmacion)
        self.assertEqual(dispositivo.ultimo_seq, 2)
        self.lectura(3)
        self.lectura(4)
        self.assertEqual(self.cantidad(Alerta), 1)
        self.lectura(5)
        self.assertEqual(self.cantidad(Alerta), 2)

    def test_replay_e_invalida_no_cuentan_y_fallo_bd_revierte(self):
        self.lectura(0)
        with self.assertRaises(ValueError):
            self.lectura(0)
        with self.assertRaises(ValueError):
            self.lectura(1, distancia=-1)
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            with self.assertRaises(SQLAlchemyError):
                self.lectura(1)
        self.assertEqual(self.dispositivo().contador_lleno, 1)
        self.assertEqual(self.dispositivo().ultimo_seq, 0)
        self.lectura(1)
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            with self.assertRaises(SQLAlchemyError):
                self.lectura(2)
        self.assertEqual(self.cantidad(Alerta), 0)
        self.assertEqual(self.dispositivo().contador_lleno, 2)

    def test_confirmacion_no_se_comparte_entre_dispositivos(self):
        otro_contenedor = db.session.scalar(db.select(Contenedor).where(
            Contenedor.id != self.dispositivo().contenedor_id))
        db.session.add(DispositivoIoT(identificador="OTRO", contenedor_id=otro_contenedor.id))
        db.session.commit()
        self.lectura(0)
        self.lectura(1)
        self.lectura(0, dispositivo_identificador="OTRO")
        self.assertEqual(self.cantidad(Alerta), 0)
        self.assertEqual(self.dispositivo().contador_lleno, 2)

    def test_endpoint_requiere_autenticacion(self):
        for path in ("/panel", "/panel/datos"):
            respuesta = self.client.get(path)
            self.assertEqual(respuesta.status_code, 302)
            self.assertIn("/login", respuesta.location)

    def test_operador_y_admin_endpoint_minimo_y_panel(self):
        self.lectura(0)
        for nombre, password in (("operador", "Operador123!"), ("admin", "Admin123!")):
            self.login(nombre, password)
            respuesta = self.client.get("/panel/datos")
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.headers["Cache-Control"], "no-store")
            fila = next(c for c in respuesta.json["contenedores"] if c["codigo"] == "DEMO-CENTRO-01")
            self.assertEqual(set(fila), {"codigo", "punto", "porcentaje", "estado", "modo", "compuerta", "ultima_actualizacion", "alerta", "conectividad"})
            self.assertEqual(fila["conectividad"], "ONLINE")
            self.assertEqual(fila["estado"], "Casi lleno")
            html = self.client.get("/panel").get_data(as_text=True)
            self.assertIn('data-intervalo="5000"', html)
            self.assertIn('data-endpoint="/panel/datos"', html)
            self.assertIn("js/panel.js", html)
            self.assertIn("DEMO-CENTRO-01", html)
            with self.client.session_transaction() as sesion:
                token = sesion["csrf_token"]
            self.client.post("/logout", data={"csrf_token": token})

    def test_online_limite_offline_y_sin_dispositivo(self):
        self.lectura(0)
        dispositivo = self.dispositivo()
        self.assertEqual(conectividad(dispositivo, self.fecha + timedelta(seconds=15)), "ONLINE")
        self.assertEqual(conectividad(dispositivo, self.fecha + timedelta(seconds=15.01)), "OFFLINE")
        self.assertEqual(conectividad(None, self.fecha), "OFFLINE")
        dispositivo.ultima_actualizacion = None
        self.assertEqual(conectividad(dispositivo, self.fecha), "OFFLINE")

    def test_endpoint_refleja_udp_real_sin_cambiar_listener(self):
        from app.integrations.udp_listener import ConfigUDP, procesar_datagrama
        from test_udp import HMAC_TEST, AEAD_TEST, paquete
        config = ConfigUDP("DEMO-IOT-01", HMAC_TEST, AEAD_TEST)
        self.login("operador", "Operador123!")
        for seq in range(1, 4):
            # El worker y HTTP tienen app_context y sesiones independientes.
            with self.app.app_context():
                self.assertTrue(procesar_datagrama(paquete(seq=seq, S1_CM="32.5", S2_CM="32.5"), "192.0.2.10", config))
            db.session.expire_all()
            fila = next(c for c in self.client.get("/panel/datos").json["contenedores"] if c["codigo"] == "DEMO-CENTRO-01")
            self.assertEqual(fila["estado"], "Casi lleno" if seq < 3 else "Lleno")
            self.assertEqual(fila["conectividad"], "ONLINE")
            self.assertEqual(fila["alerta"] is not None, seq == 3)
        dispositivo = self.dispositivo()
        dispositivo.ultima_actualizacion = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=16)
        db.session.commit()
        fila = next(c for c in self.client.get("/panel/datos").json["contenedores"] if c["codigo"] == "DEMO-CENTRO-01")
        self.assertEqual(fila["conectividad"], "OFFLINE")


class ConfirmacionPuraTests(unittest.TestCase):
    def test_umbral_y_estados_no_criticos(self):
        self.assertEqual(confirmar_llenado(95, "Casi lleno", "A", "A", 2), ("Lleno", 3))
        self.assertEqual(confirmar_llenado(94.99, "Casi lleno", "A", "A", 2), ("Casi lleno", 0))
        for porcentaje, estado in ((20, "Disponible"), (60, "Medio"), (90, "Casi lleno")):
            self.assertEqual(confirmar_llenado(porcentaje, estado, "A", "A", 3), (estado, 0))

    def test_migracion_idempotente_conserva_datos(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as conexion:
                conexion.execute(text("CREATE TABLE dispositivo_iot (id INTEGER PRIMARY KEY, identificador VARCHAR(100))"))
                conexion.execute(text("INSERT INTO dispositivo_iot VALUES (1, 'existente')"))
            actualizar_confirmacion(engine)
            actualizar_confirmacion(engine)
            with engine.connect() as conexion:
                fila = conexion.execute(text("SELECT identificador, contador_lleno, boot_confirmacion FROM dispositivo_iot")).one()
                self.assertEqual(tuple(fila), ("existente", 0, None))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
