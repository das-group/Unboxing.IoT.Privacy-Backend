import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis
from src.config import (
    REDIS_HOST,
    REDIS_PORT,
    SESSION_DURATION_DAYS,
    SESSION_TOKEN_LENGTH,
)
from src.errors import MalformedCredentialError

SESSIONS: redis.Redis = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=3,
)


@dataclass
class SessionData:
    token: str
    user_id: str

    def to_str(self) -> str:
        return f"{self.user_id}:{self.token}"

    @staticmethod
    def from_str(s: str) -> "SessionData":
        parts = s.split(":")

        if len(parts) != 2:
            raise MalformedCredentialError()

        return SessionData(
            user_id=parts[0],
            token=parts[1],
        )


def create_session(user_id: str) -> SessionData:
    token = secrets.token_urlsafe(SESSION_TOKEN_LENGTH)

    duration = timedelta(days=SESSION_DURATION_DAYS)

    SESSIONS.set(token, user_id, ex=int(duration.total_seconds()))
    
    print('Session created with id ' + token)

    return SessionData(token=token, user_id=user_id)


def verify_session(token: SessionData) -> None | datetime:
    pipe = SESSIONS.pipeline()
    pipe.get(token.token)
    pipe.ttl(token.token)
    id, ttl = pipe.execute()

    if id is None or id.decode("utf-8") != token.user_id:
        return None

    assert ttl != -1, "Session always expires"

    if ttl == -2:
        return None

    return datetime.now() + timedelta(seconds=ttl)

def get_user_id_by_session_token(session_token):
    
    pipe = SESSIONS.pipeline()
    pipe.get(session_token)
    pipe.ttl(session_token)
    id, ttl = pipe.execute()
   
    if id is None or ttl == -2:
        return None
    return id.decode("utf-8")

def delete_session(data: SessionData) -> bool:
    res = SESSIONS.delete(data.token)
    return res == 1
