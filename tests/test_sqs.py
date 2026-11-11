"""Pruebas de I2-A e I2-B con SQS emulado en memoria mediante Moto."""

import json
from unittest.mock import Mock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from fenix.services import sqs


@pytest.fixture
def sqs_client(monkeypatch):
    """Aisla cada prueba con un broker emulado y credenciales ficticias."""
    with mock_aws():
        sdk = boto3.client(
            "sqs",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        monkeypatch.setattr(sqs, "client", Mock(return_value=sdk))
        yield sdk


def test_ensure_queues_configures_work_queue_and_dlq(sqs_client):
    """Verifica retencion, visibilidad y destino real de la politica."""
    work_url, dlq_url = sqs.ensure_queues("fenix-prueba")
    work = sqs_client.get_queue_attributes(
        QueueUrl=work_url, AttributeNames=["All"],
    )["Attributes"]
    dead = sqs_client.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["All"],
    )["Attributes"]

    assert work_url != dlq_url
    assert work["VisibilityTimeout"] == "45"
    assert work["MessageRetentionPeriod"] == "345600"
    assert dead["MessageRetentionPeriod"] == "1209600"
    policy = json.loads(work["RedrivePolicy"])
    assert policy["deadLetterTargetArn"] == dead["QueueArn"]
    assert int(policy["maxReceiveCount"]) == 3


def test_ensure_queues_reuses_existing_queues(sqs_client):
    """Repetir la preparacion conserva las URLs y exactamente dos colas."""
    first = sqs.ensure_queues("fenix-prueba")
    second = sqs.ensure_queues("fenix-prueba")

    assert first == second
    assert set(sqs_client.list_queues()["QueueUrls"]) == set(first)


def test_ensure_queues_restores_policy_on_existing_work_queue(sqs_client):
    """Una cola existente vuelve a quedar vinculada con la politica pedida."""
    work_url, dlq_url = sqs.ensure_queues("fenix-prueba")
    dead = sqs_client.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=["QueueArn"],
    )["Attributes"]
    sqs_client.set_queue_attributes(
        QueueUrl=work_url,
        Attributes={
            "VisibilityTimeout": "10",
            "MessageRetentionPeriod": "86400",
            "RedrivePolicy": json.dumps({
                "deadLetterTargetArn": dead["QueueArn"],
                "maxReceiveCount": "1",
            }),
        },
    )

    assert sqs.ensure_queues("fenix-prueba") == (work_url, dlq_url)
    work = sqs_client.get_queue_attributes(
        QueueUrl=work_url, AttributeNames=["All"],
    )["Attributes"]
    assert work["VisibilityTimeout"] == "45"
    assert work["MessageRetentionPeriod"] == "345600"
    assert int(json.loads(work["RedrivePolicy"])["maxReceiveCount"]) == 3


@pytest.mark.parametrize(
    ("receive_count", "expected_seconds"),
    [(1, 2), (2, 4), (3, 8), (4, 16), (5, 30), (6, 30)],
)
def test_retry_later_changes_only_current_delivery(
    sqs_client, receive_count, expected_seconds,
):
    """El backoff usa el recibo actual y conserva el mensaje en su cola."""
    work_url, _ = sqs.ensure_queues("fenix-prueba")
    sqs.publish(work_url, {"event_id": "evt-prueba"})
    message = sqs.receive(work_url)[0]
    # Inyecta la cuenta para probar cada espera sin consumir tiempo real.
    message["Attributes"]["ApproximateReceiveCount"] = str(receive_count)

    with (
        patch.object(
            sqs_client, "change_message_visibility",
            wraps=sqs_client.change_message_visibility,
        ) as change_visibility,
        patch.object(sqs_client, "send_message") as send_message,
        patch.object(sqs_client, "delete_message") as delete_message,
    ):
        assert sqs.retry_later(work_url, message) == expected_seconds
        change_visibility.assert_called_once_with(
            QueueUrl=work_url,
            ReceiptHandle=message["ReceiptHandle"],
            VisibilityTimeout=expected_seconds,
        )
        send_message.assert_not_called()
        delete_message.assert_not_called()


def test_retry_later_propagates_transport_error(sqs_client):
    """Un fallo de SQS se informa al worker para que decida como continuar."""
    work_url, _ = sqs.ensure_queues("fenix-prueba")
    sqs.publish(work_url, {"event_id": "evt-prueba"})
    message = sqs.receive(work_url)[0]
    error = ClientError(
        {"Error": {"Code": "ServiceUnavailable", "Message": "Fallo simulado"}},
        "ChangeMessageVisibility",
    )

    with patch.object(sqs_client, "change_message_visibility", side_effect=error):
        with pytest.raises(ClientError) as captured:
            sqs.retry_later(work_url, message)

    assert captured.value is error
