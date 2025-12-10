# config_loader.py
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

REQUIRED_ENVS = ("TG_API_ID", "TG_API_HASH", "TARGET_CHAT_ID")

def load_config(config_path: str = "config.yaml") -> dict:
    """
    Load environment (via .env) and YAML config. Returns:
    {"env": {<vars>}, "cfg": <parsed_yaml>}
    Raises RuntimeError if required env vars are missing or file not found.
    """
    # load .env into environment
    load_dotenv()

    # load yaml
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise RuntimeError(f"config file not found: {config_path}")

    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    # collect required envs
    env = {k: os.getenv(k) for k in REQUIRED_ENVS}

    missing = [k for k, v in env.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    # Optionally: include all env vars if needed:
    # env_all = dict(os.environ)

    return {"env": env, "cfg": cfg}
