"""Carga idempotente de datos de demostración para desarrollo."""

from datetime import datetime, time

from app import create_app
from app.extensions import db
from app.models import Contenedor, DispositivoIoT, Horario, Material, PuntoMaterial, PuntoReciclaje, Usuario


MATERIALES = {
    "Plástico PET": "Enjuaga las botellas, sécalas y aplástalas.",
    "Cartón": "Entrega el cartón limpio, seco y plegado.",
    "Vidrio": "Enjuaga los envases y retira tapas y corchos.",
    "Latas de aluminio": "Enjuaga las latas, sécalas y aplástalas.",
    "Tetra Pak": "Enjuaga los envases, escúrrelos y aplástalos.",
}

# Ubicaciones aproximadas e ilustrativas: no representan puntos oficiales.
PUNTOS = [
    {
        "nombre": "Demostración — Centro de Valdivia",
        "direccion": "Sector centro, Valdivia (ubicación de demostración)",
        "latitud": -39.8142, "longitud": -73.2459,
        "materiales": ["Plástico PET", "Cartón", "Latas de aluminio"],
        "codigo": "DEMO-CENTRO-01", "estado": "Disponible", "porcentaje": 20,
    },
    {
        "nombre": "Demostración — Isla Teja",
        "direccion": "Sector Isla Teja, Valdivia (ubicación de demostración)",
        "latitud": -39.8067, "longitud": -73.2600,
        "materiales": ["Vidrio", "Cartón"],
        "codigo": "DEMO-TEJA-01", "estado": "Medio", "porcentaje": 55,
    },
    {
        "nombre": "Demostración — Las Ánimas",
        "direccion": "Sector Las Ánimas, Valdivia (ubicación de demostración)",
        "latitud": -39.8000, "longitud": -73.2300,
        "materiales": ["Plástico PET", "Tetra Pak", "Latas de aluminio"],
        "codigo": "DEMO-ANIMAS-01", "estado": "Casi lleno", "porcentaje": 90,
    },
]


def cargar_datos():
    """Agregar solo registros faltantes, conservando los datos existentes."""
    materiales = {}
    for nombre, instrucciones in MATERIALES.items():
        material = db.session.scalar(db.select(Material).where(Material.nombre == nombre))
        if material is None:
            material = Material(nombre=nombre, instrucciones=instrucciones)
            db.session.add(material)
        materiales[nombre] = material
    db.session.flush()

    for datos in PUNTOS:
        punto = db.session.scalar(
            db.select(PuntoReciclaje).where(PuntoReciclaje.nombre == datos["nombre"])
        )
        if punto is None:
            punto = PuntoReciclaje(
                nombre=datos["nombre"], direccion=datos["direccion"],
                latitud=datos["latitud"], longitud=datos["longitud"], activo=True,
            )
            db.session.add(punto)
            db.session.flush()

        for nombre in datos["materiales"]:
            material = materiales[nombre]
            if db.session.get(PuntoMaterial, (punto.id, material.id)) is None:
                db.session.add(PuntoMaterial(punto_id=punto.id, material_id=material.id))

        for dia in range(5):
            inicio, fin = time(9, 0), time(18, 0)
            horario = db.session.scalar(db.select(Horario).where(
                Horario.punto_id == punto.id, Horario.dia_semana == dia,
                Horario.hora_inicio == inicio, Horario.hora_fin == fin,
            ))
            if horario is None:
                db.session.add(Horario(
                    punto_id=punto.id, dia_semana=dia, hora_inicio=inicio, hora_fin=fin,
                ))

        contenedor = db.session.scalar(
            db.select(Contenedor).where(Contenedor.codigo == datos["codigo"])
        )
        if contenedor is None:
            db.session.add(Contenedor(
                punto_id=punto.id, codigo=datos["codigo"], estado=datos["estado"],
                porcentaje_llenado=datos["porcentaje"],
                ultima_actualizacion=datetime.now(), activo=True,
            ))
    db.session.flush()
    demo = db.session.scalar(db.select(DispositivoIoT).where(
        DispositivoIoT.identificador == "DEMO-IOT-01"))
    contenedor_demo = db.session.scalar(db.select(Contenedor).where(
        Contenedor.codigo == "DEMO-CENTRO-01"))
    activo = db.session.scalar(db.select(DispositivoIoT).where(
        DispositivoIoT.contenedor_id == contenedor_demo.id, DispositivoIoT.activo.is_(True)))
    if demo is None and activo is None:
        db.session.add(DispositivoIoT(
            identificador="DEMO-IOT-01", contenedor_id=contenedor_demo.id, activo=True))
    # Credenciales públicas exclusivamente para desarrollo/demostración.
    for username, nombre, rol, password in (
        ("admin", "Administrador de demostración", "administrador", "Admin123!"),
        ("operador", "Operador de demostración", "operador", "Operador123!"),
    ):
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.username == username))
        if usuario is None:
            usuario = Usuario(nombre=nombre, username=username, rol=rol, activo=True)
            usuario.establecer_password(password)
            db.session.add(usuario)
    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        try:
            cargar_datos()
        except Exception:
            db.session.rollback()
            raise
    print("Datos de demostración cargados sin duplicados.")
