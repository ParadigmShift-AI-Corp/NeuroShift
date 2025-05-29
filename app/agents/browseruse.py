import asyncio
import os
import base64
from datetime import datetime
import zipfile
import tempfile
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from browser_use import Agent
from browser_use import BrowserSession
import argparse
from pydantic import SecretStr

# Add proper Google Cloud Storage import
try:
    from google.cloud import storage, firestore
except ImportError:
    print("Google Cloud Storage library not installed. Installing now...")
    import subprocess
    subprocess.check_call(["pip", "install", "google-cloud-storage"])
    subprocess.check_call(["pip", "install", "firestore"])
    from google.cloud import storage
    from google.cloud import firestore

# Load environment variables
load_dotenv()

def zip_and_upload_to_gcs(files_to_zip, result_data, bucket_name, destination_blob_name):
    """
    Zips files and result data and uploads the resulting archive to a Google Cloud Storage bucket.
    
    Args:
        files_to_zip (list): List of file paths to be zipped
        result_data (str/dict): Result data to include in the zip
        bucket_name (str): Name of the GCS bucket
        destination_blob_name (str): Name for the zip file in the bucket
        
    Returns:
        str: Public URL of the uploaded zip file
    """
    # Create a temporary file for the zip
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        temp_zip_path = temp_zip.name
    
    # Create a temporary file for the result data
    temp_result_path = tempfile.mktemp(suffix='.json')
    # Write result data to a JSON file in text mode
    with open(temp_result_path, 'w', encoding='utf-8') as temp_result:
        if isinstance(result_data, str):
            temp_result.write(result_data)
        else:
            json.dump(result_data, temp_result, indent=2, default=str)
    
    # Create the zip file
    with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add screenshot files to the zip
        for file_path in files_to_zip:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Add file to the zip (using just the filename, not the full path)
            filename = os.path.basename(file_path)
            zip_file.write(file_path, f"{file_path}/{filename}")
        
        # Add result data to the zip
        zip_file.write(temp_result_path, "result.json")
    
    try:
        # Initialize GCS client
        storage_client = storage.Client()
        
        # Get bucket
        bucket = storage_client.bucket(bucket_name)
        
        # Create blob (object) in the bucket
        blob = bucket.blob(destination_blob_name)
        
        # Upload the zip file
        blob.upload_from_filename(temp_zip_path)
        
        # Get the public URL
        url = f"gs://{bucket_name}/{destination_blob_name}"
        
        print(f"Zip file uploaded to {url}")
        os.rmdir(temp_zip_path)
        os.rmdir(files_to_zip)
        return url
        
    finally:
        # Clean up the temporary files
        if os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
        if os.path.exists(temp_result_path):
            os.unlink(temp_result_path)

def generate_screenshot_files(result_json: dict, taskId: str, model: str) -> list[str]:
    os.makedirs(taskId, exist_ok=True)
    screenshot_files = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for index, entry in enumerate(result_json.get("history", [])):
        state = entry.get("state", {})
        screenshot_b64 = state.get("screenshot")

        if screenshot_b64:
            try:
                # Decode the base64 image data
                image_data = base64.b64decode(screenshot_b64)

                # Define the filename based on the timestamp and index
                filename = os.path.join(taskId, f"screenshot_{timestamp}_{index+1}.png")

                # Save the decoded image to a file
                with open(filename, "wb") as f:
                    f.write(image_data)

                # Update the JSON entry with the file path
                result_json["history"][index]["state"]["screenshot"] = filename
                print(f"Saved screenshot {index+1} as {filename}")
                screenshot_files.append(filename)

            except Exception as e:
                print(f"Error processing screenshot {index+1}: {e}")
                # Ensure the screenshot field is cleared if saving fails
                result_json["history"][index]["state"]["screenshot"] = None
        else:
            # Explicitly mark as no screenshot if not present
            result_json["history"][index]["state"]["screenshot"] = None
    
    return screenshot_files


