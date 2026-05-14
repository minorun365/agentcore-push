import pytest

from agentcore_push.aws_deploy import AwsContext, resolve_role_arn
from agentcore_push.errors import AwsDeploymentError


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakePaginator:
    def __init__(self, roles):
        self._roles = roles

    def paginate(self):
        return [{"Roles": self._roles}]


class FakeIam:
    def __init__(self, roles):
        self._roles = roles

    def get_role(self, RoleName):
        if RoleName not in self._roles:
            raise FakeAwsError("NoSuchEntity")
        return {"Role": {"Arn": self._roles[RoleName]}}

    def get_paginator(self, _name):
        return FakePaginator(
            [
                {"RoleName": name, "Arn": arn}
                for name, arn in self._roles.items()
            ]
        )


class FakeSession:
    def __init__(self, roles):
        self._roles = roles

    def client(self, service_name):
        assert service_name == "iam"
        return FakeIam(self._roles)


def _context(roles):
    return AwsContext(
        session=FakeSession(roles),
        account_id="123456789012",
        region="us-east-1",
    )


def test_resolve_role_arn_uses_explicit_role_without_iam() -> None:
    role_arn = "arn:aws:iam::123456789012:role/ExplicitRole"
    context = AwsContext(session=object(), account_id="123456789012", region="us-east-1")

    assert resolve_role_arn(context, explicit_role_arn=role_arn, log=lambda _message: None) == role_arn


def test_resolve_role_arn_finds_generic_role() -> None:
    role_arn = "arn:aws:iam::123456789012:role/AgentCoreRuntimeExecutionRole"

    assert (
        resolve_role_arn(
            _context({"AgentCoreRuntimeExecutionRole": role_arn}),
            explicit_role_arn=None,
            log=lambda _message: None,
        )
        == role_arn
    )


def test_resolve_role_arn_prefers_single_sdk_role_over_generic_role() -> None:
    sdk_role_arn = "arn:aws:iam::123456789012:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-abcd"
    generic_role_arn = "arn:aws:iam::123456789012:role/AgentCoreRuntimeExecutionRole"

    assert (
        resolve_role_arn(
            _context(
                {
                    "AmazonBedrockAgentCoreSDKRuntime-us-east-1-abcd": sdk_role_arn,
                    "AgentCoreRuntimeExecutionRole": generic_role_arn,
                }
            ),
            explicit_role_arn=None,
            log=lambda _message: None,
        )
        == sdk_role_arn
    )


def test_resolve_role_arn_rejects_multiple_sdk_role_candidates() -> None:
    roles = {
        "AmazonBedrockAgentCoreSDKRuntime-us-east-1-aaaa": "arn:aws:iam::123456789012:role/one",
        "AmazonBedrockAgentCoreSDKRuntime-us-east-1-bbbb": "arn:aws:iam::123456789012:role/two",
    }

    with pytest.raises(AwsDeploymentError, match="Multiple AgentCore Runtime role candidates"):
        resolve_role_arn(_context(roles), explicit_role_arn=None, log=lambda _message: None)
