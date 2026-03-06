#!/usr/bin/env python3
"""
Guardrail Hit Report Generator

Generates periodic reports for guardrail hits.

Usage:
    python generate_hit_report.py --daily
    python generate_hit_report.py --weekly
    python generate_hit_report.py --date 2024-01-15
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.hit_replay import HitReplay
from src.hit_logger import HitLogger


def generate_daily_report(date: str, output_dir: Path) -> str:
    """生成日报"""
    replay = HitReplay()
    
    report = replay.generate_report(date=date, output_format="markdown")
    
    output_file = output_dir / f"guardrail_report_{date}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    
    return str(output_file)


def generate_weekly_report(end_date: str, output_dir: Path) -> str:
    """生成周报"""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=6)
    
    logger = HitLogger()
    
    # 收集一周的数据
    all_stats = {
        "total_hits": 0,
        "by_event_type": {},
        "by_rule": {},
        "by_tool": {},
        "daily_breakdown": {},
    }
    
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        stats = logger.get_statistics(date=date_str)
        
        all_stats["total_hits"] += stats["total_hits"]
        all_stats["daily_breakdown"][date_str] = stats["total_hits"]
        
        for k, v in stats["by_event_type"].items():
            all_stats["by_event_type"][k] = all_stats["by_event_type"].get(k, 0) + v
        
        for k, v in stats["by_rule"].items():
            all_stats["by_rule"][k] = all_stats["by_rule"].get(k, 0) + v
        
        for k, v in stats["by_tool"].items():
            all_stats["by_tool"][k] = all_stats["by_tool"].get(k, 0) + v
        
        current += timedelta(days=1)
    
    # 排序
    all_stats["by_rule"] = dict(sorted(all_stats["by_rule"].items(), key=lambda x: -x[1]))
    all_stats["by_tool"] = dict(sorted(all_stats["by_tool"].items(), key=lambda x: -x[1]))
    
    # 生成报告
    lines = [
        f"# Guardrail Weekly Report: {start.strftime('%Y-%m-%d')} to {end_date}",
        "",
        "## Summary",
        "",
        f"- **Total Hits (7 days):** {all_stats['total_hits']}",
        f"- **Daily Average:** {all_stats['total_hits'] / 7:.1f}",
        "",
        "## Daily Breakdown",
        "",
        "| Date | Hits |",
        "|------|------|",
    ]
    
    for date, count in all_stats["daily_breakdown"].items():
        lines.append(f"| {date} | {count} |")
    
    lines.extend([
        "",
        "## By Event Type",
        "",
    ])
    
    for event_type, count in all_stats["by_event_type"].items():
        lines.append(f"- **{event_type}:** {count}")
    
    lines.extend([
        "",
        "## Top 10 Rules",
        "",
    ])
    
    for rule_id, count in list(all_stats["by_rule"].items())[:10]:
        lines.append(f"- `{rule_id}`: {count} hits")
    
    lines.extend([
        "",
        "## Top 10 Tools",
        "",
    ])
    
    for tool_name, count in list(all_stats["by_tool"].items())[:10]:
        lines.append(f"- `{tool_name}`: {count} hits")
    
    report = "\n".join(lines)
    
    output_file = output_dir / f"guardrail_weekly_{start.strftime('%Y-%m-%d')}_{end_date}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    
    return str(output_file)


def main():
    parser = argparse.ArgumentParser(description="Guardrail Hit Report Generator")
    
    parser.add_argument("--daily", action="store_true", help="Generate daily report")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly report")
    parser.add_argument("--date", help="Specific date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--output-dir", default="~/.openclaw/logs/anti-repeat-errors/reports", help="Output directory")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.weekly:
        date = args.date or datetime.now().strftime("%Y-%m-%d")
        output_file = generate_weekly_report(date, output_dir)
        print(f"Weekly report generated: {output_file}")
    
    else:
        # Default to daily report
        date = args.date or datetime.now().strftime("%Y-%m-%d")
        output_file = generate_daily_report(date, output_dir)
        print(f"Daily report generated: {output_file}")


if __name__ == "__main__":
    main()