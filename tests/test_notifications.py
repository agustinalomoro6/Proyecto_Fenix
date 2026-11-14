"""Pruebas de notify (I4-A): confirmación del proveedor y clasificación de errores."""
import pytest
import requests
from fenix.services import notifications
from fenix.utils.errors import PermanentError, RetryableError
 
TOKEN = "123456:TOKEN-FICTICIO-SOLO-TEST"  # Fixture pública: no es un token real.
HOOK = "https://hooks.slack.com/services/T000/B000/WEBHOOK-FICTICIO"
 
 
class FakeResponse:
    """Respuesta HTTP mínima: código, cuerpo de texto, cabeceras y JSON opcional."""
 
    def __init__(self, status=200, text="", headers=None, payload=None):
        self.status_code, self.text, self.headers = status, text, headers or {}
        self._payload = payload
 
    def json(self):
        if self._payload is None:
            raise ValueError("no es JSON")
        return self._payload
 
 
class Spy:
    """Reemplaza requests.post: registra las llamadas y devuelve o lanza lo indicado."""
 
    def __init__(self, result=None):
        default = FakeResponse(200, "ok", payload={"ok": True})
        self.result, self.calls = result or default, []
 
    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
 
 
def use(monkeypatch, provider, result=None):
    """Configura el proveedor con credenciales ficticias y un requests.post falso."""
    spy = Spy(result)
    monkeypatch.setenv("NOTIFY_PROVIDER", provider)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", HOOK)
    monkeypatch.setattr(notifications.requests, "post", spy.post)
    return spy
 
 
@pytest.mark.pendiente
def test_console_mode_prints_truncated_text_without_http(monkeypatch, capsys):
    """El modo console imprime hasta 1000 caracteres y no hace ninguna llamada HTTP."""
    spy = use(monkeypatch, "console")
    notifications.notify("x" * 1500)
    assert capsys.readouterr().out.strip() == "x" * 1000 and spy.calls == []
 
 
@pytest.mark.pendiente
def test_unknown_provider_is_permanent(monkeypatch):
    """Un proveedor desconocido es una configuración inválida: no se reintenta."""
    use(monkeypatch, "whatsapp")
    with pytest.raises(PermanentError):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
