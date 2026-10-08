"""Pruebas del CRUD administrativo y su reflejo en la vista pública."""

import unittest
from datetime import time
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import Horario, Material, PuntoMaterial, PuntoReciclaje
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        cargar_datos()
        self.client = self.app.test_client()
        self.punto = db.session.scalar(db.select(PuntoReciclaje))
        self.login("admin", "Admin123!")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def token(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, username, password):
        self.client.get("/login")
        return self.post("/login", {"username": username, "password": password})

    def post(self, path, datos=None):
        return self.client.post(path, data={**(datos or {}), "csrf_token": self.token()})

    def punto_datos(self, **cambios):
        return {"nombre": "Punto de prueba", "direccion": "Dirección de prueba", "latitud": "-39.8", "longitud": "-73.2", "activo": "1", **cambios}

    def test_admin_views(self):
        horario = db.session.scalar(db.select(Horario).where(Horario.punto_id == self.punto.id))
        material = db.session.scalar(db.select(Material))
        paths = ["/admin", "/admin/puntos", "/admin/puntos/nuevo", "/admin/materiales", "/admin/materiales/nuevo",
                 f"/admin/puntos/{self.punto.id}/editar", f"/admin/materiales/{material.id}/editar",
                 f"/admin/puntos/{self.punto.id}/horarios/nuevo", f"/admin/puntos/{self.punto.id}/horarios/{horario.id}/editar"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_every_admin_route_rejects_operator_and_anonymous(self):
        self.post("/logout")
        self.login("operador", "Operador123!")
        paths = []
        with self.app.test_request_context():
            adapter = self.app.url_map.bind("localhost")
            for rule in self.app.url_map.iter_rules():
                if rule.endpoint.startswith("admin."):
                    values = {key: 1 for key in rule.arguments}
                    paths.append((adapter.build(rule.endpoint, values), "POST" if "POST" in rule.methods else "GET"))
        for path, method in paths:
            self.assertEqual(self.client.open(path, method=method).status_code, 403, path)
        self.post("/logout")
        for path, method in paths:
            self.assertEqual(self.client.open(path, method=method).status_code, 302, path)

    def test_create_and_edit_point(self):
        self.assertEqual(self.post("/admin/puntos/nuevo", self.punto_datos()).status_code, 302)
        punto = db.session.scalar(db.select(PuntoReciclaje).where(PuntoReciclaje.nombre == "Punto de prueba"))
        self.assertIsNotNone(punto)
        self.assertEqual(punto.latitud, -39.8)
        self.post(f"/admin/puntos/{punto.id}/editar", self.punto_datos(nombre="Nombre actualizado"))
        self.assertIn("Nombre actualizado", self.client.get("/").get_data(as_text=True))

    def test_invalid_point_fields(self):
        cantidad = db.session.scalar(db.select(db.func.count()).select_from(PuntoReciclaje))
        for cambios in ({"latitud": "91"}, {"latitud": "-91"}, {"longitud": "181"}, {"longitud": "-181"},
                        {"latitud": "nan"}, {"longitud": "inf"}, {"latitud": ""}, {"nombre": " "}, {"direccion": ""}):
            with self.subTest(cambios=cambios):
                self.assertEqual(self.post("/admin/puntos/nuevo", self.punto_datos(**cambios)).status_code, 200)
                self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(PuntoReciclaje)), cantidad)

    def test_create_edit_and_duplicate_material(self):
        datos = {"nombre": "Metal de prueba", "instrucciones": "Limpiar y secar"}
        self.assertEqual(self.post("/admin/materiales/nuevo", datos).status_code, 302)
        response = self.post("/admin/materiales/nuevo", datos)
        self.assertIn(b"Ya existe", response.data)
        self.assertEqual(len(db.session.scalars(db.select(Material).where(Material.nombre == datos["nombre"])).all()), 1)
        material = db.session.scalar(db.select(Material).where(Material.nombre == datos["nombre"]))
        self.assertEqual(self.post(f"/admin/materiales/{material.id}/editar", {**datos, "instrucciones": "Nueva preparación"}).status_code, 302)
        self.assertEqual(material.instrucciones, "Nueva preparación")
        for vacio in ({"nombre": " ", "instrucciones": "X"}, {"nombre": "Otro", "instrucciones": " "}):
            self.assertEqual(self.post("/admin/materiales/nuevo", vacio).status_code, 200)

    def test_material_association_no_duplicates_and_public_update(self):
        material = Material(nombre="Material exclusivo", instrucciones="Preparación de prueba")
        db.session.add(material)
        db.session.commit()
        path = f"/admin/puntos/{self.punto.id}/materiales"
        for _ in range(2):
            self.assertEqual(self.post(path, {"material_id": str(material.id)}).status_code, 302)
        asociaciones = db.session.scalars(db.select(PuntoMaterial).where(PuntoMaterial.punto_id == self.punto.id, PuntoMaterial.material_id == material.id)).all()
        self.assertEqual(len(asociaciones), 1)
        self.assertIn("Material exclusivo", self.client.get(f"/?material={material.id}").get_data(as_text=True))
        self.post(f"{path}/{material.id}/quitar")
        self.assertIsNone(db.session.get(PuntoMaterial, (self.punto.id, material.id)))
        self.assertIsNotNone(db.session.get(Material, material.id))
        self.assertIn("No hay puntos activos", self.client.get(f"/?material={material.id}").get_data(as_text=True))

    def test_create_edit_delete_schedule(self):
        path = f"/admin/puntos/{self.punto.id}/horarios"
        datos = {"dia_semana": "6", "hora_inicio": "10:00", "hora_fin": "14:00"}
        self.assertEqual(self.post(f"{path}/nuevo", datos).status_code, 302)
        horario = db.session.scalar(db.select(Horario).where(Horario.punto_id == self.punto.id, Horario.dia_semana == 6))
        self.assertIsNotNone(horario)
        self.assertEqual(self.post(f"{path}/{horario.id}/editar", {**datos, "hora_fin": "15:30"}).status_code, 302)
        self.assertIn("15:30", self.client.get("/").get_data(as_text=True))
        horario_id = horario.id
        self.post(f"{path}/{horario_id}/eliminar")
        self.assertIsNone(db.session.get(Horario, horario_id))

    def test_create_multiple_days_and_skip_exact_duplicates(self):
        path = f"/admin/puntos/{self.punto.id}/horarios/nuevo"
        datos = {"dia_semana": ["0", "1", "2", "3", "4", "4"], "hora_inicio": "11:00", "hora_fin": "16:00"}
        self.assertEqual(self.post(path, datos).status_code, 302)
        consulta = db.select(Horario).where(Horario.punto_id == self.punto.id, Horario.hora_inicio == time(11))
        horarios = db.session.scalars(consulta).all()
        self.assertEqual({h.dia_semana for h in horarios}, {0, 1, 2, 3, 4})
        self.assertEqual(len(horarios), 5)
        self.assertEqual(self.post(path, datos).status_code, 200)
        self.assertEqual(len(db.session.scalars(consulta).all()), 5)
        self.post(path, {**datos, "dia_semana": ["4", "5"]})
        self.assertEqual(len(db.session.scalars(consulta).all()), 6)

    def test_multiple_days_validation_is_atomic_and_preserves_selection(self):
        path = f"/admin/puntos/{self.punto.id}/horarios/nuevo"
        cantidad = db.session.scalar(db.select(db.func.count()).select_from(Horario))
        for dias, fin in (([], "16:00"), (["0", "1"], "10:00"), (["0", "1"], "11:00"), (["0", "7"], "16:00")):
            with self.subTest(dias=dias, fin=fin):
                response = self.post(path, {"dia_semana": dias, "hora_inicio": "11:00", "hora_fin": fin})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Horario)), cantidad)
        response = self.post(path, {"dia_semana": ["0", "1"], "hora_inicio": "11:00", "hora_fin": "10:00"})
        self.assertIn('value="0" checked', response.get_data(as_text=True))
        self.assertIn('value="1" checked', response.get_data(as_text=True))
        self.assertIn(b"Selecciona al menos", self.post(path, {"hora_inicio": "11:00", "hora_fin": "16:00"}).data)

    def test_individual_edit_does_not_change_other_days(self):
        path = f"/admin/puntos/{self.punto.id}/horarios"
        self.post(f"{path}/nuevo", {"dia_semana": ["5", "6"], "hora_inicio": "10:00", "hora_fin": "14:00"})
        horarios = db.session.scalars(db.select(Horario).where(Horario.punto_id == self.punto.id, Horario.dia_semana.in_([5, 6])).order_by(Horario.dia_semana)).all()
        primero, segundo = horarios
        html = self.client.get(f"{path}/{primero.id}/editar").get_data(as_text=True)
        self.assertIn('<select', html)
        self.assertNotIn('type="checkbox"', html)
        self.assertEqual(self.post(f"{path}/{primero.id}/editar", {"dia_semana": "5", "hora_inicio": "10:00", "hora_fin": "15:00"}).status_code, 302)
        self.assertEqual(primero.hora_fin.hour, 15)
        self.assertEqual(segundo.hora_fin.hour, 14)
        self.assertEqual(self.post(f"{path}/{primero.id}/editar", {"dia_semana": "6", "hora_inicio": "10:00", "hora_fin": "14:00"}).status_code, 200)
        self.assertEqual(primero.dia_semana, 5)

    def test_invalid_schedules(self):
        path = f"/admin/puntos/{self.punto.id}/horarios/nuevo"
        cantidad = db.session.scalar(db.select(db.func.count()).select_from(Horario))
        for datos in ({"dia_semana": "6", "hora_inicio": "14:00", "hora_fin": "13:00"},
                      {"dia_semana": "6", "hora_inicio": "14:00", "hora_fin": "14:00"},
                      {"dia_semana": "7", "hora_inicio": "09:00", "hora_fin": "10:00"},
                      {"dia_semana": "0", "hora_inicio": "", "hora_fin": "10:00"}):
            self.assertEqual(self.post(path, datos).status_code, 200)
            self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Horario)), cantidad)

    def test_deactivated_point_not_public(self):
        self.assertIn(self.punto.nombre, self.client.get("/").get_data(as_text=True))
        self.post(f"/admin/puntos/{self.punto.id}/estado")
        self.assertNotIn(self.punto.nombre, self.client.get("/").get_data(as_text=True))
        self.post(f"/admin/puntos/{self.punto.id}/estado")
        self.assertIn(self.punto.nombre, self.client.get("/").get_data(as_text=True))

    def test_csrf_and_schedule_ownership(self):
        self.assertEqual(self.client.post("/admin/puntos/nuevo", data=self.punto_datos()).status_code, 400)
        horario = db.session.scalar(db.select(Horario).where(Horario.punto_id != self.punto.id))
        self.assertEqual(self.post(f"/admin/puntos/{self.punto.id}/horarios/{horario.id}/eliminar").status_code, 404)
        self.assertIsNotNone(db.session.get(Horario, horario.id))

    def test_database_errors_rollback(self):
        for error in (IntegrityError("insert", {}, Exception()), SQLAlchemyError("error")):
            with patch.object(db.session, "commit", side_effect=error), patch.object(db.session, "rollback", wraps=db.session.rollback) as rollback:
                response = self.post("/admin/puntos/nuevo", self.punto_datos())
                self.assertEqual(response.status_code, 200)
                rollback.assert_called_once()
            self.assertIsNone(db.session.scalar(db.select(PuntoReciclaje).where(PuntoReciclaje.nombre == "Punto de prueba")))


if __name__ == "__main__":
    unittest.main()
