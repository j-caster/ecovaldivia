class Config:
    """Configuración base de la aplicación."""

    TESTING = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///ecovaldivia.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
