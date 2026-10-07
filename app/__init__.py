from flask import Flask

from config import Config


def create_app(config_class=Config):
    """Crear y configurar una instancia de EcoValdivia."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    from app.routes.public import public_bp

    app.register_blueprint(public_bp)
    return app
