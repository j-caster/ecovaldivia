from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"
    __table_args__ = (
        db.CheckConstraint("rol IN ('operador', 'administrador')", name="ck_usuario_rol"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def is_active(self):
        return bool(self.activo)

    @validates("rol")
    def validar_rol(self, key, valor):
        if valor not in ("operador", "administrador"):
            raise ValueError("Rol no permitido.")
        return valor

    def establecer_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verificar_password(self, password):
        return check_password_hash(self.password_hash, password)
