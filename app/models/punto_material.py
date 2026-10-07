from app.extensions import db


class PuntoMaterial(db.Model):
    __tablename__ = "punto_material"

    punto_id = db.Column(
        db.Integer, db.ForeignKey("punto_reciclaje.id"), primary_key=True
    )
    material_id = db.Column(
        db.Integer, db.ForeignKey("material.id"), primary_key=True
    )
