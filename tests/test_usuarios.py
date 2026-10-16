"""Gestión de usuarios, autorización y validación con base de datos aislada."""

import unittest
from unittest.mock import patch
from flask import g

from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Usuario
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class UsuariosTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.admin = Usuario(nombre="Administración", username="admin", rol="administrador", activo=True)
        self.admin.establecer_password("Admin123!")
        db.session.add(self.admin)
        db.session.commit()
        self.client = self.app.test_client()
        self.login(self.client, "admin", "Admin123!")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def post(self, path, datos=None, client=None):
        client = client or self.client
        g.pop("_login_user", None)
        client.get("/login", follow_redirects=True)
        with client.session_transaction() as session:
            token = session["csrf_token"]
        respuesta = client.post(path, data={**(datos or {}), "csrf_token": token})
        g.pop("_login_user", None)
        return respuesta

    def login(self, client, username, password):
        return self.post("/login", {"username": username, "password": password}, client)

    def datos(self, **cambios):
        return {"nombre": "Operador nuevo", "username": "nuevo", "rol": "operador", "activo": "1",
                "password": "Clave123!", "password_confirmacion": "Clave123!", **cambios}

    def crear(self, **cambios):
        self.assertEqual(self.post("/admin/usuarios/nuevo", self.datos(**cambios)).status_code, 302)
        return db.session.scalar(db.select(Usuario).where(Usuario.username == cambios.get("username", "nuevo")))

    def test_views_and_create_with_hash_and_login(self):
        for path in ("/admin/usuarios", "/admin/usuarios/nuevo", f"/admin/usuarios/{self.admin.id}/editar"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn(b"/admin/usuarios", self.client.get("/admin").data)
        usuario = self.crear()
        self.assertNotEqual(usuario.password_hash, "Clave123!")
        self.assertTrue(usuario.verificar_password("Clave123!"))
        self.assertIn(b"nuevo", self.client.get("/admin/usuarios").data)
        otro = self.app.test_client()
        self.login(otro, "nuevo", "Clave123!")
        self.assertEqual(otro.get("/panel").status_code, 200)

    def test_edit_role_password_and_activation(self):
        usuario = self.crear()
        path = f"/admin/usuarios/{usuario.id}/editar"
        original = usuario.password_hash
        datos = self.datos(nombre="Nombre editado", rol="administrador", password="", password_confirmacion="")
        self.assertEqual(self.post(path, datos).status_code, 302)
        self.assertEqual(usuario.password_hash, original)
        self.assertEqual(usuario.rol, "administrador")
        otro = self.app.test_client()
        self.login(otro, "nuevo", "Clave123!")
        self.assertEqual(otro.get("/admin").status_code, 200)
        self.post(path, self.datos(activo="", password="Otra123!", password_confirmacion="Otra123!"))
        self.assertFalse(usuario.activo)
        self.assertTrue(usuario.verificar_password("Otra123!"))
        self.assertEqual(otro.get("/panel").status_code, 302)
        self.assertIn(b"Credenciales", self.login(otro, "nuevo", "Otra123!").data)
        self.post(path, self.datos(password="", password_confirmacion=""))
        self.login(otro, "nuevo", "Otra123!")
        self.assertEqual(otro.get("/panel").status_code, 200)

    def test_invalid_inputs_duplicate_and_no_password_echo(self):
        self.crear()
        for cambios in ({"nombre": " "}, {"nombre": "x" * 151}, {"username": ""}, {"username": "con espacio"},
                        {"username": "x" * 101}, {"rol": "ciudadano"}, {"activo": "otro"},
                        {"password": "corta"}, {"password": ""}, {"password": "x" * 129},
                        {"password_confirmacion": "distinta"}):
            with self.subTest(cambios=cambios):
                respuesta = self.post("/admin/usuarios/nuevo", self.datos(username="otro", **cambios) if "username" not in cambios else self.datos(**cambios))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Usuario)), 2)
                self.assertNotIn(b"Clave123!", respuesta.data)
        self.assertIn(b"Ya existe", self.post("/admin/usuarios/nuevo", self.datos()).data)
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == "nuevo"))
        self.assertIn(b"Ya existe", self.post(f"/admin/usuarios/{usuario.id}/editar", self.datos(username="admin")).data)
        self.assertEqual(usuario.username, "nuevo")

    def test_cannot_disable_or_demote_self(self):
        for cambios in ({"activo": ""}, {"rol": "operador"}):
            respuesta = self.post(f"/admin/usuarios/{self.admin.id}/editar", self.datos(username="admin", **cambios))
            self.assertIn(b"No puedes", respuesta.data)
            self.assertTrue(self.admin.activo)
            self.assertEqual(self.admin.rol, "administrador")

    def test_permissions_csrf_missing_user_and_rollback(self):
        usuario = self.crear()
        paths = ("/admin/usuarios", "/admin/usuarios/nuevo", f"/admin/usuarios/{usuario.id}/editar")
        anonimo = self.app.test_client()
        operador = self.app.test_client()
        self.login(operador, "nuevo", "Clave123!")
        for path in paths:
            for method in (("GET",) if path == "/admin/usuarios" else ("GET", "POST")):
                g.pop("_login_user", None)
                self.assertEqual(anonimo.open(path, method=method).status_code, 302)
                g.pop("_login_user", None)
                self.assertEqual(operador.open(path, method=method).status_code, 403)
        g.pop("_login_user", None)
        self.assertEqual(self.client.post("/admin/usuarios/nuevo", data=self.datos()).status_code, 400)
        self.assertEqual(self.client.get("/admin/usuarios/999/editar").status_code, 404)
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("fallo")):
            self.assertEqual(self.post("/admin/usuarios/nuevo", self.datos(username="fallo")).status_code, 200)
        self.assertIsNone(db.session.scalar(db.select(Usuario).where(Usuario.username == "fallo")))


if __name__ == "__main__":
    unittest.main()
