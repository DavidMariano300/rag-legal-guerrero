from app.auth import hash_password, verify_password


def test_hash_password_no_guarda_texto_plano():
    hashed = hash_password("miContraseñaSecreta123")
    assert hashed != "miContraseñaSecreta123"


def test_verify_password_correcta():
    hashed = hash_password("miContraseñaSecreta123")
    assert verify_password("miContraseñaSecreta123", hashed) is True


def test_verify_password_incorrecta():
    hashed = hash_password("miContraseñaSecreta123")
    assert verify_password("otraContraseña", hashed) is False


def test_hash_password_es_distinto_cada_vez():
    # bcrypt usa un salt aleatorio por hash, así que dos hashes de la misma
    # contraseña no deben ser iguales — evita que un data leak revele qué
    # usuarios comparten la misma contraseña.
    h1 = hash_password("misma-contraseña")
    h2 = hash_password("misma-contraseña")
    assert h1 != h2
