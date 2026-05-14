from pathlib import Path
from typing import List, Optional
import sys

import typer
from rich.console import Console
from rich.table import Table

from .config import DEFAULT_DEPENDENCIES, DEFAULT_PYTHON_VERSION, DEFAULT_RUNTIME, PushConfig
from .deploy import push
from .errors import AgentCorePushError
from .naming import runtime_name_from_path
from .quickstart import find_python_candidates


console = Console()


def app() -> None:
    typer.run(main)


def main(
    agent_file: Optional[Path] = typer.Argument(
        None,
        help="Python file to deploy, for example agent.py.",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="AWS profile. Defaults to the SDK default profile.",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="AWS region. Defaults to the SDK/default profile region.",
    ),
    role_arn: Optional[str] = typer.Option(
        None,
        "--role-arn",
        help="AgentCore Runtime execution role ARN.",
    ),
    bucket: Optional[str] = typer.Option(
        None,
        "--bucket",
        help="S3 bucket for deployment packages.",
    ),
    runtime_name: Optional[str] = typer.Option(
        None,
        "--name",
        help="AgentCore Runtime name. Defaults to the Python file stem.",
    ),
    runtime: str = typer.Option(
        DEFAULT_RUNTIME,
        "--runtime",
        help="AgentCore direct code runtime.",
    ),
    python_version: str = typer.Option(
        DEFAULT_PYTHON_VERSION,
        "--python-version",
        help="Python version used when resolving Linux ARM64 wheels.",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Additional requirements file to install into the ZIP package.",
    ),
    dependency: Optional[List[str]] = typer.Option(
        None,
        "--dependency",
        "-d",
        help="Additional dependency to install into the ZIP package. Can be repeated.",
    ),
    no_default_dependencies: bool = typer.Option(
        False,
        "--no-default-dependencies",
        help="Do not install bedrock-agentcore and strands-agents automatically.",
    ),
    no_deps: bool = typer.Option(
        False,
        "--no-deps",
        help="Skip dependency installation entirely.",
    ),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="Wait until the AgentCore Runtime reaches READY.",
    ),
    wait_timeout: int = typer.Option(
        900,
        "--wait-timeout",
        help="Maximum seconds to wait for READY.",
    ),
    keep_build: bool = typer.Option(
        False,
        "--keep-build",
        help="Keep the full build directory for debugging.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Build the ZIP package but skip AWS calls.",
    ),
) -> None:
    if agent_file is None:
        agent_file = _quickstart()
        if agent_file is None:
            raise typer.Exit(0)

    dependencies = []
    if not no_default_dependencies:
        dependencies.extend(DEFAULT_DEPENDENCIES)
    if dependency:
        dependencies.extend(dependency)

    config = PushConfig(
        agent_file=agent_file,
        profile=profile,
        region=region,
        runtime_name=runtime_name,
        runtime=runtime,
        python_version=python_version,
        role_arn=role_arn,
        bucket=bucket,
        requirements=requirements,
        dependencies=tuple(dependencies),
        install_dependencies=not no_deps,
        wait=wait,
        wait_timeout_seconds=wait_timeout,
        keep_build=keep_build,
        dry_run=dry_run,
    )

    try:
        result = push(config, log=_log)
    except AgentCorePushError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1) from error
    except ValueError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1) from error

    _print_result(result)


def _quickstart() -> Optional[Path]:
    candidates = find_python_candidates(Path.cwd())

    if not sys.stdin.isatty():
        _print_quickstart_help(candidates)
        return None

    console.print("[bold]agentcore-push quick start[/bold]")

    if not candidates:
        console.print()
        console.print("No Python files found in the current directory.")
        _print_quickstart_help(candidates)
        return None

    if len(candidates) == 1:
        selected = candidates[0]
        _print_selected_candidate(selected)
        if typer.confirm("Deploy this file to AgentCore Runtime?", default=False):
            return selected
        return None

    table = Table(title="Python files", show_header=True)
    table.add_column("#", justify="right")
    table.add_column("File")
    table.add_column("Runtime name")
    for index, path in enumerate(candidates, start=1):
        table.add_row(str(index), path.name, runtime_name_from_path(path))
    console.print(table)

    selected = _prompt_candidate(candidates)
    _print_selected_candidate(selected)
    if typer.confirm("Deploy this file to AgentCore Runtime?", default=False):
        return selected
    return None


def _prompt_candidate(candidates: List[Path]) -> Path:
    while True:
        selected_index = typer.prompt("Select a file to deploy", default=1, type=int)
        if 1 <= selected_index <= len(candidates):
            return candidates[selected_index - 1]
        console.print(f"[red]Enter a number from 1 to {len(candidates)}.[/red]")


def _print_selected_candidate(path: Path) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("File", path.name)
    table.add_row("Runtime name", runtime_name_from_path(path))
    console.print()
    console.print(table)


def _print_quickstart_help(candidates: List[Path]) -> None:
    console.print()
    console.print("[bold]Usage[/bold]")
    console.print("  agentcore-push agent.py")
    console.print()
    console.print("[bold]Codespaces[/bold]")
    console.print("  aws login --remote")
    console.print("  uvx agentcore-push agent.py")
    if candidates:
        console.print()
        console.print("[bold]Found Python files[/bold]")
        for path in candidates:
            console.print(f"  - {path.name}")


def _log(message: str) -> None:
    console.print(f"[dim]›[/dim] {message}")


def _print_result(result) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Runtime name", result.runtime_name)
    table.add_row("ZIP", str(result.package.zip_path))
    table.add_row("ZIP size", _format_bytes(result.package.zipped_bytes))
    table.add_row("Unzipped size", _format_bytes(result.package.unzipped_bytes))

    if result.aws is None:
        table.add_row("AWS", "Skipped (--dry-run)")
    else:
        table.add_row("Action", result.aws.action)
        table.add_row("Status", result.aws.status or "UNKNOWN")
        if result.aws.runtime_id:
            table.add_row("Runtime ID", result.aws.runtime_id)
        if result.aws.runtime_arn:
            table.add_row("Runtime ARN", result.aws.runtime_arn)
        if result.aws.runtime_version:
            table.add_row("Version", result.aws.runtime_version)
        table.add_row("S3 artifact", result.aws.s3_uri)
        table.add_row("Role ARN", result.aws.role_arn)
        table.add_row("Account", result.aws.account_id)
        table.add_row("Region", result.aws.region)

    console.print()
    console.print(table)


def _format_bytes(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
