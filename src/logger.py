"""
Anti-Repeat-Errors Skill - Structured Logger

Provides JSONL-format structured logging for injection events.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class InjectionEvent(Enum):
    """Injection event types"""
    HOOK_TRIGGERED = "hook_triggered"
    RULES_LOADED = "rules_loaded"
    RULES_MATCHED = "rules_matched"
    INJECTION_SUCCESS = "injection_success"
    INJECTION_SKIPPED = "injection_skipped"
    INJECTION_FAILED = "injection_failed"
    CONFIG_CHANGED = "config_changed"


@dataclass
class InjectionLog:
    """Single injection log record"""
    timestamp: str
    event: str
    session_key: str
    phase: Optional[int]
    task_type: Optional[str]
    
    # Rule matching
    rules_loaded: int = 0
    rules_matched: list[str] = field(default_factory=list)
    rules_injected: int = 0
    
    # Result
    injected: bool = False
    skip_reason: Optional[str] = None
    error: Optional[str] = None
    
    # Performance
    duration_ms: float = 0.0
    
    # Content preview (debug only)
    content_preview: Optional[str] = None
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        data = asdict(self)
        # Ensure rules_matched is not None for JSON serialization
        if data.get("rules_matched") is None:
            data["rules_matched"] = []
        return json.dumps(data, ensure_ascii=False)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class InjectionLogger:
    """
    Injection-specific logger
    
    Outputs:
    - JSONL format to file (machine-readable)
    - Human-readable format to console
    """
    
    DEFAULT_LOG_DIR = "~/.openclaw/logs/anti-repeat-errors"
    
    def __init__(
        self,
        log_dir: Optional[str | Path] = None,
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
    ):
        """
        Initialize the injection logger
        
        Args:
            log_dir: Directory for log files
            console_level: Console log level
            file_level: File log level
        """
        if log_dir is None:
            log_dir = self.DEFAULT_LOG_DIR
        
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("anti-repeat-errors")
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler - JSONL format
        log_file = self.log_dir / "injections.jsonl"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(fh)
        
        # Console handler - Human-readable
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter(
            "[%(asctime)s] [anti-repeat-errors] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.logger.addHandler(ch)
        
        self._log_file_path = log_file
    
    @property
    def log_file(self) -> Path:
        """Path to the log file"""
        return self._log_file_path
    
    def log(self, log_entry: InjectionLog) -> None:
        """
        Record a structured log entry
        
        Args:
            log_entry: InjectionLog instance
        """
        # Log as JSON to file
        self.logger.info(log_entry.to_json())
    
    def log_hook_triggered(
        self,
        session_key: str,
        phase: Optional[int] = None,
        task_type: Optional[str] = None,
    ) -> InjectionLog:
        """
        Log hook triggered event
        
        Args:
            session_key: Session identifier
            phase: Current phase number
            task_type: Current task type
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.HOOK_TRIGGERED.value,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
        )
        self.log(entry)
        return entry
    
    def log_rules_loaded(
        self,
        session_key: str,
        total_rules: int,
        source_files: list[str],
        load_time_ms: float,
        errors: Optional[list[str]] = None,
    ) -> InjectionLog:
        """
        Log rules loaded event
        
        Args:
            session_key: Session identifier
            total_rules: Total number of rules loaded
            source_files: List of source file paths
            load_time_ms: Load time in milliseconds
            errors: Optional list of errors
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.RULES_LOADED.value,
            session_key=session_key,
            phase=None,
            task_type=None,
            rules_loaded=total_rules,
            duration_ms=load_time_ms,
            error="; ".join(errors) if errors else None,
        )
        self.log(entry)
        return entry
    
    def log_rules_matched(
        self,
        session_key: str,
        phase: Optional[int],
        task_type: Optional[str],
        matched_rules: list[str],
        context: dict,
    ) -> InjectionLog:
        """
        Log rules matched event
        
        Args:
            session_key: Session identifier
            phase: Current phase
            task_type: Current task type
            matched_rules: List of matched rule IDs
            context: Matching context
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.RULES_MATCHED.value,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
            rules_matched=matched_rules,
            rules_injected=len(matched_rules),
        )
        self.log(entry)
        return entry
    
    def log_injection_success(
        self,
        session_key: str,
        phase: Optional[int],
        task_type: Optional[str],
        rules: list[str],
        duration_ms: float,
        content_preview: Optional[str] = None,
    ) -> InjectionLog:
        """
        Log successful injection event
        
        Args:
            session_key: Session identifier
            phase: Current phase
            task_type: Current task type
            rules: List of injected rule IDs
            duration_ms: Injection duration in milliseconds
            content_preview: Optional preview of injected content
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.INJECTION_SUCCESS.value,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
            rules_matched=rules,
            rules_injected=len(rules),
            injected=True,
            duration_ms=duration_ms,
            content_preview=content_preview[:500] if content_preview else None,
        )
        self.log(entry)
        return entry
    
    def log_injection_skipped(
        self,
        session_key: str,
        phase: Optional[int],
        task_type: Optional[str],
        reason: str,
        duration_ms: float,
    ) -> InjectionLog:
        """
        Log skipped injection event
        
        Args:
            session_key: Session identifier
            phase: Current phase
            task_type: Current task type
            reason: Reason for skipping
            duration_ms: Duration in milliseconds
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.INJECTION_SKIPPED.value,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
            injected=False,
            skip_reason=reason,
            duration_ms=duration_ms,
        )
        self.log(entry)
        return entry
    
    def log_injection_failed(
        self,
        session_key: str,
        phase: Optional[int],
        task_type: Optional[str],
        error: str,
        duration_ms: float,
    ) -> InjectionLog:
        """
        Log failed injection event
        
        Args:
            session_key: Session identifier
            phase: Current phase
            task_type: Current task type
            error: Error message
            duration_ms: Duration in milliseconds
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.INJECTION_FAILED.value,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
            injected=False,
            error=error,
            duration_ms=duration_ms,
        )
        self.log(entry)
        return entry
    
    def log_config_changed(
        self,
        session_key: str,
        config_key: str,
        old_value: str,
        new_value: str,
    ) -> InjectionLog:
        """
        Log configuration change event
        
        Args:
            session_key: Session identifier
            config_key: Configuration key that changed
            old_value: Previous value
            new_value: New value
            
        Returns:
            The created log entry
        """
        entry = InjectionLog(
            timestamp=datetime.now().isoformat(),
            event=InjectionEvent.CONFIG_CHANGED.value,
            session_key=session_key,
            phase=None,
            task_type=None,
        )
        self.log(entry)
        return entry


# Module-level logger instance (lazy initialization)
_logger_instance: Optional[InjectionLogger] = None


def get_logger(log_dir: Optional[str | Path] = None) -> InjectionLogger:
    """
    Get or create the singleton logger instance
    
    Args:
        log_dir: Optional log directory path
        
    Returns:
        InjectionLogger instance
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = InjectionLogger(log_dir=log_dir)
    return _logger_instance


def reset_logger() -> None:
    """Reset the logger instance (useful for testing)"""
    global _logger_instance
    _logger_instance = None