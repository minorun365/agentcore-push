# agentcore-push

Push one Python Strands Agent file to Amazon Bedrock AgentCore Runtime.

```bash
uvx agentcore-push agent.py
```

Or just run it and pick a file:

```bash
uvx agentcore-push
```

## Agent

`agent.py`

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()


@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt", "Hello!")
    response = agent(prompt)
    return {"result": str(response)}


if __name__ == "__main__":
    app.run()
```

## Codespaces

```bash
aws login --remote
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
