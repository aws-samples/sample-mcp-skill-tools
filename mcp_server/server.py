"""MCP server that registers reviewed Markdown skill definitions at startup."""
import asyncio
import json
import logging
import os
import re
import shlex
import subprocess  # nosec B404
from collections.abc import Callable

from jsonschema import ValidationError, validate
from mcp.server.lowlevel import Server
from mcp.types import TextContent, Tool as MCPTool

from mcp_server.parser import load_all_skills
from mcp_server.secrets_loader import load_secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
# Do not default to mock credentials. An unset secret must fail closed; mock
# mode requires explicitly setting SKILL_TOOLS_SECRET=__mock__.
SECRET_NAME = os.environ.get("SKILL_TOOLS_SECRET")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60
ALLOWED_COMMANDS = frozenset({"curl", "aws", "kubectl", "psql", "echo"})
_PLACEHOLDER_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CHILD_ENV_KEYS = frozenset(
    {
        "HOME", "PATH", "LANG", "LC_ALL", "AWS_REGION", "AWS_DEFAULT_REGION",
        "AWS_PROFILE", "KUBECONFIG", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER",
        "PGSSLMODE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTP_PROXY",
        "HTTPS_PROXY", "NO_PROXY",
    }
)

try:
    CREDENTIALS = load_secrets(SECRET_NAME, AWS_REGION)
    logger.info("Loaded %d credential(s) from Secrets Manager", len(CREDENTIALS))
except RuntimeError:
    logger.error("Credential loading failed")
    CREDENTIALS: dict[str, str] = {}

SKILLS = load_all_skills(SKILLS_DIR)
server = Server("skill-tools")
TOOL_LIST = [
    MCPTool(
        name=name,
        description=meta["description"],
        inputSchema=meta.get("input_schema", {"type": "object", "properties": {}}),
    )
    for name, meta in SKILLS.items()
]
TOOL_HANDLERS = dict(SKILLS)


@server.list_tools()
async def handle_list_tools() -> list[MCPTool]:
    return TOOL_LIST


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name not in TOOL_HANDLERS:
        return _error(f"Unknown tool: {name}")
    return await _execute_tool(TOOL_HANDLERS[name], arguments or {})


