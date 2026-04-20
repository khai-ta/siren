"""Environment configuration scaffold"""

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    anthropic_api_key: str
    openai_api_key: str
    pinecone_api_key: str
    pinecone_index: str
    pinecone_environment: str
    cohere_api_key: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    timescale_uri: str
    redis_url: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables in scaffold mode"""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            pinecone_index=os.getenv("PINECONE_INDEX", "siren-incidents"),
            pinecone_environment=os.getenv("PINECONE_ENVIRONMENT", ""),
            cohere_api_key=os.getenv("COHERE_API_KEY", ""),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            timescale_uri=os.getenv("TIMESCALE_URI", "postgresql://postgres:postgres@localhost:5432/siren"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        )
