"""Command-line access to the offline analysis workflow.

The CLI is useful on headless hosts and in automation: it validates settings,
analyses captured results, compares cache policies and exports reports without
requiring the browser interface.
"""

from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
from analysis import analyse
from cache_simulator import compare_algorithms
from config import load_application_config
from exporters import (
    cache_comparison_csv,
    io_samples_csv,
    report_json,
    report_summary_csv,
    samples_csv,
    task_json,
)
from fio_parser import parse_fio_json
from log_setup import configure_logs, log_alerts
from models import IOSample
from persistence import Repository
from scenario_runner import run_configured_scenario
from simulation import run_simulation


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def analyze_result(args):
    data = read_json(args.input)
    if "jobs" in data:
        result = parse_fio_json(data)
    elif "samples" in data:
        from io_analysis import analyze_io

        samples = [IOSample.from_dict(sample) for sample in data["samples"]]
        result = analyze_io(samples)
    else:
        result = analyse(data.get("points", data))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def show_cache_stat(args):
    pages = [int(value) for value in args.pages.split(",") if value.strip()]
    samples = [
        IOSample(index * 10, page, 4096, "write" if index % 3 == 0 else "read", 10)
        for index, page in enumerate(pages)
    ]
    print(
        json.dumps(
            compare_algorithms(samples, args.capacity), ensure_ascii=False, indent=2
        )
    )


def export_report(args):
    data = read_json(args.input)
    output = Path(args.output)
    output.write_text(
        samples_csv(data["points"]) if args.format == "csv" else task_json(data),
        encoding="utf-8",
    )
    print(f"已导出：{output}")


def simulate_cache(args):
    result = run_simulation(args.workload, args.count, args.capacity, args.seed)
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "workload": result["workload"],
                "algorithms": {
                    key: value["state"]
                    for key, value in result["cache_comparison"].items()
                },
                "anomaly_count": len(result["anomalies"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_scenario(args):
    configuration = load_application_config(args.config)
    log_options = configuration.logging
    logger = configure_logs(
        directory=log_options.directory,
        level=getattr(logging, log_options.level.upper()),
        max_bytes=log_options.max_bytes,
        backup_count=log_options.backup_count,
    )
    repository = Repository(args.database)
    repository.initialize()

    scenario = configuration.scenario
    logger.info(
        "scenario_started name=%s profile=%s tags=%s",
        scenario.name,
        scenario.profile,
        ",".join(scenario.tags),
    )
    result = run_configured_scenario(configuration)
    result["run_id"] = repository.save_run(result)
    alert_events = result.get("alerts", {}).get("events", [])
    log_alerts(logger, alert_events)
    logger.info(
        "scenario_completed run_id=%s samples=%s alerts=%s",
        result["run_id"],
        result.get("sample_count", 0),
        len(alert_events),
    )
    if args.output:
        Path(args.output).write_text(report_json(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "scenario": result["configuration"]["scenario"]["name"],
                "sample_count": result["sample_count"],
                "best_algorithm": result["cache_comparison"]["best_algorithm"],
                "alerts": result["alerts"]["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def validate_config(args):
    configuration = load_application_config(args.config)
    print(
        json.dumps(
            {
                "valid": True,
                "scenario": configuration.scenario.name,
                "safe_simulation": configuration.scenario.safe_simulation,
                "workload": configuration.workload.kind,
                "cache_algorithm": configuration.cache.algorithm,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def export_full_report(args):
    data = read_json(args.input)
    output = Path(args.output)
    if args.section == "summary":
        content = report_summary_csv(data)
    elif args.section == "samples":
        content = io_samples_csv(data.get("samples", []))
    elif args.section == "cache":
        content = cache_comparison_csv(data.get("cache_comparison", {}))
    else:
        content = report_json(data)
    output.write_text(content, encoding="utf-8")
    print(f"已导出：{output}")


def parser():
    root = argparse.ArgumentParser(
        prog="nvme-analyzer",
        description="企业级 NVMe SSD 缓存与性能结果分析工具",
    )
    commands = root.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze-result", help="分析已有 JSON 样本")
    analyze.add_argument("input")
    analyze.set_defaults(func=analyze_result)
    cache = commands.add_parser("show-cache-stat", help="比较缓存置换算法")
    cache.add_argument("--pages", required=True, help="以逗号分隔的页访问序列")
    cache.add_argument("--capacity", type=int, default=8)
    cache.set_defaults(func=show_cache_stat)
    export = commands.add_parser("export-report", help="导出 CSV 或 JSON")
    export.add_argument("input")
    export.add_argument("--format", choices=["csv", "json"], default="json")
    export.add_argument("--output", required=True)
    export.set_defaults(func=export_report)
    simulate = commands.add_parser(
        "simulate-cache", help="运行内存页访问与缓存算法仿真"
    )
    simulate.add_argument(
        "--workload",
        choices=["sequential", "random", "mixed", "hot-cold"],
        default="mixed",
    )
    simulate.add_argument("--count", type=int, default=200)
    simulate.add_argument("--capacity", type=int, default=32)
    simulate.add_argument("--seed", type=int, default=7)
    simulate.add_argument("--output")
    simulate.set_defaults(func=simulate_cache)
    scenario = commands.add_parser(
        "run-scenario",
        help="从 YAML 运行内存分析场景并持久化结果",
    )
    scenario.add_argument("--config", default="config/default.yaml")
    scenario.add_argument("--database", default="nvme_analysis.db")
    scenario.add_argument("--output")
    scenario.set_defaults(func=run_scenario)

    validation = commands.add_parser(
        "validate-config",
        help="校验 YAML 配置但不运行场景",
    )
    validation.add_argument("--config", default="config/default.yaml")
    validation.set_defaults(func=validate_config)

    full_export = commands.add_parser(
        "export-full-report",
        help="导出完整场景报告的 JSON 或 CSV 部分",
    )
    full_export.add_argument("input")
    full_export.add_argument(
        "--section",
        choices=["json", "summary", "samples", "cache"],
        default="json",
    )
    full_export.add_argument("--output", required=True)
    full_export.set_defaults(func=export_full_report)
    return root


def main():
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
