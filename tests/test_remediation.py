"""Pruebas de la reparación convergente (I3-C) con clientes falsos, sin LocalStack."""
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fenix.services import remediation
from fenix.utils.errors import PermanentError, RetryableError

TAGS = {"ManagedBy": "ppa2", "Project": "fenix", "GroupId": "g1", "Owner": "g1"}
NODE = {"type": "ec2", "id": "i-123"}
BUCKET = {"type": "s3", "id": "fenix-g1-demo", "expected_tags": TAGS}


def error(code, status=400):
    """Construye un ClientError con el código indicado."""
    return ClientError({"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
                       "Operacion")


class FakeEC2:
    """EC2 mínimo: no tiene reboot_instances, así que usarlo rompería la prueba."""

    def __init__(self, state="stopped", after_start="running", fail=None):
        self.state, self.after_start, self.fail = state, after_start, fail
        self.starts = 0

    def describe_instances(self, InstanceIds):
        if self.fail:
            raise self.fail
        return {"Reservations": [{"Instances": [{"State": {"Name": self.state}}]}]}

    def start_instances(self, InstanceIds):
        self.starts += 1
        self.state = self.after_start


class FakeS3:
    """S3 mínimo con etiquetas en un diccionario."""

    def __init__(self, tags=None, fail=None, ignore_put=False):
        self.tags, self.fail, self.ignore_put, self.puts = dict(tags or {}), fail, ignore_put, 0

    def get_bucket_tagging(self, Bucket):
        if self.fail:
            raise self.fail
        if not self.tags:
            raise error("NoSuchTagSet", 404)
        return {"TagSet": [{"Key": k, "Value": v} for k, v in self.tags.items()]}

    def put_bucket_tagging(self, Bucket, Tagging):
        self.puts += 1
        if not self.ignore_put:
            self.tags = {row["Key"]: row["Value"] for row in Tagging["TagSet"]}


def use(monkeypatch, ec2=None, s3=None):
    """Reemplaza el constructor de clientes por los falsos indicados."""
    monkeypatch.setattr(remediation, "client", lambda name: {"ec2": ec2, "s3": s3}[name])


@pytest.mark.pendiente
def test_running_instance_is_already_ok(monkeypatch):
    """Una instancia running no se toca: ningún start_instances."""
    ec2 = FakeEC2(state="running")
    use(monkeypatch, ec2=ec2)
    assert remediation.repair(NODE, "instance.stopped") == "already_ok"
    assert ec2.starts == 0


@pytest.mark.pendiente
def test_stopped_instance_is_started_and_verified(monkeypatch):
    """Una instancia detenida se arranca una vez y se observa running."""
    ec2 = FakeEC2(state="stopped")
    use(monkeypatch, ec2=ec2)
    assert remediation.repair(NODE, "instance.stopped") == "repaired"
    assert ec2.starts == 1 and ec2.state == "running"


@pytest.mark.pendiente
def test_repair_is_convergent_when_repeated(monkeypatch):
    """Repetir la reparación no repite la acción: la segunda vez ya está ok."""
    ec2 = FakeEC2(state="stopped")
    use(monkeypatch, ec2=ec2)
    assert remediation.repair(NODE, "instance.stopped") == "repaired"
    assert remediation.repair(NODE, "instance.stopped") == "already_ok"
    assert ec2.starts == 1


@pytest.mark.pendiente
@pytest.mark.parametrize("state", ["pending", "stopping"])
def test_transitional_state_is_retryable_without_starting(monkeypatch, state):
    """En transición se reintenta más tarde, sin tocar la instancia."""
    ec2 = FakeEC2(state=state)
    use(monkeypatch, ec2=ec2)
    with pytest.raises(RetryableError):
        remediation.repair(NODE, "instance.stopped")
    assert ec2.starts == 0


@pytest.mark.pendiente
@pytest.mark.parametrize("state", ["terminated", "shutting-down"])
def test_unrepairable_state_is_permanent(monkeypatch, state):
    """Una instancia terminada no se puede reparar: error permanente."""
    use(monkeypatch, ec2=FakeEC2(state=state))
    with pytest.raises(PermanentError):
        remediation.repair(NODE, "instance.stopped")


@pytest.mark.pendiente
def test_start_not_observed_as_running_is_retryable(monkeypatch):
    """Si tras arrancar sigue en pending, no se declara reparada: se reintenta."""
    use(monkeypatch, ec2=FakeEC2(state="stopped", after_start="pending"))
    with pytest.raises(RetryableError):
        remediation.repair(NODE, "instance.stopped")


@pytest.mark.pendiente
@pytest.mark.parametrize("failure,expected", [
    (error("InvalidInstanceID.NotFound"), PermanentError),
    (error("UnauthorizedOperation", 403), PermanentError),
    (error("Throttling", 400), RetryableError),
    (error("InternalError", 500), RetryableError),
    (error("Whatever", 503), RetryableError),
    (EndpointConnectionError(endpoint_url="http://localhost:4566"), RetryableError)])
def test_api_errors_are_classified(monkeypatch, failure, expected):
    """Solo los fallos transitorios se reintentan; el resto no."""
    use(monkeypatch, ec2=FakeEC2(fail=failure))
    with pytest.raises(expected):
        remediation.repair(NODE, "instance.stopped")


@pytest.mark.pendiente
def test_complete_tags_are_already_ok(monkeypatch):
    """Etiquetas completas: no se escribe nada."""
    s3 = FakeS3(tags=TAGS)
    use(monkeypatch, s3=s3)
    assert remediation.repair(BUCKET, "bucket.tags_missing") == "already_ok"
    assert s3.puts == 0


@pytest.mark.pendiente
def test_missing_tag_is_restored_preserving_foreign_tags(monkeypatch):
    """Se restaura Owner y se conserva la etiqueta ajena a la política."""
    s3 = FakeS3(tags={**TAGS, "Extra": "valor-ajeno"})
    del s3.tags["Owner"]
    use(monkeypatch, s3=s3)
    assert remediation.repair(BUCKET, "bucket.tags_missing") == "repaired"
    assert s3.tags == {**TAGS, "Extra": "valor-ajeno"}


@pytest.mark.pendiente
def test_no_tag_set_is_treated_as_empty(monkeypatch):
    """NoSuchTagSet equivale a "sin etiquetas": se restauran todas."""
    s3 = FakeS3(tags={})
    use(monkeypatch, s3=s3)
    assert remediation.repair(BUCKET, "bucket.tags_missing") == "repaired"
    assert s3.tags == TAGS


@pytest.mark.pendiente
def test_changed_value_is_restored(monkeypatch):
    """Un valor desviado (no solo uno faltante) también se corrige."""
    s3 = FakeS3(tags={**TAGS, "Owner": "otro"})
    use(monkeypatch, s3=s3)
    assert remediation.repair(BUCKET, "bucket.tags_missing") == "repaired"
    assert s3.tags["Owner"] == "g1"


@pytest.mark.pendiente
def test_tags_not_observed_after_put_are_retryable(monkeypatch):
    """Si tras escribir no se observan las etiquetas, no se declara reparado."""
    use(monkeypatch, s3=FakeS3(tags={}, ignore_put=True))
    with pytest.raises(RetryableError):
        remediation.repair(BUCKET, "bucket.tags_missing")


@pytest.mark.pendiente
@pytest.mark.parametrize("failure,expected", [
    (error("NoSuchBucket", 404), PermanentError),
    (error("AccessDenied", 403), PermanentError),
    (error("SlowDown", 503), RetryableError)])
def test_s3_errors_are_classified(monkeypatch, failure, expected):
    """Solo NoSuchTagSet significa vacío; los demás errores se clasifican."""
    use(monkeypatch, s3=FakeS3(fail=failure))
    with pytest.raises(expected):
        remediation.repair(BUCKET, "bucket.tags_missing")


@pytest.mark.pendiente
@pytest.mark.parametrize("resource,event_type", [
    (BUCKET, "instance.stopped"), (NODE, "bucket.tags_missing"),   # Tipo que no encaja.
    (NODE, "instance.deleted"), ({"type": "ec2"}, "instance.stopped"),
    ({"type": "s3", "id": "b", "expected_tags": {}}, "bucket.tags_missing"),
    ({"type": "s3", "id": "b"}, "bucket.tags_missing")])          # Sin expected_tags.
def test_unauthorized_or_incomplete_resource_is_permanent(monkeypatch, resource, event_type):
    """Evento que no corresponde al recurso o inventario incompleto: no se actúa."""
    use(monkeypatch, ec2=FakeEC2(), s3=FakeS3())
    with pytest.raises(PermanentError):
        remediation.repair(resource, event_type)
