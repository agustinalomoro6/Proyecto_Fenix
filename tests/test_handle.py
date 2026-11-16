"""Pruebas de handle (I5-B): registro durable, idempotencia y orden de las etapas."""
import json
import pytest
from fenix.services import remediation
from fenix.utils.errors import PermanentError, RetryableError, ValidationError
from fenix.utils.state import load, save

INVENTORY = {
    "node-01": {"type": "ec2", "id": "i-123"},
    "bucket-01": {"type": "s3", "id": "fenix-g1-demo", "expected_tags": {"Owner": "g1"}},
}


def make_event(**changes) -> dict:
    """Devuelve un evento válido de instancia, con los cambios indicados."""
    event = {"schema_version": 1, "event_id": "evt-node-001",
             "event_type": "instance.stopped", "resource_id": "node-01",
             "occurred_at": "2026-10-22T18:00:00Z", "simulate_failures": 0}
    event.update(changes)
    return event


class Spy:
    """Registra las llamadas a repair y notify, y permite hacerlas fallar."""

    def __init__(self):
        self.repairs, self.notices = [], []
        self.repair_error = self.notify_error = None

    def repair(self, resource, event_type):
        self.repairs.append((resource["id"], event_type))
        if self.repair_error:
            raise self.repair_error
        return "repaired"

    def notify(self, text):
        self.notices.append(text)
        if self.notify_error:
            raise self.notify_error


@pytest.fixture
def spy(tmp_path, monkeypatch):
    """Carpeta de trabajo temporal con inventario real en disco y repair/notify falsos."""
    monkeypatch.chdir(tmp_path)  # data/ queda dentro de la carpeta temporal.
    save("data/inventory.json", INVENTORY)
    spy = Spy()
    monkeypatch.setattr(remediation, "repair", spy.repair)
    monkeypatch.setattr(remediation, "notify", spy.notify)
    return spy


def ledger() -> dict:
    """Relee el ledger desde el disco: así se prueba que el estado es durable."""
    return load("data/events.json")


@pytest.mark.pendiente
def test_first_delivery_repairs_notifies_and_records(spy):
    """Primera entrega: una reparación, un aviso y el ledger completo en disco."""
    remediation.handle(make_event())
    assert spy.repairs == [("i-123", "instance.stopped")] and len(spy.notices) == 1
    entry = ledger()["evt-node-001"]
    assert entry["attempts"] == 1 and entry["repair_done"] and entry["notified"]
    assert entry["result"] == "repaired"


@pytest.mark.pendiente
def test_duplicate_delivery_has_no_repeated_effects(spy):
    """El mismo evento dos veces: una sola reparación y un solo aviso."""
    remediation.handle(make_event())
    before = ledger()
    remediation.handle(make_event())
    assert len(spy.repairs) == 1 and len(spy.notices) == 1
    assert ledger() == before


@pytest.mark.pendiente
def test_same_event_id_with_different_content_is_rejected(spy):
    """Reutilizar un event_id con otro contenido es un conflicto permanente."""
    remediation.handle(make_event())
    with pytest.raises(PermanentError):
        remediation.handle(make_event(simulate_failures=1))
    assert len(spy.repairs) == 1


@pytest.mark.pendiente
def test_simulated_failures_survive_restarts_and_touch_nothing(spy):
    """Con simulate_failures=2, las dos primeras entregas fallan sin tocar recursos."""
    event = make_event(simulate_failures=2)
    for expected_attempts in (1, 2):
        with pytest.raises(RetryableError):
            remediation.handle(event)
        assert ledger()["evt-node-001"]["attempts"] == expected_attempts  # Persistido.
        assert spy.repairs == [] and spy.notices == []
    remediation.handle(event)  # La tercera entrega ya repara y avisa.
    assert len(spy.repairs) == 1 and len(spy.notices) == 1
    assert ledger()["evt-node-001"]["attempts"] == 3


@pytest.mark.pendiente
def test_repair_failure_is_retried_without_notifying(spy):
    """Si repair falla no se avisa y la reparación se reintenta en la siguiente entrega."""
    spy.repair_error = RetryableError("falla pasajera")
    with pytest.raises(RetryableError):
        remediation.handle(make_event())
    assert spy.notices == []
    entry = ledger()["evt-node-001"]
    assert not entry["repair_done"] and not entry["notified"]
    spy.repair_error = None
    remediation.handle(make_event())
    assert len(spy.repairs) == 2 and len(spy.notices) == 1


@pytest.mark.pendiente
def test_notify_failure_does_not_repeat_the_repair(spy):
    """Si falla el aviso, la reparación ya quedó registrada y no se repite."""
    spy.notify_error = RetryableError("proveedor caído")
    with pytest.raises(RetryableError):
        remediation.handle(make_event())
    entry = ledger()["evt-node-001"]
    assert entry["repair_done"] and not entry["notified"]
    spy.notify_error = None
    remediation.handle(make_event())
    assert len(spy.repairs) == 1 and len(spy.notices) == 2  # Un aviso repetido es aceptado.
    assert ledger()["evt-node-001"]["notified"]


@pytest.mark.pendiente
@pytest.mark.parametrize("event", [
    {**make_event(), "extra": 1}, make_event(event_type="instance.deleted"),
    make_event(resource_id="no-existe"), make_event(resource_id="bucket-01"), [], "texto"])
def test_invalid_event_is_rejected_before_touching_the_ledger(spy, event):
    """Un evento inyectado y no válido se rechaza antes de escribir nada."""
    with pytest.raises(ValidationError):
        remediation.handle(event)
    assert ledger() == {} and spy.repairs == [] and spy.notices == []


@pytest.mark.pendiente
def test_other_events_in_the_ledger_are_preserved(spy):
    """Procesar un evento nuevo no pisa los registros de los demás."""
    remediation.handle(make_event(event_id="evt-uno-001"))
    remediation.handle(make_event(event_id="evt-dos-002",
                                  event_type="bucket.tags_missing", resource_id="bucket-01"))
    assert set(ledger()) == {"evt-uno-001", "evt-dos-002"}
    assert spy.repairs == [("i-123", "instance.stopped"),
                           ("fenix-g1-demo", "bucket.tags_missing")]


@pytest.mark.pendiente
def test_corrupt_ledger_stops_instead_of_being_overwritten(spy, tmp_path):
    """Un ledger corrupto detiene la operación: nunca se asume vacío ni se sobrescribe."""
    (tmp_path / "data" / "events.json").write_text("{corrupto", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        remediation.handle(make_event())
    assert (tmp_path / "data" / "events.json").read_text(encoding="utf-8") == "{corrupto"
    assert spy.repairs == []


@pytest.mark.pendiente
def test_notification_is_a_short_public_summary(spy):
    """El aviso incluye lo esencial y nunca el evento completo ni sus campos internos."""
    remediation.handle(make_event(simulate_failures=0))
    text = spy.notices[0]
    assert "evt-node-001" in text and "node-01" in text and len(text) <= 1000
    assert "simulate_failures" not in text and "occurred_at" not in text
