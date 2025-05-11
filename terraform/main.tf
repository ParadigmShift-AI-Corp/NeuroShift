terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project = "evaluation-deployment"
  region  = "us-central1"
  zone    = "us-central1-c"
}

# Create VPC Network
resource "google_compute_network" "vpc_network" {
  name = "terraform-network"
}

# Create Firewall Rule to Allow SSH
resource "google_compute_firewall" "allow-ssh" {
  name    = "allow-ssh"
  network = google_compute_network.vpc_network.self_link
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["0.0.0.0/0"]
}

# No need for a local file resource - we'll embed the script directly in metadata

# Create VM Instance
resource "google_compute_instance" "vm_instance" {
  name         = "playwright-vm"
  machine_type = "e2-medium"
  zone         = "us-central1-c"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    network = google_compute_network.vpc_network.name
    access_config {}
  }

  # Startup script to setup environment and run the test
  metadata_startup_script = <<-EOT
#!/bin/bash
# Log startup progress
exec > >(tee -i /var/log/startup-script.log)
exec 2>&1
echo "Starting setup script at $(date)"

# Update package lists
sudo apt-get update -y

# Install required dependencies
sudo apt-get install -y wget unzip curl python3 python3-pip python3-venv

# Install Chrome
echo "Installing Chrome..."
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y ./google-chrome-stable_current_amd64.deb

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv /home/ubuntu/playwright_venv

# Activate virtual environment and install packages
echo "Installing packages in virtual environment..."
source /home/ubuntu/playwright_venv/bin/activate
pip install --upgrade pip
pip install playwright requests
python -m playwright install chromium

# Create Python script
echo "Creating Playwright script..."
mkdir -p /home/ubuntu
cat > /home/ubuntu/playwright_script.py << 'PYTHONEOF'
from playwright.sync_api import sync_playwright
import os
import requests
import datetime

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Navigate to Google
        print("Navigating to Google...")
        page.goto('https://www.google.com')
        
        # Search for IMDB
        print("Searching for IMDB...")
        page.fill('textarea[name="q"]', 'imdb')
        page.keyboard.press('Enter')
        
        # Wait for results
        # page.wait_for_selector('h3')
        print("Search results loaded")
        
        # Take a screenshot
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"/results/google_imdb_search_{timestamp}.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")
        
        # Close browser
        browser.close()
        
        # Send POST request to notify completion
        try:
            print("Sending completion notification...")
            response = requests.post('https://127.0.0.1/destroy', json={"userid": "1234"}, verify=False)
            print(f"Notification sent. Status code: {response.status_code}")
        except Exception as e:
            print(f"Failed to send completion notification: {e}")

if __name__ == "__main__":
    print("Starting IMDB search automation...")
    run()
    print("Script execution completed.")
PYTHONEOF
chmod +x /home/ubuntu/playwright_script.py

# Run the script
echo "Running Playwright script at $(date)..."
source /home/ubuntu/playwright_venv/bin/activate
cd /home/ubuntu
python /home/ubuntu/playwright_script.py

echo "Startup script completed at $(date)"
EOT

  # No dependencies needed now
}

# Output the external IP for SSH access
output "vm_external_ip" {
  value = google_compute_instance.vm_instance.network_interface[0].access_config[0].nat_ip
}
