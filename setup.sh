#!/bin/bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Virtual environment setup complete!"
cp service/fastapi.service /etc/systemd/system/
echo "Service file copied to /etc/systemd/system/"
echo "Starting the FastAPI service..."
systemctl daemon-reload
systemctl start fastapi
systemctl enable fastapi
