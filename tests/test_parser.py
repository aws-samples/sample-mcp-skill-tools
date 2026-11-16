"""Tests for parser.py — skill file parsing and error handling."""
import os
import tempfile
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_server.parser import parse_skill_file, load_all_skills


@pytest.fixture
def tmp_skills_dir(tmp_path):
    """Create a temp directory with skill files for testing."""
    return tmp_path


def _write_skill(directory, filename, content):
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


VALID_SKILL = """\
---
name: test-tool
description: A test tool.
execution_mode: shell
input_schema:
  type: object
  properties:
    param1:
      type: string
  required:
    - param1
---

# Test Tool

## Execution

```shell
echo '{"result": "ok"}'
```
"""


class TestParseSkillFile:
    def test_valid_skill_parses_successfully(self, tmp_skills_dir):
        filepath = _write_skill(tmp_skills_dir, "test.skill.md", VALID_SKILL)
        result = parse_skill_file(filepath)

        assert result is not None
        assert result["name"] == "test-tool"
        assert result["description"] == "A test tool."
        assert result["input_schema"]["properties"]["param1"]["type"] == "string"
        assert "_body" in result
        assert "_filepath" in result

    def test_missing_frontmatter_returns_none(self, tmp_skills_dir):
        filepath = _write_skill(tmp_skills_dir, "bad.skill.md", "# No frontmatter\nJust text.")
        result = parse_skill_file(filepath)
        assert result is None

    def test_missing_closing_delimiter_returns_none(self, tmp_skills_dir):
        filepath = _write_skill(tmp_skills_dir, "bad.skill.md", "---\nname: x\ndescription: y\n")
        result = parse_skill_file(filepath)
        assert result is None

    def test_invalid_yaml_returns_none(self, tmp_skills_dir):
        filepath = _write_skill(tmp_skills_dir, "bad.skill.md", "---\n: : : invalid\n---\nbody")
        result = parse_skill_file(filepath)
        assert result is None

    def test_missing_required_keys_returns_none(self, tmp_skills_dir):
        # Has name but no description
        filepath = _write_skill(tmp_skills_dir, "bad.skill.md", "---\nname: x\n---\nbody")
        result = parse_skill_file(filepath)
        assert result is None

    def test_nonexistent_file_returns_none(self):
        result = parse_skill_file("/nonexistent/path/file.skill.md")
        assert result is None

    def test_frontmatter_not_a_mapping_returns_none(self, tmp_skills_dir):
        filepath = _write_skill(tmp_skills_dir, "bad.skill.md", "---\n- list item\n---\nbody")
        result = parse_skill_file(filepath)
        assert result is None


class TestLoadAllSkills:
    def test_loads_valid_skills(self, tmp_skills_dir):
        _write_skill(tmp_skills_dir, "a.skill.md", VALID_SKILL)
        _write_skill(tmp_skills_dir, "b.txt", "not a skill file")

        skills = load_all_skills(str(tmp_skills_dir))
        assert len(skills) == 1
        assert "test-tool" in skills

    def test_skips_bad_files_without_crashing(self, tmp_skills_dir):
        _write_skill(tmp_skills_dir, "good.skill.md", VALID_SKILL)
        _write_skill(tmp_skills_dir, "bad.skill.md", "---\ninvalid: yaml: :\n---\n")

        skills = load_all_skills(str(tmp_skills_dir))
        # Good file loaded, bad file skipped
        assert len(skills) == 1
        assert "test-tool" in skills

    def test_empty_directory_returns_empty_dict(self, tmp_skills_dir):
        skills = load_all_skills(str(tmp_skills_dir))
        assert skills == {}
