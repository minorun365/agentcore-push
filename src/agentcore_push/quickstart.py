from pathlib import Path
from typing import Iterable, List, Sequence


PREFERRED_FILENAMES = ("agent.py", "main.py", "app.py")


def find_python_candidates(directory: Path) -> List[Path]:
    """Find deployable Python files directly under the given directory."""
    return sort_python_candidates(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix == ".py" and not path.name.startswith(".")
    )


def sort_python_candidates(paths: Iterable[Path]) -> List[Path]:
    preferred_order = {name: index for index, name in enumerate(PREFERRED_FILENAMES)}

    return sorted(
        paths,
        key=lambda path: (
            preferred_order.get(path.name, len(PREFERRED_FILENAMES)),
            path.name.lower(),
        ),
    )


def format_candidate_list(paths: Sequence[Path]) -> str:
    return "\n".join(f"  {index}. {path.name}" for index, path in enumerate(paths, start=1))

