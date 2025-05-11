from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os, threading
from utils.destroy import destroy_terraform_command
from utils.run import job
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://paradigm-shift.ai"],  # Adjust to your frontend URL
    allow_methods=["GET"],
    allow_headers=["*"],
)

deployments = {}

@app.post("/deploy")
async def deploy(request: Request):
    data = await request.json()
    userid = data.get("userid")
    if not userid:
        raise HTTPException(status_code=400, detail="Missing userid")

    # Start the deployment in a separate thread
    deployments[userid] = []
    threading.Thread(target=job, args=(userid, deployments,)).start()
    return {"message": "Deployment started"}

@app.get("/logs/{userid}")
async def stream_logs(userid: str):
    async def log_generator():
        while True:
            if userid in deployments and deployments[userid]:
                while deployments[userid]:
                    log = deployments[userid].pop(0)
                    yield f"data: {log}\n\n"
                # Stop sending logs when done
                if log == "[DONE]":
                    break
            await asyncio.sleep(0.1)

    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.post("/destroy")
async def destroy(request: Request):
    data = await request.json()
    userid = data.get("userid")
    if not userid:
        raise HTTPException(status_code=400, detail="Missing userid")

    deployments[userid] = []
    threading.Thread(target=destroy_terraform_command, args=(userid, deployments,)).start()
    
    return {"message": "Destroy started"}

@app.post("/show")
async def show(request: Request):
    data = await request.json()
    userid = data.get("userid")
    if not userid:
        raise HTTPException(status_code=400, detail="Missing userid")
    
    output = job("terraform show", userid)
    return {"status": "show", "output": output}

@app.get("/health")
async def health_check():
    """Health check endpoint to verify server status."""
    return {"status": "ok", "message": "Server is running and healthy"}


async def event_stream():
    for i in range(1, 11):
        # Simulate data generation with a delay
        yield f"data: Message {i}\n\n"
        asyncio.sleep(1)

@app.get("/stream")
async def stream():
    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv('HOST'), port=int(os.getenv('PORT')), ssl_keyfile="/home/ashwin/key.pem", ssl_certfile="/home/ashwin/cert.pem")