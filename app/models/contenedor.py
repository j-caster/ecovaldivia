from app.extensions import db


class Contenedor(db.Model):
    __tablename__ = "contenedor"
    __table_args__ = (
        db.CheckConstraint(
            "porcentaje_llenado BETWEEN 0 AND 100",
            name="ck_contenedor_porcentaje_llenado",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(
        db.Integer, db.ForeignKey("punto_reciclaje.id"), nullable=False
    )
    codigo = db.Column(db.String(100), nullable=False, unique=True)
    estado = db.Column(db.String(50), nullable=False, default="sin_datos")
    porcentaje_llenado = db.Column(db.Float)
    ultima_actualizacion = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    punto = db.relationship("PuntoReciclaje", back_populates="contenedores")
    dispositivos = db.relationship("DispositivoIoT", back_populates="contenedor")
    alertas = db.relationship("Alerta", back_populates="contenedor")
    eventos_operacionales = db.relationship("EventoOperacional", back_populates="contenedor")
