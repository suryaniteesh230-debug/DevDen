from __future__ import annotations

import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

import networkx as nx


MAX_QUERY_CHARACTERS = 300
MAX_GRAPH_RESULTS = 8


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1
    }


class MedicalKnowledgeGraph:
    """Constrained, source-backed local graph; no arbitrary graph execution."""

    def __init__(self, graph_path: str | Path) -> None:
        self.graph_path = Path(graph_path)
        payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.graph_version = str(payload["graph_version"])
        self.graph = nx.MultiDiGraph(graph_version=self.graph_version)
        for node in payload["nodes"]:
            self.graph.add_node(node["id"], **node)
        for edge in payload["edges"]:
            if not all(
                edge.get(field)
                for field in (
                    "edge_id",
                    "relation",
                    "source_id",
                    "source_reference",
                    "graph_version",
                )
            ):
                raise ValueError("Every medical knowledge graph edge requires provenance")
            self.graph.add_edge(
                edge["source"], edge["target"], key=edge["edge_id"], **edge
            )

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "graph_version": self.graph_version,
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
        }

    def query(self, query: str, *, max_results: int = 5) -> dict[str, Any]:
        timer = perf_counter()
        normalized = " ".join(query.split())[:MAX_QUERY_CHARACTERS]
        query_tokens = _tokens(normalized)
        limit = min(max(int(max_results), 1), MAX_GRAPH_RESULTS)
        ranked: list[tuple[float, dict[str, Any]]] = []
        if query_tokens:
            for source, target, edge_id, data in self.graph.edges(keys=True, data=True):
                source_data = self.graph.nodes[source]
                target_data = self.graph.nodes[target]
                searchable = " ".join(
                    [
                        source_data["label"],
                        *source_data.get("aliases", []),
                        data["relation"].replace("_", " "),
                        target_data["label"],
                        *target_data.get("aliases", []),
                    ]
                )
                overlap = query_tokens & _tokens(searchable)
                if not overlap:
                    continue
                relevance = min(1.0, len(overlap) / max(1, min(len(query_tokens), 4)))
                ranked.append(
                    (
                        relevance,
                        {
                            "edge_id": edge_id,
                            "source_concept": source_data["label"],
                            "relationship": data["relation"],
                            "target_concept": target_data["label"],
                            "provenance": {
                                "source_id": data["source_id"],
                                "source_reference": data["source_reference"],
                                "graph_version": data["graph_version"],
                            },
                            "relevance": round(relevance, 6),
                        },
                    )
                )
        results = [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["edge_id"]))[:limit]]
        return {
            "status": "SUCCESS" if results else "NO_RELEVANT_EVIDENCE",
            "query": normalized,
            "results": results,
            "graph_metadata": self.metadata,
            "latency_ms": round((perf_counter() - timer) * 1000, 3),
        }
