import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from unittest.mock import MagicMock, patch

from fenix.services import demo
from fenix.utils.errors import RetryableError, ValidationError

def _inventory(alias):
    if alias == "node-01":
        return {"node-01": {"type": "ec2", "id": "i-123"}}
    if alias == "bucket-01":
        return {"bucket-01": {"type": "s3", "id": "bucket-01"}}
    return {}

def test_alias_invalido():
    with patch.object(demo, "load", return_value={}):
        with pytest.raises(ValidationError):
            demo.inject_fault("no-existe")

def test_node_01_se_detiene():
    ec2 = MagicMock()
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [{"State": {"Name": "stopped"}}]}]
    }
    with patch.object(demo, "load", return_value=_inventory("node-01")), \
         patch.object(demo, "client", return_value=ec2):
        demo.inject_fault("node-01")  # no tiene que tirar error
    ec2.stop_instances.assert_called_once_with(InstanceIds=["i-123"])

def test_node_01_retryable_si_no_se_detiene():
    ec2 = MagicMock()
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [{"State": {"Name": "running"}}]}]
    }
    with patch.object(demo, "load", return_value=_inventory("node-01")), \
         patch.object(demo, "client", return_value=ec2), \
         patch("time.sleep", return_value=None):
        with pytest.raises(RetryableError):
            demo.inject_fault("node-01")

def test_bucket_01_saca_tag_owner():
    s3 = MagicMock()
    # 1ra lectura: tiene Owner, 2da lectura: ya sin Owner
    s3.get_bucket_tagging.side_effect = [
        {"TagSet": [{"Key": "Owner", "Value": "fenix"}, {"Key": "Env", "Value": "lab"}]},
        {"TagSet": [{"Key": "Env", "Value": "lab"}]},
    ]
    with patch.object(demo, "load", return_value=_inventory("bucket-01")), \
         patch.object(demo, "client", return_value=s3):
        demo.inject_fault("bucket-01")
    s3.put_bucket_tagging.assert_called_once()
    args = s3.put_bucket_tagging.call_args.kwargs
    assert args["Bucket"] == "bucket-01"
    assert {"Key": "Owner", "Value": "fenix"} not in args["Tagging"]["TagSet"]