from app.extensions import db


class EventoOperacional(db.Model):
    __tablename__ = "evento_operacional"
    __table_args__ = (
        db.CheckConstraint("tipo IN ('VACIADO', 'ALERTA_CERRADA')", name="ck_evento_operacional_tipo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    contenedor_id = db.Column(db.Integer, db.ForeignKey("contenedor.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False)

    contenedor = db.relationship("Contenedor", back_populates="eventos_operacionales")
    usuario = db.relationship("Usuario")
