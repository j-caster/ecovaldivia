"""Verificar el puente local sin conexión a Render ni secretos reales."""

import json
import os
import unittest
from unittest.mock import patch

from gateway_local.render_bridge import RenderBridge, construir_lectura


class RespuestaSimulada:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traza):
        return False


class PuenteRenderTests(unittest.TestCase):
    def datos_udp(self):
        return {
            "S1_CM": "94.2", "S2_CM": "94.5", "MODO": "AUTO",
            "COMPUERTA": "ABIERTA", "BOOT": "20261027AABBCCDD",
            "SEQ": "18", "LAST_CMD_CTR": "6", "ID": "52",
        }

    def test_traduccion_usa_campos_arduino_original(self):
        datos = construir_lectura(self.datos_udp(), "10.175.229.77", "ECO-SODIMAC-VIDRIO-01")
        self.assertEqual(datos["sensor1_cm"], "94.2")
        self.assertEqual(datos["seq"], "18")
        self.assertEqual(datos["medicion_externa_id"], "52")
        self.assertNotIn("fuente", datos)

    def test_envio_https_autorizado_y_json(self):
        env = {
            "ECOV_RENDER_INGEST_URL": "https://ecovaldivia.onrender.com/api/iot/lecturas",
            "ECOV_RENDER_INGEST_TOKEN": "token-ficticio-de-36-o-mas-caracteres",
            "ECOV_RENDER_DEVICE_ID": "ECO-SODIMAC-VIDRIO-01",
        }
        with patch.dict(os.environ, env):
            puente = RenderBridge()
        datos = construir_lectura(self.datos_udp(), "10.175.229.77", puente.dispositivo)
        with patch("gateway_local.render_bridge.urlopen", return_value=RespuestaSimulada()) as urlopen:
            self.assertEqual(puente._enviar(datos), 200)
        peticion = urlopen.call_args.args[0]
        self.assertEqual(peticion.get_method(), "POST")
        self.assertEqual(peticion.get_header("Authorization"), f"Bearer {env['ECOV_RENDER_INGEST_TOKEN']}")
        self.assertEqual(json.loads(peticion.data.decode()), datos)

    def test_no_acepta_http_externo(self):
        env = {
            "ECOV_RENDER_INGEST_URL": "http://sitio.example/api/iot/lecturas",
            "ECOV_RENDER_INGEST_TOKEN": "token-ficticio-de-36-o-mas-caracteres",
            "ECOV_RENDER_DEVICE_ID": "ECO-SODIMAC-VIDRIO-01",
        }
        with patch.dict(os.environ, env):
            puente = RenderBridge()
        self.assertFalse(puente.iniciar())
        self.assertFalse(puente._activo)


if __name__ == "__main__":
    unittest.main()
