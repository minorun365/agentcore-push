from pathlib import Path

from agentcore_push.naming import runtime_name_from_path


def test_runtime_name_uses_file_stem() -> None:
    assert runtime_name_from_path(Path("hello.py")) == "hello"


def test_runtime_name_replaces_invalid_characters() -> None:
    assert runtime_name_from_path(Path("hello-agent.py")) == "hello_agent"


def test_runtime_name_prefixes_non_letter_start() -> None:
    assert runtime_name_from_path(Path("123-agent.py")) == "agent_123_agent"


def test_runtime_name_trims_to_agentcore_limit() -> None:
    name = runtime_name_from_path(Path("a" * 80 + ".py"))
    assert len(name) == 48
    assert name == "a" * 48

