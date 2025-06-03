import subprocess
import redis
from redis.exceptions import ConnectionError
from messages.celery_worker import celery_app
from utils.clean_log import clean_log
import time
import os
import random
import asyncio
from utils.status import send_status_webhook

# Redis connection
redis_client = redis.Redis(host='10.115.18.147')

@celery_app.task(bind=True, name="tasks.evaluation.run_browser_task")
def run_browser_task(self, job_id, tasks, model="gpt-4o", user_id="paradigm-shift-job-results"):

    def log_message(channel, message):
        redis_client.publish(channel, message)
        redis_client.rpush(channel, message)

    def get_free_display():
        for _ in range(50):  # Try 50 random times
            display = random.randint(1000, 9999)
            if not os.path.exists(f"/tmp/.X{display}-lock"):
                return display
        raise RuntimeError("Could not find free X display")

    log_channel = f"log:{job_id}"
    status_channel = f"status:{job_id}"

    try:
        if redis_client.ping():
            log_message(log_channel, "[INFO] Successfully connected to Redis")
        else:
            log_message(log_channel, "[ERROR] Redis ping failed")
            return {"status": "redis-ping-failed"}
    except ConnectionError as e:
        log_message(log_channel, f"[ERROR] Redis connection error: {str(e)}")
        return {"status": "redis-connection-error"}

    time.sleep(3)  # Optional startup delay
    redis_client.set(f"status:{job_id}", "STARTED")
    log_message(log_channel, "[INFO] Task started")
    asyncio.run(send_status_webhook(job_id, "STARTED"))

    # === Xvfb Setup ===
    display_num = get_free_display()
    display_str = f":{display_num}"
    log_message(log_channel, f"[INFO] Launching Xvfb on display {display_str}")

    xvfb_proc = None
    try:
        xvfb_proc = subprocess.Popen(
            ["Xvfb", display_str, "-screen", "0", "1024x768x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(1)  # Wait a moment for Xvfb to initialize

        # Set DISPLAY for subprocess
        env = os.environ.copy()
        env["DISPLAY"] = display_str

        # === Actual Task ===
        cmd = [
            "python", "agents/browseruse.py",
            "--jobId", job_id,
            "--tasks", tasks,
            "--user", user_id,
            "--model", model
        ]

        redis_client.set(f"status:{job_id}", "IN_PROGRESS")
        redis_client.publish(status_channel, "IN_PROGRESS")
        asyncio.run(send_status_webhook(job_id, "IN_PROGRESS"))

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )

        # Read subprocess output
        if process.stdout:
            for line in process.stdout:
                cleaned = clean_log(line)
                log_message(log_channel, cleaned)

        if process.stderr:
            for err in process.stderr:
                err_clean = f"[stderr] {clean_log(err)}"
                log_message(log_channel, err_clean)

        process.wait()

        if process.returncode == 0:
            redis_client.set(f"status:{job_id}", "POST_PROCESS")
            redis_client.publish(status_channel, "POST_PROCESS")
            log_message(log_channel, "[DONE]")
            asyncio.run(send_status_webhook(job_id, "POST_PROCESS"))
        else:
            error_status = f"[ERROR] Exit code {process.returncode}"
            redis_client.set(f"status:{job_id}", "FAILED")
            redis_client.publish(status_channel, "FAILED")
            log_message(log_channel, error_status)
            asyncio.run(send_status_webhook(job_id, "FAILED"))

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_message = f"[EXCEPTION] {str(e)}"
        redis_client.set(f"status:{job_id}", "FAILED")
        redis_client.publish(status_channel, "FAILED")
        asyncio.run(send_status_webhook(job_id, "FAILED"))
        log_message(log_channel, error_message)
        return {"status": "failed", "error": str(e)}

    finally:
        try:
            if xvfb_proc:
                xvfb_proc.terminate()
                xvfb_proc.wait()
                log_message(log_channel, "[INFO] Xvfb terminated")
        except Exception as cleanup_error:
            log_message(log_channel, f"[WARN] Failed to clean up Xvfb: {cleanup_error}")
