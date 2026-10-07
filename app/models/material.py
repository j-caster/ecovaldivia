from app.extensions import db


class Material(db.Model):
    __tablename__ = "material"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    instrucciones = db.Column(db.Text)

    puntos = db.relationship(
        "PuntoReciclaje", secondary="punto_material", back_populates="materiales"
    )
