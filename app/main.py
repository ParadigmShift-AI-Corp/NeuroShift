from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os
from dotenv import load_dotenv
import redis
from screenshot.generate import router as ScreenshotRouter
from tasks.evaluation import run_browser_task
from kombu.exceptions import OperationalError
from utils.status import router as StatusRouter
from utils.logs import router as LogRouter
import time

load_dotenv()

app = FastAPI()
app.include_router(ScreenshotRouter)
app.include_router(StatusRouter)
app.include_router(LogRouter)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://paradigm-shift.ai", "https://www.paradigm-shift.ai"],  # Adjust to your frontend URL
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint to verify server status."""
    return {"status": "ok", "message": "Server is running and healthy"}


async def event_stream():
    for i in range(1, 11):
        # Simulate data generation with a delay
        yield f"data: Message {i}\n\n"
        await asyncio.sleep(1)

@app.get("/stream")
async def stream():
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/webrun")
async def web(request: Request):
    redis_client = redis.Redis(host='10.115.18.147')
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    job_id = data.get("jobId")
    tasks = data.get("tasks")
    model = data.get("model", "gpt-4o")
    user_id = data.get("userid", "paradigm-shift-job-results")

    if not job_id:
        raise HTTPException(status_code=400, detail="Missing jobId")
    if not tasks:
        raise HTTPException(status_code=400, detail="Missing tasks")
    print('starting to run')

    # Trigger background task with Celery
    time.sleep(5)
    redis_client.set(f"status:{job_id}", "QUEUED")
    redis_client.publish(f"status:{job_id}", "QUEUED")
    print(redis_client.get(f"status:{job_id}"))
    redis_client.close()
    try:
        run_browser_task.delay(job_id, tasks, model, user_id) # type: ignore untyped
        print(f'Job Started for {job_id}')
        return {"message": f"Job {job_id} started for user {user_id}"}
    except OperationalError as e:
        print(f"[ERROR] celery connection error: {str(e)}")
        return {'message': f"[ERROR] celery connection error: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', 8000)), ssl_keyfile="/etc/letsencrypt/live/infra.paradigm-shift.ai/privkey.pem", ssl_certfile="/etc/letsencrypt/live/infra.paradigm-shift.ai/fullchain.pem")