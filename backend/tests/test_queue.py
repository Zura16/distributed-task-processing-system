import time
import pytest
import redis
from backend.core.config import settings
from backend.core.queue import TaskQueue
from backend.worker import Worker
from backend.scheduler import Scheduler
from backend.core.tasks import register_task, TASK_REGISTRY

@pytest.fixture
def clean_redis():
    """
    Cleans up all keys associated with settings before running tests.
    """
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    # Flush current DB to start clean
    client.flushdb()
    yield client
    # Clean up again
    client.flushdb()

def test_enqueue_immediate(clean_redis):
    queue = TaskQueue()
    task_id = queue.enqueue(name="add", args=[2, 3], kwargs={}, max_retries=2, retry_delay=3)
    
    # Check that task metadata exists
    task = queue.get_task(task_id)
    assert task is not None
    assert task["name"] == "add"
    assert task["args"] == [2, 3]
    assert task["status"] == "PENDING"
    assert task["max_retries"] == 2
    assert task["retries_left"] == 2
    
    # Check that task is in default queue list
    queue_len = clean_redis.llen(settings.DEFAULT_QUEUE)
    assert queue_len == 1
    
    popped_task_id = clean_redis.lpop(settings.DEFAULT_QUEUE)
    assert popped_task_id == task_id

def test_enqueue_scheduled(clean_redis):
    queue = TaskQueue()
    task_id = queue.enqueue(name="add", args=[2, 3], delay_seconds=10)
    
    # Check task metadata
    task = queue.get_task(task_id)
    assert task["status"] == "SCHEDULED"
    
    # Check delayed ZSET
    score = clean_redis.zscore(settings.DELAYED_QUEUE, task_id)
    assert score is not None
    assert score > time.time()

def test_cancel_task(clean_redis):
    queue = TaskQueue()
    task_id_pending = queue.enqueue(name="add", args=[2, 3])
    task_id_scheduled = queue.enqueue(name="add", args=[2, 3], delay_seconds=10)
    
    # Cancel pending task
    success_pending = queue.cancel_task(task_id_pending)
    assert success_pending is True
    assert queue.get_task(task_id_pending)["status"] == "CANCELLED"
    
    # Cancel scheduled task
    success_scheduled = queue.cancel_task(task_id_scheduled)
    assert success_scheduled is True
    assert queue.get_task(task_id_scheduled)["status"] == "CANCELLED"
    
    # Check that scheduled task was removed from delayed ZSET
    assert clean_redis.zscore(settings.DELAYED_QUEUE, task_id_scheduled) is None

def test_scheduler_moves_delayed_tasks(clean_redis):
    queue = TaskQueue()
    # Schedule a task with a tiny delay (1s)
    task_id = queue.enqueue(name="add", args=[2, 3], delay_seconds=1)
    
    # Initialize scheduler
    scheduler = Scheduler()
    
    # Run a check immediately - should not move it yet
    scheduler._check_delayed_tasks()
    assert queue.get_task(task_id)["status"] == "SCHEDULED"
    
    # Sleep 1.2s to expire the timer
    time.sleep(1.2)
    
    # Check again - should now move it
    scheduler._check_delayed_tasks()
    assert queue.get_task(task_id)["status"] == "PENDING"
    assert clean_redis.llen(settings.DEFAULT_QUEUE) == 1
