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

chmod +x /home/ubuntu/playwright_script.py

# Run the script
echo "Running Playwright script at $(date)..."
source /home/ubuntu/playwright_venv/bin/activate
cd /home/ubuntu
python /home/ubuntu/playwright_script.py

echo "Startup script completed at $(date)"