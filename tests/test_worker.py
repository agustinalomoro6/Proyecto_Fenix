"""Pruebas del worker (I5-A): ACK solo tras el éxito y un mensaje malo no detiene al resto."""
import json
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fenix.services import worker
from fenix.utils.errors import PermanentError, RetryableError, ValidationError

URL = "http://cola/test"
EVENT = {"event_id": "evt-001", "resource_id": "node-01"}
SECRET_TEXT = "TOKEN-SECRETO-NO-DEBE-APARECER"


def message(body=None, mid="msg-1", receipt="rec-1", count="1"):
    """Arma un mensaje crudo de SQS como lo devuelve receive."""
    raw = body if isinstance(body, str) else json.dumps(EVENT if body is None else body)
    return {"MessageId": mid, "ReceiptHandle": receipt, "Body": raw,
            "Attributes": {"ApproximateReceiveCount": count}}


class Logs:
    """Logger falso: guarda cada llamada para inspeccionar mensaje y contexto."""

    def __init__(self):
        self.records = []

    def _add(self, level, msg, extra=None):
        self.records.append((level, msg, extra or {}))

    def info(self, msg, extra=None):
        self._add("info", msg, extra)

    def warning(self, msg, extra=None):
        self._add("warning", msg, extra)

    def error(self, msg, extra=None):
        self._add("error", msg, extra)

    def text(self):
        return json.dumps(self.records, default=str)


class Env:
    """Transporte falso: registra el orden de las llamadas a ACK, retry y handler."""

    def __init__(self, batches):
        self.batches, self.calls, self.sleeps = list(batches), [], []
        self.ack_error = self.retry_error = None

    def receive(self, url):
        self.calls.append(("receive", url))
        item = self.batches.pop(0) if self.batches else []
        if isinstance(item, BaseException):
            raise item
        return item

    def acknowledge(self, url, receipt):
        self.calls.append(("ack", receipt))
        if self.ack_error:
            raise self.ack_error

    def retry_later(self, url, msg):
        self.calls.append(("retry", msg["ReceiptHandle"]))
        if self.retry_error:
            raise self.retry_error
        return 4

    def names(self):
        return [name for name, _ in self.calls if name != "receive"]


@pytest.fixture
def env(monkeypatch):
    """Worker con SQS y reloj simulados; devuelve el entorno y el logger falso."""
    holder = {}

    def build(batches):
        env = Env(batches)
        monkeypatch.setattr(worker, "receive", env.receive)
        monkeypatch.setattr(worker, "acknowledge", env.acknowledge)
        monkeypatch.setattr(worker, "retry_later", env.retry_later)
        monkeypatch.setattr(worker.time, "sleep", lambda s: env.sleeps.append(s))
        holder["env"] = env
        return env, Logs()
    return build


def make_handler(env, error=None):
    """Handler falso que registra su llamada en el mismo orden que ACK y retry."""
    def handler(event):
        env.calls.append(("handler", event["event_id"]))
        if error:
            raise error
    return handler


@pytest.mark.pendiente
def test_success_runs_handler_then_acks_once(env):
    """Éxito: primero el handler, después un único ACK con el ReceiptHandle recibido."""
    e, logs = env([[message()]])
    worker.run(URL, make_handler(e), logs, once=True)
    assert e.names() == ["handler", "ack"]
    assert ("ack", "rec-1") in e.calls
    assert any(r[1] == "mensaje_confirmado" for r in logs.records)


@pytest.mark.pendiente
@pytest.mark.parametrize("error", [RetryableError("x"), PermanentError("x"),
                                   ValidationError("x"), OSError("disco")])
def test_failed_handler_never_acks_and_schedules_retry(env, error):
    """Si el handler falla no hay ACK: el mensaje se reprograma con retry_later."""
    e, logs = env([[message()]])
    worker.run(URL, make_handler(e, error), logs, once=True)
    assert e.names() == ["handler", "retry"]


