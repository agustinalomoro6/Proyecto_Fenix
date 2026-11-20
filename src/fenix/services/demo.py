"""Laboratorio acotado de recursos. Integrante 2 prepara, integrante 6 verifica."""
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.utils.validation import identifier
from botocore.exceptions import ClientError
from fenix.services.cloud_support import aws_tags, create_group, create_instance, mock_inputs
import time
from fenix.utils.errors import PermanentError, RetryableError, ValidationError
def _bucket_tags(s3, bucket_name: str) -> dict[str, str] | None:
    try:
        response = s3.get_bucket_tagging(Bucket=bucket_name)
    except ClientError as error:
        code = error.response["Error"]["Code"]
        if code == "NoSuchBucket":
            return None
        if code == "NoSuchTagSet":
            return {}
        raise

    return {tag["Key"]: tag["Value"] for tag in response["TagSet"]}

def setup_demo(group: str) -> dict:
    """Prepara una instancia mock y un bucket a partir de identificadores estables.

    Args:
        group: ID validado del grupo; determina prefijos de los recursos.
    Returns:
        Inventario con aliases node-01 y bucket-01 y sus IDs reales del emulador.
    Raises:
        ClientError: Si el emulador no soporta una operación o falla su ejecución.
        PermanentError: Si no se puede verificar un recurso del laboratorio.
    Side Effects:
        Crea recursos de laboratorio etiquetados y data/inventory.json.
    Notes:
        Reutilizar por tags antes de crear y guardar IDs después de cada creación.
        Obtener una ImageId con describe_images; no copiar una AMI de AWS real.
    """
    group = identifier(group)

    state_path = f"data/setup-{group}.json"
    progress = load(state_path)

    if not progress:
        vpc_id, image_id = mock_inputs()
        progress = {
            "vpc_id": vpc_id,
            "image_id": image_id,
        }
        save(state_path, progress)

    ec2 = client("ec2")
    group_name = f"fenix-{group}-sg"
    tags = {
        "ManagedBy": "ppa2",
        "Project": "fenix",
        "GroupId": group,
        "Owner": group,
    }

    groups = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [progress["vpc_id"]]},
            {"Name": "group-name", "Values": [group_name]},
        ],
    )["SecurityGroups"]

    if not groups:
        if progress.get("security_group_id"):
            raise PermanentError("El grupo de seguridad registrado ya no existe")

        group_id = create_group(group_name, progress["vpc_id"], tags)
        groups = ec2.describe_security_groups(
            GroupIds=[group_id],
        )["SecurityGroups"]

    if len(groups) != 1:
        raise PermanentError("Se esperaba un unico grupo de seguridad")

    security_group = groups[0]
    actual_tags = {
        tag["Key"]: tag["Value"]
        for tag in security_group.get("Tags", [])
    }

    if any(actual_tags.get(key) != value for key, value in tags.items()):
        raise PermanentError("El grupo de seguridad no pertenece al laboratorio")

    group_id = security_group["GroupId"]
    saved_group_id = progress.get("security_group_id")

    if saved_group_id and saved_group_id != group_id:
        raise PermanentError("Cambio el grupo de seguridad registrado")

    progress["security_group_id"] = group_id
    save(state_path, progress)

    node_name = f"fenix-{group}-node-01"
    node_tags = {**tags, "Name": node_name}
    instance_id = progress.get("instance_id")

    if not instance_id:
        reservations = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Project", "Values": ["fenix"]},
                {"Name": "tag:GroupId", "Values": [group]},
                {"Name": "tag:Name", "Values": [node_name]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ],
        )["Reservations"]

        instances = [
            instance
            for reservation in reservations
            for instance in reservation["Instances"]
        ]

        if len(instances) > 1:
            raise PermanentError("Hay varias instancias con el nombre del laboratorio")

        if instances:
            instance_id = instances[0]["InstanceId"]
        else:
            instance_id = create_instance(
                progress["image_id"], group_id, node_name, node_tags,
            )
            progress["instance_id"] = instance_id
            save(state_path, progress)

    response = ec2.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    instance_tags = {
        tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])
    }
    security_group_ids = {
        item["GroupId"] for item in instance["SecurityGroups"]
    }

    if (
        any(instance_tags.get(key) != value for key, value in node_tags.items())
        or group_id not in security_group_ids
    ):
        raise PermanentError("La instancia no pertenece al laboratorio")

    state = instance["State"]["Name"]
    if state == "pending":
        ec2.get_waiter("instance_running").wait(
            InstanceIds=[instance_id],
            WaiterConfig={"Delay": 2, "MaxAttempts": 10},
        )
    elif state not in {"running", "stopping", "stopped"}:
        raise PermanentError(f"La instancia no se puede reutilizar en estado {state}")

    progress["instance_id"] = instance_id
    save(state_path, progress)


    s3 = client("s3")
    bucket_name = f"fenix-{group}-demo"
    actual_tags = _bucket_tags(s3, bucket_name)

    if actual_tags is None:
        s3.create_bucket(Bucket=bucket_name)
        progress["untagged_bucket"] = bucket_name
        save(state_path, progress)
        actual_tags = {}

    created_by_setup = (
        not actual_tags and progress.get("untagged_bucket") == bucket_name
    )
    ownership_keys = ("ManagedBy", "Project", "GroupId")
    if not created_by_setup and any(
        actual_tags.get(key) != tags[key] for key in ownership_keys
    ):
        raise PermanentError("El bucket no pertenece al laboratorio")

    desired_tags = {**actual_tags, **tags}
    if actual_tags != desired_tags:
        s3.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": aws_tags(desired_tags)},
        )

    verified_tags = _bucket_tags(s3, bucket_name) or {}
    if any(verified_tags.get(key) != value for key, value in tags.items()):
        raise PermanentError("No se pudieron verificar las etiquetas del bucket")

    if progress.pop("untagged_bucket", None) is not None:
        save(state_path, progress)

    inventory = {
        "node-01": {
            "type": "ec2",
            "id": instance_id,
            "image_id": instance["ImageId"],
            "vpc_id": progress["vpc_id"],
            "security_group_id": group_id,
            "expected_tags": node_tags,
        },
        "bucket-01": {
            "type": "s3",
            "id": bucket_name,
            "expected_tags": tags,
        },
    }
    save("data/inventory.json", inventory)
    return inventory


