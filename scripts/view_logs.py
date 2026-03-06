#!/usr/bin/env python3
"""
View and Analyze Injection Logs

Usage:
    python scripts/view_logs.py [--tail N] [--event TYPE] [--session KEY]
    python scripts/view_logs.py --summary
    python scripts/view_logs.py --export OUTPUT.json
    python scripts/view_logs.py --metrics
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default log directory
LOG_DIR = Path.home() / ".openclaw" / "logs" / "anti-repeat-errors"


def read_logs(
    limit: Optional[int] = None,
    event: Optional[str] = None,
    session: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> list[dict]:
    """
    Read and filter logs from JSONL file
    
    Args:
        limit: Maximum number of entries to return
        event: Filter by event type
        session: Filter by session key
        start_time: Filter entries after this time (ISO format)
        end_time: Filter entries before this time (ISO format)
        
    Returns:
        List of log entries
    """
    log_file = LOG_DIR / "injections.jsonl"
    if not log_file.exists():
        return []
    
    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                
                # Apply filters
                if event and entry.get("event") != event:
                    continue
                if session and entry.get("session_key") != session:
                    continue
                if start_time and entry.get("timestamp", "") < start_time:
                    continue
                if end_time and entry.get("timestamp", "") > end_time:
                    continue
                
                logs.append(entry)
            except json.JSONDecodeError:
                continue
    
    if limit:
        logs = logs[-limit:]
    return logs


def print_logs(logs: list[dict], verbose: bool = False) -> None:
    """
    Print logs in a formatted way
    
    Args:
        logs: List of log entries
        verbose: Whether to print full details
    """
    if not logs:
        print("No logs found")
        return
    
    for log in logs:
        ts = log.get("timestamp", "?")
        event = log.get("event", "?")
        session = log.get("session_key", "?")
        if len(session) > 25:
            session = session[:22] + "..."
        injected = log.get("injected", False)
        rules = log.get("rules_injected", 0)
        reason = log.get("skip_reason", "")
        duration = log.get("duration_ms", 0)
        phase = log.get("phase", "-")
        task_type = log.get("task_type", "-")
        
        if injected:
            status = f"✓ INJECTED {rules} rules"
        elif event == "injection_skipped":
            status = f"⊘ SKIP: {reason}"
        elif event == "injection_failed":
            status = f"✗ FAILED: {log.get('error', 'unknown')}"
        else:
            status = event
        
        if verbose:
            print(f"\n[{ts}]")
            print(f"  Session: {session}")
            print(f"  Phase: {phase} | Task: {task_type}")
            print(f"  Status: {status}")
            print(f"  Duration: {duration:.2f}ms")
            
            rules_matched = log.get("rules_matched", [])
            if rules_matched:
                print(f"  Rules: {', '.join(rules_matched)}")
            
            content_preview = log.get("content_preview")
            if content_preview:
                print(f"  Preview: {content_preview[:100]}...")
        else:
            print(f"[{ts}] {event} | {session} | {status} | {duration:.1f}ms")


def print_summary(logs: list[dict]) -> None:
    """
    Print statistical summary of logs
    
    Args:
        logs: List of log entries
    """
    if not logs:
        print("No logs found")
        return
    
    # Event counts
    events = Counter(log.get("event") for log in logs)
    
    # Skip reasons
    skip_reasons = Counter(
        log.get("skip_reason") for log in logs
        if log.get("event") == "injection_skipped" and log.get("skip_reason")
    )
    
    # Rule hits
    rule_hits = Counter()
    for log in logs:
        for rule in log.get("rules_matched") or []:
            rule_hits[rule] += 1
    
    # Duration stats
    durations = [log.get("duration_ms", 0) for log in logs if log.get("duration_ms")]
    avg_duration = sum(durations) / len(durations) if durations else 0
    max_duration = max(durations) if durations else 0
    
    # Session stats
    sessions = set(log.get("session_key") for log in logs if log.get("session_key"))
    
    # Phase stats
    phases = Counter(log.get("phase") for log in logs if log.get("phase"))
    
    # Task type stats
    task_types = Counter(log.get("task_type") for log in logs if log.get("task_type"))
    
    # Time range
    timestamps = [log.get("timestamp") for log in logs if log.get("timestamp")]
    time_range = f"{timestamps[0]} to {timestamps[-1]}" if timestamps else "N/A"
    
    # Calculate rates
    total = len(logs)
    injections = events.get("injection_success", 0)
    skips = events.get("injection_skipped", 0)
    failures = events.get("injection_failed", 0)
    triggers = events.get("hook_triggered", 0)
    
    injection_rate = (injections / triggers * 100) if triggers > 0 else 0
    
    print(f"""
Injection Log Summary
====================
Time range: {time_range}
Total entries: {total}
Unique sessions: {len(sessions)}

Events:
{format_counter(events)}

