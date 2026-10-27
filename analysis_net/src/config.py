import os
from pathlib import Path

DATA_SERVICE = os.getenv("DATA_SERVICE", "localhost:4070")

IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "711a971a423570")


UPLOADS_DIR = Path("data/" + os.getenv("UPLOADS_DIR", "/uploads"))
CACHE_DIR = Path("data/" + os.getenv("CACHE_DIR", "/db_cache"))


UPLOADS_CLEANUP_MIN = float(os.getenv("UPLOADS_CLEANUP_MINT", "5"))  # minutes
