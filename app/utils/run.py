import subprocess
import time, os
from utils.clean_log import clean_log


def job(userid: str, deployments: dict):
    """
    Run the Terraform command for the given user ID.
    This function runs the Terraform apply command and streams the output.
    """
    try:
        base_dir = os.path.join(os.getcwd(), "terraform")
        print(base_dir)
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

        print("Terraform apply command started.")
        # Stream logs
        for line in iter(process.stdout.readline, ''):
            clean_line = clean_log(line)
            print(line)
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