from dataclasses import dataclass
from typing import Callable, Optional

from .aws_deploy import (
    AwsDeployResult,
    create_aws_context,
    default_bucket_name,
    deploy_to_agentcore,
    resolve_role_arn,
)
from .config import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_MAX_LIFETIME_SECONDS,
    PushConfig,
)
from .naming import runtime_name_from_path
from .packager import DeploymentPackage, build_deployment_package


@dataclass(frozen=True)
class PushResult:
    runtime_name: str
    package: DeploymentPackage
    aws: Optional[AwsDeployResult]


def push(config: PushConfig, log: Callable[[str], None] = lambda _message: None) -> PushResult:
    runtime_name = config.runtime_name or runtime_name_from_path(config.agent_file)

    package = build_deployment_package(
        config.agent_file,
        entry_point=config.agent_file.name,
        dependencies=config.dependencies,
        requirements=config.requirements,
        python_version=config.python_version,
        install_dependencies=config.install_dependencies,
        keep_build=config.keep_build,
        log=log,
    )

    if config.dry_run:
        return PushResult(runtime_name=runtime_name, package=package, aws=None)

    context = create_aws_context(profile=config.profile, region=config.region)
    bucket = config.bucket or default_bucket_name(context.account_id, context.region)
    role_arn = resolve_role_arn(context, explicit_role_arn=config.role_arn, log=log)

    aws_result = deploy_to_agentcore(
        context=context,
        runtime_name=runtime_name,
        package_zip=package.zip_path,
        entry_point=package.entry_point,
        runtime=config.runtime,
        role_arn=role_arn,
        bucket=bucket,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
        max_lifetime_seconds=DEFAULT_MAX_LIFETIME_SECONDS,
        wait=config.wait,
        wait_timeout_seconds=config.wait_timeout_seconds,
        log=log,
    )

    return PushResult(runtime_name=runtime_name, package=package, aws=aws_result)
