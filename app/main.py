from asyncio import subprocess
import shutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os, threading
from utils.clean_log import clean_log
from utils.destroy import destroy_terraform_command
from utils.run import job
from dotenv import load_dotenv
from screenshot.generate import TimestampExtractor, VideoFrameExtractor

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://paradigm-shift.ai", "https://www.paradigm-shift.ai"],  # Adjust to your frontend URL
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
            log = None  # Initialize log with a default value
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
        await asyncio.sleep(1)

@app.get("/stream")
async def stream():
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/webrun")
async def web(request: Request):
    data = await request.json()
    jobId = data.get("jobId")
    tasks = data.get("tasks")
    model = data.get("aiModel", "gpt-4o")
    userid = data.get("userid", "paradigm-shift-job-results")

    # Validate inputs
    if not jobId:
        raise HTTPException(status_code=400, detail="Missing jobId")
    if not tasks:
        raise HTTPException(status_code=400, detail="Missing tasks")

    # Prepare command for subprocess
    cmd = [
        "xvfb-run", "python", "app/agents/browseruse.py",
        "--jobId", jobId,
        "--tasks", tasks,
        "--user", userid,
        "--model", model
    ]

    # Initialize logs
    deployments[jobId] = []
    print(cmd)

    async def run_subprocess():
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print('running', process.pid)
        if process.stdout is not None:
            async for line in process.stdout:
                print(clean_log(line.decode().strip()))
                deployments[jobId].append(clean_log(line.decode().strip()))
        await process.wait()
        deployments[jobId].append("[DONE]")

    # Run the subprocess in the background
    asyncio.create_task(run_subprocess())
    return {"message": f"Job {jobId} started for user {userid}"}

@app.post("/generate/screenshots")
async def generateScreenshots(request: Request):
    """
    Main processing function to extract frames from video based on JSONL events.
    
    Args:
        video_file: Path to the video file
        jsonl_file: Path to the JSONL event log file
        output_dir: Directory to save extracted frames
    """
    data = await request.json()
    video_file = data.get("video_file")
    jsonl_file = data.get("jsonl_file")
    output_dir = data.get("output_dir")
    if not video_file or not jsonl_file or not output_dir:
        raise HTTPException(status_code=400, detail="Missing required parameters")
    # Extract timestamps from the JSONL file
    timestamp_extractor = TimestampExtractor()
    timestamps = timestamp_extractor.extract_click_timestamps(jsonl_file)
    

    if not timestamps:
        print("No valid timestamps found in the JSONL file")
        return
        
    # Extract frames at the identified timestamps using context manager
    # to ensure proper resource cleanup
    with VideoFrameExtractor(video_file, output_dir) as frame_extractor:
        frame_extractor.extract_frames(timestamps)
    
    zip_path = f"{output_dir}.zip"
    shutil.make_archive(output_dir, 'zip', output_dir)
    
    # Return the zip file as a response
    return FileResponse(zip_path, media_type='application/zip', filename=f"{os.path.basename(zip_path)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', 8000)), ssl_keyfile="/etc/letsencrypt/live/infra.paradigm-shift.ai/privkey.pem", ssl_certfile="/etc/letsencrypt/live/infra.paradigm-shift.ai/fullchain.pem")