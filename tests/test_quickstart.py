from pathlib import Path

from agentcore_push.quickstart import (
    find_python_candidates,
    format_candidate_list,
    sort_python_candidates,
)


def test_sort_python_candidates_prefers_common_agent_filenames() -> None:
    paths = [
        Path("zeta.py"),
        Path("app.py"),
        Path("main.py"),
        Path("agent.py"),
        Path("alpha.py"),
    ]

    assert [path.name for path in sort_python_candidates(paths)] == [
        "agent.py",
        "main.py",
        "app.py",
        "alpha.py",
        "zeta.py",
    ]


def test_find_python_candidates_reads_current_directory_only(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("")
    (tmp_path / "notes.txt").write_text("")
    (tmp_path / ".hidden.py").write_text("")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "main.py").write_text("")

    assert [path.name for path in find_python_candidates(tmp_path)] == ["agent.py"]


def test_format_candidate_list_numbers_files() -> None:
    assert format_candidate_list([Path("agent.py"), Path("main.py")]) == (
        "  1. agent.py\n"
        "  2. main.py"
    )

