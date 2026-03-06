#!/usr/bin/env python3
"""
Anti-Repeat-Errors - Rule Validation Script

Validates rule files against schema and checks for common issues.

Usage:
    python scripts/validate_rules.py [--rules-dir PATH] [--verbose] [--check-ids]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add src to path for imports
script_dir = Path(__file__).parent
skill_dir = script_dir.parent
sys.path.insert(0, str(skill_dir))

import yaml

from src.models import RuleSet


class RuleValidator:
    """规则验证器"""

    def __init__(self, rules_dir: Path, verbose: bool = False):
        self.rules_dir = rules_dir
        self.verbose = verbose
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.valid_files: list[str] = []
        self.total_rules = 0
        self.all_rule_ids: dict[str, str] = {}  # id -> file path

    def log(self, msg: str, level: str = "info") -> None:
        """输出日志"""
        if level == "error":
            print(f"✗ {msg}")
        elif level == "warning":
            if self.verbose:
                print(f"⚠ {msg}")
        elif level == "success":
            print(f"✓ {msg}")
        elif self.verbose:
            print(f"  {msg}")

    def scan_yaml_files(self) -> list[Path]:
        """扫描所有 YAML 文件"""
        yaml_files = []

        subdirs = ["phases", "task-types", "global"]
        for subdir in subdirs:
            subdir_path = self.rules_dir / subdir
            if subdir_path.exists():
                yaml_files.extend(subdir_path.glob("*.yaml"))
                yaml_files.extend(subdir_path.glob("*.yml"))

        yaml_files.extend(self.rules_dir.glob("*.yaml"))
        yaml_files.extend(self.rules_dir.glob("*.yml"))

        return sorted(set(yaml_files))

    def validate_file(self, file_path: Path) -> bool:
        """
        验证单个规则文件

        Returns:
            是否有效
        """
        relative_path = file_path.relative_to(self.rules_dir)
        file_errors: list[str] = []

        # 1. Check file exists and is readable
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.log(f"{relative_path} - Error: Cannot read file: {e}", "error")
            self.errors.append(f"{relative_path}: Cannot read file: {e}")
            return False

        # 2. Check YAML syntax
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            self.log(f"{relative_path} - Error: Invalid YAML syntax: {e}", "error")
            self.errors.append(f"{relative_path}: Invalid YAML syntax: {e}")
            return False

        if data is None:
            self.log(f"{relative_path} - Error: Empty file", "error")
            self.errors.append(f"{relative_path}: Empty file")
            return False

        # 3. Check required fields
        required_fields = ["version", "kind", "name", "rules"]
        for field in required_fields:
            if field not in data:
                file_errors.append(f"Missing required field: {field}")

        # 4. Validate kind
        valid_kinds = ["phase", "task-type", "global"]
        if "kind" in data and data["kind"] not in valid_kinds:
            file_errors.append(f"Invalid kind: {data['kind']}. Must be one of {valid_kinds}")

        # 5. Validate rules array
        if "rules" in data:
            rules = data.get("rules", [])
            if not isinstance(rules, list):
                file_errors.append("'rules' must be an array")
            else:
                for i, rule in enumerate(rules):
                    rule_errors = self.validate_rule(rule, i, relative_path)
                    file_errors.extend(rule_errors)

        # 6. Try to parse as RuleSet
        if not file_errors:
            try:
                rule_set = RuleSet(**data)
                self.total_rules += len(rule_set.rules)

                # Check for duplicate IDs
                for rule in rule_set.rules:
                    if rule.id in self.all_rule_ids:
                        file_errors.append(
                            f"Duplicate rule ID: {rule.id} (also in {self.all_rule_ids[rule.id]})"
                        )
                    else:
                        self.all_rule_ids[rule.id] = str(relative_path)

            except Exception as e:
                file_errors.append(f"Pydantic validation error: {e}")

        # Report results
        if file_errors:
            self.log(f"{relative_path} - Error: {file_errors[0]}", "error")
            for err in file_errors[1:]:
                self.log(f"  {err}", "error")
            self.errors.extend([f"{relative_path}: {e}" for e in file_errors])
            return False
        else:
            rule_count = len(data.get("rules", []))
            self.log(f"{relative_path} - {rule_count} rules loaded", "success")
            self.valid_files.append(str(relative_path))
            return True

    def validate_rule(self, rule: dict, index: int, file_path: Path) -> list[str]:
        """
        验证单条规则

        Returns:
            错误列表
        """
        errors = []

        # Required fields
        required = ["id", "name", "content"]
        for field in required:
            if field not in rule:
                errors.append(f"Rule {index}: Missing required field '{field}'")

        # ID format
        if "id" in rule:
            import re

            if not re.match(r"^[a-zA-Z0-9_-]+$", str(rule["id"])):
                errors.append(f"Rule {index}: Invalid ID format: {rule['id']}")

        # Priority range
        if "priority" in rule:
            p = rule["priority"]
            if not isinstance(p, int) or p < 0 or p > 100:
                errors.append(f"Rule {index}: priority must be 0-100, got {p}")

        # Condition fields
        if "condition" in rule and isinstance(rule["condition"], dict):
            cond = rule["condition"]
            valid_cond_fields = ["phase", "task_type", "files_matching", "tools", "keywords"]
            for field in cond:
                if field not in valid_cond_fields:
                    self.warnings.append(f"{file_path}: Rule {index}: Unknown condition field: {field}")

            # Phase must be positive
            if "phase" in cond and isinstance(cond["phase"], int) and cond["phase"] < 1:
                errors.append(f"Rule {index}: phase must be >= 1")

        return errors

    def validate_schema_file(self) -> bool:
        """验证 schema.json 文件"""
        schema_path = self.rules_dir / "schema.json"
        if not schema_path.exists():
            self.log("schema.json not found (optional)", "warning")
            return True

        try:
            import json

            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)

            # Basic schema validation
            if "$schema" not in schema:
                self.warnings.append("schema.json: Missing $schema field")

            self.log("schema.json - valid JSON Schema", "success")
            return True

        except json.JSONDecodeError as e:
            self.errors.append(f"schema.json: Invalid JSON: {e}")
            self.log(f"schema.json - Invalid JSON: {e}", "error")
            return False
        except Exception as e:
            self.errors.append(f"schema.json: Error: {e}")
            self.log(f"schema.json - Error: {e}", "error")
            return False

    def run(self) -> bool:
        """
        运行完整验证

        Returns:
            是否全部有效
        """
        print(f"\nValidating rules in: {self.rules_dir}")
        print("=" * 60)

        # Validate schema
        self.validate_schema_file()

        # Scan and validate YAML files
        yaml_files = self.scan_yaml_files()

        if not yaml_files:
            self.log("No YAML rule files found", "warning")
            self.warnings.append("No YAML rule files found")
            return True

        print(f"\nFound {len(yaml_files)} rule files:")
        print("-" * 60)

        for file_path in yaml_files:
            self.validate_file(file_path)

        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Files scanned: {len(yaml_files)}")
        print(f"  Valid files: {len(self.valid_files)}")
        print(f"  Total rules: {self.total_rules}")
        print(f"  Errors: {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")

        if self.errors:
            print("\nErrors:")
            for err in self.errors:
                print(f"  ✗ {err}")

        if self.warnings and self.verbose:
            print("\nWarnings:")
            for warn in self.warnings:
                print(f"  ⚠ {warn}")

        if not self.errors:
            print("\n✓ All rules valid!")
            return True
        else:
            print("\n✗ Validation failed with errors")
            return False


def main():
    parser = argparse.ArgumentParser(description="Validate rule files")
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=None,
        help="Directory containing rules (default: skills/anti-repeat-errors/rules)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Determine rules directory
    if args.rules_dir:
        rules_dir = args.rules_dir
    else:
        # Default: skills/anti-repeat-errors/rules
        rules_dir = Path(__file__).parent.parent / "rules"

    if not rules_dir.exists():
        print(f"Error: Rules directory not found: {rules_dir}")
        sys.exit(1)

    validator = RuleValidator(rules_dir, verbose=args.verbose)
    success = validator.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()