import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Read from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
API_BASE = os.getenv("API_BASE", "https://api.github.com")

# HTTP headers for GitHub API requests
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}" if GITHUB_TOKEN else None,
    "Accept": "application/vnd.github+json"
}

def iso_now() -> str:
    """Return current UTC timestamp in ISO8601 with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"

def safe_str(x) -> str:
    """Convert None to empty string, else to str."""
    return "" if x is None else str(x)
