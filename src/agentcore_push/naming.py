import re
from pathlib import Path


RUNTIME_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,47}$")


def runtime_name_from_path(path: Path) -> str:
    """Create a valid AgentCore Runtime name from a Python file path."""
    stem = path.stem
    name = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "agent"

    if not name[0].isalpha():
        name = "agent_" + name

    name = name[:48]

    if not RUNTIME_NAME_PATTERN.match(name):
        raise ValueError(f"Could not derive a valid AgentCore Runtime name from {path}")

    return name

