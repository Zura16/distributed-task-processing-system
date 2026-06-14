import os
import sys
import time
import socket
import traceback
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from backend.core.config import settings
from backend.core.queue import TaskQueue
from backend.core.tasks import TASK_REGISTRY

# Setup thread-local context for stdout redirection
thread_local_ctx = threading.local()

class ThreadLocalStreamRedirector:
    def __init__(self, original_stream, queue_client):
        self.original_stream = original_stream
        self.queue = queue_client

    def write(self, message):
        # Only write non-empty messages to avoid spamming empty logs
        msg_stripped = message.strip()
        if msg_stripped:
            task_id = getattr(thread_local_ctx, "task_id", None)
            if task_id:
                try:
                    self.queue.log_to_task(task_id, msg_stripped)
                except Exception:
                    pass
        # Always output to the original console stream (stdout/stderr)
        self.original_stream.write(message)

    def flush(self):
        self.original_stream.flush()

class Worker:
    def __init__(self, concurrency=2):
        self.queue = TaskQueue()
        self.concurrency = concurrency
        self.worker_name = f"worker@{socket.gethostname()}-{os.getpid()}"
        self.executor = ThreadPoolExecutor(max_workers=concurrency)
        self.running = False
        self.active_tasks = {}  # Thread ID -> Task ID
        self.lock = threading.Lock()
        
        # Setup redirectors for print capture
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = ThreadLocalStreamRedirector(self.original_stdout, self.queue)
        sys.stderr = ThreadLocalStreamRedirector(self.original_stderr, self.queue)

    def start(self):
        self.running = True
        print(f"[*] Starting worker: {self.worker_name}")
        print(f"[*] Concurrency level: {self.concurrency}")
        print(f"[*] Registered tasks: {list(TASK_REGISTRY.keys())}")

        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        # Listen for shutdown signals
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        # Worker loop
        while self.running:
            try:
                # Block for a task ID (timeout of 2 seconds to check running status)
                res = self.queue.client.brpop(settings.DEFAULT_QUEUE, timeout=2)
                if not res:
                    continue
                
                _, task_id = res
                
                # Check if the task was cancelled while in queue
                task = self.queue.get_task(task_id)
                if not task or task.get("status") == "CANCELLED":
                    continue

                # Submit to thread pool
                self.executor.submit(self._execute_task_wrapper, task_id)
            except Exception as e:
                print(f"[!] Error in worker loop: {e}", file=self.original_stderr)
                time.sleep(1.0)

    def _execute_task_wrapper(self, task_id):
        # Register task in thread-local storage for log redirection
        thread_local_ctx.task_id = task_id
        
        # Update thread mapping
        thread_id = threading.get_ident()
        with self.lock:
            self.active_tasks[thread_id] = task_id

        # Update heartbeat status
        self.queue.register_worker_heartbeat(self.worker_name, "busy", task_id)

        try:
            self._execute_task(task_id)
        finally:
            # Clean up thread-local and active task mapping
            thread_local_ctx.task_id = None
            with self.lock:
                if thread_id in self.active_tasks:
                    del self.active_tasks[thread_id]
            
            # Reset heartbeat state
            self.queue.register_worker_heartbeat(self.worker_name, "idle")

    def _execute_task(self, task_id):
        task = self.queue.get_task(task_id)
        if not task:
            return

        print(f"Picked up task '{task['name']}' ({task_id}). Status -> RUNNING.")
        self.queue.update_task(task_id, {
            "status": "RUNNING",
            "started_at": str(time.time())
        })

        task_func = TASK_REGISTRY.get(task["name"])
        if not task_func:
            err_msg = f"Task function '{task['name']}' not found in registry."
            print(f"ERROR: {err_msg}")
            self._handle_failure(task_id, task, err_msg)
            return

        try:
            # Execute task
            result = task_func(*task["args"], **task["kwargs"])
            
            # Update task on success
            print(f"Task completed successfully.")
            self.queue.update_task(task_id, {
                "status": "SUCCESS",
                "finished_at": str(time.time()),
                "result": json_safe_dump(result)
            })
        except Exception as e:
            tb = traceback.format_exc()
            print(f"ERROR: Task raised exception:\n{tb}")
            self._handle_failure(task_id, task, f"{type(e).__name__}: {str(e)}")

    def _handle_failure(self, task_id, task, error_message):
        retries_left = task["retries_left"]
        
        if retries_left > 0:
            new_retries_left = retries_left - 1
            retry_count = task["max_retries"] - new_retries_left
            # Exponential backoff delay calculation
            backoff_delay = task["retry_delay"] * (2 ** (retry_count - 1))
            
            print(f"Task failed. Retries left: {new_retries_left}. Scheduling retry in {backoff_delay}s.")
            
            # Update state to RETRYING
            self.queue.update_task(task_id, {
                "status": "RETRYING",
                "retries_left": str(new_retries_left),
                "error": error_message
            })
            
            # Add to scheduler delayed ZSET
            scheduled_time = time.time() + backoff_delay
            self.queue.client.zadd(settings.DELAYED_QUEUE, {task_id: scheduled_time})
        else:
            print("Task failed and exhausted all retries.")
            self.queue.update_task(task_id, {
                "status": "FAILED",
                "finished_at": str(time.time()),
                "error": error_message
            })

    def _heartbeat_loop(self):
        while self.running:
            try:
                # Determine state
                with self.lock:
                    state = "busy" if self.active_tasks else "idle"
                    curr_task_id = list(self.active_tasks.values())[0] if self.active_tasks else None
                self.queue.register_worker_heartbeat(self.worker_name, state, curr_task_id)
            except Exception as e:
                print(f"[!] Error sending heartbeat: {e}", file=self.original_stderr)
            time.sleep(5.0)

    def shutdown(self, signum=None, frame=None):
        print(f"\n[*] Shutting down worker {self.worker_name} gracefully...")
        self.running = False
        
        # Deregister worker from Redis
        try:
            self.queue.client.hdel(settings.WORKERS_HEARTBEATS_KEY, self.worker_name)
        except Exception:
            pass

        # Shutdown thread pool
        self.executor.shutdown(wait=True)
        
        # Restore stdout/stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        print("[*] Worker shutdown complete.")
        sys.exit(0)

def json_safe_dump(obj):
    try:
        import json
        return json.dumps(obj)
    except Exception:
        return str(obj)

if __name__ == "__main__":
    concurrency_env = int(os.getenv("CONCURRENCY", "2"))
    worker = Worker(concurrency=concurrency_env)
    worker.start()
