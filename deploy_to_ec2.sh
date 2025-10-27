#!/bin/bash
# Deploy to EC2 - Updated for /data/inception path
EC2_IP=13.61.217.12
EC2_USER=ubuntu
EC2_PATH=/data/inception

# Sync code (exclude sensitive files)
rsync -avz --exclude='.env' --exclude='.git' --exclude='__pycache__' app/ $EC2_USER@$EC2_IP:$EC2_PATH/app/
rsync -avz --exclude='.git' storage/ $EC2_USER@$EC2_IP:$EC2_PATH/storage/

# SSH and deploy
ssh $EC2_USER@$EC2_IP << EOF
cd $EC2_PATH
source app/venv/bin/activate  # Use your existing venv
pip install -r requirements.txt  # If you have a requirements.txt
sudo systemctl restart ollama  # Restart Ollama
# Kill any existing app process
pkill -f "python app/main.py"
# Start app in background
nohup python app/main.py > app/logs/app.log 2>&1 &
EOF