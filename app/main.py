import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import time
import threading
import asyncio, os
from dotenv import load_dotenv

load_dotenv()
from fastapi.responses import StreamingResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://paradigm-shift.ai"],  # Adjust to your frontend URL
    allow_methods=["GET"],
    allow_headers=["*"],
)

deployments = {}

def clean_log(log: str) -> str:
    """
    Remove ANSI escape codes and unnecessary whitespace from the log.
    """
    # Regex to match ANSI escape codes
    ansi_escape = re.compile(r'(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~])')
    # Remove ANSI codes and strip extra whitespace
    clean_line = ansi_escape.sub('', log).strip()
    return clean_line

def destroy_terraform_command(userid: str):
    try:
        base_dir = "../terraform"
        
        # Initialize and select the workspace
        subprocess.run(f"terraform workspace select {userid}", shell=True, cwd=base_dir, capture_output=True, text=True)

        # Run Terraform destroy and stream the output
        process = subprocess.Popen(
            "terraform destroy -auto-approve",
            shell=True,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in iter(process.stdout.readline, ''):
            # Save logs to a global dictionary
            print(clean_log(line))
            deployments[userid].append(clean_log(line))
            time.sleep(0.1)

        subprocess.run(f"terraform workspace select default", shell=True, cwd=base_dir, capture_output=True, text=True)
        subprocess.run(f"terraform workspace delete {userid}", shell=True, cwd=base_dir, capture_output=True, text=True)

        process.stdout.close()
        process.wait()

        if process.returncode != 0:
            deployments[userid].append(f"Error: Command failed with exit code {process.returncode}\n")
    except Exception as e:
        print(f"Error during destroy: {e}")
        deployments[userid].append(f"Exception: {str(e)}\n")

def run_terraform_command(userid: str):
    try:
        base_dir = "../terraform"

        # Initialize Terraform and select workspace
        subprocess.run(f"terraform workspace new {userid}", shell=True, cwd=base_dir, capture_output=True, text=True)
        subprocess.run(f"terraform workspace select {userid}", shell=True, cwd=base_dir, capture_output=True, text=True)

        # Run the Terraform command
        process = subprocess.Popen(
            "terraform apply -auto-approve",
            shell=True,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Stream logs
        for line in iter(process.stdout.readline, ''):
            clean_line = clean_log(line)
            if clean_line:  # Only log non-empty lines
                deployments[userid].append(clean_line)
            time.sleep(0.1)

        process.stdout.close()
        process.wait()

        # Append success message and signal completion
        if process.returncode == 0:
            deployments[userid].append("Successfully deployed resources.\n")
            deployments[userid].append("[DONE]")
        else:
            deployments[userid].append(f"Error: Command failed with exit code {process.returncode}\n")
            deployments[userid].append("[DONE]")

    except Exception as e:
        print(f"Error during deployment: {e}")
        deployments[userid].append(f"Exception: {str(e)}\n")
        deployments[userid].append("[DONE]")

@app.post("/deploy")
async def deploy(request: Request):
    data = await request.json()
    userid = data.get("userid")
    if not userid:
        raise HTTPException(status_code=400, detail="Missing userid")

    # Start the deployment in a separate thread
    deployments[userid] = []
    threading.Thread(target=run_terraform_command, args=(userid,)).start()
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
    threading.Thread(target=destroy_terraform_command, args=(userid,)).start()
    
    return {"message": "Destroy started"}

@app.post("/show")
async def show(request: Request):
    data = await request.json()
    userid = data.get("userid")
    if not userid:
        raise HTTPException(status_code=400, detail="Missing userid")
    
    output = run_terraform_command("terraform show", userid)
    return {"status": "show", "output": output}

@app.get("/health")
async def health_check():
    """Health check endpoint to verify server status."""
    return {"status": "ok", "message": "Server is running and healthy"}


async def event_stream():
    for i in range(1, 11):
        # Simulate data generation with a delay
        yield f"data: Message {i}\n\n"
        time.sleep(1)

@app.get("/stream")
async def stream():
    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv('HOST'), port=int(os.getenv('PORT')))