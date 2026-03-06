#!/usr/bin/env python3
"""
基线初始化脚本

用法:
    python scripts/baseline_init.py [--days 7] [--description "Initial baseline"]

功能:
    1. 聚合最近 N 天的日志
    2. 计算初始错误率
    3. 创建并保存基线
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到路径
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from error_rate_tracker import ErrorRateTracker, Baseline


def main():
    parser = argparse.ArgumentParser(description="创建错误率基线")
    parser.add_argument("--days", type=int, default=7, help="使用最近 N 天的数据作为基线")
    parser.add_argument("--description", type=str, default="Initial baseline", help="基线描述")
    parser.add_argument("--data-dir", type=str, default=None, help="数据目录")
    parser.add_argument("--force", action="store_true", help="强制创建新基线（即使已有基线）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际创建")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 确定路径
    data_dir = Path(args.data_dir) if args.data_dir else None
    
    print(f"[baseline_init] Starting...")
    print(f"  - Days: {args.days}")
    print(f"  - Description: {args.description}")
    print(f"  - Force: {args.force}")
    
    # 初始化追踪器
    tracker = ErrorRateTracker(data_dir=data_dir)
    
    # 检查现有基线
    existing = tracker.get_latest_baseline()
    if existing and not args.force:
        print(f"\n[warn] Baseline already exists: {existing.baseline_id}")
        print(f"  Created at: {existing.created_at}")
        print(f"  Repeat error rate: {existing.baseline_repeat_error_rate * 100:.2f}%")
        print("\nUse --force to create a new baseline.")
        return 1
    
    if existing:
        print(f"\n[info] Overwriting existing baseline: {existing.baseline_id}")
    
    # 计算快照
    print("\n[1/2] Calculating error rate snapshot...")
    snapshot = tracker.calculate_snapshot(days=args.days)
    
    print(f"  Total events: {snapshot.total_events}")
    print(f"  Total errors: {snapshot.total_errors}")
    print(f"  Error rate: {snapshot.error_rate * 100:.2f}%")
    print(f"  Unique signatures: {snapshot.unique_error_signatures}")
    print(f"  Repeat error rate: {snapshot.repeat_error_rate * 100:.2f}%")
    
    if args.verbose and snapshot.top_error_signatures:
        print("\n  Top error signatures:")
        for i, err in enumerate(snapshot.top_error_signatures[:5], 1):
            sig = err['signature'][:50]
            print(f"    {i}. {sig}: {err['count']}")
    
    # 创建基线
    print("\n[2/2] Creating baseline...")
    
    if args.dry_run:
        print("  [dry-run] Skipping baseline creation")
        baseline_id = f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    else:
        baseline = tracker.create_baseline(
            description=args.description,
            days=args.days,
        )
        baseline_id = baseline.baseline_id
        print(f"  Baseline created: {baseline_id}")
    
    # 输出摘要
    print("\n" + "=" * 60)
    print("BASELINE CREATED")
    print("=" * 60)
    print(f"Baseline ID: {baseline_id}")
    print(f"Description: {args.description}")
    print(f"Period: {snapshot.period_start[:10]} ~ {snapshot.period_end[:10]}")
    print(f"Total events: {snapshot.total_events}")
    print(f"Total errors: {snapshot.total_errors}")
    print(f"Error rate: {snapshot.error_rate * 100:.2f}%")
    print(f"Repeat error rate: {snapshot.repeat_error_rate * 100:.2f}%")
    
    print("\n✅ Baseline initialized successfully")
    print("\nNext steps:")
    print("1. Wait for some time (e.g., 1 week)")
    print("2. Run `python scripts/cron_weekly_report.py` to generate reports")
    print("3. Compare current error rate with baseline")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())