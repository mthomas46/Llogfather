import os
import json
import yaml
from dotenv import load_dotenv

CONFIG_FILE = "config.json"
YAML_CONFIG_FILE = "config.yaml"

# Load .env if present
load_dotenv()

def load_yaml_config():
    if os.path.exists(YAML_CONFIG_FILE):
        with open(YAML_CONFIG_FILE, "r") as f:
            return yaml.safe_load(f) or {}
    return {}

def load_config():
    # Load all config sources
    config = {}
    # 1. YAML config
    config.update(load_yaml_config())
    # 2. config.json
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config.update(json.load(f))
    # 3. .env and environment variables (already loaded by dotenv)
    # Flatten YAML/config.json for top-level keys
    for key in ["llamalyticshub_api_key", "github_token", "LLAMALYTICSHUB_URL"]:
        env_val = os.environ.get(key)
        if env_val:
            config[key] = env_val
    # Also support nested YAML keys
    if "llamalyticshub" in config:
        if "api_key" in config["llamalyticshub"]:
            config["llamalyticshub_api_key"] = config["llamalyticshub"]["api_key"]
        if "url" in config["llamalyticshub"]:
            config["LLAMALYTICSHUB_URL"] = config["llamalyticshub"]["url"]
    if "github" in config and "token" in config["github"]:
        config["github_token"] = config["github"]["token"]
    return config

def get_config_value(key, default=None):
    # Priority: env > .env > YAML > config.json
    val = os.environ.get(key)
    if val:
        return val
    config = load_config()
    return config.get(key, default)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2) 