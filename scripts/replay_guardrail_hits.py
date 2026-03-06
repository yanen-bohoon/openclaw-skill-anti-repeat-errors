#!/usr/bin/env python3
"""
Guardrail Hit Replay CLI

Usage:
    python replay_guardrail_hits.py --date 2024-01-15
    python replay_guardrail_hits.py --hit-id "2024-01-15T10-30-00_guard-git-operations_exec"
    python replay_guardrail_hits.py --session-key "agent:main:session:xxx"
    python replay_guardrail_hits.py --report --date 2024-01-15
"""

import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.hit_replay import HitReplay
from src.hit_logger import HitEventType


def main():
    parser = argparse.ArgumentParser(description="Guardrail Hit Replay CLI")
    
    # Query options
    parser.add_argument("--date", help="Filter by date (YYYY-MM-DD)")
    parser.add_argument("--hit-id", help="Replay specific hit by ID")
    parser.add_argument("--session-key", help="Filter by session key")
    parser.add_argument("--rule-id", help="Filter by rule ID")
    parser.add_argument("--tool-name", help="Filter by tool name")
    parser.add_argument("--action", help="Filter by action (block/rewrite/warn/log)")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    
    # Output options
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format")
    parser.add_argument("--report", action="store_true", help="Generate summary report")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    
    args = parser.parse_args()
    
    replay = HitReplay()
    output = []
    
    if args.report:
        # Generate report
        output.append(replay.generate_report(date=args.date, output_format=args.format))
    
    elif args.hit_id:
        # Replay specific hit
        trace = replay.replay_hit(args.hit_id)
        if trace:
            output.append(trace.format_trace(style=args.format))
        else:
            print(f"Hit not found: {args.hit_id}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_key:
        # Replay session
        traces = replay.replay_session(args.session_key, limit=args.limit)
        if not traces:
            print(f"No hits found for session: {args.session_key}", file=sys.stderr)
            sys.exit(0)
        
        for trace in traces:
            output.append(trace.format_trace(style=args.format))
            output.append("")  # Blank line between traces
    
    else:
        # Replay by date
        date = args.date
        if not date:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")
        
        traces = replay.replay_date(
            date=date,
            rule_id=args.rule_id,
            tool_name=args.tool_name,
            action=args.action,
            limit=args.limit,
        )
        
        if not traces:
            print(f"No hits found for date: {date}", file=sys.stderr)
            sys.exit(0)
        
        for trace in traces:
            output.append(trace.format_trace(style=args.format))
            output.append("")  # Blank line between traces
    
    # Output
    result = "\n".join(output)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Output written to: {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()