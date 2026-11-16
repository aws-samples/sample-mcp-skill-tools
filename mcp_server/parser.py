"""
parser.py — Parse .skill.md files into structured tool definitions.

Each .skill.md file is:
  ---
  <YAML frontmatter: name, description, input_schema, ...>
  ---
  <Markdown body, including a "## Execution" section with a fenced code block>

parse_skill_file() splits on the '---' delimiters, parses the frontmatter with
yaml.safe_load(), and validates that `name` and `description` are present. The
raw markdown body is stored as `_body`; command extraction from the
"## Execution" block is the server's responsibility. Any failure returns None
with a logged warning so one bad file never crashes the server.
"""
import os
import logging
import yaml

logger = logging.getLogger(__name__)


def parse_skill_file(filepath: str) -> dict | None:
    """
    Parse a single .skill.md file and extract YAML frontmatter.

    Uses a two-split approach: verifies the file starts with '---',
    then splits on the closing '---' delimiter to separate frontmatter
    from body content. Returns None (with a warning) if parsing fails.
    """
    try:
        with open(filepath, encoding="utf-8") as fh:
            content = fh.read()
    except OSError as e:
        logger.warning("Cannot read skill file %s: %s", filepath, e)
        return None

    stripped = content.strip()
    if not stripped.startswith("---"):
        logger.warning("Skill file %s missing YAML frontmatter (no leading '---')", filepath)
        return None

    # Remove leading '---' then split on the next '---' occurrence
    after_first = stripped[3:]
    parts = after_first.split("---", 1)
    if len(parts) < 2:
        logger.warning("Skill file %s has no closing '---' delimiter", filepath)
        return None

    frontmatter_text = parts[0]
    body = parts[1]

    try:
        meta = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        logger.warning("Invalid YAML in %s: %s", filepath, e)
        return None

    if not isinstance(meta, dict):
        logger.warning("Frontmatter in %s is not a mapping", filepath)
        return None

    required_keys = {"name", "description"}
    missing = required_keys - meta.keys()
    if missing:
        logger.warning("Skill file %s missing required keys: %s", filepath, missing)
        return None

    meta["_body"] = body
    meta["_filepath"] = filepath
    return meta


def load_all_skills(directory: str) -> dict:
    """
    Load all .skill.md files from a directory. Files that fail to parse
    are skipped with a warning — one bad file does not prevent other
    tools from loading.
    """
    skills = {}
    try:
        filenames = sorted(os.listdir(directory))
    except OSError as e:
        logger.warning("Cannot list skills directory %s: %s", directory, e)
        return skills

    for filename in filenames:
        if not filename.endswith(".skill.md"):
            continue
        filepath = os.path.join(directory, filename)
        meta = parse_skill_file(filepath)
        if meta is not None:
            skills[meta["name"]] = meta
            logger.info("Loaded skill: %s from %s", meta["name"], filename)
    logger.info("Loaded %d skill(s) from %s", len(skills), directory)
    return skills
