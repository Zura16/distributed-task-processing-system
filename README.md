# Antigravity Flow: Distributed Task Processing System

Antigravity Flow is a lightweight, custom-built distributed task scheduling and execution system (similar to a mini-Airflow + Celery) written in Python and React. 

Instead of wrapping standard task queues, this project implements a custom Redis-backed messaging queue, concurrency-capable workers, scheduled task state machines, and a dynamic telemetry dashboard from scratch to demonstrate low-level systems engineering.

---

## Key Features

- **Custom Redis Broker**: Uses Redis Lists for blocking task pop (`BLPOP`), Sorted Sets (`ZSET`) for delayed scheduled execution timers, and Hashes for task state metadata.
- **Concurrency-Capable Workers**: Multiple worker daemons process tasks in parallel via a thread-safe `ThreadPoolExecutor`.
- **Thread-Isolated Log Interception**: Uses a custom stdout/stderr redirector coupled with Python's `threading.local` context to stream task prints and exception tracebacks directly to Redis logs without inter-thread log pollution.
- **Exponential Backoff Retries**: Failed tasks automatically reschedule themselves with an exponential delay curve:
  $$\text{Delay} = \text{retry\_delay} \times 2^{\text{attempts}}$$
- **Atomic Scheduling**: Uses Redis transactions and atomic removal (`ZREM`) to prevent race conditions when shifting delayed tasks to the active queue.
- **Interactive Dashboard**: A premium dark-mode dashboard built in React (Vite) showing real-time cluster metrics, active workers, task submission controls, and a live-streaming log terminal.

---

## Directory Structure

```
.
├── docker-compose.yml       # Orchestrates Redis, Backend, Workers, and Dashboard
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py              # FastAPI Web API
│   ├── worker.py            # Worker daemon with thread pool executor
│   ├── scheduler.py         # Scheduler daemon for delayed tasks
│   ├── core/
│   │   ├── config.py        # Redis & system settings
│   │   ├── queue.py         # Custom TaskQueue client wrapper
│   │   └── tasks.py         # Task registry & task definitions
│   └── tests/
│       ├── test_queue.py    # Queue lifecycle & scheduling unit tests
│       └── test_worker.py   # Worker execution & retry flow unit tests
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx          # Dashboard application
        ├── index.css        # Premium custom CSS styling
        └── App.css          # Blank styling override
```

---

## Getting Started

### Prerequisites
- Docker & Docker Compose OR
- Python 3.11+ & Node.js 20+ (with local Redis server running on port `6379`)

### Running with Docker (Recommended)
Launch the entire cluster (Redis, FastAPI, Scheduler, 2 Workers, and the React Frontend) with one command:
```bash
docker compose up --build
```
Once started:
- **React Dashboard**: `http://localhost:5173`
- **FastAPI API Docs**: `http://localhost:8000/docs`

### Running Locally (Alternative)
1. **Start Redis**:
   ```bash
   brew services start redis  # On macOS
   ```
2. **Setup Backend**:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Run services (in separate terminals)
   python main.py       # API Server
   python worker.py     # Worker Daemon
   python scheduler.py  # Scheduler Daemon
   ```
3. **Setup Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

---

## Verification & Testing

Verify queue state changes, thread-local log capture, and backoff retries using pytest:
```bash
# Run from repository root
PYTHONPATH=. pytest backend/tests/
```

Results:
```bash
backend/tests/test_queue.py ....                                         [ 66%]
backend/tests/test_worker.py ..                                          [100%]
========================= 6 passed, 1 warning in 5.40s =========================
```
