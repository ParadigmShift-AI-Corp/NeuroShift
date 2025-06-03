from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis
import asyncio, io

router = APIRouter()

REDIS_URL = "redis://10.115.18.147:6379/0"  # adjust for your Redis connection

async def event_generator(job_id: str):
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    channel = f"log:{job_id}"

    try:
        # Step 1: Replay rpush history
        log_history = await redis.lrange(channel, 0, -1) # type: ignore
        for entry in log_history:
            yield f"data: {entry}\n\n"

        # Step 2: Subscribe to real-time logs
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
            if message:
                data = message["data"]
                print(data)
                yield f"data: {data}\n\n"
            else:
                # Keep the connection alive
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()

@router.get("/download-logs/{job_id}")
async def download_logs(job_id: str):
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    channel = f"log:{job_id}"

    # Fetch logs from Redis list
    log_entries = await redis.lrange(channel, 0, -1) # type: ignore

    if not log_entries:
        raise HTTPException(status_code=404, detail="No logs found for this job ID")

    # Create in-memory .log content
    file_content = "\n".join(log_entries)
    file_stream = io.StringIO(file_content)

    filename = f"{job_id}.log"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }

    return StreamingResponse(file_stream, media_type="text/plain", headers=headers)

@router.get("/logs/{job_id}")
async def status_stream(request: Request, job_id: str):
    # StreamingResponse for SSE
    generator = event_generator(job_id)

    async def event_streamer():
        async for event in generator:
            # If client disconnects, exit
            if await request.is_disconnected():
                break
            yield event

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Prevents some proxies from buffering SSE
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(event_streamer(), headers=headers)
