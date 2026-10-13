"""Read Terraform resource numbers in memory; never log or persist state contents."""
import json
import os

from dotenv import load_dotenv

from engine.config import settings

load_dotenv()
ENDPOINT = "https://kr.object.ncloudstorage.com"
STATE_KEYS = ("core/terraform.tfstate", "test/terraform.tfstate")
TYPES = {"ncloud_server", "ncloud_public_ip", "ncloud_block_storage"}
MAX_STATE_BYTES = 16 * 1024 * 1024


class IacError(RuntimeError):
    """A safe error message that contains no Terraform state or credentials."""


def _client():
    import boto3
    from botocore.config import Config

    prefix = "FINSH_SCANNER" if os.getenv("FINSH_SCANNER_ACCESS_KEY") else "NCLOUD"
    access = os.getenv(f"{prefix}_ACCESS_KEY")
    secret = os.getenv(f"{prefix}_SECRET_KEY")
    if not access or not secret:
        raise IacError("Terraform 기록 조회용 인증키가 없습니다")
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="kr-standard",
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(connect_timeout=5, read_timeout=15,
                      retries={"max_attempts": 2}, s3={"addressing_style": "path"}),
    )


def nos_from_state(state):
    """Extract managed server/IP/additional-disk IDs, including deposed instances."""
    if not isinstance(state, dict) or not isinstance(state.get("resources"), list):
        raise IacError("Terraform 기록의 자원 목록 형식이 올바르지 않습니다")
    nos = set()
    for resource in state["resources"]:
        if not isinstance(resource, dict):
            raise IacError("Terraform 자원 기록 형식이 올바르지 않습니다")
        if resource.get("mode") != "managed" or resource.get("type") not in TYPES:
            continue
        instances = resource.get("instances")
        if not isinstance(instances, list):
            raise IacError("Terraform 인스턴스 목록을 확인할 수 없습니다")
        for instance in instances:
            attributes = instance.get("attributes") if isinstance(instance, dict) else None
            number = attributes.get("id") if isinstance(attributes, dict) else None
            if isinstance(number, bool) or not str(number or "").isascii() or not str(number or "").isdigit():
                raise IacError("Terraform 자원 번호를 확인할 수 없습니다")
            nos.add(str(number))
    return nos


def terraform_nos():
    """Core is required; only a missing, not-yet-created test state is optional."""
    bucket = os.getenv("FINSH_TFSTATE_BUCKET") or settings.get("tfstate_bucket")
    if not bucket:
        raise IacError("FINSH_TFSTATE_BUCKET 설정이 없습니다")
    try:
        client = _client()
    except Exception:
        raise IacError("Terraform 기록 조회 클라이언트를 준비할 수 없습니다") from None
    numbers = set()
    for key in STATE_KEYS:
        body = None
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            raw = body.read(MAX_STATE_BYTES + 1)
            if len(raw) > MAX_STATE_BYTES:
                raise IacError("Terraform 기록이 허용 크기를 초과했습니다")
            numbers.update(nos_from_state(json.loads(raw)))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if key == STATE_KEYS[1] and code == "NoSuchKey":
                continue
            # Do not chain API/JSON exceptions: they may contain sensitive contents.
            raise IacError(f"Terraform 기록 확인 실패: {key}") from None
        finally:
            if body is not None:
                body.close()
    return numbers
