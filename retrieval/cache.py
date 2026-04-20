"""Redis cache for repeated retrievals"""

import hashlib
import json
import os
from typing import Any

import redis


class RetrievalCache:
    def __init__(self) -> None:
        self.client = redis.from_url(os.getenv("REDIS_URL"))
        self.ttl = 3600

    def _key(self, namespace: str, *args: Any) -> str:
        raw = f"{namespace}:{json.dumps(args, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, namespace: str, *args: Any) -> Any:
        key = self._key(namespace, *args)
        raw = self.client.get(key)
        return json.loads(raw) if raw else None

    def set(self, namespace: str, *args: Any, value: Any) -> None:
        key = self._key(namespace, *args)
        self.client.setex(key, self.ttl, json.dumps(value, default=str))

    def clear(self) -> None:
        self.client.flushdb()