@pytest.mark.pendiente
@pytest.mark.parametrize("body", ["{no es json", "", "[1, 2]", "42", '"texto"', "null"])
def test_corrupt_or_non_object_body_skips_handler_and_retries(env, body):
    """JSON roto o que no es un objeto: no se llama al handler ni se confirma."""
    e, logs = env([[message(body)]])
    worker.run(URL, make_handler(e), logs, once=True)
    assert e.names() == ["retry"]
    assert any(r[2].get("message_id") == "msg-1" for r in logs.records)  # Contexto previo.


@pytest.mark.pendiente
def test_poison_message_does_not_hide_the_next_one(env):
    """Un mensaje corrupto no impide procesar y confirmar el siguiente."""
    e, logs = env([[message("{roto", mid="m1", receipt="r1"),
                    message(mid="m2", receipt="r2")]])
    worker.run(URL, make_handler(e), logs, once=True)
    assert e.names() == ["retry", "handler", "ack"]
    assert ("ack", "r2") in e.calls and ("ack", "r1") not in e.calls


@pytest.mark.pendiente
def test_ack_failure_leaves_event_available_and_worker_alive(env):
    """Si falla el ACK no se rompe el worker: el evento se reprograma."""
    e, logs = env([[message()]])
    e.ack_error = ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteMessage")
    worker.run(URL, make_handler(e), logs, once=True)
    assert e.names() == ["handler", "ack", "retry"]


@pytest.mark.pendiente
def test_retry_failure_is_logged_and_does_not_crash(env):
    """Si también falla retry_later se registra y el worker sigue vivo."""
    e, logs = env([[message("{roto")]])
    e.retry_error = ClientError({"Error": {"Code": "Throttling"}}, "ChangeMessageVisibility")
    worker.run(URL, make_handler(e), logs, once=True)
    assert any(r[1] == "fallo_retry_later" for r in logs.records)


@pytest.mark.pendiente
def test_receive_failure_in_once_mode_returns_without_crashing(env):
    """Un fallo de transporte al recibir se registra y, con once, termina sin excepción."""
    e, logs = env([EndpointConnectionError(endpoint_url="http://localhost:4566")])
    worker.run(URL, make_handler(e), logs, once=True)
    assert any(r[1] == "fallo_receive" for r in logs.records) and e.sleeps == []


@pytest.mark.pendiente
def test_receive_failure_waits_two_seconds_and_retries(env):
    """Sin once, tras un fallo de transporte espera 2 s y vuelve a consultar."""
    e, logs = env([EndpointConnectionError(endpoint_url="x"), [message()], KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):  # Ctrl+C sale; lo atiende el main de la CLI.
        worker.run(URL, make_handler(e), logs)
    assert e.sleeps == [2] and e.names() == ["handler", "ack"]


@pytest.mark.pendiente
def test_once_does_a_single_receive(env):
    """once hace una sola consulta aunque la cola siga teniendo mensajes."""
    e, logs = env([[message()], [message(mid="m2", receipt="r2")]])
    worker.run(URL, make_handler(e), logs, once=True)
    assert [c for c in e.calls if c[0] == "receive"] == [("receive", URL)]


@pytest.mark.pendiente
def test_not_implemented_error_propagates(env):
    """Una tarea pendiente no se esconde como un reintento: el error se propaga."""
    e, logs = env([[message()]])
    with pytest.raises(NotImplementedError):
        worker.run(URL, make_handler(e, NotImplementedError("falta I5-B")), logs, once=True)
    assert "ack" not in e.names()


@pytest.mark.pendiente
def test_logs_never_include_error_text_or_body(env):
    """El log guarda el tipo del error, nunca su texto ni el cuerpo del mensaje."""
    e, logs = env([[message({"event_id": "evt-001", "resource_id": "node-01",
                             "extra": SECRET_TEXT})]])
    worker.run(URL, make_handler(e, RetryableError(SECRET_TEXT)), logs, once=True)
    assert SECRET_TEXT not in logs.text()
    assert any(r[2].get("status") == "RetryableError" for r in logs.records)


@pytest.mark.pendiente
def test_untrusted_ids_are_not_logged_when_too_long(env):
    """Un event_id enorme o que no es texto no se vuelca al log."""
    e, logs = env([[message({"event_id": "x" * 500, "resource_id": 7})]])
    worker.run(URL, make_handler(e), logs, once=True)
    assert "x" * 100 not in logs.text()