def _error(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": message}))]


def _extract_shell_command(body: str) -> str | None:
    start = body.find("```shell")
    if start == -1:
        return None
    start += len("```shell")
    end = body.find("```", start)
    return None if end == -1 else body[start:end].strip()


def _apply_schema_defaults(kwargs: dict, schema: dict) -> dict:
    result = dict(kwargs)
    for name, definition in schema.get("properties", {}).items():
        if name not in result and "default" in definition:
            result[name] = definition["default"]
    return result


def _placeholders(value: str) -> list[tuple[int, int, str, str]]:
    result = []
    cursor = 0
    while (start := value.find("${", cursor)) != -1:
        end = value.find("}", start + 2)
        if end == -1:
            raise ValueError(f"Unterminated placeholder: {value[start:]}")
        token, name = value[start:end + 1], value[start + 2:end]
        if not _PLACEHOLDER_NAME.fullmatch(name):
            raise ValueError(f"Invalid placeholder: {token}")
        result.append((start, end + 1, token, name))
        cursor = end + 1
    return result


def _check_unsubstituted_placeholders(parts: list[str]) -> str | None:
    for part in parts:
        tokens = _placeholders(part)
        if tokens:
            return tokens[0][2]
    return None


def _split_template(template: str) -> list[str]:
    try:
        return shlex.split(template, posix=True)
    except ValueError as error:
        raise ValueError(f"Invalid command template: {error}") from error


# A conditional token lets a skill pick one of two literal values based on a
# boolean parameter: ${name ? value_if_true : value_if_false}. Only boolean
# parameters may drive a conditional, and the branch values are restricted to a
# safe literal charset so this cannot become an injection or placeholder-nesting
# vector. Resolution happens on the raw template before shlex splitting, so the
# chosen literal is subject to the same quoting and rendering as any other text.
_CONDITIONAL = re.compile(
    r"\$\{\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\?\s*"
    r"(?P<if_true>[A-Za-z0-9_.\- ]*)\s*:\s*(?P<if_false>[A-Za-z0-9_.\- ]*)\}"
)


def _resolve_conditionals(template: str, params: dict) -> str:
    """Replace ${name ? a : b} tokens using boolean params, before splitting."""
    def _replace(match: "re.Match[str]") -> str:
        name = match.group("name")
        if name not in params:
            raise ValueError(f"Unknown conditional parameter: ${{{name}}}")
        value = params[name]
        if not isinstance(value, bool):
            raise ValueError(f"Conditional parameter must be boolean: ${{{name}}}")
        return match.group("if_true" if value else "if_false").strip()

    return _CONDITIONAL.sub(_replace, template)


def _render_parts(parts: list[str], substitutions: dict[str, str]) -> list[str]:
    rendered = []
    for part in parts:
        chunks, cursor = [], 0
        for start, end, token, name in _placeholders(part):
            if name not in substitutions:
                raise ValueError(f"Unsubstituted placeholder: {token}")
            chunks.extend((part[cursor:start], substitutions[name]))
            cursor = end
        chunks.append(part[cursor:])
        rendered.append("".join(chunks))
    return rendered


def _substitute_command(template: str, params: dict, credentials: dict[str, str]) -> list[str]:
    """Render a template for unit-tested, non-process use.

    Not used on the execution path: credentials are delivered out of band by
    _prepare_command so they never appear in process arguments.
    """
    substitutions = {key: str(value) for key, value in params.items()}
    substitutions.update(credentials)
    return _render_parts(_split_template(_resolve_conditionals(template, params)), substitutions)


def _curl_config_header(token: str) -> str:
    """Encode one curl Authorization header for delivery over stdin."""
    escaped = token.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'header = "Authorization: Bearer {escaped}"\n'


def _prepare_command(
    template: str, params: dict, credentials: dict[str, str]
) -> tuple[list[str], str | None]:
    """Build process argv without placing any credential in argv or the environment.

    The only supported credential convention is a curl bearer header, which is
    moved out of argv and delivered through curl's ``--config -`` stdin channel.
    A credential referenced any other way fails closed, because rendering argv
    uses request parameters only — never credential values.
    """
    parts = _split_template(_resolve_conditionals(template, params))
    retained: list[str] = []
    curl_config: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part in {"-H", "--header"} and index + 1 < len(parts):
            header = parts[index + 1]
            matches = _placeholders(header)
            if (
                len(matches) == 1
                and matches[0][3] in credentials
                and header == f"Authorization: Bearer {matches[0][2]}"
            ):
                curl_config.append(_curl_config_header(credentials[matches[0][3]]))
                index += 2
                continue
        retained.append(part)
        index += 1

    command_parts = _render_parts(retained, {key: str(value) for key, value in params.items()})
    if curl_config:
        if not command_parts or command_parts[0] != "curl":
            raise ValueError("Credential stdin transport is supported only for curl")
        command_parts.extend(["--config", "-"])
        return command_parts, "".join(curl_config)
    return command_parts, None


def _validate_command(command: str) -> bool:
    return command in ALLOWED_COMMANDS


def _timeout(skill: dict) -> int:
    value = skill.get("timeout", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"Timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds")
    return value


def _child_env() -> dict[str, str]:
    """Build the child environment. Credentials are never placed here; they are
    delivered out of band (curl stdin) so they cannot leak via /proc/[pid]/environ."""
    return {
        key: value for key in _CHILD_ENV_KEYS
        if isinstance((value := os.environ.get(key)), str) and value
    }


def _run_curl(args: list[str], *, env: dict[str, str], timeout: int, stdin_data: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["curl", *args], capture_output=True, text=True, timeout=timeout, env=env, input=stdin_data, shell=False)  # nosec


def _run_aws(args: list[str], *, env: dict[str, str], timeout: int, stdin_data: str | None) -> subprocess.CompletedProcess[str]:
    if stdin_data is not None:
        raise ValueError("Credential stdin transport is not supported for aws")
    return subprocess.run(["aws", *args], capture_output=True, text=True, timeout=timeout, env=env, shell=False)  # nosec


def _run_kubectl(args: list[str], *, env: dict[str, str], timeout: int, stdin_data: str | None) -> subprocess.CompletedProcess[str]:
    if stdin_data is not None:
        raise ValueError("Credential stdin transport is not supported for kubectl")
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout, env=env, shell=False)  # nosec


