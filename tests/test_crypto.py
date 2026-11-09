"""Pruebas de la verificación HMAC (I3-A): formato, ventana de tiempo y firma."""
import pytest
from fenix.utils.crypto import signature, verify
from fenix.utils.errors import ValidationError

SECRET = "clave-ficticia-solo-test"  # Fixture pública: no es un secreto real.
BODY = b'{"x":1}'
NOW = 1000


def header_for(timestamp=NOW, body=BODY, secret=SECRET) -> str:
    """Arma una cabecera válida con la misma función del emisor."""
    return f"t={timestamp},v1={signature(secret, timestamp, body)}"


@pytest.mark.pendiente
def test_valid_signature_is_accepted():
    """Una cabecera correcta no lanza excepción y devuelve None."""
    assert verify(SECRET, header_for(), BODY, now=NOW) is None


@pytest.mark.pendiente
def test_header_order_does_not_matter():
    """v1 puede ir antes que t: lo que importa es que estén los dos una vez."""
    digest = signature(SECRET, NOW, BODY)
    verify(SECRET, f"v1={digest},t={NOW}", BODY, now=NOW)


@pytest.mark.pendiente
@pytest.mark.parametrize("offset", [-300, 0, 300])
def test_time_window_limits_are_accepted(offset):
    """Los bordes exactos de la ventana (300 segundos) se aceptan."""
    verify(SECRET, header_for(), BODY, now=NOW + offset)


@pytest.mark.pendiente
@pytest.mark.parametrize("offset", [-301, 301, 3600])
def test_outside_time_window_is_rejected(offset):
    """Un mensaje viejo o del futuro se rechaza aunque la firma sea correcta."""
    with pytest.raises(ValidationError):
        verify(SECRET, header_for(), BODY, now=NOW + offset)


@pytest.mark.pendiente
def test_tampered_body_is_rejected():
    """La misma firma con otro cuerpo (otros bytes) no se acepta."""
    with pytest.raises(ValidationError):
        verify(SECRET, header_for(), b'{"x": 1}', now=NOW)


@pytest.mark.pendiente
def test_wrong_secret_is_rejected():
    """Una firma hecha con otra clave no se acepta."""
    with pytest.raises(ValidationError):
        verify(SECRET, header_for(secret="otra-clave-ficticia-12345"), BODY, now=NOW)


@pytest.mark.pendiente
@pytest.mark.parametrize("header", [
    "", "basura", "t=1000", "v1=" + "a" * 64,                   # Faltan campos.
    "t=1000,t=1000", "t=1000,v1=" + "a" * 64 + ",x=1",          # Repetidos o extra.
    "t=1000,v1=" + "a" * 64 + ",v1=" + "b" * 64,                # v1 duplicado.
    "t=abc,v1=" + "a" * 64, "t=-5,v1=" + "a" * 64,              # t no entero.
    "t=10.5,v1=" + "a" * 64, "t= 1000,v1=" + "a" * 64,
    "t=\uff11\uff10\uff10\uff10,v1=" + "a" * 64,                # Dígitos de ancho completo.
    "t=1000,v1=" + "a" * 63, "t=1000,v1=" + "a" * 65,           # v1 con largo incorrecto.
    "t=1000,v1=" + "g" * 64, "t=1000,v1=" + "A" * 64,           # No hexadecimal minúscula.
    "t=1000;v1=" + "a" * 64, "t=1000,v1",                       # Separadores rotos.
])
def test_malformed_header_is_rejected(header):
    """Toda cabecera ambigua o mal formada se rechaza con ValidationError."""
    with pytest.raises(ValidationError):
        verify(SECRET, header, BODY, now=NOW)


@pytest.mark.pendiente
@pytest.mark.parametrize("header,body", [(None, BODY), (123, BODY), ("x", "texto")])
def test_wrong_types_are_rejected(header, body):
    """Cabecera que no es texto o cuerpo que no son bytes se rechazan."""
    with pytest.raises(ValidationError):
        verify(SECRET, header, body, now=NOW)


@pytest.mark.pendiente
def test_error_messages_do_not_leak_secrets():
    """Ningún mensaje de error incluye la cabecera, la firma ni el secreto."""
    header = header_for()
    with pytest.raises(ValidationError) as info:
        verify(SECRET, header, b"otro", now=NOW)
    message = str(info.value)
    assert SECRET not in message and header not in message
    assert signature(SECRET, NOW, BODY) not in message
