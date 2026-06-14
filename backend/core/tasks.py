import time
import random

# Global task registry
TASK_REGISTRY = {}

def register_task(name):
    """
    Decorator to register a task function in the system registry.
    """
    def decorator(func):
        TASK_REGISTRY[name] = func
        return func
    return decorator

@register_task("add")
def add(x, y):
    print(f"Adding {x} + {y}...")
    time.sleep(1.0)
    result = x + y
    print(f"Result is: {result}")
    return result

@register_task("heavy_computation")
def heavy_computation(duration=5):
    print(f"Starting heavy computation for {duration} seconds...")
    for i in range(1, duration + 1):
        time.sleep(1.0)
        percent = int((i / duration) * 100)
        print(f"Processing... {percent}% complete")
    print("Heavy computation finished successfully.")
    return f"Completed in {duration}s"

@register_task("fetch_data_api")
def fetch_data_api(url):
    print(f"Connecting to API endpoint: {url}...")
    time.sleep(1.5)
    print("Sending request headers...")
    time.sleep(1.0)
    print("Response received: 200 OK")
    data = {"status": "success", "data": [random.randint(1, 100) for _ in range(5)]}
    print(f"Data payload: {data}")
    return data

@register_task("flaky_task")
def flaky_task(fail_rate=0.7):
    print(f"Executing flaky task with fail rate: {fail_rate}...")
    time.sleep(1.0)
    roll = random.random()
    print(f"Rolled: {roll:.2f}")
    if roll < fail_rate:
        print("CRITICAL: Internal Server Error occurred!")
        raise RuntimeError("Simulated transient network timeout.")
    print("Task succeeded against the odds!")
    return "Succeeded"
