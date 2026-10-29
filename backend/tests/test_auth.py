def test_health_no_auth_required(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_query_sin_token_rechazado(client):
    res = client.post("/api/query", json={"pregunta": "hola"})
    assert res.status_code in (401, 403)  # HTTPBearer sin credenciales devuelve 403


def test_registro_y_login(client):
    res = client.post("/api/auth/register", json={"email": "abogado@example.com", "password": "contraseña123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert token

    res = client.post("/api/auth/login", json={"email": "abogado@example.com", "password": "contraseña123"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_registro_duplicado_rechazado(client):
    payload = {"email": "duplicado@example.com", "password": "contraseña123"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 409


def test_login_password_incorrecta(client):
    client.post("/api/auth/register", json={"email": "test@example.com", "password": "correcta123"})
    res = client.post("/api/auth/login", json={"email": "test@example.com", "password": "incorrecta"})
    assert res.status_code == 401


def test_invitado_desactivado_devuelve_404(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "PERMITIR_INVITADOS", False)
    assert client.post("/api/auth/invitado").status_code == 404


def test_invitado_comparte_un_usuario_que_no_se_puede_registrar(client, monkeypatch):
    import jwt
    from app import main
    from app.auth import JWT_ALGORITHM, JWT_SECRET_KEY

    monkeypatch.setattr(main, "PERMITIR_INVITADOS", True)
    tokens = [client.post("/api/auth/invitado").json()["access_token"] for _ in range(2)]
    assert len({jwt.decode(t, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])["sub"] for t in tokens}) == 1
    res = client.get("/api/documents/templates", headers={"Authorization": f"Bearer {tokens[0]}"})
    assert res.status_code == 200

    res = client.post("/api/auth/register", json={"email": main.EMAIL_INVITADO, "password": "contraseña123"})
    assert res.status_code == 422


def test_limite_por_ip_real_detras_del_proxy(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "PERMITIR_INVITADOS", True)
    codigos = [client.post("/api/auth/invitado", headers={"X-Real-IP": "203.0.113.1"}).status_code for _ in range(6)]
    assert codigos[-1] == 429
    assert client.post("/api/auth/invitado", headers={"X-Real-IP": "203.0.113.2"}).status_code == 200


def test_registro_password_corta_rechazada(client):
    res = client.post("/api/auth/register", json={"email": "corta@example.com", "password": "123"})
    assert res.status_code == 422  # validación de Pydantic (min_length=8)


def test_token_permite_acceder_a_endpoint_protegido(client):
    res = client.post("/api/auth/register", json={"email": "protegido@example.com", "password": "contraseña123"})
    token = res.json()["access_token"]

    res = client.get("/api/documents/templates", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_token_invalido_rechazado(client):
    res = client.get("/api/documents/templates", headers={"Authorization": "Bearer token-invalido"})
    assert res.status_code == 401


def test_ollama_saturado_devuelve_503(client, monkeypatch):
    import httpx

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.main.answer_query", timeout)
    token = client.post(
        "/api/auth/register", json={"email": "saturado@example.com", "password": "contraseña123"}
    ).json()["access_token"]
    res = client.post("/api/query", json={"pregunta": "hola"}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 503
