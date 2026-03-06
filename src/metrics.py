"""
Anti-Repeat-Errors Skill - Metrics Collector

Collects and aggregates injection metrics.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .logger import InjectionLog, InjectionEvent


@dataclass
class InjectionMetrics:
    """Injection metrics statistics"""
    
    # Counters
    total_hook_triggers: int = 0
    total_injections: int = 0
    total_skips: int = 0
    total_failures: int = 0
    
    # Skip reason distribution
    skip_reasons: dict[str, int] = field(default_factory=dict)
    
    # Rule hit statistics
    rule_hits: dict[str, int] = field(default_factory=dict)
    
    # Performance statistics
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    
    # Time window
    window_start: str = ""
    window_end: str = ""
    
    # Session tracking
    unique_sessions: set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Initialize mutable defaults"""
        if not self.skip_reasons:
            self.skip_reasons = {}
        if not self.rule_hits:
            self.rule_hits = {}
        if not self.unique_sessions:
            self.unique_sessions = set()
    
    def record_injection(self, rules: list[str], duration_ms: float, session_key: str = "") -> None:
        """
        Record a successful injection
        
        Args:
            rules: List of injected rule IDs
            duration_ms: Injection duration in milliseconds
            session_key: Session identifier
        """
        self.total_injections += 1
        self.total_duration_ms += duration_ms
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        
        for rule in rules:
            self.rule_hits[rule] = self.rule_hits.get(rule, 0) + 1
        
        if session_key:
            self.unique_sessions.add(session_key)
    
    def record_skip(self, reason: str, duration_ms: float, session_key: str = "") -> None:
        """
        Record a skipped injection
        
        Args:
            reason: Reason for skipping
            duration_ms: Duration in milliseconds
            session_key: Session identifier
        """
        self.total_skips += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1
        self.total_duration_ms += duration_ms
        
        if session_key:
            self.unique_sessions.add(session_key)
    
    def record_failure(self, error: str, duration_ms: float, session_key: str = "") -> None:
        """
        Record a failed injection
        
        Args:
            error: Error message
            duration_ms: Duration in milliseconds
            session_key: Session identifier
        """
        self.total_failures += 1
        self.total_duration_ms += duration_ms
        
        if session_key:
            self.unique_sessions.add(session_key)
    
    def record_hook_trigger(self, session_key: str = "") -> None:
        """
        Record a hook trigger event
        
        Args:
            session_key: Session identifier
        """
        self.total_hook_triggers += 1
        if session_key:
            self.unique_sessions.add(session_key)
    
    @property
    def injection_rate(self) -> float:
        """Calculate injection rate (injections / triggers)"""
        if self.total_hook_triggers == 0:
            return 0.0
        return self.total_injections / self.total_hook_triggers
    
    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration"""
        if self.total_hook_triggers == 0:
            return 0.0
        return self.total_duration_ms / self.total_hook_triggers
    
    @property
    def unique_session_count(self) -> int:
        """Get count of unique sessions"""
        return len(self.unique_sessions)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_hook_triggers": self.total_hook_triggers,
            "total_injections": self.total_injections,
            "total_skips": self.total_skips,
            "total_failures": self.total_failures,
            "injection_rate": round(self.injection_rate, 4),
            "skip_reasons": dict(self.skip_reasons),
            "rule_hits": dict(self.rule_hits),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "window_start": self.window_start,
            "window_end": self.window_end,
            "unique_sessions": self.unique_session_count,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def merge(self, other: "InjectionMetrics") -> "InjectionMetrics":
        """
        Merge another metrics instance into this one
        
        Args:
            other: Another InjectionMetrics instance
            
        Returns:
            Self for chaining
        """
        self.total_hook_triggers += other.total_hook_triggers
        self.total_injections += other.total_injections
        self.total_skips += other.total_skips
        self.total_failures += other.total_failures
        
        for reason, count in other.skip_reasons.items():
            self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + count
        
        for rule, count in other.rule_hits.items():
            self.rule_hits[rule] = self.rule_hits.get(rule, 0) + count
        
        self.total_duration_ms += other.total_duration_ms
        self.max_duration_ms = max(self.max_duration_ms, other.max_duration_ms)
        
        self.unique_sessions.update(other.unique_sessions)
        
        # Update time window
        if other.window_start and (not self.window_start or other.window_start < self.window_start):
            self.window_start = other.window_start
        if other.window_end and (not self.window_end or other.window_end > self.window_end):
            self.window_end = other.window_end
        
        return self
    
    def reset(self) -> None:
        """Reset all metrics"""
        self.total_hook_triggers = 0
        self.total_injections = 0
        self.total_skips = 0
        self.total_failures = 0
        self.skip_reasons.clear()
        self.rule_hits.clear()
        self.total_duration_ms = 0.0
        self.max_duration_ms = 0.0
        self.window_start = ""
        self.window_end = ""
        self.unique_sessions.clear()


class MetricsCollector:
    """
    Metrics collector for injection events
    
    Collects metrics from log entries and provides summary reports.
    """
    
    DEFAULT_METRICS_DIR = "~/.openclaw/logs/anti-repeat-errors"
    
    def __init__(self, metrics_dir: Optional[str | Path] = None):
        """
        Initialize the metrics collector
        
        Args:
            metrics_dir: Directory for metrics files
        """
        if metrics_dir is None:
            metrics_dir = self.DEFAULT_METRICS_DIR
        
        self.metrics_dir = Path(metrics_dir).expanduser()
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_metrics = InjectionMetrics()
        self._start_time: Optional[str] = None
    
    def start_window(self) -> None:
        """Start a new metrics collection window"""
        self._start_time = datetime.now().isoformat()
        self.current_metrics.window_start = self._start_time
    
    def end_window(self) -> None:
        """End the current metrics collection window"""
        self.current_metrics.window_end = datetime.now().isoformat()
    
    def update(self, log_entry: "InjectionLog") -> None:
        """
        Update metrics from a log entry
        
        Args:
            log_entry: InjectionLog instance
        """
        from .logger import InjectionEvent
        
        self.current_metrics.total_hook_triggers += 1
        
        event = log_entry.event
        session_key = log_entry.session_key
        
        if event == InjectionEvent.INJECTION_SUCCESS.value:
            self.current_metrics.record_injection(
                rules=log_entry.rules_matched or [],
                duration_ms=log_entry.duration_ms,
                session_key=session_key,
            )
        elif event == InjectionEvent.INJECTION_SKIPPED.value:
            self.current_metrics.record_skip(
                reason=log_entry.skip_reason or "unknown",
                duration_ms=log_entry.duration_ms,
                session_key=session_key,
            )
        elif event == InjectionEvent.INJECTION_FAILED.value:
            self.current_metrics.record_failure(
                error=log_entry.error or "unknown",
                duration_ms=log_entry.duration_ms,
                session_key=session_key,
            )
        elif event == InjectionEvent.HOOK_TRIGGERED.value:
            self.current_metrics.record_hook_trigger(session_key=session_key)
    
    def update_from_dict(self, data: dict) -> None:
        """
        Update metrics from a dictionary (parsed JSON log)
        
        Args:
            data: Dictionary with log entry data
        """
        event = data.get("event", "")
        session_key = data.get("session_key", "")
        
        self.current_metrics.total_hook_triggers += 1
        
        if event == "injection_success":
            self.current_metrics.record_injection(
                rules=data.get("rules_matched", []),
                duration_ms=data.get("duration_ms", 0),
                session_key=session_key,
            )
        elif event == "injection_skipped":
            self.current_metrics.record_skip(
                reason=data.get("skip_reason", "unknown"),
                duration_ms=data.get("duration_ms", 0),
                session_key=session_key,
            )
        elif event == "injection_failed":
            self.current_metrics.record_failure(
                error=data.get("error", "unknown"),
                duration_ms=data.get("duration_ms", 0),
                session_key=session_key,
            )
        elif event == "hook_triggered":
            self.current_metrics.record_hook_trigger(session_key=session_key)
    
    def save(self, filename: Optional[str] = None) -> Path:
        """
        Save current metrics to a file
        
        Args:
            filename: Optional filename, defaults to timestamp-based name
            
        Returns:
            Path to saved metrics file
        """
        self.end_window()
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_{timestamp}.json"
        
        metrics_file = self.metrics_dir / filename
        with open(metrics_file, "w", encoding="utf-8") as f:
            f.write(self.current_metrics.to_json())
        
        return metrics_file
    
    def load(self, filename: str) -> InjectionMetrics:
        """
        Load metrics from a file
        
        Args:
            filename: Metrics filename
            
        Returns:
            Loaded InjectionMetrics instance
        """
        metrics_file = self.metrics_dir / filename
        with open(metrics_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        metrics = InjectionMetrics(
            total_hook_triggers=data.get("total_hook_triggers", 0),
            total_injections=data.get("total_injections", 0),
            total_skips=data.get("total_skips", 0),
            total_failures=data.get("total_failures", 0),
            skip_reasons=data.get("skip_reasons", {}),
            rule_hits=data.get("rule_hits", {}),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            max_duration_ms=data.get("max_duration_ms", 0.0),
            window_start=data.get("window_start", ""),
            window_end=data.get("window_end", ""),
        )
        
        return metrics
    
    def get_summary(self) -> str:
        """
        Generate a human-readable summary
        
        Returns:
            Formatted summary string
        """
        m = self.current_metrics
        return f"""
