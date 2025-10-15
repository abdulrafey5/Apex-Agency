#!/usr/bin/env python3
import time
import yaml
import logging
from datetime import datetime, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler

# === Paths ===
ROOT = Path("/data/inception")
AGENTS_DIR = ROOT / "storage/instructions/agents"
DMS_DIR = ROOT / "storage/instructions/dms"
MEMORY_FILE = ROOT / "storage/instructions/memory.yaml"
LOG_FILE = ROOT / "app/logs/agentzero.log"

# === Logging with rotation ===
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[handler]
)

# === YAML utilities ===
def load_yaml(path):
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f)

# === Validate agent YAML ===
REQUIRED_KEYS = ["name", "department", "tasks", "schedule"]
def validate_agent(agent):
    for key in REQUIRED_KEYS:
        if key not in agent:
            logging.warning(f"Agent YAML missing required key: {key}")
            return False
    return True

# === Schedule checker ===
def should_run(schedule, last_run):
    """Return True if agent or DM should run now (daily schedule only)."""
    now = datetime.now(timezone.utc)
    if schedule.get("type") == "daily":
        run_hour, run_minute = map(int, schedule.get("time", "10:00").split(":"))
        run_time = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
        # Run if never run today
        if last_run is None or now.date() > last_run.date():
            return now >= run_time
    return False

# === Task executor for Agents ===
def perform_task(agent, memory):
    name = agent.get("name", "Unnamed Agent")
    logging.info(f"🤖 Executing {name} tasks...")
    for task in agent.get("tasks", []):
        if task.get("enabled", True):
            logging.info(f"🧩 Running task: {task['id']} — {task.get('description','No description')}")
            time.sleep(2)  # Simulate task logic; replace with actual API calls
    logging.info(f"✅ Completed {name} cycle.")
    agent.setdefault("memory", {})["last_run"] = datetime.now(timezone.utc).isoformat()

# === Task executor for DMs ===
def perform_dm_tasks(dm, memory):
    name = dm.get("name", "Unnamed DM")
    logging.info(f"👔 Executing DM tasks for {name}...")
    dm_memory = dm.setdefault("memory", {})

    # Iterate through assigned agents
    for agent_file_name in dm.get("agents", []):
        agent_file = AGENTS_DIR / agent_file_name
        if not agent_file.exists():
            logging.warning(f"Agent file {agent_file_name} not found for DM {name}")
            continue

        agent = load_yaml(agent_file)
        if not agent or not validate_agent(agent):
            continue

        # Convert last_run string to datetime
        last_run_str = agent.get("memory", {}).get("last_run")
        last_run = None
        if last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)

        if should_run(agent.get("schedule", {}), last_run):
            perform_task(agent, memory)
            save_yaml(agent_file, agent)

    # Update DM last_run
    dm_memory["last_run"] = datetime.now(timezone.utc).isoformat()
    logging.info(f"✅ DM {name} completed cycle.")

# === Main loop ===
def main():
    logging.info("🚀 Agent Zero runner started.")
    while True:
        try:
            memory = load_yaml(MEMORY_FILE)

            # --- Run standalone agents ---
            for agent_file in AGENTS_DIR.glob("*.yaml"):
                agent = load_yaml(agent_file)
                if not agent or not validate_agent(agent):
                    continue
                last_run_str = agent.get("memory", {}).get("last_run")
                last_run = None
                if last_run_str:
                    last_run = datetime.fromisoformat(last_run_str)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                if should_run(agent.get("schedule", {}), last_run):
                    perform_task(agent, memory)
                    save_yaml(agent_file, agent)
                    logging.info(f"🕓 Updated last_run for {agent_file.name}")

            # --- Run DMs ---
            for dm_file in DMS_DIR.glob("*.yaml"):
                dm = load_yaml(dm_file)
                if not dm:
                    continue
                last_run_str = dm.get("memory", {}).get("last_run")
                last_run = None
                if last_run_str:
                    last_run = datetime.fromisoformat(last_run_str)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                # Default DM schedule to 10:00 daily if missing
                dm_schedule = dm.get("schedule", {"type": "daily", "time": "10:00"})
                if should_run(dm_schedule, last_run):
                    perform_dm_tasks(dm, memory)
                    save_yaml(dm_file, dm)

            # --- Save global memory ---
            save_yaml(MEMORY_FILE, memory)

        except Exception as e:
            logging.exception(f"❌ Error in Agent Zero runner loop: {e}")

        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()

