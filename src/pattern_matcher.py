"""
Anti-Repeat-Errors Skill - Pattern Matcher

High-performance pattern matching for tool call interception.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from .guardrail_models import (
        GuardrailAction,
        GuardrailRule,
        GuardrailRuleSet,
        ToolCallPattern,
    )
except ImportError:
    # Allow direct import for testing
    from guardrail_models import (
        GuardrailAction,
        GuardrailRule,
        GuardrailRuleSet,
        ToolCallPattern,
    )


@dataclass
class MatchResult:
    """匹配结果"""
    
    matched: bool
    rule: Optional[GuardrailRule] = None
    action: Optional[GuardrailAction] = None
    original_params: dict[str, Any] = field(default_factory=dict)
    result_params: dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None
    duration_ms: float = 0.0
    match_reason: Optional[str] = None


class PatternMatcher:
    """
    模式匹配引擎
    
    负责:
    1. 加载 guardrail 规则
    2. 对工具调用进行模式匹配
    3. 执行规则动作
    """
    
    def __init__(self, rules_dir: Optional[Path] = None):
        """
        初始化匹配引擎
        
        Args:
            rules_dir: guardrail 规则目录
        """
        if rules_dir is None:
            rules_dir = Path(__file__).parent.parent / "rules" / "guardrails"
        
        self.rules_dir = Path(rules_dir)
        self._rule_sets: list[GuardrailRuleSet] = []
        self._loaded = False
        self._load_errors: list[str] = []
    
    def load_rules(self, force_reload: bool = False) -> int:
        """
        加载 guardrail 规则
        
        Args:
            force_reload: 强制重新加载
            
        Returns:
            加载的规则数量
        """
        if self._loaded and not force_reload:
            return sum(len(rs.rules) for rs in self._rule_sets)
        
        self._rule_sets = []
        self._load_errors = []
        
        if not self.rules_dir.exists():
            self._loaded = True
            return 0
        
        for yaml_file in self.rules_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                
                if data and data.get("kind") == "guardrail":
                    rule_set = GuardrailRuleSet(**data)
                    self._rule_sets.append(rule_set)
            except Exception as e:
                error_msg = f"Error loading {yaml_file}: {e}"
                self._load_errors.append(error_msg)
                # 记录错误但继续加载其他文件
        
        self._loaded = True
        return sum(len(rs.rules) for rs in self._rule_sets)
    
    def get_load_errors(self) -> list[str]:
        """获取加载过程中的错误"""
        return self._load_errors.copy()
    
    def match(self, tool_name: str, tool_params: dict[str, Any], context: Optional[dict] = None) -> MatchResult:
        """
        对工具调用进行模式匹配
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数
            context: 可选的上下文信息（session_key, phase 等）
            
        Returns:
            MatchResult 对象
        """
        start = time.time()
        
        # 确保规则已加载
        if not self._loaded:
            self.load_rules()
        
        # 按优先级排序所有规则
        all_rules = []
        for rs in self._rule_sets:
            if rs.enabled:
                for rule in rs.rules:
                    if rule.enabled:
                        all_rules.append(rule)
        
        # 按优先级降序排序
        all_rules.sort(key=lambda r: -r.priority)
        
        # 找到第一个匹配的规则
        for rule in all_rules:
            matched, reason = rule.matches(tool_name, tool_params, context)
            if matched:
                # 执行规则动作
                action, result_params, message = rule.execute(tool_name, tool_params)
                
                duration_ms = (time.time() - start) * 1000
                
                return MatchResult(
                    matched=True,
                    rule=rule,
                    action=action,
                    original_params=tool_params,
                    result_params=result_params,
                    message=message,
                    duration_ms=duration_ms,
                    match_reason=reason,
                )
        
        # 无匹配
        duration_ms = (time.time() - start) * 1000
        return MatchResult(
            matched=False,
            duration_ms=duration_ms,
        )
    
    def match_all(self, tool_name: str, tool_params: dict[str, Any], context: Optional[dict] = None) -> list[MatchResult]:
        """
        对工具调用进行模式匹配，返回所有匹配结果
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数
            context: 可选的上下文信息
            
        Returns:
            所有匹配的 MatchResult 列表，按优先级排序
        """
        start = time.time()
        
        # 确保规则已加载
        if not self._loaded:
            self.load_rules()
        
        results = []
        
        # 按优先级排序所有规则
        all_rules = []
        for rs in self._rule_sets:
            if rs.enabled:
                for rule in rs.rules:
                    if rule.enabled:
                        all_rules.append(rule)
        
        # 按优先级降序排序
        all_rules.sort(key=lambda r: -r.priority)
        
        # 找到所有匹配的规则
        for rule in all_rules:
            matched, reason = rule.matches(tool_name, tool_params, context)
            if matched:
                action, result_params, message = rule.execute(tool_name, tool_params)
                duration_ms = (time.time() - start) * 1000
                
                results.append(MatchResult(
                    matched=True,
                    rule=rule,
                    action=action,
                    original_params=tool_params,
                    result_params=result_params,
                    message=message,
                    duration_ms=duration_ms,
                    match_reason=reason,
                ))
        
        return results
    
    def get_all_rules(self) -> list[GuardrailRule]:
        """获取所有规则"""
        if not self._loaded:
            self.load_rules()
        
        rules = []
        for rs in self._rule_sets:
            rules.extend(rs.rules)
        return rules
    
    def get_rules_by_tool(self, tool_name: str) -> list[GuardrailRule]:
        """获取针对特定工具的规则"""
        rules = []
        for rule in self.get_all_rules():
            if rule.enabled:
                pattern = rule.pattern
                if pattern.tool == tool_name:
                    rules.append(rule)
                elif pattern.tool_pattern:
                    if re.search(pattern.tool_pattern, tool_name):
                        rules.append(rule)
        return rules
    
    def get_rules_by_tag(self, tag: str) -> list[GuardrailRule]:
        """获取带有特定标签的规则"""
        rules = []
        for rule in self.get_all_rules():
            if rule.enabled and tag in rule.tags:
                rules.append(rule)
        return rules
    
    def get_rules_by_action(self, action: GuardrailAction) -> list[GuardrailRule]:
        """获取特定动作类型的规则"""
        rules = []
        for rule in self.get_all_rules():
            if rule.enabled and rule.action == action:
                rules.append(rule)
        return rules
    
    def get_stats(self) -> dict[str, Any]:
        """获取匹配器统计信息"""
        if not self._loaded:
            self.load_rules()
        
        total_rules = sum(len(rs.rules) for rs in self._rule_sets)
        enabled_rules = sum(len(rs.get_enabled_rules()) for rs in self._rule_sets)
        
        action_counts = {}
        for rule in self.get_all_rules():
            action_name = rule.action.value
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
        
        tag_counts = {}
        for rule in self.get_all_rules():
            for tag in rule.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        return {
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "rule_sets": len(self._rule_sets),
            "action_counts": action_counts,
            "tag_counts": tag_counts,
            "load_errors": len(self._load_errors),
        }


def create_matcher(rules_dir: Optional[Path] = None) -> PatternMatcher:
    """
    创建匹配器的便捷函数
    
    Args:
        rules_dir: guardrail 规则目录
        
    Returns:
        PatternMatcher 实例
    """
    return PatternMatcher(rules_dir=rules_dir)