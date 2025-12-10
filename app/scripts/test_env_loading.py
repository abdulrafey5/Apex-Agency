#!/usr/bin/env python3
"""
Quick test to verify .env loading works.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(script_dir)
sys.path.insert(0, app_dir)

# Load .env
try:
    from dotenv import load_dotenv
    print("✅ python-dotenv is installed")
except ImportError:
    print("❌ python-dotenv is NOT installed!")
    print("   Run: pip install python-dotenv")
    sys.exit(1)

# Load .env file
env_path = Path(app_dir) / ".env"
print(f"📁 Looking for .env at: {env_path}")
print(f"   Exists: {env_path.exists()}")

if env_path.exists():
    load_dotenv(env_path)
    print("✅ load_dotenv() called successfully")
else:
    print("❌ .env file not found!")
    sys.exit(1)

# Check values
print("\n📊 Environment variables:")
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT")

print(f"   DB_HOST: {db_host}")
print(f"   DB_PORT: {db_port}")
print(f"   DB_NAME: {db_name}")
print(f"   DB_USER: {db_user}")
print(f"   DB_PASSWORD: {'***' if db_password else 'None'}")

if db_host and db_user and db_password:
    print("\n✅ All database credentials loaded successfully!")
    sys.exit(0)
else:
    print("\n❌ Missing database credentials!")
    sys.exit(1)

