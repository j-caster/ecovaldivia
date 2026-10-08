"""Pruebas de autenticación con SQLite en memoria, sin alterar datos reales."""

import unittest

from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import Usuario
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        cargar_datos()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def token(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, username, password):
        return self.client.post("/login", data={
            "username": username, "password": password, "csrf_token": self.token(),
        })

    def test_public_and_anonymous_access(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        for path in ("/panel", "/admin"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.location)

    def test_operator_access_and_logout(self):
        self.assertEqual(self.login("operador", "Operador123!").status_code, 302)
        self.assertEqual(self.client.get("/panel").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.post("/logout").status_code, 400)
        response = self.client.post("/logout", data={"csrf_token": self.token()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/panel").status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_administrator_access(self):
        self.login("admin", "Admin123!")
        for path in ("/panel", "/admin", "/"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn(b"Cerrar", self.client.get("/").data)

    def test_invalid_and_inactive_credentials(self):
        for username in ("admin", "desconocido"):
            response = self.login(username, "incorrecta")
            self.assertIn(b"Credenciales", response.data)
            self.assertEqual(self.client.get("/panel").status_code, 302)
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == "operador"))
        usuario.activo = False
        db.session.commit()
        self.assertIn(b"Credenciales", self.login("operador", "Operador123!").data)
        self.assertEqual(self.client.get("/panel").status_code, 302)

    def test_deactivation_invalidates_existing_session(self):
        self.login("admin", "Admin123!")
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == "admin"))
        usuario.activo = False
        db.session.commit()
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_login_csrf_and_external_redirect(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "Admin123!"}).status_code, 400)
        response = self.client.post("/login?next=https://example.com", data={
            "username": "admin", "password": "Admin123!", "csrf_token": self.token(),
        })
        self.assertEqual(response.location, "/panel")

    def test_seed_hashes_roles_and_uniqueness(self):
        usuarios = db.session.scalars(db.select(Usuario)).all()
        hashes = {u.username: u.password_hash for u in usuarios}
        cargar_datos()
        self.assertEqual(hashes, {u.username: u.password_hash for u in db.session.scalars(db.select(Usuario))})
        for username, password in (("admin", "Admin123!"), ("operador", "Operador123!")):
            usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == username))
            self.assertNotEqual(usuario.password_hash, password)
            self.assertTrue(usuario.verificar_password(password))
            self.assertFalse(usuario.verificar_password("incorrecta"))
        with self.assertRaises(ValueError):
            Usuario(rol="ciudadano")
        duplicado = Usuario(nombre="Duplicado", username="admin", rol="operador")
        duplicado.establecer_password("otra")
        db.session.add(duplicado)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


if __name__ == "__main__":
    unittest.main()
