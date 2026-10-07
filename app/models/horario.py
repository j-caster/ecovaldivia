from app.extensions import db


class Horario(db.Model):
    __tablename__ = "horario"
    __table_args__ = (
        db.CheckConstraint("dia_semana BETWEEN 0 AND 6", name="ck_horario_dia_semana"),
    )

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(
        db.Integer, db.ForeignKey("punto_reciclaje.id"), nullable=False
    )
    # Convención: lunes = 0, domingo = 6.
    dia_semana = db.Column(db.Integer, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)

    punto = db.relationship("PuntoReciclaje", back_populates="horarios")