def inject_fault(alias: str) -> None:
    """Inyecta y verifica un fallo controlado en un recurso del laboratorio."""

    kinds = {
        "node-01": "ec2",
        "bucket-01": "s3",
    }

    if alias not in kinds:
        raise ValidationError(
            "El alias no pertenece al inventario autorizado"
        )

    inventory = load("data/inventory.json")

    if not isinstance(inventory, dict):
        raise ValidationError("El inventario no es válido")

    record = inventory.get(alias)

    if (
        not isinstance(record, dict)
        or record.get("type") != kinds[alias]
        or not isinstance(record.get("id"), str)
        or not record["id"].strip()
    ):
        raise ValidationError(
            "El recurso no pertenece al inventario autorizado"
        )

    resource_id = record["id"]

    if alias == "node-01":
        ec2 = client("ec2")
        ec2.stop_instances(InstanceIds=[resource_id])

        for _ in range(10):
            response = ec2.describe_instances(
                InstanceIds=[resource_id]
            )
            reservations = response.get("Reservations", [])
            instances = [
                instance
                for reservation in reservations
                for instance in reservation.get("Instances", [])
            ]

            if (
                instances
                and instances[0]["State"]["Name"] == "stopped"
            ):
                return

            time.sleep(1)

        raise RetryableError(
            "No se observó la instancia detenida dentro del tiempo permitido"
        )

    s3 = client("s3")
    tags = _bucket_tags(s3, resource_id)

    if tags is None:
        raise PermanentError("El bucket del inventario no existe")

    remaining_tags = {
        key: value for key, value in tags.items()
        if key != "Owner"
    }

    if remaining_tags != tags:
        if remaining_tags:
            s3.put_bucket_tagging(
                Bucket=resource_id,
                Tagging={"TagSet": aws_tags(remaining_tags)},
            )
        else:
            s3.delete_bucket_tagging(Bucket=resource_id)

    verified_tags = _bucket_tags(s3, resource_id)

    if verified_tags != remaining_tags:
        raise RetryableError(
            "No se pudo comprobar la eliminación de la etiqueta Owner"
        )
