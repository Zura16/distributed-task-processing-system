from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from backend.core.queue import TaskQueue
from backend.core.tasks import TASK_REGISTRY

app = FastAPI(title="Distributed Task Processing System API")

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

queue = TaskQueue()

# Pydantic Request Models
class TaskSubmitRequest(BaseModel):
    name: str = Field(..., description="Name of the task function to run")
    args: List[Any] = Field(default_factory=list, description="Positional arguments for the task")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for the task")
    delay_seconds: int = Field(0, ge=0, description="Delay execution by N seconds")
    max_retries: int = Field(3, ge=0, description="Maximum number of retry attempts")
    retry_delay: int = Field(5, ge=0, description="Initial retry delay in seconds")

class TaskResponse(BaseModel):
    id: str
    name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    status: str
    retries_left: int
    max_retries: int
    retry_delay: int
    created_at: Optional[float]
    started_at: Optional[float]
    finished_at: Optional[float]
    error: Optional[str]
    result: Optional[str] = None

@app.get("/api/tasks/available", response_model=List[str])
def list_available_tasks():
    """
    Returns a list of all registered tasks in the system.
    """
    return list(TASK_REGISTRY.keys())

@app.post("/api/tasks", response_model=Dict[str, str])
def submit_task(req: TaskSubmitRequest):
    """
    Submits a task to the system.
    """
    if req.name not in TASK_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Task '{req.name}' is not registered in the system. Available: {list(TASK_REGISTRY.keys())}"
        )
    
    try:
        task_id = queue.enqueue(
            name=req.name,
            args=req.args,
            kwargs=req.kwargs,
            delay_seconds=req.delay_seconds,
            max_retries=req.max_retries,
            retry_delay=req.retry_delay
        )
        return {"task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks", response_model=List[TaskResponse])
def get_tasks(
    status: Optional[str] = Query(None, description="Filter tasks by status"),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Lists all submitted tasks, optionally filtered by status.
    """
    try:
        tasks = queue.get_all_tasks(limit=limit)
        if status:
            tasks = [t for t in tasks if t.get("status") == status.upper()]
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task_details(task_id: str):
    """
    Gets details of a specific task.
    """
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/api/tasks/{task_id}/logs", response_model=List[str])
def get_task_logs(task_id: str):
    """
    Retrieves the execution logs for a task.
    """
    # Verify task exists
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    try:
        return queue.get_logs(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/{task_id}/cancel", response_model=Dict[str, bool])
def cancel_task(task_id: str):
    """
    Cancels a scheduled or pending task.
    """
    success = queue.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Could not cancel task. It may have already run, failed, or was cancelled."
        )
    return {"success": success}

@app.post("/api/tasks/{task_id}/retry", response_model=Dict[str, bool])
def retry_task(task_id: str):
    """
    Manually retries a failed or cancelled task.
    """
    success = queue.retry_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Could not retry task. It must be in FAILED or CANCELLED status."
        )
    return {"success": success}

@app.get("/api/metrics")
def get_system_metrics():
    """
    Fetches real-time system metrics.
    """
    try:
        return queue.get_metrics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers")
def get_workers_status():
    """
    Lists active workers and their execution states.
    """
    try:
        return queue.get_workers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