Injection Metrics Summary
========================
Time window: {m.window_start or 'N/A'} to {m.window_end or 'now'}

Counts:
  Total hook triggers: {m.total_hook_triggers}
  Injections: {m.total_injections} ({m.injection_rate * 100:.1f}%)
  Skips: {m.total_skips}
  Failures: {m.total_failures}
  Unique sessions: {m.unique_session_count}

Top skip reasons:
{self._format_dict(m.skip_reasons, 5)}

Top hit rules:
{self._format_dict(m.rule_hits, 5)}

Performance:
  Avg duration: {m.avg_duration_ms:.2f}ms
  Max duration: {m.max_duration_ms:.2f}ms
"""
    
    def _format_dict(self, d: dict, top_n: int) -> str:
        """Format dictionary for display"""
        if not d:
            return "  (none)"
        items = sorted(d.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return "\n".join(f"  - {k}: {v}" for k, v in items)
    
    def reset(self) -> None:
        """Reset current metrics"""
        self.current_metrics.reset()
        self._start_time = None
    
    def get_top_rules(self, limit: int = 10) -> list[tuple[str, int]]:
        """
        Get top rules by hit count
        
        Args:
            limit: Maximum number of rules to return
            
        Returns:
            List of (rule_id, count) tuples
        """
        return sorted(
            self.current_metrics.rule_hits.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
    
    def get_top_skip_reasons(self, limit: int = 10) -> list[tuple[str, int]]:
        """
        Get top skip reasons by count
        
        Args:
            limit: Maximum number of reasons to return
            
        Returns:
            List of (reason, count) tuples
        """
        return sorted(
            self.current_metrics.skip_reasons.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]


# Module-level collector instance (lazy initialization)
_collector_instance: Optional[MetricsCollector] = None


def get_collector(metrics_dir: Optional[str | Path] = None) -> MetricsCollector:
    """
    Get or create the singleton collector instance
    
    Args:
        metrics_dir: Optional metrics directory path
        
    Returns:
        MetricsCollector instance
    """
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = MetricsCollector(metrics_dir=metrics_dir)
    return _collector_instance


def reset_collector() -> None:
    """Reset the collector instance (useful for testing)"""
    global _collector_instance
    _collector_instance = None