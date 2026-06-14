import json
import time
import uuid
import redis
from backend.core.config import settings

class TaskQueue:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )

    def enqueue(
        self,
        name: str,
        args: list | None = None,
        kwargs: dict | None = None,
        delay_seconds: int = 0,
        max_retries: int = 3,
        retry_delay: int = 5
    ) -> str:
        """
        Enqueues a task. If delay_seconds > 0, schedules it for future execution.
        """
        task_id = str(uuid.uuid4())
        args = args or []
        kwargs = kwargs or {}

        task_data = {
            "id": task_id,
            "name": name,
            "args": json.dumps(args),
            "kwargs": json.dumps(kwargs),
            "status": "PENDING",
            "retries_left": str(max_retries),
            "max_retries": str(max_retries),
            "retry_delay": str(retry_delay),
            "created_at": str(time.time()),
            "started_at": "",
            "finished_at": "",
            "error": ""
        }

        # Save metadata to hash
        metadata_key = f"{settings.TASK_METADATA_PREFIX}:{task_id}"
        self.client.hset(metadata_key, mapping=task_data)
        
        # Add to all tasks set for tracking
        self.client.sadd("tasks:all", task_id)

        if delay_seconds > 0:
            # Schedule for delayed execution
            scheduled_time = time.time() + delay_seconds
            self.client.zadd(settings.DELAYED_QUEUE, {task_id: scheduled_time})
            self.client.hset(metadata_key, "status", "SCHEDULED")
            self.log_to_task(task_id, f"Task scheduled to run in {delay_seconds} seconds.")
        else:
            # Push to the active execution queue
            self.client.lpush(settings.DEFAULT_QUEUE, task_id)
            self.log_to_task(task_id, "Task submitted to active queue.")

        return task_id

    def get_task(self, task_id: str) -> dict | None:
        """
        Gets a task's metadata.
        """
        metadata_key = f"{settings.TASK_METADATA_PREFIX}:{task_id}"
        data = self.client.hgetall(metadata_key)
        if not data:
            return None

        # Parse JSON fields back to objects
        data["args"] = json.loads(data["args"])
        data["kwargs"] = json.loads(data["kwargs"])
        data["created_at"] = float(data["created_at"]) if data.get("created_at") else None
        data["started_at"] = float(data["started_at"]) if data.get("started_at") else None
        data["finished_at"] = float(data["finished_at"]) if data.get("finished_at") else None
        data["retries_left"] = int(data["retries_left"])
        data["max_retries"] = int(data["max_retries"])
        data["retry_delay"] = int(data["retry_delay"])
        return data

    def update_task(self, task_id: str, mapping: dict):
        """
        Updates task metadata fields.
        """
        metadata_key = f"{settings.TASK_METADATA_PREFIX}:{task_id}"
        self.client.hset(metadata_key, mapping=mapping)

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancels a task if it is scheduled or pending.
        """
        metadata_key = f"{settings.TASK_METADATA_PREFIX}:{task_id}"
        status = self.client.hget(metadata_key, "status")
        
        if status not in ["PENDING", "SCHEDULED"]:
            return False

        # Attempt to remove from delayed ZSET
        self.client.zrem(settings.DELAYED_QUEUE, task_id)
        # Attempt to remove from default queue
        self.client.lrem(settings.DEFAULT_QUEUE, 0, task_id)

        self.update_task(task_id, {
            "status": "CANCELLED",
            "finished_at": str(time.time())
        })
        self.log_to_task(task_id, "Task cancelled by user.")
        return True

    def retry_task(self, task_id: str) -> bool:
        """
        Manually re-triggers a failed or cancelled task.
        """
        task = self.get_task(task_id)
        if not task:
            return False
        
        if task["status"] not in ["FAILED", "CANCELLED"]:
            return False

        self.update_task(task_id, {
            "status": "PENDING",
            "retries_left": str(task["max_retries"]),
            "started_at": "",
            "finished_at": "",
            "error": ""
        })
        self.client.lpush(settings.DEFAULT_QUEUE, task_id)
        self.log_to_task(task_id, "Task manually re-submitted to active queue.")
        return True

    def log_to_task(self, task_id: str, message: str):
        """
        Appends a log line to a task.
        """
        log_key = f"{settings.TASK_LOG_PREFIX}:{task_id}"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.client.rpush(log_key, log_line)
        # Set expiration of 7 days on logs to avoid bloating Redis memory
        self.client.expire(log_key, 604800)

    def get_logs(self, task_id: str) -> list[str]:
        """
        Gets all log lines for a task.
        """
        log_key = f"{settings.TASK_LOG_PREFIX}:{task_id}"
        return self.client.lrange(log_key, 0, -1)

    def get_all_tasks(self, limit: int = 100) -> list[dict]:
        """
        Fetches metadata of all tasks, ordered by created_at descending.
        """
        task_ids = self.client.smembers("tasks:all")
        tasks = []
        for tid in task_ids:
            task = self.get_task(tid)
            if task:
                tasks.append(task)
        # Sort by created_at descending
        tasks.sort(key=lambda t: t.get("created_at") or 0.0, reverse=True)
        return tasks[:limit]

    def get_workers(self) -> dict:
        """
        Returns all registered workers and their current heartbeat info.
        """
        workers = self.client.hgetall(settings.WORKERS_HEARTBEATS_KEY)
        parsed_workers = {}
        now = time.time()
        for name, data_str in workers.items():
            data = json.loads(data_str)
            # Mark as offline if heartbeat has not been received in 15 seconds
            data["online"] = (now - data["last_seen"]) < 15.0
            parsed_workers[name] = data
        return parsed_workers

    def register_worker_heartbeat(self, worker_name: str, status: str, current_task_id: str | None = None):
        """
        Registers worker status and updates heartbeat timestamp.
        """
        workers = self.client.hgetall(settings.WORKERS_HEARTBEATS_KEY)
        existing_data = {}
        if worker_name in workers:
            existing_data = json.loads(workers[worker_name])

        heartbeat_data = {
            "name": worker_name,
            "status": status,
            "current_task_id": current_task_id,
            "last_seen": time.time(),
            "tasks_completed": existing_data.get("tasks_completed", 0) + (1 if status == "idle" and existing_data.get("status") == "busy" else 0)
        }
        self.client.hset(settings.WORKERS_HEARTBEATS_KEY, worker_name, json.dumps(heartbeat_data))

    def get_metrics(self) -> dict:
        """
        Aggregates system-wide performance and status metrics.
        """
        task_ids = self.client.smembers("tasks:all")
        status_counts = {
            "PENDING": 0,
            "SCHEDULED": 0,
            "RUNNING": 0,
            "SUCCESS": 0,
            "FAILED": 0,
            "CANCELLED": 0,
            "RETRYING": 0
        }
        
        for tid in task_ids:
            metadata_key = f"{settings.TASK_METADATA_PREFIX}:{tid}"
            status = self.client.hget(metadata_key, "status")
            if status in status_counts:
                status_counts[status] += 1

        queue_size = self.client.llen(settings.DEFAULT_QUEUE)
        delayed_size = self.client.zcard(settings.DELAYED_QUEUE)
        
        workers = self.get_workers()
        active_workers = sum(1 for w in workers.values() if w["online"])
        busy_workers = sum(1 for w in workers.values() if w["online"] and w["status"] == "busy")

        total_completed = status_counts["SUCCESS"] + status_counts["FAILED"]
        success_rate = (status_counts["SUCCESS"] / total_completed * 100) if total_completed > 0 else 0

        return {
            "queue_size": queue_size,
            "delayed_size": delayed_size,
            "active_workers": active_workers,
            "busy_workers": busy_workers,
            "statuses": status_counts,
            "success_rate": round(success_rate, 2)
        }
