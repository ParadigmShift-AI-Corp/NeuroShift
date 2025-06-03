from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis
import asyncio
import httpx

router = APIRouter()

REDIS_URL = "redis://10.115.18.147:6379/0"  # adjust for your Redis connection

async def event_generator(job_id: str):
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    channel = f"status:{job_id}"

    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10)
            if message:
                data = message["data"]
                print(data)
                yield f"data: {data}\n\n"
            else:
                # Send a comment to keep connection alive (optional)
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.close()

@router.get("/status/{job_id}")
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

async def send_status_webhook(jobId: str, status: str):
    url = "https://paradigm-shift.ai/api/webhook"  # Replace with your endpoint

    data = {
        "type": "job_status",  # Replace with actual type
        "payload": {
            "status": status,
            "id": jobId
        }
    }

    print(data)

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")