from app.extensions import db


class DispositivoIoT(db.Model):
    __tablename__ = "dispositivo_iot"
    __table_args__ = (
        db.Index(
            "uq_dispositivo_activo_contenedor", "contenedor_id", unique=True,
            sqlite_where=db.text("activo = true"),
            postgresql_where=db.text("activo = true"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    identificador = db.Column(db.String(100), nullable=False, unique=True)
    contenedor_id = db.Column(db.Integer, db.ForeignKey("contenedor.id"), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    modo_actual = db.Column(db.String(10))
    compuerta_actual = db.Column(db.String(10))
    ultima_ip = db.Column(db.String(45))
    ultimo_boot = db.Column(db.String(100))
    ultimo_seq = db.Column(db.BigInteger)
    ultima_actualizacion = db.Column(db.DateTime)

    contenedor = db.relationship("Contenedor", back_populates="dispositivos")
    mediciones = db.relationship("Medicion", back_populates="dispositivo")
