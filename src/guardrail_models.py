"""
Anti-Repeat-Errors Skill - Guardrail Models

Extended models for before_tool_call interception.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class GuardrailAction(str, Enum):
    """拦截动作类型"""
    REWRITE = "rewrite"  # 改写工具调用参数
    BLOCK = "block"      # 阻断调用，返回错误信息
    WARN = "warn"        # 警告但允许继续
    LOG = "log"          # 仅记录日志


class ToolCallPattern(BaseModel):
    """工具调用匹配模式"""
    
    # 工具名称匹配
    tool: Optional[str] = None           # 精确匹配: "exec"
    tool_pattern: Optional[str] = None   # 正则匹配: "exec|write|edit"
    
    # 参数匹配
    param_patterns: Optional[dict[str, str]] = None  # 参数名 -> 正则模式
    # 例: {"command": "git\\s+(add|commit|push)"}
    
    # 参数值包含关键词
    param_contains: Optional[dict[str, list[str]]] = None  # 参数名 -> 关键词列表
    # 例: {"command": ["--force", "-f", "--no-verify"]}
    
    # 参数路径匹配
    param_paths: Optional[dict[str, list[str]]] = None  # 参数名 -> glob 模式
    # 例: {"file_path": ["**/.openclaw/openclaw.json", "**/gateway.env"]}
    
    @field_validator("tool_pattern")
    @classmethod
    def validate_regex(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v
    
    @field_validator("param_patterns")
    @classmethod
    def validate_param_patterns(cls, v: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
        if v is not None:
            for param_name, pattern in v.items():
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"Invalid regex pattern for param '{param_name}': {e}")
        return v
    
    def matches(self, tool_name: str, tool_params: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        检查工具调用是否匹配此模式
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数字典
            
        Returns:
            (是否匹配, 匹配说明)
        """
        import fnmatch
        
        # 检查工具名称 - 精确匹配
        if self.tool and tool_name != self.tool:
            return False, f"Tool name mismatch: expected {self.tool}, got {tool_name}"
        
        # 检查工具名称 - 正则匹配
        if self.tool_pattern:
            if not re.search(self.tool_pattern, tool_name):
                return False, f"Tool pattern mismatch: {self.tool_pattern}"
        
        # 检查参数正则模式
        if self.param_patterns:
            for param_name, pattern in self.param_patterns.items():
                param_value = str(tool_params.get(param_name, ""))
                if not re.search(pattern, param_value, re.IGNORECASE):
                    return False, f"Param pattern mismatch: {param_name}={param_value} !~ {pattern}"
        
        # 检查参数关键词包含
        if self.param_contains:
            for param_name, keywords in self.param_contains.items():
                param_value = str(tool_params.get(param_name, "")).lower()
                matched_keywords = [kw for kw in keywords if kw.lower() in param_value]
                if not matched_keywords:
                    return False, f"Param keywords not found: {param_name} missing {keywords}"
        
        # 检查参数路径匹配
        if self.param_paths:
            for param_name, patterns in self.param_paths.items():
                param_value = str(tool_params.get(param_name, ""))
                matched = False
                for pattern in patterns:
                    if pattern.startswith("**/"):
                        suffix = pattern[3:]
                        if fnmatch.fnmatch(param_value, suffix) or fnmatch.fnmatch(param_value, pattern):
                            matched = True
                            break
                    elif fnmatch.fnmatch(param_value, pattern):
                        matched = True
                        break
                if not matched:
                    return False, f"Param path mismatch: {param_name}={param_value} not in {patterns}"
        
        return True, "Pattern matched"


class RewriteRule(BaseModel):
    """改写规则"""
    
    # 改写类型
    type: Literal["replace", "prepend", "append", "template"] = "replace"
    
    # 目标参数
    target_param: str  # 要改写的参数名
    
    # 改写内容
    # replace: 完全替换
    # prepend: 在前面追加
    # append: 在后面追加
    # template: 使用模板生成新值
    value: str
    
    # 模板变量（仅 type=template 时使用）
    template_vars: Optional[dict[str, str]] = None
    
    def apply(self, original_params: dict[str, Any]) -> dict[str, Any]:
        """
        应用改写规则到参数
        
        Args:
            original_params: 原始参数字典
            
        Returns:
            改写后的参数字典
        """
        params = original_params.copy()
        original_value = str(params.get(self.target_param, ""))
        
        if self.type == "replace":
            params[self.target_param] = self.value
        elif self.type == "prepend":
            params[self.target_param] = self.value + original_value
        elif self.type == "append":
            params[self.target_param] = original_value + self.value
        elif self.type == "template":
            # 模板替换
            result = self.value
            for var_name, var_path in (self.template_vars or {}).items():
                # 支持从原参数提取值: "$original_param"
                if var_path.startswith("$"):
                    source_param = var_path[1:]
                    var_value = str(original_params.get(source_param, ""))
                    result = result.replace(f"{{{var_name}}}", var_value)
            params[self.target_param] = result
        
        return params