def _run_psql(args: list[str], *, env: dict[str, str], timeout: int, stdin_data: str | None) -> subprocess.CompletedProcess[str]:
    if stdin_data is not None:
        raise ValueError("Credential stdin transport is not supported for psql")
    return subprocess.run(["psql", *args], capture_output=True, text=True, timeout=timeout, env=env, shell=False)  # nosec


def _run_echo(args: list[str], *, env: dict[str, str], timeout: int, stdin_data: str | None) -> subprocess.CompletedProcess[str]:
    if stdin_data is not None:
        raise ValueError("Credential stdin transport is not supported for echo")
    return subprocess.run(["echo", *args], capture_output=True, text=True, timeout=timeout, env=env, shell=False)  # nosec


_RUNNERS: dict[str, Callable[..., subprocess.CompletedProcess[str]]] = {
    "curl": _run_curl, "aws": _run_aws, "kubectl": _run_kubectl,
    "psql": _run_psql, "echo": _run_echo,
}


def _run_allowlisted_command(parts: list[str], *, timeout: int, stdin_data: str | None = None) -> subprocess.CompletedProcess[str]:
    if not parts or not _validate_command(parts[0]):
        raise PermissionError(f"Command not in allowlist. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}")
    if not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"Timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds")
    return _RUNNERS[parts[0]](parts[1:], env=_child_env(), timeout=timeout, stdin_data=stdin_data)


def _redact_secrets(text: str, credentials: dict[str, str]) -> str:
    values = list(credentials.values())
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("Credential values must be non-empty strings for redaction")
    if not values:
        return text
    return re.compile("|".join(re.escape(value) for value in sorted(set(values), key=len, reverse=True))).sub("[REDACTED]", text)


async def _execute_tool(skill: dict, arguments: dict) -> list[TextContent]:
    schema = skill.get("input_schema", {})
    kwargs = _apply_schema_defaults(arguments, schema)
    try:
        if schema:
            validate(instance=kwargs, schema=schema)
        template = _extract_shell_command(skill.get("_body", ""))
        if not template:
            return _error("No shell command found in skill file")
        command_parts, stdin_data = _prepare_command(template, kwargs, CREDENTIALS)
        result = _run_allowlisted_command(
            command_parts, timeout=_timeout(skill), stdin_data=stdin_data
        )
    except (ValidationError, ValueError, PermissionError) as error:
        prefix = "Input validation failed: " if isinstance(error, ValidationError) else ""
        return _error(f"{prefix}{error.message if isinstance(error, ValidationError) else error}")
    except subprocess.TimeoutExpired:
        return _error(f"Command timed out after {skill.get('timeout', DEFAULT_TIMEOUT_SECONDS)}s")
    except FileNotFoundError:
        return _error("Allowlisted binary was not found")

    stdout, stderr = _redact_secrets(result.stdout, CREDENTIALS), _redact_secrets(result.stderr, CREDENTIALS)
    if result.returncode != 0:
        return _error(f"Exit {result.returncode}: {stderr[:500]}")
    try:
        output = json.loads(stdout)
        output = output if isinstance(output, dict) else {"result": output}
    except json.JSONDecodeError:
        output = {"raw_output": stdout.strip()}
    if skill.get("output_schema"):
        try:
            validate(instance=output, schema=skill["output_schema"])
        except ValidationError:
            output["_validation_warning"] = "Output did not satisfy the declared schema"
    output["_meta"] = {
        "source": skill.get("description", ""),
        "data_freshness": "live — queried at request time",
        "skill_file": os.path.basename(skill["_filepath"]),
    }
    return [TextContent(type="text", text=json.dumps(output))]


if __name__ == "__main__":
    from mcp.server.stdio import stdio_server

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(main())
