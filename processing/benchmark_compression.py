"""Benchmark token compression across incident types"""

import json
from pathlib import Path

from processing.log_compressor import cluster_similar_logs, estimate_token_savings
from processing.metric_summarizer import summarize_metrics


def benchmark_log_compression() -> dict:
    """Measure compression savings on all 6 incident types' log files"""
    logs_dir = Path("data/logs")
    results = {}

    for csv_file in logs_dir.glob("*_benchmark.csv"):
        import csv

        with open(csv_file) as f:
            raw_logs = list(csv.DictReader(f))

        compressed = cluster_similar_logs(raw_logs)
        savings = estimate_token_savings(raw_logs, compressed)
        incident_name = csv_file.stem.replace("_benchmark", "")
        results[incident_name] = savings

    return results


if __name__ == "__main__":
    results = benchmark_log_compression()
    print("\nLog compression savings per incident:")
    print("=" * 60)
    for incident, stats in results.items():
        print(
            f"{incident:25} "
            f"{stats['original_tokens_est']:>6} → {stats['compressed_tokens_est']:>6} tokens  "
            f"(-{stats['reduction_pct']}%)"
        )
