import argparse
import datetime
import json
import random
import statistics
import subprocess
import sys
from pathlib import Path

from test_data import ELO_TEST_DATA


RUNNER = r'''
import json
import statistics
import sys
import time

from unstak_balancer import balance_players_by_skill_variance, player_info_list_from_steam_id_name_ext_obj_elo_dict

payload = json.loads(sys.argv[1])
player_dict = {}
for index, elo in enumerate(payload["elos"]):
    player_dict[index] = ("P{}".format(index), elo, None)
players = player_info_list_from_steam_id_name_ext_obj_elo_dict(player_dict)
durations = []
for _ in range(payload["repeats"]):
    started_at = time.perf_counter()
    balance_players_by_skill_variance(players, max_results=1, strategy=payload["strategy"])
    durations.append((time.perf_counter() - started_at) * 1000.0)
print(json.dumps({
    "min_ms": min(durations),
    "avg_ms": statistics.mean(durations),
    "max_ms": max(durations),
    "repeats": payload["repeats"],
}))
'''

STRATEGIES = ("pairwise", "quartets", "adaptive_blocks", "stddev_buckets")
REPO_ROOT = Path(__file__).resolve().parent


def descending_case(player_count):
    start, end = 2700, 700
    return [int(round(start - (start - end) * (index / float(player_count - 1)))) for index in range(player_count)]


def gaussian_case(player_count, seed):
    rng = random.Random(seed)
    return [max(600, min(2700, int(round(rng.gauss(1400, 380))))) for _ in range(player_count)]


def build_cases():
    cases = []
    for test_case in ELO_TEST_DATA:
        if len(test_case.input_elos) % 2 == 0:
            cases.append({
                "name": test_case.name,
                "elos": test_case.input_elos,
                "source": "test_data",
            })
    for player_count in range(8, 25, 4):
        cases.append({
            "name": "Generated-desc-{}".format(player_count),
            "elos": descending_case(player_count),
            "source": "generated",
        })
        cases.append({
            "name": "Generated-gauss-{}".format(player_count),
            "elos": gaussian_case(player_count, 100 + player_count),
            "source": "generated",
        })
    return cases


def benchmark_strategy(elos, strategy):
    if strategy == "stddev_buckets":
        repeats = 5 if len(elos) <= 16 else 1
        timeout = 15
    else:
        repeats = 20
        timeout = 15

    payload = json.dumps({
        "elos": elos,
        "strategy": strategy,
        "repeats": repeats,
    })
    try:
        completed = subprocess.run(
            [sys.executable, "-c", RUNNER, payload],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {"timeout_seconds": timeout, "repeats": repeats}


def run_benchmarks():
    benchmark = {
        "captured_at": datetime.datetime.now().isoformat(),
        "cwd": str(REPO_ROOT),
        "strategies": list(STRATEGIES),
        "cases": [],
    }
    for case in build_cases():
        case_result = {
            "name": case["name"],
            "players": len(case["elos"]),
            "source": case["source"],
            "results": {},
        }
        for strategy in STRATEGIES:
            case_result["results"][strategy] = benchmark_strategy(case["elos"], strategy)
        benchmark["cases"].append(case_result)
    return benchmark


def format_result_cell(result):
    if "avg_ms" in result:
        return "{:.3f}".format(result["avg_ms"])
    return "timeout>{}s".format(result["timeout_seconds"])


def format_delta_cell(old_result, new_result):
    if "avg_ms" in old_result and "avg_ms" in new_result:
        delta = new_result["avg_ms"] - old_result["avg_ms"]
        return ("+" if delta > 0 else "") + "{:.3f}".format(delta)
    if "avg_ms" in old_result and "timeout_seconds" in new_result:
        return "timed out"
    if "timeout_seconds" in old_result and "avg_ms" in new_result:
        return "resolved timeout"
    return "no change"


def numeric_delta(old_result, new_result):
    if "avg_ms" in old_result and "avg_ms" in new_result:
        return new_result["avg_ms"] - old_result["avg_ms"]
    return None


def build_report_lines(result_bundle, source_label):
    lines = [
        "# Optimized benchmark report",
        "",
        "Compared against: `{}`".format(source_label),
        "",
        "Captured at: `{}`".format(result_bundle["captured_at"]),
        "",
        "| Case | Players | Pairwise avg (ms) | Quartets avg (ms) | Adaptive avg (ms) | Stddev buckets |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in result_bundle["cases"]:
        results = case["results"]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            case["name"],
            case["players"],
            format_result_cell(results["pairwise"]),
            format_result_cell(results["quartets"]),
            format_result_cell(results["adaptive_blocks"]),
            format_result_cell(results["stddev_buckets"]),
        ))
    lines.append("")
    return lines