Rates:
  Injection rate: {injection_rate:.1f}% ({injections}/{triggers})
  Skip rate: {(skips/triggers*100) if triggers > 0 else 0:.1f}% ({skips}/{triggers})
  Failure rate: {(failures/triggers*100) if triggers > 0 else 0:.1f}% ({failures}/{triggers})

Skip reasons:
{format_counter(skip_reasons, 10)}

Top rules:
{format_counter(rule_hits, 10)}

Top phases:
{format_counter(phases, 5)}

Top task types:
{format_counter(task_types, 5)}

Performance:
  Avg duration: {avg_duration:.2f}ms
  Max duration: {max_duration:.2f}ms
""")


def format_counter(c: Counter, limit: int = 5) -> str:
    """Format a Counter for display"""
    if not c:
        return "  (none)"
    items = c.most_common(limit)
    return "\n".join(f"  {k}: {v}" for k, v in items)


def export_logs(logs: list[dict], output: str) -> None:
    """
    Export logs to a JSON file
    
    Args:
        logs: List of log entries
        output: Output file path
    """
    with open(output, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(logs)} entries to {output}")


def show_metrics(logs: list[dict]) -> None:
    """
    Show metrics from logs
    
    Args:
        logs: List of log entries
    """
    # Try to import metrics module
    script_dir = Path(__file__).parent
    src_dir = script_dir.parent / "src"
    
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))
        
        try:
            from metrics import MetricsCollector
            
            collector = MetricsCollector()
            collector.start_window()
            
            for log in logs:
                collector.update_from_dict(log)
            
            print(collector.get_summary())
            return
        except ImportError:
            pass
    
    # Fallback to basic metrics
    print_summary(logs)


def watch_logs(interval: int = 2) -> None:
    """
    Watch log file for new entries
    
    Args:
        interval: Polling interval in seconds
    """
    import time
    
    log_file = LOG_DIR / "injections.jsonl"
    if not log_file.exists():
        print(f"Log file not found: {log_file}")
        print("Waiting for logs...")
        while not log_file.exists():
            time.sleep(interval)
    
    print(f"Watching {log_file} (Ctrl+C to stop)...")
    print()
    
    # Track last position
    last_size = 0
    if log_file.exists():
        last_size = log_file.stat().st_size
    
    try:
        while True:
            time.sleep(interval)
            
            if not log_file.exists():
                continue
            
            current_size = log_file.stat().st_size
            
            if current_size > last_size:
                # Read new content
                with open(log_file, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    new_content = f.read()
                
                # Process new lines
                for line in new_content.strip().split("\n"):
                    if line:
                        try:
                            entry = json.loads(line)
                            ts = entry.get("timestamp", "?")
                            event = entry.get("event", "?")
                            session = entry.get("session_key", "?")[:20]
                            injected = entry.get("injected", False)
                            rules = entry.get("rules_injected", 0)
                            reason = entry.get("skip_reason", "")
                            
                            if injected:
                                status = f"✓ INJECTED {rules} rules"
                            elif reason:
                                status = f"⊘ {reason}"
                            else:
                                status = event
                            
                            print(f"[{ts}] {session} | {status}")
                        except json.JSONDecodeError:
                            print(f"[raw] {line[:100]}")
                
                last_size = current_size
            
    except KeyboardInterrupt:
        print("\nStopped watching logs")


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="View and analyze injection logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --tail 10           # Last 10 entries
  %(prog)s --summary           # Statistical summary
  %(prog)s --event injection_success  # Only successful injections
  %(prog)s --session agent:main:main  # Filter by session
  %(prog)s --export logs.json  # Export to JSON
  %(prog)s --watch             # Watch for new entries
"""
    )
    
    # Output options
    parser.add_argument("--tail", type=int, help="Show last N entries")
    parser.add_argument("--summary", action="store_true", help="Show statistical summary")
    parser.add_argument("--metrics", action="store_true", help="Show detailed metrics")
    parser.add_argument("--export", metavar="FILE", help="Export logs to JSON file")
    parser.add_argument("--watch", action="store_true", help="Watch for new log entries")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    # Filter options
    parser.add_argument("--event", help="Filter by event type")
    parser.add_argument("--session", help="Filter by session key")
    parser.add_argument("--start", metavar="TIME", help="Start time (ISO format)")
    parser.add_argument("--end", metavar="TIME", help="End time (ISO format)")
    
    args = parser.parse_args()
    
    # Handle watch mode
    if args.watch:
        watch_logs()
        return 0
    
    # Read logs
    logs = read_logs(
        limit=args.tail,
        event=args.event,
        session=args.session,
        start_time=args.start,
        end_time=args.end,
    )
    
    # Handle different output modes
    if args.export:
        export_logs(logs, args.export)
    elif args.metrics:
        show_metrics(logs)
    elif args.summary:
        print_summary(logs)
    else:
        print_logs(logs, verbose=args.verbose)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())