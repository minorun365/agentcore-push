import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .errors import AwsDeploymentError


@dataclass(frozen=True)
class AwsContext:
    session: object
    account_id: str
    region: str


@dataclass(frozen=True)
class AwsDeployResult:
    action: str
    runtime_name: str
    runtime_id: Optional[str]
    runtime_arn: Optional[str]
    runtime_version: Optional[str]
    status: Optional[str]
    s3_uri: str
    role_arn: str
    account_id: str
    region: str


def create_aws_context(profile: Optional[str], region: Optional[str]) -> AwsContext:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as error:
        raise AwsDeploymentError(
            "boto3 is required. Install agentcore-push with its project dependencies."
        ) from error

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        resolved_region = region or session.region_name
        if not resolved_region:
            raise AwsDeploymentError(
                "AWS region is not configured. In Codespaces, run aws login --remote and set a "
                "default region with aws configure set region <region>, or pass --region."
            )

        sts = session.client("sts", region_name=resolved_region)
        identity = sts.get_caller_identity()
        return AwsContext(
            session=session,
            account_id=identity["Account"],
            region=resolved_region,
        )
    except (BotoCoreError, ClientError) as error:
        raise AwsDeploymentError(
            "Could not resolve AWS identity. In Codespaces, run aws login --remote first."
        ) from error


def default_bucket_name(account_id: str, region: str) -> str:
    return f"bedrock-agentcore-code-{account_id}-{region}"


def default_role_arn(account_id: str, region: str) -> str:
    return f"arn:aws:iam::{account_id}:role/AmazonBedrockAgentCoreSDKRuntime-{region}"


def resolve_role_arn(
    context: AwsContext,
    *,
    explicit_role_arn: Optional[str],
    log: Callable[[str], None],
) -> str:
    if explicit_role_arn:
        return explicit_role_arn

    try:
        iam = context.session.client("iam")
    except Exception as error:
        raise AwsDeploymentError("Could not create IAM client to discover AgentCore role.") from error

    exact_candidates = [
        f"AmazonBedrockAgentCoreSDKRuntime-{context.region}",
    ]
    for role_name in exact_candidates:
        role_arn = _get_role_arn(iam, role_name)
        if role_arn:
            log(f"Using inferred AgentCore Runtime role: {role_name}")
            return role_arn

    sdk_prefix = f"AmazonBedrockAgentCoreSDKRuntime-{context.region}-"
    sdk_roles = _list_role_arns_by_prefix(iam, sdk_prefix)
    if len(sdk_roles) == 1:
        role_name, role_arn = sdk_roles[0]
        log(f"Using inferred AgentCore Runtime role: {role_name}")
        return role_arn
    if len(sdk_roles) > 1:
        suggestions = "\n".join(f"  - {arn}" for _name, arn in sdk_roles[:10])
        raise AwsDeploymentError(
            "Multiple AgentCore Runtime role candidates were found. "
            "Pass one explicitly with --role-arn.\n"
            f"{suggestions}"
        )

    generic_role_name = "AgentCoreRuntimeExecutionRole"
    role_arn = _get_role_arn(iam, generic_role_name)
    if role_arn:
        log(f"Using inferred AgentCore Runtime role: {generic_role_name}")
        return role_arn

    fallback = default_role_arn(context.account_id, context.region)
    raise AwsDeploymentError(
        "Could not infer an AgentCore Runtime execution role. "
        "Create one first or pass --role-arn explicitly.\n"
        f"Tried: {', '.join(exact_candidates)}, {sdk_prefix}*, {generic_role_name}.\n"
        f"Legacy fallback format would be: {fallback}"
    )


