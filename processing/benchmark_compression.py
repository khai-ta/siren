"""Benchmark token compression across incident types"""

import csv
import json
from pathlib import Path

from log_compressor import cluster_similar_logs, estimate_token_savings


def benchmark_log_compression() -> dict:
    """Measure compression savings on all 6 incident types' log files"""
    logs_dir = Path("../data/logs")
    results = {}

    for csv_file in logs_dir.glob("*.csv"):
        with open(csv_file) as f:
            raw_logs = list(csv.DictReader(f))

        if not raw_logs:
            continue

        compressed = cluster_similar_logs(raw_logs)
        savings = estimate_token_savings(raw_logs, compressed)
        incident_name = csv_file.stem.replace("_benchmark", "")
        results[incident_name] = savings

    return results


if __name__ == "__main__":
    results = benchmark_log_compression()
    print("\nLog compression savings per incident:")
    print("-" * 70)
    for incident, stats in sorted(results.items()):
        orig = stats['original_tokens_est']
        comp = stats['compressed_tokens_est']
        pct = stats['reduction_pct']
        print(f"{incident:25} {orig:>6} -> {comp:>6} tokens  (-{pct}%)")

    if results:
        avg_reduction = sum(r['reduction_pct'] for r in results.values()) / len(results)
        print(f"\nAverage reduction: {avg_reduction:.1f}%")
        print(f"\nDetailed results: {json.dumps(results, indent=2)}")
