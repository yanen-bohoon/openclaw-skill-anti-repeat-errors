#!/usr/bin/env python3
"""
Cron 任务: 生成周报

用法:
    python scripts/cron_weekly_report.py [--days 7] [--output-dir ./reports]

功能:
    1. 计算错误率指标
    2. 对比基线
    3. 生成 Markdown 周报
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

from error_rate_tracker import ErrorRateTracker, Baseline
from weekly_report import WeeklyReportGenerator, WeeklyReportConfig


def main():
    parser = argparse.ArgumentParser(description="生成周报")
    parser.add_argument("--days", type=int, default=7, help="统计最近 N 天的数据")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    parser.add_argument("--baseline-id", type=str, default=None, help="指定对比的基线 ID")
    parser.add_argument("--data-dir", type=str, default=None, help="数据目录")
    parser.add_argument("--title", type=str, default="Anti-Repeat-Errors 周报", help="报告标题")
    parser.add_argument("--target", type=float, default=80.0, help="目标改善百分比")
    parser.add_argument("--dry-run", action="store_true", help="仅输出到控制台，不写入文件")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 确定路径
    skill_root = Path(__file__).parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else skill_root / "reports"
    data_dir = Path(args.data_dir) if args.data_dir else None
    
    print(f"[cron_weekly_report] Starting...")
    print(f"  - Days: {args.days}")
    print(f"  - Target improvement: {args.target}%")
    print(f"  - Output dir: {output_dir}")
    
    # 初始化组件
    tracker = ErrorRateTracker(data_dir=data_dir)
    config = WeeklyReportConfig(
        title=args.title,
        target_improvement_pct=args.target,
    )
    generator = WeeklyReportGenerator(tracker=tracker, config=config)
    
    # 加载基线
    baseline = None
    if args.baseline_id:
        baseline = tracker.load_baseline(args.baseline_id)
        if baseline is None:
            print(f"[warn] Baseline not found: {args.baseline_id}")
    else:
        baseline = tracker.get_latest_baseline()
    
    if baseline:
        print(f"  - Baseline: {baseline.baseline_id} ({baseline.created_at[:10]})")
    else:
        print("  - No baseline available")
    
    # 检查目标达成
    print("\n[1/3] Checking target achievement...")
    achieved, details = tracker.check_target_achieved(
        target_improvement_pct=args.target,
        baseline=baseline,
    )
    
    print(f"  Current improvement: {details['actual_improvement_pct']:.1f}%")
    print(f"  Target: {details['target_improvement_pct']}%")
    print(f"  Achieved: {'✅ Yes' if achieved else '⚠️ No'}")
    
    if args.verbose:
        print(f"\n  Details:")
        print(f"    Baseline rate: {details['baseline_repeat_error_rate'] * 100:.2f}%")
        print(f"    Current rate: {details['current_repeat_error_rate'] * 100:.2f}%")
    
    # 计算趋势
    print("\n[2/3] Calculating trend...")
    trend = tracker.calculate_trend(baseline=baseline, days=args.days)
    
    print(f"  Trend direction: {trend.trend_direction}")
    print(f"  Avg error rate: {trend.avg_error_rate * 100:.2f}%")
    print(f"  Avg repeat error rate: {trend.avg_repeat_error_rate * 100:.2f}%")
    
    # 生成报告
    print("\n[3/3] Generating report...")
    
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"weekly_report_{timestamp}.md"
    else:
        output_path = None
    
    report = generator.generate(
        baseline=baseline,
        days=args.days,
        output_path=output_path,
    )
    
    if output_path:
        print(f"  Report saved: {output_path}")
    
    # 输出摘要
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if baseline:
        print(f"Baseline: {baseline.baseline_id}")
        print(f"Baseline repeat error rate: {baseline.baseline_repeat_error_rate * 100:.2f}%")
    
    print(f"Current repeat error rate: {details['current_repeat_error_rate'] * 100:.2f}%")
    print(f"Improvement: {details['actual_improvement_pct']:.1f}%")
    print(f"Target: {details['target_improvement_pct']}%")
    print(f"Status: {'✅ ACHIEVED' if achieved else '⚠️ NOT ACHIEVED'}")
    
    # 输出报告预览（前 50 行）
    if args.verbose or args.dry_run:
        print("\n" + "=" * 60)
        print("REPORT PREVIEW")
        print("=" * 60)
        print("\n".join(report.split("\n")[:50]))
        if len(report.split("\n")) > 50:
            print("\n... (truncated)")
    
    # 返回码
    if achieved:
        print("\n✅ Target achieved!")
        return 0
    else:
        print("\n⚠️ Target not achieved yet")
        return 1


if __name__ == "__main__":
    sys.exit(main())