def deploy_to_agentcore(
    *,
    context: AwsContext,
    runtime_name: str,
    package_zip: Path,
    entry_point: str,
    runtime: str,
    role_arn: str,
    bucket: str,
    idle_timeout_seconds: int,
    max_lifetime_seconds: int,
    wait: bool,
    wait_timeout_seconds: int,
    log: Callable[[str], None],
) -> AwsDeployResult:
    try:
        s3 = context.session.client("s3", region_name=context.region)
        control = context.session.client("bedrock-agentcore-control", region_name=context.region)
    except Exception as error:
        raise AwsDeploymentError("Could not create AWS service clients.") from error

    ensure_bucket(s3, bucket=bucket, region=context.region, account_id=context.account_id, log=log)

    artifact_key = f"{runtime_name}/deployment_package.zip"
    s3_uri = f"s3://{bucket}/{artifact_key}"
    upload_package(
        s3,
        package_zip=package_zip,
        bucket=bucket,
        key=artifact_key,
        account_id=context.account_id,
        log=log,
    )

    artifact = {
        "codeConfiguration": {
            "code": {
                "s3": {
                    "bucket": bucket,
                    "prefix": artifact_key,
                }
            },
            "runtime": runtime,
            "entryPoint": [entry_point],
        }
    }

    lifecycle = {
        "idleRuntimeSessionTimeout": idle_timeout_seconds,
        "maxLifetime": max_lifetime_seconds,
    }

    existing = find_runtime_by_name(control, runtime_name)
    if existing is None:
        log("Creating AgentCore Runtime")
        response = _create_runtime(
            control,
            runtime_name=runtime_name,
            artifact=artifact,
            role_arn=role_arn,
            lifecycle=lifecycle,
        )
        action = "created"
    else:
        log("Updating AgentCore Runtime")
        response = _update_runtime(
            control,
            runtime_id=existing["agentRuntimeId"],
            artifact=artifact,
            role_arn=role_arn,
            lifecycle=lifecycle,
        )
        action = "updated"

    runtime_id = response.get("agentRuntimeId") or (existing or {}).get("agentRuntimeId")
    status = response.get("status")
    if wait and runtime_id:
        status = wait_for_runtime(control, runtime_id, timeout_seconds=wait_timeout_seconds, log=log)
        latest = get_runtime(control, runtime_id)
        response = {**response, **latest}

    return AwsDeployResult(
        action=action,
        runtime_name=runtime_name,
        runtime_id=runtime_id,
        runtime_arn=response.get("agentRuntimeArn"),
        runtime_version=response.get("agentRuntimeVersion"),
        status=status,
        s3_uri=s3_uri,
        role_arn=role_arn,
        account_id=context.account_id,
        region=context.region,
    )


def _get_role_arn(iam: object, role_name: str) -> Optional[str]:
    try:
        response = iam.get_role(RoleName=role_name)
        return response["Role"]["Arn"]
    except Exception as error:
        if _is_missing_role_error(error):
            return None
        raise AwsDeploymentError(f"Failed to inspect IAM role {role_name}.") from error


def _list_role_arns_by_prefix(iam: object, prefix: str) -> List[tuple]:
    roles: List[tuple] = []
    try:
        paginator = iam.get_paginator("list_roles")
        pages = paginator.paginate()
    except Exception:
        pages = _manual_list_role_pages(iam)

    try:
        for page in pages:
            for role in page.get("Roles", []):
                role_name = role.get("RoleName", "")
                if role_name.startswith(prefix):
                    roles.append((role_name, role["Arn"]))
    except Exception as error:
        raise AwsDeploymentError("Failed to list IAM roles for AgentCore role discovery.") from error
    return sorted(roles)


def _manual_list_role_pages(iam: object):
    marker = None
    while True:
        kwargs = {}
        if marker:
            kwargs["Marker"] = marker
        page = iam.list_roles(**kwargs)
        yield page
        if not page.get("IsTruncated"):
            break
        marker = page.get("Marker")


def ensure_bucket(
    s3: object,
    *,
    bucket: str,
    region: str,
    account_id: str,
    log: Callable[[str], None],
) -> None:
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)
        return
    except Exception as error:
        if not _is_missing_bucket_error(error):
            raise AwsDeploymentError(f"Cannot access S3 bucket {bucket}.") from error

    log(f"Creating S3 bucket {bucket}")
    try:
        kwargs = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
    except Exception as error:
        raise AwsDeploymentError(f"Failed to create S3 bucket {bucket}.") from error


