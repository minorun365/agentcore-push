import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from .errors import AwsDeploymentError

AGENTCORE_PUSH_ROLE_PREFIX = "AmazonBedrockAgentCorePushRuntime"
AGENTCORE_PUSH_POLICY_NAME = "AgentCorePushRuntimeExecutionPolicy"


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
    return f"arn:aws:iam::{account_id}:role/{default_role_name(region)}"


def default_role_name(region: str) -> str:
    return f"{AGENTCORE_PUSH_ROLE_PREFIX}-{region}"


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

    return ensure_agentcore_push_role(iam, context=context, log=log)


def ensure_agentcore_push_role(
    iam: object,
    *,
    context: AwsContext,
    log: Callable[[str], None],
) -> str:
    role_name = default_role_name(context.region)
    role = _get_role(iam, role_name)

    if role is None:
        log(f"Creating AgentCore Runtime execution role: {role_name}")
        role = _create_agentcore_push_role(iam, context=context, role_name=role_name)
    else:
        log(f"Using agentcore-push managed Runtime role: {role_name}")

    _put_agentcore_push_role_policy(iam, context=context, role_name=role_name)
    return role["Arn"]


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


def _get_role(iam: object, role_name: str) -> Optional[Dict]:
    try:
        response = iam.get_role(RoleName=role_name)
        return response["Role"]
    except Exception as error:
        if _is_missing_role_error(error):
            return None
        raise AwsDeploymentError(f"Failed to inspect IAM role {role_name}.") from error


def _create_agentcore_push_role(iam: object, *, context: AwsContext, role_name: str) -> Dict:
    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(_runtime_trust_policy(context)),
            Description="Execution role for agentcore-push managed Bedrock AgentCore Runtimes",
            Tags=[
                {"Key": "ManagedBy", "Value": "agentcore-push"},
                {"Key": "AgentCorePushRegion", "Value": context.region},
            ],
        )
        return response["Role"]
    except Exception as error:
        raise AwsDeploymentError(
            "Failed to create the AgentCore Runtime execution role. "
            "The caller needs iam:CreateRole, iam:PutRolePolicy, and iam:PassRole permissions "
            f"for {role_name}."
        ) from error


def _put_agentcore_push_role_policy(iam: object, *, context: AwsContext, role_name: str) -> None:
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=AGENTCORE_PUSH_POLICY_NAME,
            PolicyDocument=json.dumps(_runtime_execution_policy(context)),
        )
    except Exception as error:
        raise AwsDeploymentError(
            "Failed to attach the AgentCore Runtime execution policy. "
            "The caller needs iam:PutRolePolicy permission "
            f"for {role_name}."
        ) from error


def _runtime_trust_policy(context: AwsContext) -> Dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com",
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": context.account_id,
                    },
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:aws:bedrock-agentcore:{context.region}:{context.account_id}:*"
                        ),
                    },
                },
            },
        ],
    }


def _runtime_execution_policy(context: AwsContext) -> Dict:
    region = context.region
    account_id = context.account_id
    runtime_log_group = f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"

    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AgentCoreRuntimeLogsSetup",
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup",
                ],
                "Resource": [
                    runtime_log_group,
                ],
            },
            {
                "Sid": "AgentCoreRuntimeLogsDescribeGroups",
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogGroups",
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:*",
                ],
            },
            {
                "Sid": "AgentCoreRuntimeLogsWrite",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": [
                    f"{runtime_log_group}:log-stream:*",
                ],
            },
            {
                "Sid": "AgentCoreRuntimeTrace",
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": [
                    "*",
                ],
            },
            {
                "Sid": "AgentCoreRuntimeMetrics",
                "Effect": "Allow",
                "Action": "cloudwatch:PutMetricData",
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore",
                    },
                },
            },
            {
                "Sid": "BedrockModelInvocation",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ApplyGuardrail",
                ],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{account_id}:inference-profile/*",
                    f"arn:aws:bedrock:{region}:{account_id}:*",
                ],
            },
        ],
    }


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
        raise AwsDeploymentError(
            "Failed to create AgentCore Runtime. "
            "Confirm the caller can pass the execution role with iam:PassRole."
        ) from error


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
        raise AwsDeploymentError(
            "Failed to update AgentCore Runtime. "
            "Confirm the caller can pass the execution role with iam:PassRole."
        ) from error


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
