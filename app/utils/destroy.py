import subprocess
import time, os
from utils.clean_log import clean_log

def destroy_terraform_command(userid: str, deployments: dict):
    """
    Destroy the Terraform resources for the given user ID.
    This function runs the Terraform destroy command and streams the output.
    """
    try:
        base_dir = os.path.join(os.getcwd(), "terraform")
        
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

        if process.stdout is not None:
            for line in iter(process.stdout.readline, ''):
                # Save logs to a global dictionary
                deployments[userid].append(clean_log(line))
                time.sleep(0.1)
        else:
            deployments[userid].append("Error: process.stdout is None\n")

        subprocess.run(f"terraform workspace select default", shell=True, cwd=base_dir, capture_output=True, text=True)
        subprocess.run(f"terraform workspace delete {userid}", shell=True, cwd=base_dir, capture_output=True, text=True)

        if process.stdout is not None:
            process.stdout.close()
        process.wait()

        if process.returncode != 0:
            deployments[userid].append(f"Error: Command failed with exit code {process.returncode}\n")
    except Exception as e:
        print(f"Error during destroy: {e}")
        deployments[userid].append(f"Exception: {str(e)}\n")