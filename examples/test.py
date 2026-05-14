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
