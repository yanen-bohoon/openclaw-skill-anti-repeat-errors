"""
Anti-Repeat-Errors Skill - Rule Injector

Core injection logic that matches rules and generates injection content.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from .config import InjectorConfig, HookContext
from .rule_loader import RuleLoader
from .models import Rule


@dataclass
class InjectionResult:
    """注入结果"""

    injected: bool
    rules_count: int
    content: Optional[str] = None
    matched_rules: list[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        return asdict(self)


class RuleInjector:
    """
    规则注入器

    负责:
    1. 根据 Hook 上下文匹配规则
    2. 格式化规则为注入内容
    3. 返回注入结果
    """

    def __init__(self, config: InjectorConfig):
        self.config = config
        self._loader: Optional[RuleLoader] = None
        self._logger = logging.getLogger("anti-repeat-errors.injector")

        # 设置日志级别
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        self._logger.setLevel(level)

    @property
    def loader(self) -> RuleLoader:
        """延迟初始化规则加载器"""
        if self._loader is None:
            self._loader = RuleLoader(
                rules_dir=self.config.rules_dir,
                cache_enabled=self.config.cache_enabled,
                cache_ttl_seconds=self.config.cache_ttl_seconds,
            )
        return self._loader

    def reload_rules(self) -> int:
        """
        强制重新加载规则

        Returns:
            加载的规则数量
        """
        loaded = self.loader.reload()
        self._logger.info(f"Reloaded {loaded.total_rules} rules from {self.config.rules_dir}")
        return loaded.total_rules

    def build_injection_content(self, context: HookContext | dict[str, Any]) -> InjectionResult:
        """
        根据上下文构建注入内容

        Args:
            context: Hook 上下文，包含:
                - session_key: str
                - phase: Optional[int]
                - task_type: Optional[str]
                - recent_tools: List[str]
                - recent_files: List[str]
                - message_content: str (用户输入)

        Returns:
            InjectionResult 对象
        """
        start = time.time()

        # 检查是否启用
        if not self.config.is_effectively_enabled():
            skip_reason = self.config.get_skip_reason()
            self._logger.info(f"Injection skipped: {skip_reason}")
            return InjectionResult(
                injected=False,
                rules_count=0,
                content=None,
                matched_rules=[],
                skipped_reason=skip_reason or "Injection disabled",
                duration_ms=0,
            )

        # 规范化上下文
        ctx = self._normalize_context(context)

        try:
            # 获取匹配的规则
            matched = self._get_matching_rules(ctx)

            if not matched:
                reason = "No rules matched current context"
                self._logger.debug(f"No injection: {reason}")
                self._logger.debug(
                    f"Context: phase={ctx.get('phase')}, task_type={ctx.get('task_type')}, "
                    f"files={len(ctx.get('files', []))}, tools={ctx.get('tools', [])}"
                )
                return InjectionResult(
                    injected=False,
                    rules_count=0,
                    content=None,
                    matched_rules=[],
                    skipped_reason=reason,
                    duration_ms=(time.time() - start) * 1000,
                )

            # 构建注入内容
            content = self._format_rules_for_injection(matched)

            duration_ms = (time.time() - start) * 1000
            matched_ids = [r.id for r in matched]

            self._logger.info(
                f"Injected {len(matched)} rules: {', '.join(matched_ids)} ({duration_ms:.2f}ms)"
            )

            return InjectionResult(
                injected=True,
                rules_count=len(matched),
                content=content,
                matched_rules=matched_ids,
                skipped_reason=None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            self._logger.error(f"Injection failed: {e}")
            return InjectionResult(
                injected=False,
                rules_count=0,
                content=None,
                matched_rules=[],
                skipped_reason=f"Error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
                errors=[str(e)],
            )

    def _normalize_context(self, context: HookContext | dict[str, Any]) -> dict[str, Any]:
        """规范化上下文字典"""
        if isinstance(context, HookContext):
            ctx = {
                "session_key": context.session_key,
                "phase": context.phase,
                "task_type": context.task_type,
                "tools": context.recent_tools,
                "files": context.recent_files,
                "message": context.message_content,
                "project_dir": context.project_dir,
                "workspace_dir": context.workspace_dir,
            }
        else:
            ctx = {
                "session_key": context.get("session_key"),
                "phase": context.get("phase"),
                "task_type": context.get("task_type"),
                "tools": context.get("recent_tools", context.get("tools", [])),
                "files": context.get("recent_files", context.get("files", [])),
                "message": context.get("message_content", context.get("message", "")),
                "project_dir": context.get("project_dir"),
                "workspace_dir": context.get("workspace_dir"),
            }

        return ctx

    def _get_matching_rules(self, context: dict[str, Any]) -> list[Rule]:
        """获取匹配当前上下文的规则"""
        try:
            return self.loader.get_matching_rules(context)
        except Exception as e:
            self._logger.error(f"Failed to load rules: {e}")
            return []

    def _format_rules_for_injection(self, rules: list[Rule]) -> str:
        """
        格式化规则为注入文本

        使用 XML 格式，便于调试和解析
        """
        lines = [
            "<!-- anti-repeat-errors: injected rules -->",
            "<injected_rules>",
            "<!-- These rules are proactively injected to prevent repeated errors -->",
            "",
        ]

        for rule in rules:
            lines.append(f'<rule id="{rule.id}" priority="{rule.priority}">')
            lines.append(f"  <name>{rule.name}</name>")
            if rule.tags:
                lines.append(f"  <tags>{', '.join(rule.tags)}</tags>")
            lines.append("  <content>")
            # 缩进规则内容
            content_lines = rule.content.strip().split("\n")
            for line in content_lines:
                lines.append(f"    {line}")
            lines.append("  </content>")
            lines.append("</rule>")
            lines.append("")

        lines.append("</injected_rules>")
        return "\n".join(lines)


def create_injector(
    config: Optional[InjectorConfig] = None, **kwargs
) -> RuleInjector:
    """
    创建规则注入器的便捷函数

    Args:
        config: InjectorConfig 对象，如果为 None 则使用默认配置
        **kwargs: 传递给 InjectorConfig 的参数

    Returns:
        RuleInjector 实例
    """
    if config is None:
        config = InjectorConfig(**kwargs)
    return RuleInjector(config)


# 用于 JSON 输出的便捷函数
def build_injection_json(context: dict[str, Any], config_dict: dict[str, Any]) -> str:
    """
    构建注入内容并返回 JSON 字符串

    用于 CLI 调用
    """
    config = InjectorConfig(**config_dict)
    injector = RuleInjector(config)
    result = injector.build_injection_content(context)
    return json.dumps(result.to_dict())