# agentcore-push

Push one Python Strands Agent file to Amazon Bedrock AgentCore Runtime.

```bash
uvx agentcore-push agent.py
```

Or just run it and pick a file:

```bash
uvx agentcore-push
```

## Quick Start

```bash
# 1. Create your Strands agent
$EDITOR agent.py

# 2. Login to AWS from Codespaces or another remote shell
aws login --remote

# 3. Push it to AgentCore Runtime
uvx agentcore-push agent.py
```

From this checkout:

```bash
uvx --from . agentcore-push examples/test.py
```

## Development

```bash
uv run --extra dev pytest
```

## Note

Community OSS. Not an AWS official tool.