def build_comparison_lines(baseline_bundle, current_bundle, baseline_label, current_label):
    baseline_cases = {case["name"]: case for case in baseline_bundle["cases"]}
    summary_deltas = {strategy: [] for strategy in STRATEGIES}
    lines = [
        "# Optimized benchmark comparison",
        "",
        "Baseline: `{}`".format(baseline_label),
        "",
        "Current: `{}`".format(current_label),
        "",
        "| Case | Players | Pairwise Delta avg (ms) | Quartets Delta avg (ms) | Adaptive Delta avg (ms) | Stddev buckets Delta |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in current_bundle["cases"]:
        baseline_case = baseline_cases[case["name"]]
        baseline_results = baseline_case["results"]
        current_results = case["results"]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            case["name"],
            case["players"],
            format_delta_cell(baseline_results["pairwise"], current_results["pairwise"]),
            format_delta_cell(baseline_results["quartets"], current_results["quartets"]),
            format_delta_cell(baseline_results["adaptive_blocks"], current_results["adaptive_blocks"]),
            format_delta_cell(baseline_results["stddev_buckets"], current_results["stddev_buckets"]),
        ))
        for strategy in STRATEGIES:
            delta = numeric_delta(baseline_results[strategy], current_results[strategy])
            if delta is not None:
                summary_deltas[strategy].append(delta)

    lines.extend([
        "",
        "## Average delta over cases with numeric results",
        "",
        "| Strategy | Avg Delta avg (ms) |",
        "|---|---:|",
    ])
    for strategy in STRATEGIES:
        deltas = summary_deltas[strategy]
        if deltas:
            average_delta = statistics.mean(deltas)
            delta_text = ("+" if average_delta > 0 else "") + "{:.3f}".format(average_delta)
        else:
            delta_text = "n/a"
        lines.append("| {} | {} |".format(strategy, delta_text))
    lines.append("")
    return lines


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark team balancing strategies and optionally compare to a baseline JSON.")
    parser.add_argument("--baseline-json", help="Optional path to a prior benchmark JSON file.")
    parser.add_argument("--output-json", default="benchmark_optimized_results.json", help="Path for the new benchmark JSON.")
    parser.add_argument("--report-md", default="benchmark_optimized_report.md", help="Path for the new benchmark markdown report.")
    parser.add_argument("--comparison-md", default="benchmark_optimized_comparison.md", help="Path for the markdown comparison report.")
    return parser.parse_args()


def main():
    args = parse_args()
    result_bundle = run_benchmarks()

    output_json_path = (REPO_ROOT / args.output_json).resolve()
    report_md_path = (REPO_ROOT / args.report_md).resolve()
    comparison_md_path = (REPO_ROOT / args.comparison_md).resolve()

    output_json_path.write_text(json.dumps(result_bundle, indent=2) + "\n", encoding="utf-8")
    report_md_path.write_text(
        "\n".join(build_report_lines(result_bundle, "benchmark_baseline_report.md")) + "\n",
        encoding="utf-8",
    )

    summary = {}
    if args.baseline_json:
        baseline_path = Path(args.baseline_json).resolve()
        baseline_bundle = json.loads(baseline_path.read_text(encoding="utf-8"))
        comparison_md_path.write_text(
            "\n".join(build_comparison_lines(
                baseline_bundle,
                result_bundle,
                baseline_path.name,
                report_md_path.name,
            )) + "\n",
            encoding="utf-8",
        )
        baseline_cases = {case["name"]: case for case in baseline_bundle["cases"]}
        for strategy in STRATEGIES:
            deltas = []
            for case in result_bundle["cases"]:
                delta = numeric_delta(baseline_cases[case["name"]]["results"][strategy], case["results"][strategy])
                if delta is not None:
                    deltas.append(delta)
            summary[strategy] = statistics.mean(deltas) if deltas else None

    print(json.dumps({
        "captured_at": result_bundle["captured_at"],
        "output_json": str(output_json_path),
        "report_md": str(report_md_path),
        "comparison_md": str(comparison_md_path) if args.baseline_json else None,
        "summary_avg_delta_ms": summary,
    }, indent=2))


if __name__ == "__main__":
    main()
