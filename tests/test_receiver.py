"""Pruebas del receptor HTTP (I3-B): orden de las comprobaciones y códigos de estado."""
import json
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient
from fenix.services import receiver
from fenix.utils.crypto import signature

SECRET = "clave-ficticia-solo-test"  # Fixture pública: no es un secreto real.
INVENTORY = {"node-01": {"type": "ec2", "id": "i-0123456789abcdef0"},
             "bucket-01": {"type": "s3", "id": "fenix-grupo01-demo",
                           "expected_tags": {"Owner": "g"}}}
EVENT = {"schema_version": 1, "event_id": "evt-node-001", "event_type": "instance.stopped",
         "resource_id": "node-01", "occurred_at": "2026-10-22T18:00:00Z",
         "simulate_failures": 0}


class Spy:
    """Registra las publicaciones para comprobar si hubo o no efectos en la cola."""

    def __init__(self):
        self.published = []

    def publish(self, url, event, delay=0):
        self.published.append(event)
        return "msg-123"


@pytest.fixture
def spy(monkeypatch):
    """Receptor con la nube simulada: inventario fijo, cola falsa y clave de prueba."""
    spy = Spy()
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("QUEUE_PREFIX", "fenix-test")
    monkeypatch.setattr(receiver, "load", lambda path: INVENTORY)
    monkeypatch.setattr(receiver, "queue_url", lambda prefix: "http://cola/test")
    monkeypatch.setattr(receiver, "publish", spy.publish)
    return spy


def post(body, header=None, now=None):
    """Envía un POST firmado (o con la cabecera indicada) al receptor."""
    import time
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    ts = int(time.time()) if now is None else now
    headers = {} if header == "" else {
        "X-Webhook-Signature": header or f"t={ts},v1={signature(SECRET, ts, raw)}"}
    return TestClient(receiver.app).post("/webhook", content=raw, headers=headers)


@pytest.mark.pendiente
def test_valid_event_is_accepted_after_publishing(spy):
    """Un evento correcto responde 202 con los identificadores y se encola una vez."""
    response = post(EVENT)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "event_id": "evt-node-001",
                               "message_id": "msg-123"}
    assert spy.published == [EVENT]


@pytest.mark.pendiente
@pytest.mark.parametrize("header", ["", "basura", "t=1000,v1=" + "a" * 64])
def test_bad_signature_is_401_and_not_published(spy, header):
    """Sin firma, con formato roto o con una firma falsa: 401 y nada en la cola."""
    assert post(EVENT, header=header).status_code == 401
    assert spy.published == []


@pytest.mark.pendiente
def test_old_timestamp_is_401_with_same_message(spy):
    """Una firma correcta pero vieja da el mismo 401 genérico que una firma falsa."""
    old = post(EVENT, now=1000)
    fake = post(EVENT, header="t=1000,v1=" + "a" * 64)
    assert old.status_code == fake.status_code == 401
    assert old.json() == fake.json()  # No se revela cuál de las validaciones falló.
    assert spy.published == []


@pytest.mark.pendiente
@pytest.mark.parametrize("body", [b"no es json", b"\xff\xfe\x00", b"[1, 2"])
def test_signed_but_invalid_json_is_400(spy, body):
    """Firma válida sobre un cuerpo que no es JSON: 400, no 401 ni 422."""
    assert post(body).status_code == 400
    assert spy.published == []


@pytest.mark.pendiente
@pytest.mark.parametrize("event", [
    {**EVENT, "extra": 1}, {**EVENT, "event_type": "instance.deleted"},
    {**EVENT, "resource_id": "no-existe"}, {**EVENT, "resource_id": "bucket-01"},
    {**EVENT, "simulate_failures": 6}, [], "texto"])
def test_contract_violation_is_422_and_not_published(spy, event):
    """Firma válida pero evento fuera del contrato o del inventario: 422 y sin cola."""
    assert post(event).status_code == 422
    assert spy.published == []


@pytest.mark.pendiente
def test_oversized_body_is_413(spy):
    """Más de 16 KiB se rechaza antes de verificar o encolar."""
    assert post(b"x" * 16385).status_code == 413
    assert spy.published == []


@pytest.mark.pendiente
@pytest.mark.parametrize("error", [
    ClientError({"Error": {"Code": "AccessDenied"}}, "SendMessage"),
    EndpointConnectionError(endpoint_url="http://localhost:4566")])
def test_sqs_failure_is_503_and_never_accepted(spy, monkeypatch, error):
    """Si SQS falla no se promete aceptación: 503 sin la palabra accepted."""
    def broken(url, event, delay=0):
        raise error
    monkeypatch.setattr(receiver, "publish", broken)
    response = post(EVENT)
    assert response.status_code == 503
    assert "accepted" not in response.text


@pytest.mark.pendiente
def test_queue_lookup_failure_is_503(spy, monkeypatch):
    """Si no se encuentra la cola, también es 503."""
    def missing(prefix):
        raise ClientError({"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}},
                          "GetQueueUrl")
    monkeypatch.setattr(receiver, "queue_url", missing)
    assert post(EVENT).status_code == 503


@pytest.mark.pendiente
@pytest.mark.parametrize("secret", ["", "corta"])
def test_missing_secret_is_500_not_401(spy, monkeypatch, secret):
    """Un servidor sin clave es un error del servidor: 500 y nada en la cola."""
    monkeypatch.setenv("WEBHOOK_SECRET", secret)
    assert post(EVENT).status_code == 500
    assert spy.published == []
