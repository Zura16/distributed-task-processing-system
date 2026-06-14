import time
import signal
import sys
from backend.core.config import settings
from backend.core.queue import TaskQueue

class Scheduler:
    def __init__(self):
        self.queue = TaskQueue()
        self.running = False

    def start(self):
        self.running = True
        print("[*] Starting scheduler daemon...")
        
        # Setup signals
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        while self.running:
            try:
                self._check_delayed_tasks()
            except Exception as e:
                print(f"[!] Error in scheduler loop: {e}", file=sys.stderr)
            time.sleep(1.0)

    def _check_delayed_tasks(self):
        now = time.time()
        # Retrieve all task IDs whose scheduled execution time has passed
        task_ids = self.queue.client.zrangebyscore(settings.DELAYED_QUEUE, 0, now)
        
        for task_id in task_ids:
            # Atomically attempt to remove the task from the delayed ZSET.
            # ZREM returns 1 if the element was removed successfully.
            # If multiple schedulers run, only one will succeed.
            if self.queue.client.zrem(settings.DELAYED_QUEUE, task_id):
                # Check if task is cancelled
                task = self.queue.get_task(task_id)
                if not task or task.get("status") == "CANCELLED":
                    continue

                # Push to active queue
                self.queue.client.lpush(settings.DEFAULT_QUEUE, task_id)
                
                # Update status in metadata
                self.queue.update_task(task_id, {"status": "PENDING"})
                
                # Log state change
                self.queue.log_to_task(task_id, "Scheduled task is due. Pushed to active queue.")
                print(f"[+] Scheduled task '{task['name']}' ({task_id}) pushed to active queue.")

    def shutdown(self, signum=None, frame=None):
        print("\n[*] Shutting down scheduler daemon gracefully...")
        self.running = False
        print("[*] Scheduler shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.start()
