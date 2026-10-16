"""Pruebas de contenedores, dispositivos IoT y de la traza horaria en hora de Chile."""

import unittest
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import Contenedor, DispositivoIoT, Material, Medicion, PuntoReciclaje
from app.services.medicion_service import procesar_medicion
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ContenedorTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        cargar_datos()
        self.client = self.app.test_client()
        self.punto = db.session.scalar(db.select(PuntoReciclaje))
        self.material = db.session.scalar(db.select(Material))
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

    def post(self, path, datos=None, seguir=False):
        return self.client.post(path, data={**(datos or {}), "csrf_token": self.token()},
                                follow_redirects=seguir)

    def crear(self, **cambios):
        return self.post(f"/admin/puntos/{self.punto.id}/contenedores", {
            "codigo": "CONT-VIDRIO-01",
            "material_id": str(self.material.id),
            "identificador": "ECO-PRUEBA-VIDRIO-01",
            **cambios,
        }, seguir=True)

    def test_crear_contenedor_vincula_material_y_dispositivo(self):
        respuesta = self.crear()
        self.assertEqual(respuesta.status_code, 200)
        contenedor = db.session.scalar(db.select(Contenedor).where(Contenedor.codigo == "CONT-VIDRIO-01"))
        self.assertIsNotNone(contenedor)
        self.assertEqual(contenedor.punto_id, self.punto.id)
        self.assertEqual(contenedor.material_id, self.material.id)
        self.assertTrue(contenedor.activo)
        self.assertIsNotNone(contenedor.dispositivo_activo)
        self.assertEqual(contenedor.dispositivo_activo.identificador, "ECO-PRUEBA-VIDRIO-01")
        self.assertIn("CONT-VIDRIO-01", respuesta.get_data(as_text=True))
        self.assertIn("ECO-PRUEBA-VIDRIO-01", respuesta.get_data(as_text=True))

    def test_identificador_y_codigo_duplicados_se_rechazan(self):
        self.crear()
        repetido_id = self.crear(codigo="CONT-VIDRIO-02")
        self.assertIn("Ya existe un dispositivo con ese identificador", repetido_id.get_data(as_text=True))
        repetido_codigo = self.crear(identificador="ECO-PRUEBA-VIDRIO-02")
        self.assertIn("Ya existe un contenedor con ese código", repetido_codigo.get_data(as_text=True))
        self.assertEqual(db.session.query(DispositivoIoT).count(), 2)  # el de demostración y uno nuevo

    def test_contenedor_sin_material_es_valido(self):
        self.crear(codigo="CONT-SIN-MATERIAL", material_id="")
        contenedor = db.session.scalar(db.select(Contenedor).where(Contenedor.codigo == "CONT-SIN-MATERIAL"))
        self.assertIsNotNone(contenedor)
        self.assertIsNone(contenedor.material_id)

    def test_editar_contenedor_y_dispositivo(self):
        self.crear()
        contenedor = db.session.scalar(db.select(Contenedor).where(Contenedor.codigo == "CONT-VIDRIO-01"))
        otro = db.session.scalars(db.select(Material).where(Material.id != self.material.id)).first()
        respuesta = self.post(f"/admin/contenedores/{contenedor.id}/editar", {
            "codigo": "CONT-VIDRIO-EDITADO",
            "material_id": str(otro.id),
            "identificador": "ECO-PRUEBA-VIDRIO-99",
            "activo": "1",
            "dispositivo_activo": "1",
        }, seguir=True)
        self.assertEqual(respuesta.status_code, 200)
        db.session.refresh(contenedor)
        self.assertEqual(contenedor.codigo, "CONT-VIDRIO-EDITADO")
        self.assertEqual(contenedor.material_id, otro.id)
        self.assertEqual(contenedor.dispositivo_activo.identificador, "ECO-PRUEBA-VIDRIO-99")

    def test_desactivar_dispositivo_lo_saca_del_simulador(self):
        self.crear()
        contenedor = db.session.scalar(db.select(Contenedor).where(Contenedor.codigo == "CONT-VIDRIO-01"))
        dispositivo = contenedor.dispositivo_activo
        self.post(f"/admin/contenedores/{contenedor.id}/editar", {
            "codigo": contenedor.codigo,
            "material_id": str(self.material.id),
            "identificador": dispositivo.identificador,
            "activo": "1",
        }, seguir=True)
        self.assertFalse(dispositivo.activo)
        self.assertIsNone(contenedor.dispositivo_activo)
        html = self.client.get("/admin/mediciones/simular").get_data(as_text=True)
        self.assertNotIn(dispositivo.identificador, html)

    def test_punto_editar_muestra_contenedores_y_simulador_preselecciona(self):
        self.crear()
        html = self.client.get(f"/admin/puntos/{self.punto.id}/editar").get_data(as_text=True)
        self.assertIn("Contenedores y dispositivos IoT", html)
        self.assertIn("Agregar contenedor y vincular dispositivo", html)
        self.assertIn("ECO-PRUEBA-VIDRIO-01", html)
        dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
            DispositivoIoT.identificador == "ECO-PRUEBA-VIDRIO-01"))
        simulador = self.client.get(f"/admin/mediciones/simular?dispositivo={dispositivo.id}").get_data(as_text=True)
        self.assertIn(f'value="{dispositivo.identificador}" selected', simulador)
        self.assertIn(self.punto.nombre, simulador)
        self.assertIn(self.material.nombre, simulador)

    def test_historial_de_mediciones_muestra_hora_de_chile(self):
        """El registro se guarda en UTC, pero se muestra en hora local de Chile."""
        dispositivo = db.session.scalar(db.select(DispositivoIoT))
        procesar_medicion(dict(dispositivo_identificador=dispositivo.identificador, sensor1_cm=25,
                               sensor2_cm=25, modo="AUTO", compuerta="CERRADA", fuente="REAL",
                               boot="prueba-hora", seq=7,
                               fecha_recepcion=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)))
        medicion = db.session.scalar(db.select(Medicion).where(Medicion.boot == "prueba-hora"))
        self.assertEqual(medicion.recibida_en, datetime(2026, 1, 15, 12, 0))  # UTC sin zona
        html = self.client.get(f"/admin/dispositivos/{dispositivo.id}/mediciones").get_data(as_text=True)
        self.assertIn("15-01-2026 09:00:00", html)  # UTC-3 en verano en Chile
        self.assertIn("Fechas en hora local de Chile", html)
        self.assertNotIn("15-01-2026 12:00:00", html)


if __name__ == "__main__":
    unittest.main()
