"""Load validated credential maps from AWS Secrets Manager."""
import json
import re

MOCK_SENTINEL = "__mock__"
_CREDENTIAL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_credential_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise RuntimeError("Secret value must be a non-empty JSON object")
    if not all(
        isinstance(key, str)
        and _CREDENTIAL_NAME.fullmatch(key)
        and isinstance(secret, str)
        and secret
        for key, secret in value.items()
    ):
        raise RuntimeError(
            "Secret value must use identifier keys and non-empty string values"
        )
    return value


def load_secrets(secret_name: str | None, region: str = "us-east-1") -> dict[str, str]:
    """Load an explicit secret name, or mock credentials for local tests."""
    if not secret_name:
        raise RuntimeError("SKILL_TOOLS_SECRET must be explicitly configured")
    if secret_name == MOCK_SENTINEL:
        return _validate_credential_map(
            {"DR_API_TOKEN": "mock-token-for-testing", "CANARY_TOKEN": "mock-canary"}
        )

    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "Unknown")
        if code == "ResourceNotFoundException":
            raise RuntimeError("Configured secret was not found") from error
        if code == "AccessDeniedException":
            raise RuntimeError("Access to the configured secret was denied") from error
        raise RuntimeError("Failed to retrieve configured secret") from error

    if not isinstance(response, dict):
        raise RuntimeError("Secrets Manager returned an invalid response")
    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str) or not secret_string:
        raise RuntimeError("Secrets Manager response did not contain a non-empty SecretString")
    try:
        return _validate_credential_map(json.loads(secret_string))
    except json.JSONDecodeError as error:
        raise RuntimeError("Secret value must contain valid JSON") from error
