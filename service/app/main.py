from fastapi import FastAPI


app = FastAPI(title="Dify Agent Workspace Tools")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "dify-agent-workspace-tools",
    }