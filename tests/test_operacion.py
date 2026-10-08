"""Alertas, vaciados y muestreo de historial con estado persistente."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Alerta, DispositivoIoT, EventoOperacional, Medicion, Usuario
from app.services.medicion_service import procesar_medicion
from app.services.operacion_service import ESTADO_TRAS_VACIADO, registrar_vaciado
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class OperacionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        cargar_datos()
        self.dispositivo = db.session.scalar(db.select(DispositivoIoT))
        self.contenedor = self.dispositivo.contenedor
        self.usuario = db.session.scalar(db.select(Usuario).where(Usuario.rol == "operador"))
        self.fecha = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def lectura(self, seq=0, segundos=0, **cambios):
        datos = dict(dispositivo_identificador=self.dispositivo.identificador,
                     sensor1_cm=25, sensor2_cm=25, modo="AUTO", compuerta="CERRADA",
                     fuente="REAL", boot="boot-1", seq=seq, ip_origen="192.0.2.1",
                     fecha_recepcion=self.fecha + timedelta(seconds=segundos))
        datos.update(cambios)
        return procesar_medicion(datos)

    def cantidad(self, modelo):
        return db.session.scalar(db.select(db.func.count()).select_from(modelo))

    def test_alerta_al_llenarse_y_no_duplicar(self):
        self.lectura(sensor1_cm=175, sensor2_cm=175)
        self.assertEqual(self.cantidad(Alerta), 0)
        self.lectura(seq=1, segundos=2)
        alerta = db.session.scalar(db.select(Alerta))
        self.assertTrue(alerta.activa)
        self.assertEqual(alerta.tipo, "LLENO")
        self.assertEqual(alerta.contenedor_id, self.contenedor.id)
        self.assertEqual(alerta.creada_en, (self.fecha + timedelta(seconds=2)).replace(tzinfo=None))
        self.lectura(seq=2, segundos=4)
        self.lectura(seq=3, segundos=64)
        self.assertEqual(self.cantidad(Alerta), 1)

    def test_vaciado_cierra_alerta_crea_evento_y_conserva_historial(self):
        medicion = self.lectura()
        previo_boot, previo_seq = self.dispositivo.ultimo_boot, self.dispositivo.ultimo_seq
        evento = registrar_vaciado(self.contenedor.id, self.usuario.id)
        alerta = db.session.scalar(db.select(Alerta))
        self.assertFalse(alerta.activa)
        self.assertIsNotNone(alerta.cerrada_en)
        self.assertEqual(evento.tipo, "VACIADO")
        self.assertEqual(evento.usuario_id, self.usuario.id)
        self.assertIn("cerradas: 1", evento.descripcion)
        self.assertEqual(self.contenedor.estado, ESTADO_TRAS_VACIADO)
        self.assertIsNone(self.contenedor.porcentaje_llenado)
        self.assertEqual(self.cantidad(Medicion), 1)
        self.assertEqual(db.session.get(Medicion, medicion.id).porcentaje_llenado, 100)
        self.assertEqual((self.dispositivo.ultimo_boot, self.dispositivo.ultimo_seq), (previo_boot, previo_seq))
        self.lectura(seq=1, segundos=2, sensor1_cm=175, sensor2_cm=175)
        self.lectura(seq=2, segundos=4)
        self.assertEqual(self.cantidad(Alerta), 2)
        activas = db.session.scalars(db.select(Alerta).where(Alerta.activa.is_(True))).all()
        self.assertEqual(len(activas), 1)

    def test_lectura_no_persistida_actualiza_estado_y_antireplay(self):
        primera = self.lectura(sensor1_cm=100, sensor2_cm=100)
        segunda = self.lectura(seq=1, segundos=2, sensor1_cm=90, sensor2_cm=90, ip_origen="192.0.2.2")
        self.assertIsNotNone(primera.id)
        self.assertIsNone(segunda.id)
        self.assertEqual(self.cantidad(Medicion), 1)
        db.session.expire_all()
        self.assertEqual(self.dispositivo.ultimo_seq, 1)
        self.assertEqual(self.dispositivo.ultima_ip, "192.0.2.2")
        self.assertEqual(self.dispositivo.ultima_actualizacion, (self.fecha + timedelta(seconds=2)).replace(tzinfo=None))
        self.assertAlmostEqual(self.contenedor.porcentaje_llenado, 56.66666667)
        self.assertEqual(self.contenedor.ultima_actualizacion, self.dispositivo.ultima_actualizacion)
        for seq in (0, 1):
            with self.assertRaisesRegex(ValueError, "replay"):
                self.lectura(seq=seq, segundos=4)
        self.assertEqual(self.dispositivo.ultimo_seq, 1)

    def test_identica_antes_60_no_persiste_y_a_60_si(self):
        self.lectura()
        self.assertIsNone(self.lectura(seq=1, segundos=2).id)
        self.assertIsNone(self.lectura(seq=2, segundos=59).id)
        self.assertIsNotNone(self.lectura(seq=3, segundos=60).id)
        self.assertEqual(self.cantidad(Medicion), 2)

    def test_cambios_estado_modo_compuerta_boot_persisten(self):
        self.lectura()
        self.assertIsNotNone(self.lectura(seq=1, segundos=2, sensor1_cm=100, sensor2_cm=100).id)
        self.assertIsNotNone(self.lectura(seq=2, segundos=4, sensor1_cm=100, sensor2_cm=100, modo="MANUAL").id)
        self.assertIsNotNone(self.lectura(seq=3, segundos=6, sensor1_cm=100, sensor2_cm=100, modo="MANUAL", compuerta="ABIERTA").id)
        self.assertIsNotNone(self.lectura(seq=0, segundos=8, sensor1_cm=100, sensor2_cm=100, modo="MANUAL", compuerta="ABIERTA", boot="boot-2").id)
        self.assertEqual(self.cantidad(Medicion), 5)

    def test_alerta_unica_en_base_de_datos(self):
        self.lectura()
        db.session.add(Alerta(contenedor_id=self.contenedor.id, tipo="LLENO", mensaje="Duplicada",
                             activa=True, creada_en=self.fecha.replace(tzinfo=None)))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_fallo_vaciado_revierte_alerta_evento_y_estado(self):
        self.lectura()
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            with self.assertRaises(SQLAlchemyError):
                registrar_vaciado(self.contenedor.id, self.usuario.id)
        self.assertTrue(db.session.scalar(db.select(Alerta)).activa)
        self.assertEqual(self.cantidad(EventoOperacional), 0)
        self.assertEqual(self.contenedor.estado, "Lleno")

    def test_fallo_lectura_no_persistida_no_avanza_seq(self):
        self.lectura()
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            with self.assertRaises(SQLAlchemyError):
                self.lectura(seq=1, segundos=2)
        self.assertEqual(self.dispositivo.ultimo_seq, 0)
        self.assertEqual(self.cantidad(Medicion), 1)

    def token(self):
        self.client.get("/login")
        self.client.get("/")
        with self.client.session_transaction() as sesion:
            return sesion["csrf_token"]

    def login(self, usuario, password):
        self.client.post("/login", data={"username": usuario, "password": password, "csrf_token": self.token()})

    def test_anonimo_no_accede_y_post_tiene_csrf(self):
        self.lectura()
        ruta = f"/operacion/contenedores/{self.contenedor.id}/vaciado"
        for path in ("/operacion/alertas", "/operacion/historial"):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.client.post(ruta).status_code, 302)
        self.assertEqual(self.cantidad(EventoOperacional), 0)
        self.login("operador", "Operador123!")
        self.assertEqual(self.client.post(ruta).status_code, 400)
        self.assertEqual(self.cantidad(EventoOperacional), 0)

    def test_operador_y_administrador_acceden_y_registran(self):
        self.lectura()
        ruta = f"/operacion/contenedores/{self.contenedor.id}/vaciado"
        for nombre, password in (("operador", "Operador123!"), ("admin", "Admin123!")):
            self.login(nombre, password)
            for path in ("/operacion/alertas", "/operacion/historial", "/panel"):
                self.assertEqual(self.client.get(path).status_code, 200)
            self.assertIn("Historial operacional", self.client.get("/panel").get_data(as_text=True))
            respuesta = self.client.post(ruta, data={"csrf_token": self.token()}, follow_redirects=True)
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("Pendiente de lectura", respuesta.get_data(as_text=True))
            evento = db.session.scalar(db.select(EventoOperacional).order_by(EventoOperacional.id.desc()))
            self.assertEqual(evento.usuario.username, nombre)
            self.assertIn("VACIADO", self.client.get("/operacion/historial").get_data(as_text=True))
            self.client.post("/logout", data={"csrf_token": self.token()})


if __name__ == "__main__":
    unittest.main()
