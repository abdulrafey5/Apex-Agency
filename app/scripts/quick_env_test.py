#!/usr/bin/env python3
"""Quick test to verify .env loading in db_service."""

import os
import sys
from pathlib import Path

# Add app to path
script_dir = Path(__file__).parent
app_dir = script_dir.parent
sys.path.insert(0, str(app_dir))

# Load .env first
from dotenv import load_dotenv
env_path = app_dir / ".env"
print(f"1. Looking for .env at: {env_path}")
print(f"   Exists: {env_path.exists()}")

if env_path.exists():
    load_dotenv(env_path)
    print(f"2. After load_dotenv():")
    print(f"   DB_HOST={os.getenv('DB_HOST')}")
    print(f"   DB_USER={os.getenv('DB_USER')}")
    print(f"   DB_PASSWORD={'***' if os.getenv('DB_PASSWORD') else 'None'}")

# Now import db_service (this will also try to load .env)
print("\n3. Importing db_service...")
from services.db_service import DatabaseService

print("\n4. Creating DatabaseService instance...")
db = DatabaseService()
print(f"   db.db_host = {db.db_host}")
print(f"   db.db_user = {db.db_user}")

if db.db_host == "localhost":
    print("\n❌ ERROR: Still using localhost! .env not loaded properly.")
    sys.exit(1)
else:
    print(f"\n✅ SUCCESS: Using DB_HOST={db.db_host}")

