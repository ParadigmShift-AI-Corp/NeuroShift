#!/bin/bash

# Update packages
sudo apt-get update -y

# Install necessary packages
sudo apt-get install -y wget curl git unzip python3 python3-pip

# Install Chrome
wget -q -O google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y ./google-chrome.deb
rm google-chrome.deb

# Install Node.js (required for Playwright dependencies)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Playwright
pip3 install playwright
playwright install --with-deps

# Confirm installation
google-chrome --version > /home/ubuntu/chrome_version.txt
python3 -m playwright --version > /home/ubuntu/playwright_version.txt