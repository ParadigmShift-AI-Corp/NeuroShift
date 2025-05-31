import subprocess
import redis
from redis.exceptions import ConnectionError
from messages.celery_worker import celery_app
from utils.clean_log import clean_log
import time

# Redis connection
redis_client = redis.Redis(host='10.115.18.147')

@celery_app.task(bind=True, name="tasks.evaluation.run_browser_task")
def run_browser_task(self, job_id, tasks, model="gpt-4o", user_id="paradigm-shift-job-results"):

    def log_message(channel, message):
        redis_client.publish(channel, message)
        redis_client.rpush(channel, message)

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
    time.sleep(10)

    redis_client.set(f"status:{job_id}", "STARTED")
    log_message(log_channel, "[INFO] Task started")
    print(redis_client.get(f"status:{job_id}"))

    cmd = [
        "xvfb-run", "python", "agents/browseruse.py",
        "--jobId", job_id,
        "--tasks", tasks,
        "--user", user_id,
        "--model", model
    ]

    try:
        redis_client.set(f"status:{job_id}", "IN_PROGRESS")
        redis_client.publish(status_channel, "IN_PROGRESS")

        # You should probably run the actual subprocess here.
        # subprocess.run(cmd, check=True)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

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
            redis_client.set(f"status:{job_id}", "COMPLETED")
            redis_client.publish(status_channel, "COMPLETED")
            log_message(log_channel, "[DONE]")
        else:
            error_status = f"[ERROR] Exit code {process.returncode}"
            redis_client.set(f"status:{job_id}", "FAILED")
            redis_client.publish(status_channel, "FAILED")
            log_message(log_channel, error_status)

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_message = f"[EXCEPTION] {str(e)}"
        redis_client.set(f"status:{job_id}", "FAILED")
        redis_client.publish(status_channel, "FAILED")
        log_message(log_channel, error_message)
        return {"status": "failed", "error": str(e)}