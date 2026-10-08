from app.extensions import db


class Medicion(db.Model):
    __tablename__ = "medicion"
    __table_args__ = (
        db.UniqueConstraint("dispositivo_id", "boot", "seq", name="uq_medicion_dispositivo_boot_seq"),
        db.CheckConstraint("seq >= 0", name="ck_medicion_seq"),
        db.CheckConstraint("porcentaje_llenado BETWEEN 0 AND 100", name="ck_medicion_porcentaje"),
        db.CheckConstraint("sensor1_cm > 0 AND sensor2_cm > 0", name="ck_medicion_sensores"),
        db.CheckConstraint("last_cmd_ctr IS NULL OR last_cmd_ctr >= 0", name="ck_medicion_ctr"),
    )

    id = db.Column(db.Integer, primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey("dispositivo_iot.id"), nullable=False)
    medicion_externa_id = db.Column(db.String(100))
    sensor1_cm = db.Column(db.Float, nullable=False)
    sensor2_cm = db.Column(db.Float, nullable=False)
    porcentaje_llenado = db.Column(db.Float, nullable=False)
    estado_calculado = db.Column(db.String(50), nullable=False)
    modo = db.Column(db.String(10), nullable=False)
    compuerta = db.Column(db.String(10), nullable=False)
    fuente = db.Column(db.String(20), nullable=False)
    boot = db.Column(db.String(100), nullable=False)
    seq = db.Column(db.BigInteger, nullable=False)
    last_cmd_ctr = db.Column(db.BigInteger)
    ip_origen = db.Column(db.String(45))
    recibida_en = db.Column(db.DateTime, nullable=False)

    dispositivo = db.relationship("DispositivoIoT", back_populates="mediciones")
