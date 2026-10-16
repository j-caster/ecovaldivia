"""Prioridad, filtro y resumen de alertas sin alterar mediciones ni IoT."""

from datetime import datetime
import unittest
from flask import g

from app import create_app
from app.extensions import db
from app.models import Alerta, Contenedor, PuntoReciclaje, Usuario
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class AlertasVisibilidadTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.usuario = Usuario(nombre="Equipo", username="equipo", rol="operador", activo=True)
        self.usuario.establecer_password("Prueba123!")
        punto = PuntoReciclaje(nombre="Punto prueba", direccion="Dirección")
        self.contenedor = Contenedor(codigo="PRUEBA", punto=punto, estado="Lleno", porcentaje_llenado=100)
        db.session.add_all([self.usuario, self.contenedor])
        db.session.commit()
        self.client = self.app.test_client()
        self.autenticar()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def autenticar(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.usuario.id)
            session["_fresh"] = True
        g.pop("_login_user", None)

    def alerta(self, mensaje, activa, contenedor=None):
        alerta = Alerta(contenedor=contenedor or self.contenedor, mensaje=mensaje,
                        activa=activa, creada_en=datetime(2026, 10, 9, 12))
        db.session.add(alerta)
        db.session.commit()
        return alerta

    def test_active_first_filter_and_panel_highlight(self):
        activa = self.alerta("Pendiente de vaciado", True)
        self.alerta("Alerta histórica cerrada", False)
        html = self.client.get("/operacion/alertas").get_data(as_text=True)
        self.assertIn("1 alerta activa", html)
        self.assertLess(html.index("Pendiente de vaciado"), html.index("Alerta histórica cerrada"))
        self.assertIn('class="alert-active"', html)
        filtrado = self.client.get("/operacion/alertas?estado=activas").get_data(as_text=True)
        self.assertIn("Pendiente de vaciado", filtrado)
        self.assertNotIn("Alerta histórica cerrada", filtrado)
        self.assertIn('aria-current="page">Solo activas', filtrado)
        panel = self.client.get("/panel").get_data(as_text=True)
        self.assertIn("1 contenedor con alerta activa", panel)
        self.assertIn('class="alert-active"', panel)
        self.client.get("/login", follow_redirects=True)
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.assertEqual(self.client.post(f"/operacion/contenedores/{self.contenedor.id}/vaciado",
                                         data={"csrf_token": token}).status_code, 302)
        self.assertFalse(activa.activa)
        self.assertIn("No hay alertas activas pendientes.", self.client.get(
            "/operacion/alertas?estado=activas").get_data(as_text=True))
        panel = self.client.get("/panel").get_data(as_text=True)
        self.assertIn("0 contenedores con alerta activa", panel)
        self.assertNotIn('class="alert-active"', panel)

    def test_global_count_and_filter_survive_pagination(self):
        for numero in range(51):
            contenedor = Contenedor(codigo=f"EXTRA-{numero}", punto=self.contenedor.punto, estado="Lleno")
            db.session.add(Alerta(contenedor=contenedor, activa=True, mensaje=f"Activa {numero}",
                                 creada_en=datetime(2026, 10, 9, 12)))
        db.session.commit()
        self.alerta("Histórica excluida", False)
        html = self.client.get("/operacion/alertas?estado=activas").get_data(as_text=True)
        self.assertIn("51 alertas activas", html)
        self.assertIn("estado=activas", html)
        self.assertIn("page=2", html)
        segunda = self.client.get("/operacion/alertas?estado=activas&page=2").get_data(as_text=True)
        self.assertIn("51 alertas activas", segunda)
        self.assertNotIn("Histórica excluida", segunda)
        self.assertEqual(segunda.count('class="alert-active"'), 1)
        self.assertIn("page=1", segunda)

    def test_empty_filter_validation_and_permissions(self):
        self.assertIn("0 alertas activas", self.client.get("/operacion/alertas").get_data(as_text=True))
        self.assertEqual(self.client.get("/operacion/alertas?estado=incorrecto").status_code, 400)
        self.usuario.rol = "administrador"
        db.session.commit()
        self.assertEqual(self.client.get("/operacion/alertas?estado=activas").status_code, 200)
        with self.client.session_transaction() as session:
            session.clear()
        g.pop("_login_user", None)
        self.assertEqual(self.client.get("/operacion/alertas?estado=activas").status_code, 302)


if __name__ == "__main__":
    unittest.main()
