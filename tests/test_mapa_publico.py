"""Datos públicos del mapa y filtro existente, sin automatizar Leaflet."""

import json
import re
import unittest
from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import Contenedor, Material, PuntoMaterial, PuntoReciclaje
from app.services.mapa_publico_service import coordenada_valida
from config import Config
from seed import cargar_datos


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class MapaPublicoTests(unittest.TestCase):
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

    def respuesta(self, ruta="/"):
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.get_data(as_text=True)
        bloque = re.search(r'<script id="datos-mapa-publico" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(bloque)
        return html, json.loads(bloque.group(1))

    def test_inicio_conserva_hero_filtro_y_tarjetas(self):
        html, puntos = self.respuesta()
        self.assertIn('class="hero-ecovaldivia"', html)
        self.assertIn('id="material"', html)
        self.assertIn('id="mapa-publico"', html)
        # Las librerías se sirven desde el propio proyecto, sin depender de CDN.
        self.assertIn("vendor/leaflet/leaflet.css", html)
        self.assertIn("vendor/leaflet/leaflet.js", html)
        self.assertIn("vendor/bootstrap/bootstrap.min.css", html)
        for externo in ("cdn.jsdelivr.net", "unpkg.com", "fonts.googleapis.com"):
            self.assertNotIn(externo, html)
        self.assertIn("js/mapa_publico.js", html)
        self.assertLess(html.index('id="material"'), html.index('id="mapa-publico"'))
        self.assertLess(html.index('id="mapa-publico"'), html.index('class="card h-100"'))
        self.assertEqual(len(puntos), 9)

    def test_activos_incluidos_inactivos_excluidos(self):
        punto = db.session.scalar(db.select(PuntoReciclaje))
        punto.activo = False
        db.session.commit()
        html, datos = self.respuesta()
        self.assertNotIn(punto.id, {p["punto_id"] for p in datos})
        self.assertNotIn(punto.nombre, html)
        esperados = db.session.scalars(db.select(PuntoReciclaje).where(PuntoReciclaje.activo.is_(True))).all()
        self.assertEqual({p["punto_id"] for p in datos}, {p.id for p in esperados})
        for p in esperados:
            self.assertIn(p.nombre, html)

    def test_filtro_material_comparte_resultado_con_tarjetas(self):
        punto = db.session.scalar(db.select(PuntoReciclaje))
        material = Material(nombre="Material exclusivo para mapa", instrucciones="Limpiar")
        db.session.add(material)
        db.session.flush()
        db.session.add(PuntoMaterial(punto_id=punto.id, material_id=material.id))
        db.session.commit()
        html, datos = self.respuesta(f"/?material={material.id}")
        self.assertEqual([p["punto_id"] for p in datos], [punto.id])
        self.assertIn(punto.nombre, html)
        for otro in db.session.scalars(db.select(PuntoReciclaje).where(PuntoReciclaje.id != punto.id)):
            self.assertNotIn(otro.direccion, html)
        for valor in ("abc", "999999"):
            _, vacios = self.respuesta(f"/?material={valor}")
            self.assertEqual(vacios, [])

    def test_coordenadas_ausentes_o_fuera_de_rango_no_rompen_tarjetas(self):
        punto = PuntoReciclaje(nombre="Punto sin coordenadas", direccion="Dirección de prueba", activo=True)
        db.session.add(punto)
        db.session.commit()
        for latitud, longitud in ((None, None), (None, -73), (-39, None),
                                  (91, -73), (-39, 181), (float("inf"), -73)):
            with self.subTest(latitud=latitud, longitud=longitud):
                punto.latitud, punto.longitud = latitud, longitud
                db.session.commit()
                html, datos = self.respuesta()
                registro = next(p for p in datos if p["punto_id"] == punto.id)
                self.assertIsNone(registro["latitud"])
                self.assertIsNone(registro["longitud"])
                self.assertIn(punto.nombre, html)

    def test_contrato_publico_y_solo_contenedores_activos(self):
        punto = db.session.scalar(db.select(PuntoReciclaje))
        db.session.add(Contenedor(punto_id=punto.id, codigo="INACTIVO-MAPA", activo=False))
        activo = punto.contenedores[0]
        activo.porcentaje_llenado = None
        activo.estado = "Vaciado pendiente de lectura"
        db.session.commit()
        _, datos = self.respuesta()
        registro = next(p for p in datos if p["punto_id"] == punto.id)
        self.assertEqual(set(registro), {"punto_id", "nombre", "direccion", "latitud", "longitud", "materiales", "contenedores"})
        self.assertEqual(registro["latitud"], punto.latitud)
        self.assertEqual(registro["longitud"], punto.longitud)
        self.assertEqual(registro["materiales"], sorted(m.nombre for m in punto.materiales))
        self.assertEqual(registro["contenedores"], [{"codigo": activo.codigo,
            "estado": "Vaciado pendiente de lectura", "porcentaje_llenado": None,
            "ultima_actualizacion": activo.ultima_actualizacion.isoformat() + "Z"}])

    def test_json_seguro_para_nombres_de_usuario(self):
        punto = db.session.scalar(db.select(PuntoReciclaje))
        malicioso = '</script><script>alert("mapa")</script>'
        punto.nombre = malicioso
        punto.direccion = '<img src=x onerror="alert(1)">'
        db.session.commit()
        html, datos = self.respuesta()
        self.assertNotIn(malicioso, html)
        self.assertNotIn(punto.direccion, html)
        self.assertEqual(next(p for p in datos if p["punto_id"] == punto.id)["nombre"], malicioso)

    def test_endpoint_publico_activos_y_campos_permitidos(self):
        punto = db.session.scalar(db.select(PuntoReciclaje))
        punto.activo = False
        db.session.commit()
        respuesta = self.client.get("/public/datos")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["Cache-Control"], "no-store")
        datos = respuesta.json["puntos"]
        self.assertNotIn(punto.id, {p["punto_id"] for p in datos})
        self.assertEqual(len(datos), 8)
        for p in datos:
            self.assertEqual(set(p), {"punto_id", "nombre", "direccion", "latitud", "longitud", "materiales", "contenedores"})
            for c in p["contenedores"]:
                self.assertEqual(set(c), {"codigo", "porcentaje_llenado", "estado", "ultima_actualizacion"})

    def test_endpoint_comparte_filtro_con_html(self):
        for material in db.session.scalars(db.select(Material)):
            _, inicial = self.respuesta(f"/?material={material.id}")
            respuesta = self.client.get(f"/public/datos?material={material.id}")
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json["puntos"], inicial)
        for valor in ("abc", "999999", "-1"):
            self.assertEqual(self.client.get(f"/public/datos?material={valor}").json["puntos"], [])

    def test_endpoint_refleja_cambios_sin_modificar_historial(self):
        contenedor = db.session.scalar(db.select(Contenedor))
        codigo, punto_id = contenedor.codigo, contenedor.punto_id
        def datos_actuales():
            datos = self.client.get("/public/datos").json["puntos"]
            punto = next(p for p in datos if p["punto_id"] == punto_id)
            return next(c for c in punto["contenedores"] if c["codigo"] == codigo)
        antes = datos_actuales()
        contenedor.porcentaje_llenado = 97
        contenedor.estado = "Lleno"
        contenedor.ultima_actualizacion = datetime(2026, 10, 8, 12, 30)
        db.session.commit()
        despues = datos_actuales()
        self.assertNotEqual(antes["porcentaje_llenado"], despues["porcentaje_llenado"])
        self.assertEqual(despues["porcentaje_llenado"], 97)
        self.assertEqual(despues["estado"], "Lleno")
        self.assertEqual(despues["ultima_actualizacion"], "2026-10-08T12:30:00Z")
        contenedor.activo = False
        db.session.commit()
        puntos = self.client.get("/public/datos").json["puntos"]
        self.assertNotIn(codigo, {c["codigo"] for p in puntos for c in p["contenedores"]})

    def test_limites_de_coordenadas_y_no_finitos(self):
        self.assertEqual(coordenada_valida(0, 90), 0)
        self.assertEqual(coordenada_valida(-90, 90), -90)
        self.assertEqual(coordenada_valida(180, 180), 180)
        for valor in (None, "inválido", float("nan"), float("inf"), -91, 91):
            self.assertIsNone(coordenada_valida(valor, 90))


if __name__ == "__main__":
    unittest.main()
