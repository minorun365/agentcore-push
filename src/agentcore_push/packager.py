import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from .errors import PackagingError


MAX_ZIPPED_BYTES = 250 * 1024 * 1024
MAX_UNZIPPED_BYTES = 750 * 1024 * 1024


@dataclass(frozen=True)
class DeploymentPackage:
    zip_path: Path
    entry_point: str
    zipped_bytes: int
    unzipped_bytes: int
    build_dir: Optional[Path] = None


def build_deployment_package(
    agent_file: Path,
    *,
    entry_point: Optional[str] = None,
    dependencies: Sequence[str] = (),
    requirements: Optional[Path] = None,
    python_version: str = "3.13",
    install_dependencies: bool = True,
    keep_build: bool = False,
    log: Callable[[str], None] = lambda _message: None,
) -> DeploymentPackage:
    agent_file = agent_file.expanduser().resolve()
    _validate_agent_file(agent_file)

    if requirements is not None:
        requirements = requirements.expanduser().resolve()
        if not requirements.exists():
            raise PackagingError(f"Requirements file not found: {requirements}")

    selected_entry_point = entry_point or agent_file.name
    if not selected_entry_point.endswith(".py"):
        raise PackagingError("AgentCore Python entry point must end with .py")

    temp_context = None
    if keep_build:
        build_root = Path(".agentcore-push").resolve() / agent_file.stem
        if build_root.exists():
            shutil.rmtree(build_root)
        build_root.mkdir(parents=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="agentcore-push-")
        build_root = Path(temp_context.name)

    try:
        package_dir = build_root / "package"
        package_dir.mkdir(parents=True, exist_ok=True)

        if install_dependencies:
            _install_dependencies(
                package_dir,
                dependencies=dependencies,
                requirements=requirements,
                python_version=python_version,
                log=log,
            )

        shutil.copy2(agent_file, package_dir / selected_entry_point)
        _apply_posix_permissions(package_dir)

        zip_path = build_root / "deployment_package.zip"
        log("Creating deployment ZIP")
        unzipped_bytes = _directory_size(package_dir)
        _zip_directory(package_dir, zip_path)
        zipped_bytes = zip_path.stat().st_size

        if zipped_bytes > MAX_ZIPPED_BYTES:
            raise PackagingError(
                f"Deployment ZIP is too large: {_format_bytes(zipped_bytes)} "
                f"(limit: {_format_bytes(MAX_ZIPPED_BYTES)})"
            )
        if unzipped_bytes > MAX_UNZIPPED_BYTES:
            raise PackagingError(
                f"Deployment package is too large when unzipped: {_format_bytes(unzipped_bytes)} "
                f"(limit: {_format_bytes(MAX_UNZIPPED_BYTES)})"
            )

        final_zip_path = zip_path
        if not keep_build:
            stable_dir = Path(".agentcore-push").resolve() / "last"
            stable_dir.mkdir(parents=True, exist_ok=True)
            final_zip_path = stable_dir / "deployment_package.zip"
            shutil.copy2(zip_path, final_zip_path)

        return DeploymentPackage(
            zip_path=final_zip_path,
            entry_point=selected_entry_point,
            zipped_bytes=zipped_bytes,
            unzipped_bytes=unzipped_bytes,
            build_dir=build_root if keep_build else stable_dir,
        )
    finally:
        if temp_context is not None:
            temp_context.cleanup()


def _validate_agent_file(agent_file: Path) -> None:
    if not agent_file.exists():
        raise PackagingError(f"Agent file not found: {agent_file}")
    if not agent_file.is_file():
        raise PackagingError(f"Agent path is not a file: {agent_file}")
    if agent_file.suffix != ".py":
        raise PackagingError("agentcore-push expects a .py file")


def _install_dependencies(
    target_dir: Path,
    *,
    dependencies: Sequence[str],
    requirements: Optional[Path],
    python_version: str,
    log: Callable[[str], None],
) -> None:
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise PackagingError("uv is required to package Linux ARM64 dependencies. Install uv first.")

    command = [
        uv_path,
        "pip",
        "install",
        "--python-platform",
        "aarch64-manylinux2014",
        "--python-version",
        python_version,
        "--target",
        str(target_dir),
        "--only-binary=:all:",
        "--upgrade",
    ]

    if requirements is not None:
        command.extend(["-r", str(requirements)])
    command.extend(dependencies)

    if requirements is None and not dependencies:
        return

    log("Installing Linux ARM64 dependencies with uv")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise PackagingError(
            "Failed to install dependencies for Linux ARM64. "
            "A dependency may not publish a compatible wheel."
        ) from error


def _apply_posix_permissions(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if _should_skip(path):
                continue
            arcname = path.relative_to(source_dir).as_posix()
            if path.is_dir():
                _write_directory(archive, path, arcname)
            else:
                _write_file(archive, path, arcname)


def _write_directory(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname.rstrip("/") + "/")
    info.external_attr = 0o755 << 16
    info.date_time = _zip_timestamp(path)
    archive.writestr(info, b"")


def _write_file(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname)
    info.external_attr = 0o644 << 16
    info.date_time = _zip_timestamp(path)
    with path.open("rb") as source:
        archive.writestr(info, source.read())


def _zip_timestamp(path: Path) -> tuple:
    timestamp = max(path.stat().st_mtime, 315532800)
    return tuple(__import__("time").localtime(timestamp)[:6])


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return "__pycache__" in parts or path.suffix in {".pyc", ".pyo"}


def _directory_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not _should_skip(path):
            total += path.stat().st_size
    return total


def _format_bytes(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
