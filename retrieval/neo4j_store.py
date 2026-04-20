"""
Neo4j graph store with Cypher topology queries

Neo4j browser: http://localhost:7474
"""

import os
from typing import Any, Dict, List

from neo4j import GraphDatabase

from simulator.topology import CRITICAL_EDGES, DEPENDENCIES


class Neo4jStore:
    def __init__(self) -> None:
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USER"),
                os.getenv("NEO4J_PASSWORD"),
            ),
        )

    def close(self) -> None:
        self.driver.close()

    def initialize_topology(self) -> None:
        """Create Service nodes and DEPENDS_ON relationships from topology.py"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

            for service in DEPENDENCIES.keys():
                session.run("MERGE (s:Service {name: $name})", name=service)

            for service, deps in DEPENDENCIES.items():
                for dep in deps:
                    is_critical = (service, dep) in CRITICAL_EDGES
                    session.run(
                        """
                        MATCH (a:Service {name: $from_svc})
                        MATCH (b:Service {name: $to_svc})
                        MERGE (a)-[r:DEPENDS_ON]->(b)
                        SET r.critical = $critical
                        """,
                        from_svc=service,
                        to_svc=dep,
                        critical=is_critical,
                    )

    def get_blast_radius(self, service: str) -> List[str]:
        """All services that transitively depend on the target service"""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (s:Service)-[:DEPENDS_ON*1..5]->(target:Service {name: $name})
                RETURN DISTINCT s.name AS name
                """,
                name=service,
            )
            return [record["name"] for record in result]

    def get_dependencies(self, service: str) -> List[str]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (s:Service {name: $name})-[:DEPENDS_ON]->(dep:Service)
                RETURN dep.name AS name
                """,
                name=service,
            )
            return [record["name"] for record in result]

    def get_callers(self, service: str) -> List[str]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (caller:Service)-[:DEPENDS_ON]->(s:Service {name: $name})
                RETURN caller.name AS name
                """,
                name=service,
            )
            return [record["name"] for record in result]

    def get_shortest_path(self, from_svc: str, to_svc: str) -> List[str]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH path = shortestPath(
                    (a:Service {name: $from_svc})-[:DEPENDS_ON*]->(b:Service {name: $to_svc})
                )
                RETURN [node IN nodes(path) | node.name] AS path
                """,
                from_svc=from_svc,
                to_svc=to_svc,
            )
            record = result.single()
            return record["path"] if record else []

    def get_critical_cascade_paths(self, origin: str) -> List[List[str]]:
        """All paths to origin where every traversed edge is marked critical"""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH path = (top:Service)-[r:DEPENDS_ON*1..5]->(origin:Service {name: $origin})
                WHERE ALL(rel IN r WHERE rel.critical = true)
                RETURN [node IN nodes(path) | node.name] AS path
                ORDER BY length(path) DESC
                """,
                origin=origin,
            )
            return [record["path"] for record in result]

    # Backward-compatible scaffold aliases
    def upsert_service_graph(self, services: List[Dict[str, Any]]) -> int:
        self.initialize_topology()
        return len(DEPENDENCIES)

    def query_neighbors(self, service: str, hops: int = 2) -> List[Dict[str, Any]]:
        del hops
        neighbors = self.get_dependencies(service)
        return [
            {
                "evidence_id": f"dep:{service}->{dep}",
                "text": f"{service} depends on {dep}",
                "metadata": {"from": service, "to": dep},
                "score": 1.0,
            }
            for dep in neighbors
        ]
