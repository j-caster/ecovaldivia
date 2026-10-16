"""Fechas de presentación en Chile; persistencia y timestamps JSON en UTC."""

from datetime import datetime, timedelta, timezone
import unittest

from app import create_app
from app.extensions import db
from app.models import Alerta, Contenedor, EventoOperacional, PuntoReciclaje, Usuario
from app.services.fecha_service import fecha_chile
from config import Config


class FechaChileTests(unittest.TestCase):
    def test_verano_invierno_y_cambio_de_dia(self):
        for fecha, esperado in ((datetime(2026, 1, 15, 12), "15-01-2026 09:00:00"),
                                (datetime(2026, 7, 15, 12), "15-07-2026 08:00:00"),
                                (datetime(2026, 1, 15, 1, 2, 3), "14-01-2026 22:02:03")):
            with self.subTest(fecha=fecha):
                self.assertEqual(fecha_chile(fecha), esperado)
                self.assertEqual(fecha_chile(fecha.replace(tzinfo=timezone.utc)), esperado)
                self.assertEqual(fecha_chile(fecha.isoformat() + "Z"), esperado)
                self.assertIsNone(fecha.tzinfo)

    def test_fecha_con_zona_y_sin_fecha(self):
        fecha = datetime(2026, 7, 15, 14, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(fecha_chile(fecha), "15-07-2026 08:00:00")
        self.assertEqual(fecha_chile(None), "Sin datos")
        self.assertEqual(fecha_chile(None, ""), "")
        self.assertEqual(fecha.hour, 14)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class FechasVistasTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.usuario = Usuario(nombre="Equipo", username="equipo", rol="operador", activo=True)
        self.usuario.establecer_password("Prueba123!")
        punto = PuntoReciclaje(nombre="Punto", direccion="Dirección")
        self.fecha = datetime(2026, 7, 15, 1, 2, 3)
        self.cierre = datetime(2026, 1, 15, 12, 34, 56)
        self.contenedor = Contenedor(codigo="FECHAS", punto=punto, ultima_actualizacion=self.fecha)
        self.evento = EventoOperacional(contenedor=self.contenedor, usuario=self.usuario, tipo="VACIADO",
                                       descripcion="Vaciado de prueba", creado_en=self.fecha)
        self.alerta = Alerta(contenedor=self.contenedor, mensaje="Cerrada de prueba", activa=False,
                             creada_en=self.fecha, cerrada_en=self.cierre)
        db.session.add_all([self.evento, self.alerta])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.usuario.id)
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def test_historial_alertas_panel_y_persistencia_utc(self):
        self.assertIs(self.app.jinja_env.filters["fecha_chile"], fecha_chile)
        for path in ("/operacion/historial", "/operacion/alertas", "/panel"):
            with self.subTest(path=path):
                respuesta = self.client.get(path)
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.get_data(as_text=True)
                self.assertIn("14-07-2026 21:02:03", html)
                self.assertIn("hora local de Chile", html)
                self.assertNotIn("Fechas en UTC", html)
                self.assertNotIn("2026-07-15T01:02:03Z", html)
        alertas = self.client.get("/operacion/alertas").get_data(as_text=True)
        self.assertIn("15-01-2026 09:34:56", alertas)
        historial = self.client.get("/operacion/historial").get_data(as_text=True)
        self.assertIn("Vaciados y acciones registradas. Fechas en hora local de Chile.", historial)
        db.session.expire_all()
        self.assertEqual(self.evento.creado_en, self.fecha)
        self.assertEqual(self.alerta.creada_en, self.fecha)
        self.assertEqual(self.alerta.cerrada_en, self.cierre)
        self.assertEqual(self.contenedor.ultima_actualizacion, self.fecha)

    def test_panel_json_conserva_timestamp_y_reutiliza_filtro(self):
        respuesta = self.client.get("/panel/datos")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json["contenedores"][0]["ultima_actualizacion"], "2026-07-15T01:02:03Z")
        self.assertEqual(respuesta.json["fechas_locales"], {"2026-07-15T01:02:03Z": fecha_chile(self.fecha)})
        self.contenedor.ultima_actualizacion = None
        self.alerta.cerrada_en = None
        db.session.commit()
        self.assertEqual(self.client.get("/panel/datos").json["fechas_locales"], {})
        self.assertIn("Sin datos", self.client.get("/panel").get_data(as_text=True))
        self.assertEqual(self.client.get("/operacion/alertas").status_code, 200)


if __name__ == "__main__":
    unittest.main()