async def BrowserAgent(tasks: list[dict[str, str]], bucket_name: str, jobId: str, model: str, userid:str):
    # Create an Agent to perform the browser task
    all_results = []
    db = firestore.Client(database=os.getenv('FIRESTORE_DB', ''))
    browser = BrowserSession(
        headless=True, # type: ignore
        viewport={'width': 964, 'height': 647}, # type: ignore
        user_data_dir='~/.config/browseruse/profiles/default', # type: ignore
    )
    screenshot_files = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"{userid}/{jobId}_result_{timestamp}.zip"
    if browser is None:
        return
    try:
        for i, task in enumerate(tasks):
            agent = Agent(
                browser_session=browser,
                task=task["task"],
                llm=getLLM(model),
                use_vision=False
            )
    
            # Run the agent to get the result
            result = await agent.run()
            result_json = json.loads(result.model_dump_json())
            task["model"] = model
            result_json["jobId"], result_json["task"] = jobId, task
    
            # List to store paths of saved screenshots
            screenshot_files += generate_screenshot_files(result_json, task["taskId"], model='gpt-4o')
            all_results.append(result_json)
            
            # Generate timestamp for the zip file name
        
        try:
            doc_ref = db.collection("job_results").document(jobId)
            doc_ref.set({"results": all_results, "timestamp": timestamp})
            print(f"Results saved to Firestore under document: {jobId}")
        except Exception as e:
            print(f"Error saving to Firestore: {e}")
            
        # Upload screenshots and result to Google Cloud Storage
        try:
            upload_url = zip_and_upload_to_gcs(
                files_to_zip=screenshot_files,
                result_data=all_results,
                bucket_name=bucket_name,
                destination_blob_name=zip_name
            )
            print(f"Upload successful. Files available at: {upload_url}")
        except Exception as e:
            print(f"Error uploading to Google Cloud Storage: {e}")
    except Exception as e:
        print(f"Error uploading to Google Cloud Storage: {e}")

def getLLM(model: str):
    match str(model):
        case 'gemini-2.0-flash':
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                api_key=SecretStr(os.getenv("GOOGLE_API_KEY", ''))
                # other params...
            )
        case 'gemini-2.5-pro':
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                api_key=SecretStr(os.getenv("GOOGLE_API_KEY", ''))
                # other params...
            )
        case 'gpt-4o':
            llm = ChatOpenAI(model='gpt-4o', api_key=SecretStr(openai_api_key_value))
        case 'gpt-o1':
            llm = ChatOpenAI(model='gpt-o1', api_key=SecretStr(openai_api_key_value))
        case 'gpt-o3':
            llm = ChatOpenAI(model='gpt-o3', api_key=SecretStr(openai_api_key_value))
        case 'claude-3.7':
            llm = ChatAnthropic(
                model_name="claude-3.7",
                api_key=SecretStr(os.getenv("ANTHROPIC_API_KEY", "")),
                timeout=None,
                stop=None
            )
        case 'claude-4':
            llm = ChatAnthropic(
                model_name="claude-4",
                api_key=SecretStr(os.getenv("ANTHROPIC_API_KEY", "")),
                timeout=None,
                stop=None
            )
        case _:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                api_key=SecretStr(os.getenv("GOOGLE_API_KEY", ''))
                # other params...
            )
    return llm                

if __name__ == "__main__":
    # Replace with your actual bucket name
    # Initialize LLM
    MODEL="gpt-4o"
    OPENAI_API_KEY = "OPENAI_API_KEY"
    openai_api_key_value = os.getenv(OPENAI_API_KEY, '')
    BUCKET_NAME = os.getenv("BUCKET_NAME", '')
    # llm = ChatOpenAI(model=MODEL, api_key=SecretStr(openai_api_key_value))
    parser = argparse.ArgumentParser(description="Run BrowserAgent with given parameters.")
    parser.add_argument("--jobId", required=True, help="Unique job ID")
    parser.add_argument("--tasks", required=True, help="Tasks in JSON format (e.g., '[{\"taskId\": \"1\", \"task\": \"goto netflix.com\"}]')")
    parser.add_argument("--user", required=True, help="unique user id")
    parser.add_argument("--model", type=str, required=False, help="Model used to run the agent to successful execution")

    args = parser.parse_args()        

    # Parse tasks from JSON string
    try:
        tasks = json.loads(args.tasks)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format for tasks.")
        exit(1)
    
    # Run the browser agent
    """asyncio.run(BrowserAgent(
        tasks=[{"taskId": "1", "task": "goto netflix.com"}, {"taskId": "2","task": "goto google.com"}],
        bucket_name=BUCKET_NAME,
        jobId="Test_Job",
        model="gpt-4o",
        userid="Test User"
    ))"""
    # print(args.tasks)

    asyncio.run(BrowserAgent(
        tasks=tasks,
        bucket_name=BUCKET_NAME,
        jobId=args.jobId,
        model=MODEL,
        userid=args.user
    ))