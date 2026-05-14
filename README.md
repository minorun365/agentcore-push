# agentcore-push

Deploy a single-file Strands Agent to Bedrock AgentCore Runtime.

```bash
uvx agentcore-push agent.py
```

## Quick Start

```bash
# 1. Write your agent
nano agent.py

# 2. Authenticate from Codespaces
aws login --remote

# 3. Deploy
uvx agentcore-push agent.py
```

## agent.py

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()


@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt", "Hello")
    response = agent(prompt)
    return {"result": str(response)}


if __name__ == "__main__":
    app.run()
```

## Note

Community OSS. Not an AWS official tool.
