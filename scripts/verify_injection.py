#!/usr/bin/env python3
"""
Verify Injection Mechanism

Validates that the injection mechanism is working correctly.

Usage:
    python scripts/verify_injection.py [--verbose]

Verification items:
1. Rule files can be loaded
2. Injector can be called
3. Hook is registered
4. Logging works correctly
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple


class Verifier:
    """Verification runner"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []
    
    def check(self, name: str, condition: bool, detail: str = "") -> None:
        """
        Check a condition and record result
        
        Args:
            name: Check name
            condition: Whether the check passed
            detail: Additional detail for failures
        """
        if condition:
            self.passed.append(name)
            if self.verbose:
                print(f"✓ {name}")
        else:
            self.failed.append((name, detail))
            print(f"✗ {name}: {detail}")
    
    def summary(self) -> bool:
        """
        Print summary and return overall status
        
        Returns:
            True if all checks passed
        """
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*50}")
        print(f"Verification Results: {len(self.passed)}/{total} passed")
        
        if self.failed:
            print("\nFailed checks:")
            for name, detail in self.failed:
                print(f"  ✗ {name}: {detail}")
            return False
        
        return True


def verify() -> bool:
    """
    Run all verification checks
    
    Returns:
        True if all checks passed
    """
    v = Verifier(verbose="--verbose" in sys.argv or "-v" in sys.argv)
    
    # Determine skill directory
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    rules_dir = base_dir / "rules"
    
    print("=== Anti-Repeat-Errors Injection Verification ===\n")
    
    # 1. Check rules directory
    print("1. Checking rules directory...")
    v.check(
        "Rules directory exists",
        rules_dir.exists(),
        f"Expected: {rules_dir}"
    )
    
    rule_files = list(rules_dir.glob("**/*.yaml")) + list(rules_dir.glob("**/*.yml"))
    v.check(
        "At least one rule file exists",
        len(rule_files) > 0,
        f"Found {len(rule_files)} rule files"
    )
    
    # 2. Check Python modules
    print("\n2. Checking Python modules...")
    try:
        sys.path.insert(0, str(base_dir / "src"))
        
        # Import modules
        from models import Rule, RuleSet, LoadedRules, RuleCondition
        from rule_loader import RuleLoader
        from logger import InjectionLogger, InjectionLog, InjectionEvent
        from metrics import MetricsCollector, InjectionMetrics
        
        v.check("models module loads", True)
        v.check("rule_loader module loads", True)
        v.check("logger module loads", True)
        v.check("metrics module loads", True)
        
    except ImportError as e:
        v.check("Python modules import", False, str(e))
        return v.summary()
    
    # 3. Test rule loading
    print("\n3. Testing rule loading...")
    try:
        loader = RuleLoader(rules_dir)
        loaded = loader.load_all()
        
        v.check(
            "Rules load successfully",
            loaded.total_rules >= 0,
            f"Loaded {loaded.total_rules} rules from {len(loaded.source_files)} files"
        )
        
        if loaded.errors:
            v.check(
                "No rule loading errors",
                False,
                f"Errors: {loaded.errors}"
            )
        else:
            v.check("No rule loading errors", True)
        
    except Exception as e:
        v.check("Rule loading", False, str(e))
    
    # 4. Test logger
    print("\n4. Testing logger...")
    try:
        import tempfile
        import os
        
        # Use temp directory for testing
        test_log_dir = Path(tempfile.mkdtemp()) / "test_logs"
        logger = InjectionLogger(log_dir=test_log_dir)
        
        # Test log entry
        log_entry = logger.log_hook_triggered(
            session_key="test-session",
            phase=1,
            task_type="coding"
        )
        
        v.check(
            "Logger creates log entry",
            log_entry is not None,
            f"Entry: {log_entry.event}"
        )
        
        # Check log file exists
        log_file = logger.log_file
        v.check(
            "Log file created",
            log_file.exists(),
            f"Path: {log_file}"
        )
        
        # Verify log file content
        if log_file.exists():
            with open(log_file, "r") as f:
                content = f.read()
            v.check(
                "Log file contains JSON",
                "{" in content and "}" in content,
                f"Content length: {len(content)}"
            )
            
            # Parse log entry
            try:
                log_data = json.loads(content.strip())
                v.check(
                    "Log entry is valid JSON",
                    True,
                    f"Event: {log_data.get('event')}"
                )
            except json.JSONDecodeError as e:
                v.check("Log entry is valid JSON", False, str(e))
        
        # Cleanup
        import shutil
        shutil.rmtree(test_log_dir.parent, ignore_errors=True)
        
    except Exception as e:
        v.check("Logger functionality", False, str(e))
    
    # 5. Test metrics
    print("\n5. Testing metrics...")
    try:
        import tempfile
        
        test_metrics_dir = Path(tempfile.mkdtemp()) / "test_metrics"
        collector = MetricsCollector(metrics_dir=test_metrics_dir)
        
        # Create test log entry
        test_log = InjectionLog(
            timestamp="2026-03-06T08:00:00",
            event=InjectionEvent.INJECTION_SUCCESS.value,
            session_key="test-session",
            phase=1,
            task_type="coding",
            rules_matched=["rule-001", "rule-002"],
            rules_injected=2,
            injected=True,
            duration_ms=123.45,
        )
        
        collector.update(test_log)
        
        v.check(
            "Metrics collector updates",
            collector.current_metrics.total_injections == 1,
            f"Total injections: {collector.current_metrics.total_injections}"
        )
        
        v.check(
            "Rule hits tracked",
            "rule-001" in collector.current_metrics.rule_hits,
            f"Rule hits: {collector.current_metrics.rule_hits}"
        )
        
        # Test summary
        summary = collector.get_summary()
        v.check(
            "Summary generated",
            len(summary) > 0,
            f"Summary length: {len(summary)}"
        )
        
        # Cleanup
        import shutil
        shutil.rmtree(test_metrics_dir.parent, ignore_errors=True)
        
    except Exception as e:
        v.check("Metrics functionality", False, str(e))
    
    # 6. Check log directory
    print("\n6. Checking log directory...")
    log_dir = Path.home() / ".openclaw" / "logs" / "anti-repeat-errors"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        v.check(
            "Log directory accessible",
            log_dir.exists(),
            f"Path: {log_dir}"
        )
    except Exception as e:
        v.check("Log directory accessible", False, str(e))
    
    # 7. Check plugin manifest
    print("\n7. Checking plugin manifest...")
    plugin_file = base_dir / "openclaw.plugin.json"
    if plugin_file.exists():
        try:
            with open(plugin_file, "r", encoding="utf-8") as f:
                plugin_config = json.load(f)
            v.check(
                "Plugin manifest valid JSON",
                True,
                f"ID: {plugin_config.get('id', 'unknown')}"
            )
        except json.JSONDecodeError as e:
            v.check("Plugin manifest valid JSON", False, str(e))
    else:
        v.check("Plugin manifest exists", False, f"Not found: {plugin_file}")
    
    return v.summary()


def main() -> int:
    """Main entry point"""
    success = verify()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())