"""Carga idempotente de datos iniciales: materiales, puntos, horarios y contenedores."""

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
    "Laton": "Material de laton como latas de atun, sardinas, tarros de cafe.",
    "Plásticos Tipo 2 (ADPE)": (
        "Polietileno de Alta densidad , es un plástico rígido , resisten a impactos y a químicos. \n"
        "Ejemplo:\n"
        "-Envase de Limpiezas (Detergentes liquido, lavalozas y limpia pisos)\n"
        "-Cuidado Personal (Botellas de Champú, Acondicionador, jabón liquido y cremas)\n"
        "-Tapas plásticas \n"
        "-Lácteos (Botellas blancas u opacas de leche , yogurt liquido)"
    ),
}

# Puntos de reciclaje registrados en la base del proyecto. Cada punto declara sus
# materiales, horarios (lunes = 0 ... domingo = 6) y contenedores.
PUNTOS = [
    {
        "nombre": "Demostración — Centro de Valdivia",
        "direccion": "Sector centro, Valdivia (ubicación de demostración)",
        "latitud": -39.8142, "longitud": -73.2459,
        "materiales": ["Plástico PET", "Cartón", "Latas de aluminio"],
        "horarios": [(0, "09:00", "18:00"), (1, "09:00", "18:00"), (2, "09:00", "18:00"),
                     (3, "09:00", "18:00"), (4, "09:00", "18:00")],
        "contenedores": [{"codigo": "DEMO-CENTRO-01", "estado": "Disponible", "porcentaje": 20, "material": None}],
    },
    {
        "nombre": "Demostración — Isla Teja",
        "direccion": "Sector Isla Teja, Valdivia (ubicación de demostración)",
        "latitud": -39.8067, "longitud": -73.2600,
        "materiales": ["Vidrio", "Cartón"],
        "horarios": [(0, "09:00", "18:00"), (1, "09:00", "18:00"), (2, "09:00", "18:00"),
                     (3, "09:00", "18:00"), (4, "09:00", "18:00")],
        "contenedores": [{"codigo": "DEMO-TEJA-01", "estado": "Medio", "porcentaje": 55, "material": None}],
    },
    {
        "nombre": "Demostración — Las Ánimas",
        "direccion": "Sector Las Ánimas, Valdivia (ubicación de demostración)",
        "latitud": -39.8000, "longitud": -73.2300,
        "materiales": ["Plástico PET", "Tetra Pak", "Latas de aluminio"],
        "horarios": [(0, "09:00", "18:00"), (1, "09:00", "18:00"), (2, "09:00", "18:00"),
                     (3, "09:00", "18:00"), (4, "09:00", "18:00")],
        "contenedores": [{"codigo": "DEMO-ANIMAS-01", "estado": "Casi lleno", "porcentaje": 90, "material": None}],
    },
    {
        "nombre": "Contenedor de Latas",
        "direccion": "Bombero Hernandez 143",
        "latitud": -39.8136, "longitud": -73.2269,
        "materiales": ["Laton"],
        "horarios": [(0, "09:00", "20:00")],
        "contenedores": [{"codigo": "CONT-LATA-LATA01", "estado": "Casi lleno", "porcentaje": 86.67, "material": "Laton"}],
    },
    {
        "nombre": "Sector Sodimac",
        "direccion": "Alonso Villanuevas 145",
        "latitud": -39.8329, "longitud": -73.2201,
        "materiales": ["Vidrio"],
        "horarios": [(6, "09:00", "20:00")],
        "contenedores": [{"codigo": "CONT-SODIMAC-VIDRIO-01", "estado": "Casi lleno", "porcentaje": 100, "material": "Vidrio"}],
    },
    {
        "nombre": "Latas de aluminio",
        "direccion": "Avenida Argentina Pasaje Bonifacio",
        "latitud": -39.819588, "longitud": -73.245209,
        "materiales": ["Cartón", "Latas de aluminio"],
        "horarios": [(0, "09:00", "20:00"), (1, "09:00", "20:00"), (2, "09:00", "20:00"),
                     (3, "09:00", "20:00")],
        "contenedores": [],
    },
    {
        "nombre": "Parque Guillermo  Harnecker",
        "direccion": "Avenida Pedro Montt #779, Valdivia, Los Rios",
        "latitud": -39.820102, "longitud": -73.235199,
        "materiales": ["Plástico PET", "Cartón", "Latas de aluminio", "Laton", "Plásticos Tipo 2 (ADPE)"],
        "horarios": [(0, "08:00", "21:00"), (1, "08:00", "21:00"), (2, "08:00", "21:00"),
                     (3, "08:00", "21:00"), (4, "08:00", "21:00")],
        "contenedores": [],
    },
    {
        "nombre": "Parque Krahmer",
        "direccion": "Rodolfo Beckdorf 1657, Valdivia, Los Ríos",
        "latitud": -39.8302432408177, "longitud": -73.2281215754843,
        "materiales": ["Plástico PET", "Vidrio"],
        "horarios": [(0, "08:00", "20:00"), (1, "08:00", "20:00"), (2, "08:00", "20:00"),
                     (3, "08:00", "20:00"), (4, "08:00", "20:00"), (5, "08:00", "20:00"),
                     (6, "08:00", "20:00")],
        "contenedores": [],
    },
    {
        "nombre": "Parque Saval",
        "direccion": "Parque Saval 1, Valdivia, Los Ríos",
        "latitud": -39.80561942413646, "longitud": -73.25538357519324,
        "materiales": ["Plástico PET", "Vidrio", "Latas de aluminio"],
        "horarios": [(1, "08:00", "18:00"), (2, "08:00", "18:00"), (3, "08:00", "18:00"),
                     (4, "08:00", "18:00"), (5, "08:00", "18:00"), (6, "08:00", "18:00")],
        "contenedores": [],
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

        for dia, inicio, fin in datos.get("horarios", []):
            hora_inicio, hora_fin = time.fromisoformat(inicio), time.fromisoformat(fin)
            horario = db.session.scalar(db.select(Horario).where(
                Horario.punto_id == punto.id, Horario.dia_semana == dia,
                Horario.hora_inicio == hora_inicio, Horario.hora_fin == hora_fin,
            ))
            if horario is None:
                db.session.add(Horario(
                    punto_id=punto.id, dia_semana=dia,
                    hora_inicio=hora_inicio, hora_fin=hora_fin,
                ))

        for datos_contenedor in datos.get("contenedores", []):
            contenedor = db.session.scalar(
                db.select(Contenedor).where(Contenedor.codigo == datos_contenedor["codigo"])
            )
            if contenedor is None:
                material_id = None
                if datos_contenedor.get("material"):
                    material_id = materiales[datos_contenedor["material"]].id
                db.session.add(Contenedor(
                    punto_id=punto.id, codigo=datos_contenedor["codigo"],
                    estado=datos_contenedor["estado"],
                    porcentaje_llenado=datos_contenedor["porcentaje"],
                    ultima_actualizacion=datetime.now(), activo=True,
                    material_id=material_id,
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


# Dispositivos IoT vinculados a contenedores ya existentes. Solo se cargan al
# iniciar la aplicación o al ejecutar python seed.py; cargar_datos() conserva
# únicamente el dispositivo de demostración para no alterar las pruebas.
DISPOSITIVOS = {
    "CONT-SODIMAC-VIDRIO-01": "ECO-SODIMAC-VIDRIO-01",
    "CONT-LATA-LATA01": "ECO-LATA-LATA-01",
}


def cargar_dispositivos():
    """Vincular los dispositivos IoT a sus contenedores (idempotente)."""
    for codigo_contenedor, identificador in DISPOSITIVOS.items():
        contenedor = db.session.scalar(
            db.select(Contenedor).where(Contenedor.codigo == codigo_contenedor))
        if contenedor is None:
            continue
        dispositivo = db.session.scalar(
            db.select(DispositivoIoT).where(DispositivoIoT.identificador == identificador))
        if dispositivo is None:
            db.session.add(DispositivoIoT(
                identificador=identificador, contenedor_id=contenedor.id, activo=True,
                modo_actual="AUTO", compuerta_actual="ABIERTA",
            ))
    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        try:
            cargar_datos()
            cargar_dispositivos()
        except Exception:
            db.session.rollback()
            raise
    print("Datos cargados sin duplicados.")
