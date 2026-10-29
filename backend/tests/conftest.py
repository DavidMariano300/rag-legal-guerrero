import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    """TestClient con una base SQLite en memoria en vez de la Postgres real.

    Importante: NO se usa `with TestClient(app) as c:` — eso dispara el evento de
    startup de FastAPI, que intenta conectarse a la Postgres/Qdrant reales del
    docker-compose (inexistentes en este entorno de pruebas). Como las rutas que
    probamos aquí no dependen de ese startup, basta con crear las tablas nosotros
    mismos contra el motor de pruebas.

    `poolclass=StaticPool` es obligatorio aquí: una base SQLite ":memory:" vive
    solo mientras dura UNA conexión. Sin StaticPool, el engine abre una conexión
    nueva (y por tanto una base vacía, sin la tabla `users`) por cada sesión.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
