import json

from agentcore_push.aws_deploy import (
    AGENTCORE_PUSH_POLICY_NAME,
    AwsContext,
    default_role_name,
    resolve_role_arn,
)


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class FakeIam:
    def __init__(self, roles):
        self._roles = roles
        self.created_roles = []
        self.inline_policies = {}

    def get_role(self, RoleName):
        if RoleName not in self._roles:
            raise FakeAwsError("NoSuchEntity")
        role = self._roles[RoleName]
        if isinstance(role, dict):
            return {"Role": role}
        return {"Role": {"RoleName": RoleName, "Arn": role}}

    def create_role(self, RoleName, AssumeRolePolicyDocument, Description, Tags):
        arn = f"arn:aws:iam::123456789012:role/{RoleName}"
        role = {
            "RoleName": RoleName,
            "Arn": arn,
            "AssumeRolePolicyDocument": json.loads(AssumeRolePolicyDocument),
            "Description": Description,
            "Tags": Tags,
        }
        self._roles[RoleName] = role
        self.created_roles.append(role)
        return {"Role": role}

    def put_role_policy(self, RoleName, PolicyName, PolicyDocument):
        if RoleName not in self._roles:
            raise FakeAwsError("NoSuchEntity")
        self.inline_policies[(RoleName, PolicyName)] = json.loads(PolicyDocument)


class FakeSession:
    def __init__(self, roles):
        self._roles = roles
        self.iam = FakeIam(self._roles)

    def client(self, service_name):
        assert service_name == "iam"
        return self.iam


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


def test_resolve_role_arn_uses_existing_agentcore_push_role() -> None:
    role_name = default_role_name("us-east-1")
    role_arn = f"arn:aws:iam::123456789012:role/{role_name}"
    context = _context({role_name: role_arn})

    assert (
        resolve_role_arn(
            context,
            explicit_role_arn=None,
            log=lambda _message: None,
        )
        == role_arn
    )
    assert (role_name, AGENTCORE_PUSH_POLICY_NAME) in context.session.iam.inline_policies


def test_resolve_role_arn_creates_agentcore_push_role_when_missing() -> None:
    context = _context({})
    role_name = default_role_name("us-east-1")

    role_arn = resolve_role_arn(context, explicit_role_arn=None, log=lambda _message: None)

    assert role_arn == f"arn:aws:iam::123456789012:role/{role_name}"
    assert context.session.iam.created_roles[0]["RoleName"] == role_name

    trust_policy = context.session.iam.created_roles[0]["AssumeRolePolicyDocument"]
    statement = trust_policy["Statement"][0]
    assert statement["Principal"]["Service"] == "bedrock-agentcore.amazonaws.com"
    assert statement["Condition"]["StringEquals"]["aws:SourceAccount"] == "123456789012"
    assert (
        statement["Condition"]["ArnLike"]["aws:SourceArn"]
        == "arn:aws:bedrock-agentcore:us-east-1:123456789012:*"
    )

    execution_policy = context.session.iam.inline_policies[(role_name, AGENTCORE_PUSH_POLICY_NAME)]
    actions = {
        action
        for policy_statement in execution_policy["Statement"]
        for action in (
            policy_statement["Action"]
            if isinstance(policy_statement["Action"], list)
            else [policy_statement["Action"]]
        )
    }
    assert "bedrock:InvokeModel" in actions
    assert "logs:PutLogEvents" in actions
    assert "cloudwatch:PutMetricData" in actions


def test_resolve_role_arn_creates_agentcore_push_role_even_with_multiple_sdk_candidates() -> None:
    roles = {
        "AmazonBedrockAgentCoreSDKRuntime-us-east-1-aaaa": "arn:aws:iam::123456789012:role/one",
        "AmazonBedrockAgentCoreSDKRuntime-us-east-1-bbbb": "arn:aws:iam::123456789012:role/two",
    }
    context = _context(roles)
    role_name = default_role_name("us-east-1")

    role_arn = resolve_role_arn(context, explicit_role_arn=None, log=lambda _message: None)

    assert role_arn == f"arn:aws:iam::123456789012:role/{role_name}"
    assert context.session.iam.created_roles[0]["RoleName"] == role_name
