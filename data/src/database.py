from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from src.config import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_USER,
    MONGO_PASS,
)

## --------------------- MongoDB Setup --------------------- ##

URI: str = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}"
CLIENT: AsyncMongoClient = AsyncMongoClient(URI)

DATA_DB: AsyncDatabase = CLIENT.get_database(MONGO_DB)
