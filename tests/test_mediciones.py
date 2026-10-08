"""Dominio, restricciones y simulación administrativa con SQLite en memoria."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Contenedor, DispositivoIoT, Medicion
from app.services.medicion_service import calcular_llenado, procesar_medicion
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class CalculoTests(unittest.TestCase):
    def test_porcentajes_limites_y_promedio(self):
        for distancia, porcentaje, estado in (
            (175, 0, "Disponible"), (100, 50, "Medio"),
            (25, 100, "Lleno"), (200, 0, "Disponible"),
            (10, 100, "Lleno"), (55, 80, "Casi lleno"),
            (55.01, (175 - 55.01) / 150 * 100, "Medio"),
            (100.01, (175 - 100.01) / 150 * 100, "Disponible"),
        ):
            with self.subTest(distancia=distancia):
                resultado, etiqueta = calcular_llenado(distancia, distancia)
                self.assertAlmostEqual(resultado, porcentaje)
                self.assertEqual(etiqueta, estado)
        self.assertEqual(calcular_llenado(75, 125), (50, "Medio"))


class MedicionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        cargar_datos()
        self.dispositivo = db.session.scalar(db.select(DispositivoIoT))
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def datos(self, **cambios):
        return {
            "dispositivo_identificador": self.dispositivo.identificador,
            "medicion_externa_id": 42, "sensor1_cm": 75, "sensor2_cm": 125,
            "modo": "AUTO", "compuerta": "CERRADA", "fuente": "REAL",
            "boot": "arranque-1", "seq": 0, "last_cmd_ctr": 2,
            "ip_origen": "192.168.1.25", **cambios,
        }

    def cantidad(self):
        return db.session.scalar(db.select(db.func.count()).select_from(Medicion))

    def test_persistencia_y_actualizaciones(self):
        fecha = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        medicion = procesar_medicion(self.datos(fecha_recepcion=fecha))
        db.session.expire_all()
        guardada = db.session.get(Medicion, medicion.id)
        self.assertEqual(self.cantidad(), 1)
        self.assertEqual(guardada.dispositivo_id, self.dispositivo.id)
        self.assertEqual(guardada.medicion_externa_id, "42")
        self.assertEqual((guardada.sensor1_cm, guardada.sensor2_cm), (75, 125))
        self.assertEqual((guardada.porcentaje_llenado, guardada.estado_calculado), (50, "Medio"))
        self.assertEqual(guardada.last_cmd_ctr, 2)
        self.assertEqual(guardada.recibida_en, fecha.replace(tzinfo=None))
        dispositivo = self.dispositivo
        self.assertEqual((dispositivo.modo_actual, dispositivo.compuerta_actual), ("AUTO", "CERRADA"))
        self.assertEqual(dispositivo.ultima_ip, "192.168.1.25")
        self.assertEqual((dispositivo.ultimo_boot, dispositivo.ultimo_seq), ("arranque-1", 0))
        self.assertEqual(dispositivo.ultima_actualizacion, guardada.recibida_en)
        contenedor = dispositivo.contenedor
        self.assertEqual((contenedor.porcentaje_llenado, contenedor.estado), (50, "Medio"))
        self.assertEqual(contenedor.ultima_actualizacion, guardada.recibida_en)

    def test_sensores_invalidos(self):
        for campo in ("sensor1_cm", "sensor2_cm"):
            for valor in (None, "abc", 0, -1, float("nan"), float("inf"), True):
                with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                    procesar_medicion(self.datos(**{campo: valor}))
        self.assertEqual(self.cantidad(), 0)

    def test_campos_invalidos_no_modifican_estado(self):
        anterior = self.dispositivo.contenedor.porcentaje_llenado
        for campo, valor in (
            ("modo", "OTRO"), ("compuerta", "OTRA"), ("fuente", "OTRA"),
            ("boot", None), ("boot", ""), ("seq", -1), ("seq", 1.5),
            ("seq", True), ("seq", "1.2"), ("last_cmd_ctr", -1),
            ("last_cmd_ctr", 2.5), ("dispositivo_identificador", "42"),
            ("ip_origen", "no-ip"), ("fecha_recepcion", "hoy"),
        ):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                procesar_medicion(self.datos(**{campo: valor}))
        self.assertEqual(self.cantidad(), 0)
        self.assertIsNone(self.dispositivo.ultimo_seq)
        self.assertEqual(self.dispositivo.contenedor.porcentaje_llenado, anterior)

    def test_duplicados_y_identidad(self):
        procesar_medicion(self.datos())
        with self.assertRaisesRegex(ValueError, "duplicada"):
            procesar_medicion(self.datos(sensor1_cm=25, sensor2_cm=25, medicion_externa_id=999))
        self.assertEqual(self.cantidad(), 1)
        self.assertEqual(self.dispositivo.contenedor.porcentaje_llenado, 50)
        # El mismo ID externo no impide una nueva secuencia ni identifica al dispositivo.
        procesar_medicion(self.datos(seq=1))
        procesar_medicion(self.datos(boot="arranque-2", seq=0))
        self.assertEqual(self.cantidad(), 2)

    def test_simulacion_y_dispositivos_inactivos(self):
        medicion = procesar_medicion(self.datos(fuente="SIMULACION", boot=None, last_cmd_ctr=None))
        self.assertTrue(medicion.boot.startswith("sim-"))
        self.assertIsNone(medicion.last_cmd_ctr)
        for objeto in (self.dispositivo, self.dispositivo.contenedor):
            objeto.activo = False
            db.session.commit()
            with self.assertRaises(ValueError):
                procesar_medicion(self.datos(seq=3))
            objeto.activo = True
            db.session.commit()

    def test_restricciones_base_datos(self):
        db.session.add(DispositivoIoT(identificador="otro", contenedor_id=self.dispositivo.contenedor_id))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(DispositivoIoT(identificador="retirado", contenedor_id=self.dispositivo.contenedor_id, activo=False))
        db.session.commit()
        db.session.add(DispositivoIoT(identificador=self.dispositivo.identificador, contenedor_id=self.dispositivo.contenedor_id, activo=False))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        medicion = procesar_medicion(self.datos())
        for campo, valor in (("seq", -1), ("porcentaje_llenado", -1), ("porcentaje_llenado", 101)):
            setattr(medicion, campo, valor)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()
        copia = {col.name: getattr(medicion, col.name) for col in Medicion.__table__.columns if col.name != "id"}
        db.session.add(Medicion(**copia))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_error_persistencia_revierte_todos_los_cambios(self):
        previo = self.dispositivo.contenedor.porcentaje_llenado
        for error in (SQLAlchemyError("fallo"), IntegrityError("insert", {}, Exception())):
            with patch.object(db.session, "commit", side_effect=error):
                with self.assertRaises((SQLAlchemyError, ValueError)):
                    procesar_medicion(self.datos())
            self.assertEqual(self.cantidad(), 0)
            self.assertIsNone(self.dispositivo.ultimo_seq)
            self.assertEqual(self.dispositivo.contenedor.porcentaje_llenado, previo)

    def token(self):
        self.client.get("/login")
        self.client.get("/")
        with self.client.session_transaction() as sesion:
            return sesion["csrf_token"]

    def login(self, usuario, password):
        self.client.post("/login", data={"username": usuario, "password": password, "csrf_token": self.token()})

    def test_simulacion_protegida_y_historial(self):
        ruta = "/admin/mediciones/simular"
        historial = f"/admin/dispositivos/{self.dispositivo.id}/mediciones"
        for path in (ruta, historial):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.client.post(ruta, data=self.datos()).status_code, 302)
        self.login("operador", "Operador123!")
        for path in (ruta, historial):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post(ruta, data={**self.datos(), "csrf_token": self.token()}).status_code, 403)
        self.assertEqual(self.cantidad(), 0)
        self.client.post("/logout", data={"csrf_token": self.token()})
        self.login("admin", "Admin123!")
        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertEqual(self.client.post(ruta, data=self.datos()).status_code, 400)
        respuesta = self.client.post(ruta, data={**self.datos(), "csrf_token": self.token()}, follow_redirects=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("50.00%", respuesta.get_data(as_text=True))
        self.assertIn("SIMULACION", respuesta.get_data(as_text=True))
        self.assertEqual(self.cantidad(), 1)
        self.assertEqual(db.session.scalar(db.select(Medicion)).fuente, "SIMULACION")
        respuesta = self.client.post(ruta, data={**self.datos(sensor1_cm=-1), "csrf_token": self.token()})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("positivo", respuesta.get_data(as_text=True))
        self.assertEqual(self.cantidad(), 1)

    def test_seed_idempotente(self):
        cargar_datos()
        self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(DispositivoIoT)), 1)
        self.assertEqual(self.dispositivo.contenedor.codigo, "DEMO-CENTRO-01")


if __name__ == "__main__":
    unittest.main()
