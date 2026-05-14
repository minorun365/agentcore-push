from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence


DEFAULT_RUNTIME = "PYTHON_3_13"
DEFAULT_PYTHON_VERSION = "3.13"
DEFAULT_DEPENDENCIES = ("bedrock-agentcore", "strands-agents")
DEFAULT_IDLE_TIMEOUT_SECONDS = 300
DEFAULT_MAX_LIFETIME_SECONDS = 1800


@dataclass(frozen=True)
class PushConfig:
    agent_file: Path
    profile: Optional[str] = None
    region: Optional[str] = None
    runtime_name: Optional[str] = None
    runtime: str = DEFAULT_RUNTIME
    python_version: str = DEFAULT_PYTHON_VERSION
    role_arn: Optional[str] = None
    bucket: Optional[str] = None
    requirements: Optional[Path] = None
    dependencies: Sequence[str] = field(default_factory=lambda: DEFAULT_DEPENDENCIES)
    install_dependencies: bool = True
    wait: bool = True
    wait_timeout_seconds: int = 900
    keep_build: bool = False
    dry_run: bool = False

