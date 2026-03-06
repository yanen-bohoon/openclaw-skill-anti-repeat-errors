"""
Anti-Repeat-Errors Skill - Rule Loader

Loads and manages rules from YAML files.
"""

from __future__ import annotations

import fnmatch
import json
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import ValidationError

from .models import LoadedRules, Rule, RuleLoaderConfig, RuleSet


class RuleLoader:
    """
    规则加载器

    支持:
    - 从目录加载所有规则文件
    - 按 phase/task-type 筛选
    - 缓存和热重载
    - 错误容忍（无效规则不阻塞加载）
    """

    def __init__(
        self,
        rules_dir: Path | str,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 300,
        validate_schema: bool = True,
        fail_on_error: bool = False,
    ):
        """
        初始化规则加载器

        Args:
            rules_dir: 规则文件目录
            cache_enabled: 是否启用缓存
            cache_ttl_seconds: 缓存有效期（秒）
            validate_schema: 是否验证 JSON Schema
            fail_on_error: 是否在遇到错误时抛出异常（False 则记录错误并跳过）
        """
        self.rules_dir = Path(rules_dir)
        self.cache_enabled = cache_enabled
        self.cache_ttl_seconds = cache_ttl_seconds
        self.validate_schema = validate_schema
        self.fail_on_error = fail_on_error

        self._cache: Optional[LoadedRules] = None
        self._cache_time: float = 0
        self._schema: Optional[dict] = None

    def _load_schema(self) -> Optional[dict]:
        """加载 JSON Schema"""
        if not self.validate_schema:
            return None

        schema_path = self.rules_dir / "schema.json"
        if not schema_path.exists():
            return None

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RuleLoader] Warning: Failed to load schema: {e}")
            return None

    def _validate_against_schema(self, data: dict, schema: Optional[dict]) -> list[str]:
        """验证数据是否符合 schema"""
        errors = []
        if not schema:
            return errors

        try:
            import jsonschema

            jsonschema.validate(data, schema)
        except ImportError:
            # jsonschema not installed, skip validation
            pass
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")
        except Exception as e:
            errors.append(f"Validation error: {e}")

        return errors

    def _load_yaml_file(self, file_path: Path) -> tuple[Optional[RuleSet], list[str]]:
        """
        加载单个 YAML 文件

        Returns:
            (RuleSet or None, list of errors)
        """
        errors = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                errors.append(f"Empty file: {file_path}")
                return None, errors

            # Schema validation
            if self.validate_schema and self._schema:
                schema_errors = self._validate_against_schema(data, self._schema)
                if schema_errors:
                    errors.extend(schema_errors)
                    if self.fail_on_error:
                        return None, errors

            # Parse into RuleSet
            try:
                rule_set = RuleSet(**data)
                return rule_set, errors
            except ValidationError as e:
                errors.append(f"Pydantic validation error in {file_path}: {e}")
                return None, errors

        except yaml.YAMLError as e:
            errors.append(f"YAML parse error in {file_path}: {e}")
            return None, errors
        except Exception as e:
            errors.append(f"Error loading {file_path}: {e}")
            return None, errors

    def _scan_rule_files(self) -> list[Path]:
        """扫描规则目录中的所有 YAML 文件"""
        yaml_files = []

        if not self.rules_dir.exists():
            return yaml_files

        # 定义扫描的子目录
        subdirs = ["phases", "task-types", "global"]

        for subdir in subdirs:
            subdir_path = self.rules_dir / subdir
            if subdir_path.exists() and subdir_path.is_dir():
                yaml_files.extend(subdir_path.glob("*.yaml"))
                yaml_files.extend(subdir_path.glob("*.yml"))

        # 也扫描根目录
        yaml_files.extend(self.rules_dir.glob("*.yaml"))
        yaml_files.extend(self.rules_dir.glob("*.yml"))

        return sorted(set(yaml_files))

    def load_all(self, force_reload: bool = False) -> LoadedRules:
        """
        加载所有规则

        Args:
            force_reload: 强制重新加载（忽略缓存）

        Returns:
            LoadedRules 对象
        """
        # 检查缓存
        if self.cache_enabled and self._cache is not None and not force_reload:
            cache_age = time.time() - self._cache_time
            if cache_age < self.cache_ttl_seconds:
                return self._cache

        start_time = time.time()

        # Load schema
        self._schema = self._load_schema()

        # Scan and load files
        yaml_files = self._scan_rule_files()
        rule_sets: list[RuleSet] = []
        source_files: list[str] = []
        errors: list[str] = []

        for file_path in yaml_files:
            rule_set, file_errors = self._load_yaml_file(file_path)

            if file_errors:
                errors.extend(file_errors)
                if self.fail_on_error:
                    break

            if rule_set:
                rule_sets.append(rule_set)
                source_files.append(str(file_path.relative_to(self.rules_dir)))

        # Build result
        load_time = time.time() - start_time
        total_rules = sum(len(rs.rules) for rs in rule_sets)

        result = LoadedRules(
            rule_sets=rule_sets,
            total_rules=total_rules,
            load_time=load_time,
            source_files=source_files,
            errors=errors,
        )

        # Update cache
        if self.cache_enabled:
            self._cache = result
            self._cache_time = time.time()

        return result

    def reload(self) -> LoadedRules:
        """强制重新加载"""
        return self.load_all(force_reload=True)

    def load_by_kind(self, kind: str) -> list[RuleSet]:
        """
        按类型加载规则集

        Args:
            kind: "phase", "task-type", or "global"

        Returns:
            匹配的 RuleSet 列表
        """
        loaded = self.load_all()
        return [rs for rs in loaded.rule_sets if rs.kind == kind and rs.enabled]

    def load_by_phase(self, phase: int) -> list[Rule]:
        """
        加载指定阶段的规则

        Args:
            phase: 阶段编号

        Returns:
            匹配的 Rule 列表，按优先级排序
        """
        loaded = self.load_all()
        return loaded.get_rules_by_phase(phase)

    def load_by_task_type(self, task_type: str) -> list[Rule]:
        """
        加载指定任务类型的规则

        Args:
            task_type: 任务类型名称

        Returns:
            匹配的 Rule 列表，按优先级排序
        """
        loaded = self.load_all()
        return loaded.get_rules_by_task_type(task_type)

    def get_global_rules(self) -> list[Rule]:
        """获取全局规则"""
        loaded = self.load_all()
        return loaded.get_global_rules()

    def get_matching_rules(self, context: dict[str, Any]) -> list[Rule]:
        """
        获取匹配当前上下文的规则

        Args:
            context: 上下文字典，可包含:
                - phase: int
                - task_type: str
                - files: list[str]
                - tools: list[str]
                - message: str

        Returns:
            匹配的 Rule 列表，按优先级降序排序
        """
        loaded = self.load_all()
        return loaded.get_matching_rules(context)

    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache = None
        self._cache_time = 0

    def get_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        """
        根据 ID 获取规则

        Args:
            rule_id: 规则 ID

        Returns:
            Rule 对象或 None
        """
        loaded = self.load_all()
        for rs in loaded.rule_sets:
            for r in rs.rules:
                if r.id == rule_id:
                    return r
        return None

    def get_all_rule_ids(self) -> list[str]:
        """获取所有规则 ID（用于唯一性检查）"""
        loaded = self.load_all()
        return [r.id for rs in loaded.rule_sets for r in rs.rules]


def create_loader(
    rules_dir: Optional[Path | str] = None,
    cache_enabled: bool = True,
) -> RuleLoader:
    """
    创建规则加载器的便捷函数

    Args:
        rules_dir: 规则目录，默认为 skills/anti-repeat-errors/rules
        cache_enabled: 是否启用缓存

    Returns:
        RuleLoader 实例
    """
    if rules_dir is None:
        # 默认路径
        rules_dir = Path(__file__).parent.parent / "rules"

    return RuleLoader(rules_dir=rules_dir, cache_enabled=cache_enabled)