def upload_package(
    s3: object,
    *,
    package_zip: Path,
    bucket: str,
    key: str,
    account_id: str,
    log: Callable[[str], None],
) -> None:
    log(f"Uploading deployment ZIP to s3://{bucket}/{key}")
    try:
        s3.upload_file(
            str(package_zip),
            bucket,
            key,
            ExtraArgs={"ExpectedBucketOwner": account_id},
        )
    except Exception as error:
        raise AwsDeploymentError("Failed to upload deployment package to S3.") from error


def find_runtime_by_name(control: object, runtime_name: str) -> Optional[Dict]:
    try:
        paginator = control.get_paginator("list_agent_runtimes")
        pages = paginator.paginate()
    except Exception:
        pages = _manual_list_runtime_pages(control)

    try:
        for page in pages:
            for runtime in page.get("agentRuntimes", []):
                if runtime.get("agentRuntimeName") == runtime_name:
                    return runtime
    except Exception as error:
        raise AwsDeploymentError("Failed to list AgentCore Runtimes.") from error
    return None


def get_runtime(control: object, runtime_id: str) -> Dict:
    try:
        return control.get_agent_runtime(agentRuntimeId=runtime_id)
    except Exception as error:
        raise AwsDeploymentError(f"Failed to get AgentCore Runtime {runtime_id}.") from error


def wait_for_runtime(
    control: object,
    runtime_id: str,
    *,
    timeout_seconds: int,
    log: Callable[[str], None],
) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_status = "UNKNOWN"
    while time.monotonic() < deadline:
        response = get_runtime(control, runtime_id)
        last_status = response.get("status", "UNKNOWN")
        if last_status == "READY":
            return last_status
        if last_status in {"CREATE_FAILED", "UPDATE_FAILED", "DELETING"}:
            raise AwsDeploymentError(f"AgentCore Runtime reached terminal status: {last_status}")
        log(f"Waiting for AgentCore Runtime status: {last_status}")
        time.sleep(10)
    raise AwsDeploymentError(
        f"Timed out waiting for AgentCore Runtime to become READY. Last status: {last_status}"
    )


def _create_runtime(
    control: object,
    *,
    runtime_name: str,
    artifact: Dict,
    role_arn: str,
    lifecycle: Dict,
) -> Dict:
    try:
        return control.create_agent_runtime(
            agentRuntimeName=runtime_name,
            agentRuntimeArtifact=artifact,
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            lifecycleConfiguration=lifecycle,
            tags={
                "ManagedBy": "agentcore-push",
            },
        )
    except Exception as error:
        raise AwsDeploymentError("Failed to create AgentCore Runtime.") from error


def _update_runtime(
    control: object,
    *,
    runtime_id: str,
    artifact: Dict,
    role_arn: str,
    lifecycle: Dict,
) -> Dict:
    try:
        return control.update_agent_runtime(
            agentRuntimeId=runtime_id,
            agentRuntimeArtifact=artifact,
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            lifecycleConfiguration=lifecycle,
        )
    except Exception as error:
        raise AwsDeploymentError("Failed to update AgentCore Runtime.") from error


def _manual_list_runtime_pages(control: object):
    next_token = None
    while True:
        kwargs = {}
        if next_token:
            kwargs["nextToken"] = next_token
        page = control.list_agent_runtimes(**kwargs)
        yield page
        next_token = page.get("nextToken")
        if not next_token:
            break


def _is_missing_bucket_error(error: Exception) -> bool:
    response = getattr(error, "response", {})
    status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    error_code = response.get("Error", {}).get("Code")
    return status_code == 404 or error_code in {"404", "NoSuchBucket", "NotFound"}


def _is_missing_role_error(error: Exception) -> bool:
    response = getattr(error, "response", {})
    error_code = response.get("Error", {}).get("Code")
    return error_code == "NoSuchEntity"
