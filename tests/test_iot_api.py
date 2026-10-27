"""Pruebas del ingreso HTTPS sin necesidad de red, Arduino ni Render."""

import unittest

from app import create_app
from app.extensions import db
from app.models import DispositivoIoT, Medicion
from config import Config
from seed import cargar_datos, cargar_dispositivos


TOKEN_PRUEBA = "token-de-prueba-iot-de-36-caracteres-interno"
ID_DISPOSITIVO = "ECO-SODIMAC-VIDRIO-01"


class ConfigPrueba(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    IOT_INGEST_TOKEN = TOKEN_PRUEBA
    IOT_INGEST_DEVICE_ID = ID_DISPOSITIVO


class IngestaHTTPSPruebas(unittest.TestCase):
    def setUp(self):
        self.app = create_app(ConfigPrueba)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        cargar_datos()
        cargar_dispositivos()
        self.cliente = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def datos(self, **cambios):
        return {
            "dispositivo_identificador": ID_DISPOSITIVO,
            "sensor1_cm": 94.2,
            "sensor2_cm": 94.5,
            "modo": "AUTO",
            "compuerta": "ABIERTA",
            "fuente": "SIMULACION",  # No debe poder suplantar el tipo de medición.
            "boot": "20261027AABBCCDD",
            "seq": 18,
            "last_cmd_ctr": 6,
            "medicion_externa_id": "52",
            "ip_origen": "10.175.229.77",
            **cambios,
        }

    def enviar(self, datos=None, token=TOKEN_PRUEBA):
        return self.cliente.post(
            "/api/iot/lecturas",
            json=datos if datos is not None else self.datos(),
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_ingesta_actualiza_dominio_y_fuerza_fuente_real(self):
        respuesta = self.enviar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json["aceptada"])
        self.assertTrue(respuesta.json["persistida"])
        dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
            DispositivoIoT.identificador == ID_DISPOSITIVO))
        self.assertEqual(dispositivo.ultimo_seq, 18)
        self.assertEqual(dispositivo.modo_actual, "AUTO")
        self.assertEqual(dispositivo.contenedor.estado, "Medio")
        self.assertAlmostEqual(dispositivo.contenedor.porcentaje_llenado, 53.76667, places=3)
        medicion = db.session.scalar(db.select(Medicion).where(
            Medicion.dispositivo_id == dispositivo.id))
        self.assertEqual(medicion.fuente, "REAL")

    def test_repeticion_y_validaciones(self):
        self.assertEqual(self.enviar().status_code, 200)
        self.assertEqual(self.enviar().status_code, 409)
        self.assertEqual(self.enviar(self.datos(seq=19, sensor1_cm=-1)).status_code, 422)
        dispositivo = db.session.scalar(db.select(DispositivoIoT).where(
            DispositivoIoT.identificador == ID_DISPOSITIVO))
        self.assertEqual(dispositivo.ultimo_seq, 18)

    def test_seguridad_del_endpoint(self):
        self.assertEqual(self.cliente.post("/api/iot/lecturas", json=self.datos()).status_code, 401)
        self.assertEqual(self.enviar(token="incorrecto").status_code, 401)
        self.assertEqual(self.enviar(self.datos(
            dispositivo_identificador="ECO-LATA-LATA-01")).status_code, 403)
        self.assertEqual(self.cliente.post("/api/iot/lecturas", data="texto",
                                          headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"}).status_code, 415)

    def test_falla_cerrada_sin_configuracion(self):
        self.app.config["IOT_INGEST_TOKEN"] = ""
        self.assertEqual(self.enviar().status_code, 503)


if __name__ == "__main__":
    unittest.main()
