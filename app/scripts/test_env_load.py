#!/usr/bin/env python3
"""Simple test to verify .env loading works."""

import os
import sys
from pathlib import Path

# Get app directory
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(script_dir)

print(f"Script dir: {script_dir}")
print(f"App dir: {app_dir}")
print(f"CWD: {os.getcwd()}")

# Load .env
env_path = Path(app_dir) / ".env"
print(f"\nLooking for .env at: {env_path}")
print(f"Exists: {env_path.exists()}")

if env_path.exists():
    print("\nLoading .env file...")
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                os.environ[key] = value
                if key.startswith('DB_'):
                    print(f"  {key} = {value}")

    print(f"\nAfter loading:")
    print(f"  DB_HOST = {os.getenv('DB_HOST', 'NOT_SET')}")
    print(f"  DB_USER = {os.getenv('DB_USER', 'NOT_SET')}")
    print(f"  DB_PASSWORD = {'SET' if os.getenv('DB_PASSWORD') else 'NOT_SET'}")
else:
    print(f"\nERROR: .env file not found!")

