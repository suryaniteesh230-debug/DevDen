"""Benchmark only the local RAG and knowledge-graph components."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import numpy as np

from app.clinical_reasoning.knowledge_graph import MedicalKnowledgeGraph
from app.clinical_reasoning.retrieval import ClinicalKnowledgeRetriever
from app.core.config import get_settings


RUNS = 1000
OUTPUT_PATH = Path(__file__).with_name("latency_benchmark.json")


def stats(values: list[float]) -> dict[str, float | int]:
    return {
        "runs": len(values),
        "mean_ms": round(mean(values), 4),
        "p50_ms": round(median(values), 4),
        "p95_ms": round(float(np.percentile(values, 95)), 4),
    }


def main() -> None:
    settings = get_settings()
    retriever = ClinicalKnowledgeRetriever(
        settings.clinical_corpus_path, settings.clinical_vector_index_path
    )
    graph = MedicalKnowledgeGraph(settings.medical_knowledge_graph_path)
    rag_times: list[float] = []
    graph_times: list[float] = []
    rag_query = "acute chest pain shortness of breath serial troponin ECG evaluation"
    graph_query = "chest pain dyspnea troponin acute coronary syndrome"
    for _ in range(RUNS):
        timer = perf_counter()
        retriever.retrieve(rag_query, top_k=3)
        rag_times.append((perf_counter() - timer) * 1000)
        timer = perf_counter()
        graph.query(graph_query, max_results=5)
        graph_times.append((perf_counter() - timer) * 1000)
    result = {
        "scope": "Local-only warm component benchmark; excludes Gemini, workflow, and persistence",
        "rag": stats(rag_times),
        "knowledge_graph": stats(graph_times),
        "retriever": retriever.index_metadata,
        "graph": graph.metadata,
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
