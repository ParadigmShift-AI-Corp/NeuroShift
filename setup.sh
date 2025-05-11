#!/bin/bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Virtual environment setup complete!"
sudo cp service/fastapi.service /etc/systemd/system/
echo "Service file copied to /etc/systemd/system/"
echo "Starting the FastAPI service..."
systemctl daemon-reload
systemctl enable fastapi.service
systemctl start fastapi.service
systemctl status fastapi.service