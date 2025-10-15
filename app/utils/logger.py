import logging
from pathlib import Path


def setup_logging(log_dir: Path):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "app.log"
    handlers = [logging.FileHandler(str(log_file)), logging.StreamHandler()]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=handlers)

