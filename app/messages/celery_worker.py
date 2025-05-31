from celery import Celery
import os


# Replace with your GCP Redis IP and port
REDIS_URL = os.getenv("REDIS_IP", "")

celery_app = Celery("neurosim", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
)

import tasks.evaluation