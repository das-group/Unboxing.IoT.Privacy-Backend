import json
import os

RP_ID = os.environ.get("RP_ID", "localhost")
RP_NAME = os.environ.get("RP_NAME", "Unboxing IoT Privacy")
ORIGIN = json.loads(
    os.environ.get("ORIGIN", '["http://localhost:4040", "http://localhost:5173"]')
)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))


MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27018))
MONGO_USER = os.environ.get("MONGO_USER", "admin")
MONGO_PASS = os.environ.get("MONGO_PASS", "password")
MONGO_DB = os.environ.get("MONGO_DB", "userdb")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "users")


SESSION_DURATION_DAYS = int(os.environ.get("SESSION_DURATION_DAYS", 7))
SESSION_TOKEN_LENGTH = int(os.environ.get("SESSION_TOKEN_LENGTH", 64))

DEFAULT_USER_PERMISSIONS = ['create_post']
