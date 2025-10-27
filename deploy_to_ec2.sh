#!/bin/bash
# Deploy to EC2
EC2_IP=13.61.217.12  # Update if needed
rsync -avz --exclude='.env' app/ ubuntu@$EC2_IP:/home/ubuntu/inception/app/
ssh ubuntu@$EC2_IP "cd /home/ubuntu/inception && pip install -r requirements.txt && sudo systemctl restart ollama && python app/main.py"