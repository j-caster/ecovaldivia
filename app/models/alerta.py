from app.extensions import db


class Alerta(db.Model):
    __tablename__ = "alerta"
    __table_args__ = (
        db.CheckConstraint("tipo = 'LLENO'", name="ck_alerta_tipo"),
        db.Index("uq_alerta_activa_contenedor_tipo", "contenedor_id", "tipo", unique=True,
                 sqlite_where=db.text("activa = true"), postgresql_where=db.text("activa = true")),
    )

    id = db.Column(db.Integer, primary_key=True)
    contenedor_id = db.Column(db.Integer, db.ForeignKey("contenedor.id"), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default="LLENO")
    mensaje = db.Column(db.Text, nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada_en = db.Column(db.DateTime, nullable=False)
    cerrada_en = db.Column(db.DateTime)

    contenedor = db.relationship("Contenedor", back_populates="alertas")