class GuardrailRule(BaseModel):
    """单条 Guardrail 规则"""
    
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    
    # 匹配模式
    pattern: ToolCallPattern
    
    # 动作
    action: GuardrailAction
    
    # 改写规则（仅 action=REWRITE 时使用）
    rewrite: Optional[RewriteRule] = None
    
    # 阻断消息（仅 action=BLOCK 时使用）
    block_message: Optional[str] = None
    
    # 警告消息（仅 action=WARN 时使用）
    warn_message: Optional[str] = None
    
    # 优先级和元数据
    priority: int = Field(default=50, ge=0, le=100)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    
    # 上下文条件（可选，用于更精细控制）
    context_condition: Optional[dict[str, Any]] = None  # 复用 Phase 1 的 RuleCondition 格式
    
    @field_validator("id")
    @classmethod
    def id_pattern(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("id must contain only alphanumeric, underscore, and hyphen characters")
        return v
    
    @model_validator(mode="after")
    def validate_action_fields(self) -> "GuardrailRule":
        """验证动作相关字段"""
        if self.action == GuardrailAction.REWRITE and self.rewrite is None:
            raise ValueError("rewrite field is required when action=REWRITE")
        if self.action == GuardrailAction.BLOCK and self.block_message is None:
            raise ValueError("block_message is required when action=BLOCK")
        return self
    
    def matches(self, tool_name: str, tool_params: dict[str, Any], context: Optional[dict] = None) -> tuple[bool, Optional[str]]:
        """
        检查工具调用是否匹配此规则
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数字典
            context: 可选的上下文信息
            
        Returns:
            (是否匹配, 匹配说明)
        """
        if not self.enabled:
            return False, "Rule disabled"
        
        return self.pattern.matches(tool_name, tool_params)
    
    def execute(self, tool_name: str, tool_params: dict[str, Any]) -> tuple[GuardrailAction, dict[str, Any], Optional[str]]:
        """
        执行规则动作
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数字典
            
        Returns:
            (动作类型, 处理后参数, 消息)
        """
        if self.action == GuardrailAction.REWRITE:
            new_params = self.rewrite.apply(tool_params)  # type: ignore
            return self.action, new_params, f"Rewritten by rule {self.id}"
        
        elif self.action == GuardrailAction.BLOCK:
            return self.action, tool_params, self.block_message
        
        elif self.action == GuardrailAction.WARN:
            return self.action, tool_params, self.warn_message
        
        else:  # LOG
            return self.action, tool_params, f"Logged by rule {self.id}"


class GuardrailRuleSet(BaseModel):
    """Guardrail 规则集（单文件）"""
    
    version: str = Field(default="1.0")
    kind: Literal["guardrail"] = "guardrail"
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    enabled: bool = True
    rules: list[GuardrailRule] = Field(default_factory=list)
    
    @field_validator("version")
    @classmethod
    def version_format(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+$", v):
            raise ValueError("version must be in format X.Y (e.g., 1.0)")
        return v
    
    def get_enabled_rules(self) -> list[GuardrailRule]:
        """获取启用的规则"""
        if not self.enabled:
            return []
        return [r for r in self.rules if r.enabled]
    
    def get_matching_rule(self, tool_name: str, tool_params: dict[str, Any]) -> Optional[GuardrailRule]:
        """
        获取匹配的最高优先级规则
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数字典
            
        Returns:
            匹配的规则，或 None
        """
        if not self.enabled:
            return None
        
        matching = []
        for rule in self.rules:
            if rule.enabled and rule.matches(tool_name, tool_params)[0]:
                matching.append(rule)
        
        if not matching:
            return None
        
        # 返回最高优先级的规则
        return max(matching, key=lambda r: r.priority)


class GuardrailHit(BaseModel):
    """Guardrail 命中记录"""
    
    timestamp: str
    rule_id: str
    rule_name: str
    action: GuardrailAction
    
    # 原始输入
    tool_name: str
    original_params: dict[str, Any]
    
    # 处理结果
    result_params: Optional[dict[str, Any]] = None
    message: Optional[str] = None
    
    # 上下文
    session_key: Optional[str] = None
    phase: Optional[int] = None