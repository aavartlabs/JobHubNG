from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="JobHub Agent Runtime", version="0.1.0")

class AgentRunRequest(BaseModel):
    job_raw_id: int
    correlation_id: str

@app.get("/health")
def health():
    return {"service": "jobhub-agent-runtime", "phase": "0+1", "status": "READY"}

@app.post("/internal/v1/agent-runs/job-enrichment")
def job_enrichment(request: AgentRunRequest):
    return {
        "status": "NOT_IMPLEMENTED_IN_PHASE_0_1",
        "jobRawId": request.job_raw_id,
        "correlationId": request.correlation_id,
        "nextPhase": "Phase 5 - OpenAI Agents SDK job enrichment"
    }