def test_telegram_success_sends_expected_request(monkeypatch):
    """Telegram: URL con el token, chat_id y texto, y timeout explícito (2, 5)."""
    spy = use(monkeypatch, "telegram")
    assert notifications.notify("alerta") is None
    call = spy.calls[0]
    assert call["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert call["json"] == {"chat_id": "-100123", "text": "alerta"}
    assert call["timeout"] == (2, 5)
 
 
@pytest.mark.pendiente
def test_text_is_truncated_to_1000_characters(monkeypatch):
    """Nunca se envían más de 1000 caracteres al proveedor."""
    spy = use(monkeypatch, "telegram")
    notifications.notify("y" * 5000)
    assert len(spy.calls[0]["json"]["text"]) == 1000
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("missing", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
def test_telegram_missing_credentials_is_permanent(monkeypatch, missing):
    """Sin token o sin chat no se llama al proveedor y no se reintenta."""
    spy = use(monkeypatch, "telegram")
    monkeypatch.setenv(missing, "")
    with pytest.raises(PermanentError):
        notifications.notify("hola")
    assert spy.calls == []
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("response", [
    FakeResponse(200, payload={"ok": False}),     # HTTP 200 pero Telegram no lo aceptó.
    FakeResponse(200, payload={"result": {}}),    # Falta el campo ok.
    FakeResponse(200, "<html>", payload=None)])   # Cuerpo que no es JSON.
def test_telegram_requires_ok_true_not_just_http_200(monkeypatch, response):
    """Un HTTP 200 no basta: el JSON debe traer ok igual a True."""
    use(monkeypatch, "telegram", response)
    with pytest.raises(PermanentError):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
def test_slack_success_sends_expected_request(monkeypatch):
    """Slack: POST al webhook con {"text": ...}, timeout (2, 5) y cuerpo "ok"."""
    spy = use(monkeypatch, "slack", FakeResponse(200, "ok\n"))
    assert notifications.notify("alerta") is None
    assert spy.calls[0] == {"url": HOOK, "json": {"text": "alerta"}, "timeout": (2, 5)}
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("url", ["", "http://hooks.slack.com/x", "no-es-una-url"])
def test_slack_invalid_webhook_is_permanent(monkeypatch, url):
    """El webhook debe estar configurado y usar HTTPS; si no, no se envía nada."""
    spy = use(monkeypatch, "slack")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", url)
    with pytest.raises(PermanentError):
        notifications.notify("hola")
    assert spy.calls == []
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("body", ["invalid_payload", "", "no_service"])
def test_slack_requires_ok_body(monkeypatch, body):
    """Un HTTP 200 con un cuerpo distinto de "ok" no confirma el envío."""
    use(monkeypatch, "slack", FakeResponse(200, body))
    with pytest.raises(PermanentError):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("provider", ["telegram", "slack"])
@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_retryable(monkeypatch, provider, status):
    """Un 5xx del proveedor es transitorio: se reintenta."""
    use(monkeypatch, provider, FakeResponse(status))
    with pytest.raises(RetryableError):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("provider", ["telegram", "slack"])
@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_permanent(monkeypatch, provider, status):
    """Credenciales inválidas o recurso inexistente: no se reintenta infinitamente."""
    use(monkeypatch, provider, FakeResponse(status))
    with pytest.raises(PermanentError):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("headers,payload,expected", [
    ({"Retry-After": "3"}, None, "3"),                          # Cabecera (Slack).
    ({}, {"parameters": {"retry_after": 7}}, "7"),              # JSON (Telegram).
    ({"Retry-After": "9999"}, None, "60"),                      # Se acota a 60 s.
    ({"Retry-After": "0"}, None, "1"),                          # Mínimo 1 s.
    ({"Retry-After": "mañana"}, None, "5"),                     # Valor inutilizable: 5 s.
    ({}, None, "5")])                                           # Sin dato: 5 s.
def test_rate_limit_is_retryable_bounded(monkeypatch, headers, payload, expected):
    """429 es transitorio y la espera informada nunca supera los 60 segundos."""
    use(monkeypatch, "telegram", FakeResponse(429, headers=headers, payload=payload))
    with pytest.raises(RetryableError) as info:
        notifications.notify("hola")
    assert f"esperar {expected} s" in str(info.value)
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("failure,expected", [
    (requests.Timeout("timeout"), RetryableError),
    (requests.ConnectionError("sin red"), RetryableError),
    (requests.exceptions.InvalidURL("url rota"), PermanentError)])
def test_network_failures_are_classified(monkeypatch, failure, expected):
    """Timeout y falla de conexión se reintentan; una URL inválida no."""
    use(monkeypatch, "telegram", failure)
    with pytest.raises(expected):
        notifications.notify("hola")
 
 
@pytest.mark.pendiente
@pytest.mark.parametrize("provider", ["telegram", "slack"])
def test_errors_never_leak_the_token_or_url(monkeypatch, provider):
    """El error no incluye el token ni el webhook, ni encadena la excepción original."""
    secret_failure = requests.ConnectionError(f"fallo conectando a {TOKEN} y {HOOK}")
    use(monkeypatch, provider, secret_failure)
    with pytest.raises(RetryableError) as info:
        notifications.notify("hola")
    error = info.value
    assert TOKEN not in str(error) and HOOK not in str(error)
    assert error.__cause__ is None and error.__suppress_context__  # Sin la original.
 
 
@pytest.mark.pendiente
def test_status_errors_never_leak_the_token(monkeypatch):
    """Los mensajes por código HTTP tampoco incluyen credenciales."""
    use(monkeypatch, "telegram", FakeResponse(401, text=f"token {TOKEN} inválido"))
    with pytest.raises(PermanentError) as info:
        notifications.notify("hola")
    assert TOKEN not in str(info.value)