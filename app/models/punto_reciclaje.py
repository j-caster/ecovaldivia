from app.extensions import db


class PuntoReciclaje(db.Model):
    __tablename__ = "punto_reciclaje"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    latitud = db.Column(db.Float)
    longitud = db.Column(db.Float)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    horarios = db.relationship("Horario", back_populates="punto")
    contenedores = db.relationship("Contenedor", back_populates="punto")
    materiales = db.relationship(
        "Material", secondary="punto_material", back_populates="puntos"
    )
