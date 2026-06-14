import time
import pytest
import redis
from backend.core.config import settings
from backend.core.queue import TaskQueue
from backend.worker import Worker
from backend.core.tasks import register_task

@pytest.fixture
def clean_redis():
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    client.flushdb()
    yield client
    client.flushdb()

def test_worker_executes_success(clean_redis):
    queue = TaskQueue()
    # Enqueue standard successful task
    task_id = queue.enqueue(name="add", args=[10, 5], kwargs={}, max_retries=1)
    
    worker = Worker(concurrency=1)
    
    # Manually execute the task wrapper (simulating one step of worker popping it)
    worker._execute_task_wrapper(task_id)
    
    # Check status and result
    task = queue.get_task(task_id)
    assert task["status"] == "SUCCESS"
    assert task["result"] == "15" # json safe dump of 15
    assert task["started_at"] is not None
    assert task["finished_at"] is not None
    
    # Check that logs were captured
    logs = queue.get_logs(task_id)
    assert len(logs) > 0
    # The 'add' task prints: "Adding 10 + 5..."
    assert any("Adding 10 + 5..." in log for log in logs)
    assert any("Result is: 15" in log for log in logs)

def test_worker_executes_flaky_task_with_retries(clean_redis):
    queue = TaskQueue()
    # Enqueue a flaky task that always fails (fail_rate=1.0)
    task_id = queue.enqueue(name="flaky_task", args=[1.0], kwargs={}, max_retries=2, retry_delay=1)
    
    worker = Worker(concurrency=1)
    
    # Run first attempt - should fail and trigger retry
    worker._execute_task_wrapper(task_id)
    
    task = queue.get_task(task_id)
    assert task["status"] == "RETRYING"
    assert task["retries_left"] == 1
    assert "Simulated transient network timeout" in task["error"]
    
    # Verify it is scheduled in delayed queue ZSET
    score = clean_redis.zscore(settings.DELAYED_QUEUE, task_id)
    assert score is not None
    
    # Run second attempt (we will pop manually and execute again to simulate scheduler waking it up)
    clean_redis.zrem(settings.DELAYED_QUEUE, task_id)
    worker._execute_task_wrapper(task_id)
    
    task = queue.get_task(task_id)
    assert task["status"] == "RETRYING"
    assert task["retries_left"] == 0
    
    # Run third attempt (last retry exhausted -> FAILED)
    clean_redis.zrem(settings.DELAYED_QUEUE, task_id)
    worker._execute_task_wrapper(task_id)
    
    task = queue.get_task(task_id)
    assert task["status"] == "FAILED"
    assert task["retries_left"] == 0
    assert task["finished_at"] is not None
