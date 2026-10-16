"""Estructura visual y conservación de formularios y selectores existentes."""

import unittest
from unittest.mock import patch
from flask import g

from app import create_app
from app.extensions import db
from app.models import Usuario
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.contexto = self.app.app_context()
        self.contexto.push()
        db.create_all()
        cargar_datos()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.contexto.pop()

    def autenticar(self, rol):
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.rol == rol))
        with self.client.session_transaction() as sesion:
            sesion["_user_id"] = str(usuario.id)
            sesion["_fresh"] = True
        g.pop("_login_user", None)

    def test_publico_y_login_conservan_controles(self):
        publico = self.client.get("/")
        self.assertEqual(publico.status_code, 200)
        html = publico.get_data(as_text=True)
        for fragmento in ('navbar-toggler', 'id="navegacion-principal"', 'data-bs-target="#navegacion-principal"',
                          'id="mapa-publico"', 'id="datos-mapa-publico"', 'data-punto-id=',
                          'data-contenedor-codigo=', 'data-campo="estado"', 'data-campo="porcentaje"',
                          'data-campo="progreso"', 'role="progressbar"', 'data-campo="fecha"'):
            self.assertIn(fragmento, html)
        login = self.client.get("/login").get_data(as_text=True)
        for fragmento in ('login-card', 'name="csrf_token"', 'name="username"', 'name="password"', 'autocomplete="current-password"'):
            self.assertIn(fragmento, login)

    def test_paginas_privadas_y_resumen_visual(self):
        for rol in ("operador", "administrador"):
            self.autenticar(rol)
            for path in ("/panel", "/operacion/alertas", "/operacion/historial"):
                respuesta = self.client.get(path)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('table-responsive', respuesta.get_data(as_text=True))
            panel = self.client.get("/panel").get_data(as_text=True)
            for fragmento in ('id="panel-operacional"', 'id="panel-contenedores"', 'id="panel-actualizacion"',
                              'data-intervalo="5000"', 'resumen-puntos', 'resumen-disponibles', 'resumen-criticos',
                              'resumen-alertas', 'resumen-online', 'role="progressbar"'):
                self.assertIn(fragmento, panel)
        admin = self.client.get("/admin").get_data(as_text=True)
        self.assertEqual(admin.count('card admin-card'), 5)
        for destino in ('/admin/puntos', '/admin/materiales', '/admin/mediciones/simular', '/operacion/alertas', '/operacion/historial'):
            self.assertIn(destino, admin)

    def test_disponibles_explica_unidad_y_cuenta_estado_independiente_de_conectividad(self):
        self.autenticar("operador")
        # El servicio entrega solo contenedores activos al panel.
        contenedores = [dict(codigo=str(i), punto="Punto", porcentaje=porcentaje, estado=estado,
                            modo=None, compuerta=None, ultima_actualizacion=None, alerta=None,
                            conectividad=conexion)
                       for i, (estado, porcentaje, conexion) in enumerate([
                           ("Disponible", 20, "ONLINE"), ("Disponible", 49.9, "OFFLINE"),
                           ("Medio", 50, "ONLINE"), ("Casi lleno", 90, "ONLINE"),
                           ("Lleno", 100, "ONLINE"), ("Pendiente de lectura", None, "OFFLINE")])]
        with patch("app.routes.auth.datos_panel", return_value=contenedores):
            html = self.client.get("/panel").get_data(as_text=True)
        self.assertIn('id="resumen-disponibles" aria-describedby="resumen-disponibles-titulo resumen-disponibles-nota">2</p>', html)
        self.assertIn('id="resumen-disponibles-titulo">Contenedores disponibles</h2>', html)
        self.assertIn("Activos con estado «Disponible»: llenado menor al 50%.", html)
        self.assertIn("Según el último estado registrado, incluso con el dispositivo offline.", html)
        with patch("app.routes.auth.datos_panel", return_value=[]):
            vacio = self.client.get("/panel").get_data(as_text=True)
        self.assertIn('id="resumen-disponibles" aria-describedby="resumen-disponibles-titulo resumen-disponibles-nota">0</p>', vacio)


if __name__ == "__main__":
    unittest.main()
