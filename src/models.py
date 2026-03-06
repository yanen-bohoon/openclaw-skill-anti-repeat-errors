"""
Anti-Repeat-Errors Skill - Data Models

Pydantic models for rule loading and validation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class RuleCondition(BaseModel):
    """规则触发条件"""

    phase: Optional[int] = None
    task_type: Optional[str] = None
    files_matching: Optional[list[str]] = None
    tools: Optional[list[str]] = None
    keywords: Optional[list[str]] = None

    @field_validator("phase")
    @classmethod
    def phase_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("phase must be >= 1")
        return v

    def matches(self, context: dict[str, Any]) -> bool:
        """
        检查上下文是否匹配此条件

        Args:
            context: 包含 phase, task_type, files, tools, message 等字段的上下文

        Returns:
            是否匹配
        """
        # 如果没有任何条件，则匹配所有
        if not any([self.phase, self.task_type, self.files_matching, self.tools, self.keywords]):
            return True

        # 检查 phase
        if self.phase is not None:
            ctx_phase = context.get("phase")
            if ctx_phase != self.phase:
                return False

        # 检查 task_type
        if self.task_type is not None:
            ctx_task_type = context.get("task_type")
            if ctx_task_type != self.task_type:
                return False

        # 检查 files_matching (glob 匹配)
        if self.files_matching:
            import fnmatch

            ctx_files = context.get("files", [])
            if not ctx_files:
                return False
            matched = False
            for pattern in self.files_matching:
                for f in ctx_files:
                    # 处理 ** 开头的模式
                    if pattern.startswith("**/"):
                        # **/name 应该匹配 name 和 any/path/name
                        suffix = pattern[3:]
                        if fnmatch.fnmatch(str(f), suffix) or fnmatch.fnmatch(str(f), pattern):
                            matched = True
                            break
                    elif fnmatch.fnmatch(str(f), pattern):
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                return False

        # 检查 tools
        if self.tools:
            ctx_tools = context.get("tools", [])
            if not any(t in ctx_tools for t in self.tools):
                return False

        # 检查 keywords
        if self.keywords:
            ctx_message = context.get("message", "")
            if not any(kw.lower() in ctx_message.lower() for kw in self.keywords):
                return False

        return True


class Rule(BaseModel):
    """单条规则"""

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    condition: RuleCondition = Field(default_factory=RuleCondition)
    content: str = Field(..., min_length=1)
    priority: int = Field(default=50, ge=0, le=100)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_pattern(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("id must contain only alphanumeric, underscore, and hyphen characters")
        return v

    def matches(self, context: dict[str, Any]) -> bool:
        """检查规则是否匹配上下文"""
        if not self.enabled:
            return False
        return self.condition.matches(context)


class RuleSet(BaseModel):
    """规则集（单文件）"""

    version: str = Field(default="1.0")
    kind: Literal["phase", "task-type", "global"]
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    enabled: bool = True
    rules: list[Rule] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def version_format(cls, v: str) -> str:
        import re

        if not re.match(r"^\d+\.\d+$", v):
            raise ValueError("version must be in format X.Y (e.g., 1.0)")
        return v

    def get_enabled_rules(self) -> list[Rule]:
        """获取启用的规则"""
        if not self.enabled:
            return []
        return [r for r in self.rules if r.enabled]

    def get_rules_by_phase(self, phase: int) -> list[Rule]:
        """获取匹配指定阶段的规则"""
        return [r for r in self.get_enabled_rules() if r.condition.phase == phase]


class LoadedRules(BaseModel):
    """运行时加载的规则集合"""

    rule_sets: list[RuleSet] = Field(default_factory=list)
    total_rules: int = 0
    load_time: float = 0.0
    source_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    load_timestamp: float = Field(default_factory=time.time)

    def get_all_rules(self, enabled_only: bool = True) -> list[Rule]:
        """获取所有规则"""
        rules = []
        for rs in self.rule_sets:
            if enabled_only and not rs.enabled:
                continue
            for r in rs.rules:
                if enabled_only and not r.enabled:
                    continue
                rules.append(r)
        return rules

    def get_rules_by_phase(self, phase: int) -> list[Rule]:
        """获取匹配指定阶段的规则"""
        rules = []
        for rs in self.rule_sets:
            if not rs.enabled:
                continue
            rules.extend(rs.get_rules_by_phase(phase))
        return sorted(rules, key=lambda r: -r.priority)

    def get_rules_by_task_type(self, task_type: str) -> list[Rule]:
        """获取匹配指定任务类型的规则"""
        rules = []
        for rs in self.rule_sets:
            if not rs.enabled:
                continue
            for r in rs.get_enabled_rules():
                if r.condition.task_type == task_type:
                    rules.append(r)
        return sorted(rules, key=lambda r: -r.priority)

    def get_global_rules(self) -> list[Rule]:
        """获取全局规则"""
        rules = []
        for rs in self.rule_sets:
            if not rs.enabled or rs.kind != "global":
                continue
            rules.extend(rs.get_enabled_rules())
        return sorted(rules, key=lambda r: -r.priority)

    def get_matching_rules(self, context: dict[str, Any]) -> list[Rule]:
        """
        获取匹配当前上下文的所有规则

        合并策略: global + phase + task-type，按优先级排序
        """
        rules = []

        for rs in self.rule_sets:
            if not rs.enabled:
                continue

            for r in rs.rules:
                if r.enabled and r.matches(context):
                    rules.append(r)

        # 按优先级降序排序
        return sorted(rules, key=lambda r: -r.priority)


class RuleLoaderConfig(BaseModel):
    """规则加载器配置"""

    rules_dir: Path
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    validate_schema: bool = True
    fail_on_error: bool = False  # False = 跳过无效文件并记录错误