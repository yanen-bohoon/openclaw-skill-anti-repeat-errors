#!/usr/bin/env python3
"""
Cron 任务: 生成候选规则

用法:
    python scripts/cron_generate_candidates.py [--days 7] [--output-dir ./candidates]

功能:
    1. 聚合最近 N 天的日志
    2. 聚类错误
    3. 生成候选规则
    4. 输出到指定目录
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到路径
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from log_aggregator import LogAggregator, AggregatedLogs
from error_clusterer import ErrorClusterer, ClusteringResult
from rule_generator import RuleGenerator, GenerationResult


def load_existing_rule_ids(rules_dir: Path) -> set[str]:
    """加载现有规则 ID"""
    rule_ids = set()
    
    # 尝试从 guardrail YAML 文件加载
    guardrail_dir = rules_dir / "guardrails"
    if guardrail_dir.exists():
        for yaml_file in guardrail_dir.glob("*.yaml"):
            try:
                import yaml
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and data.get("kind") == "guardrail":
                    for rule in data.get("rules", []):
                        if "id" in rule:
                            rule_ids.add(rule["id"])
            except Exception:
                pass
    
    # 也检查候选规则目录
    candidates_dir = rules_dir.parent / "candidates"
    if candidates_dir.exists():
        for json_file in candidates_dir.glob("candidates_*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for candidate in data.get("candidates", []):
                    rule_data = candidate.get("rule", {})
                    if "id" in rule_data:
                        rule_ids.add(rule_data["id"])
            except Exception:
                pass
    
    return rule_ids


def main():
    parser = argparse.ArgumentParser(description="生成候选规则")
    parser.add_argument("--days", type=int, default=7, help="聚合最近 N 天的日志")
    parser.add_argument("--min-cluster-size", type=int, default=2, help="最小聚类大小")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    parser.add_argument("--rules-dir", type=str, default=None, help="规则目录")
    parser.add_argument("--log-dir", type=str, default=None, help="日志目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 确定路径
    skill_root = Path(__file__).parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else skill_root / "candidates"
    rules_dir = Path(args.rules_dir) if args.rules_dir else skill_root / "rules"
    log_dir = Path(args.log_dir) if args.log_dir else None
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[cron_generate_candidates] Starting...")
    print(f"  - Days: {args.days}")
    print(f"  - Min cluster size: {args.min_cluster_size}")
    print(f"  - Output dir: {output_dir}")
    
    # 1. 加载现有规则 ID（用于去重）
    print("\n[1/4] Loading existing rule IDs...")
    existing_rule_ids = load_existing_rule_ids(rules_dir)
    print(f"  Found {len(existing_rule_ids)} existing rules")
    
    # 2. 聚合日志
    print("\n[2/4] Aggregating logs...")
    aggregator = LogAggregator(log_dir=log_dir)
    aggregated = aggregator.aggregate(days=args.days)
    print(f"  Total records: {aggregated.total_records}")
    print(f"  Total errors: {aggregated.total_errors}")
    print(f"  Guardrail hits: {aggregated.total_guardrail_hits}")
    print(f"  Unique signatures: {aggregated.unique_signatures}")
    
    if args.verbose:
        summary = aggregator.get_error_summary(aggregated)
        print(f"\n  Top tools: {list(summary['top_tools'].items())[:5]}")
        print(f"  Top commands: {list(summary['top_commands'].items())[:5]}")
    
    # 3. 聚类错误
    print("\n[3/4] Clustering errors...")
    clusterer = ErrorClusterer(min_cluster_size=args.min_cluster_size)
    clustering_result = clusterer.cluster(aggregated)
    print(f"  Total clusters: {clustering_result.total_clusters}")
    print(f"  High priority clusters: {clustering_result.high_priority_clusters}")
    
    if args.verbose and clustering_result.clusters:
        print("\n  Top clusters:")
        for cluster in clusterer.get_top_clusters(clustering_result, 5):
            print(f"    - {cluster.cluster_id}: {cluster.count}x, priority={cluster.priority}, tool={cluster.tool_name}")
    
    # 4. 生成候选规则
    print("\n[4/4] Generating candidate rules...")
    generator = RuleGenerator(existing_rule_ids=existing_rule_ids)
    generation_result = generator.generate(clustering_result)
    print(f"  Total candidates: {generation_result.total_candidates}")
    print(f"  High priority candidates: {generation_result.high_priority_candidates}")
    print(f"  Duplicates removed: {generation_result.duplicates_removed}")
    print(f"  Existing rules skipped: {generation_result.existing_rules_skipped}")
    
    if args.verbose and generation_result.candidates:
        print("\n  Top candidates:")
        for candidate in generation_result.candidates[:5]:
            print(f"    - {candidate.rule.id}: action={candidate.rule.action.value}, priority={candidate.rule.priority}")
    
    # 5. 输出结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if not args.dry_run:
        # 输出 JSON
        json_output = output_dir / f"candidates_{timestamp}.json"
        generator.export_candidates(generation_result, json_output)
        print(f"\n  JSON output: {json_output}")
        
        # 输出 YAML（可进入规则库）
        yaml_output = output_dir / f"candidates_{timestamp}.yaml"
        generator.export_to_yaml(generation_result, yaml_output)
        print(f"  YAML output: {yaml_output}")
        
        # 输出聚类报告
        cluster_report = output_dir / f"clusters_{timestamp}.json"
        clusterer.export_clusters(clustering_result, cluster_report)
        print(f"  Cluster report: {cluster_report}")
    else:
        print("\n[dry-run] Skipping file output")
    
    # 6. 输出摘要
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Time window: {aggregated.window_start} to {aggregated.window_end}")
    print(f"Total error records: {aggregated.total_records}")
    print(f"Unique error signatures: {aggregated.unique_signatures}")
    print(f"Error clusters: {clustering_result.total_clusters}")
    print(f"Candidate rules generated: {generation_result.total_candidates}")
    print(f"High priority candidates: {generation_result.high_priority_candidates}")
    
    # 返回码
    if generation_result.total_candidates > 0:
        print("\n✅ Candidate rules generated successfully")
        return 0
    else:
        print("\n⚠️ No candidate rules generated")
        return 1


if __name__ == "__main__":
    sys.exit(main())