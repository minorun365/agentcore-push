class AgentCorePushError(RuntimeError):
    """Base error for user-facing failures."""


class PackagingError(AgentCorePushError):
    """Raised when the deployment package cannot be built."""


class AwsDeploymentError(AgentCorePushError):
    """Raised when AWS deployment fails."""

