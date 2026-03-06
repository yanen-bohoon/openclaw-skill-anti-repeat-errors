"""
Anti-Repeat-Errors Skill - Guardrail Hook Handler

Handles before_tool_call interception and rewriting.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# Handle both package and direct imports
try:
    from .guardrail_models import GuardrailAction, GuardrailRule, GuardrailHit
    from .pattern_matcher import PatternMatcher, MatchResult
    from .logger import InjectionLogger, get_logger
except ImportError:
    from guardrail_models import GuardrailAction, GuardrailRule, GuardrailHit
    from pattern_matcher import PatternMatcher, MatchResult
    from logger import InjectionLogger, get_logger


@dataclass
class ToolCallContext:
    """工具调用上下文"""
    
    tool_name: str
    tool_params: dict[str, Any]
    session_key: Optional[str] = None
    phase: Optional[int] = None
    task_type: Optional[str] = None
    message_content: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GuardrailResult:
    """Guardrail 处理结果"""
    
    # 核心结果
    allowed: bool  # 是否允许继续执行
    modified: bool  # 是否修改了参数
    
    # 工具信息
    tool_name: str
    original_params: dict[str, Any]
    result_params: dict[str, Any]
    
    # 规则信息
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    action: Optional[str] = None  # rewrite/block/warn/log
    
    # 消息
    message: Optional[str] = None
    
    # 性能
    duration_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


class GuardrailHook:
    """
    Guardrail Hook 处理器
    
    负责:
    1. 在 before_tool_call 时进行模式匹配
    2. 执行拦截/改写动作
    3. 记录命中日志
    """
    
    def __init__(
        self,
        rules_dir: Optional[Path] = None,
        logger: Optional[InjectionLogger] = None,
    ):
        """
        初始化 Guardrail Hook
        
        Args:
            rules_dir: guardrail 规则目录
            logger: 日志记录器
        """
        self.matcher = PatternMatcher(rules_dir=rules_dir)
        self.logger = logger or get_logger()
        self._internal_logger = logging.getLogger("anti-repeat-errors.guardrail")
    
    def process_tool_call(self, context: ToolCallContext) -> GuardrailResult:
        """
        处理工具调用
        
        Args:
            context: 工具调用上下文
            
        Returns:
            GuardrailResult 对象
        """
        start = time.time()
        
        try:
            # 执行模式匹配
            match_result = self.matcher.match(
                tool_name=context.tool_name,
                tool_params=context.tool_params,
                context={
                    "session_key": context.session_key,
                    "phase": context.phase,
                    "task_type": context.task_type,
                    "message": context.message_content,
                }
            )
            
            duration_ms = (time.time() - start) * 1000
            
            # 无匹配，放行
            if not match_result.matched:
                return GuardrailResult(
                    allowed=True,
                    modified=False,
                    tool_name=context.tool_name,
                    original_params=context.tool_params,
                    result_params=context.tool_params,
                    duration_ms=duration_ms,
                )
            
            # 有匹配，根据动作处理
            rule = match_result.rule
            action = match_result.action
            
            # 记录命中日志
            self._log_hit(context, match_result)
            
            if action == GuardrailAction.BLOCK:
                # 阻断
                return GuardrailResult(
                    allowed=False,
                    modified=False,
                    tool_name=context.tool_name,
                    original_params=context.tool_params,
                    result_params=context.tool_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action=action.value,
                    message=match_result.message,
                    duration_ms=duration_ms,
                )
            
            elif action == GuardrailAction.REWRITE:
                # 改写
                return GuardrailResult(
                    allowed=True,
                    modified=True,
                    tool_name=context.tool_name,
                    original_params=context.tool_params,
                    result_params=match_result.result_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action=action.value,
                    message=match_result.message,
                    duration_ms=duration_ms,
                )
            
            elif action == GuardrailAction.WARN:
                # 警告但放行
                return GuardrailResult(
                    allowed=True,
                    modified=False,
                    tool_name=context.tool_name,
                    original_params=context.tool_params,
                    result_params=context.tool_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action=action.value,
                    message=match_result.message,
                    duration_ms=duration_ms,
                )
            
            else:  # LOG
                # 仅记录，放行
                return GuardrailResult(
                    allowed=True,
                    modified=False,
                    tool_name=context.tool_name,
                    original_params=context.tool_params,
                    result_params=context.tool_params,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action=action.value,
                    message=match_result.message,
                    duration_ms=duration_ms,
                )
                
        except Exception as e:
            self._internal_logger.error(f"Guardrail processing failed: {e}")
            # 错误时不阻断正常流程
            return GuardrailResult(
                allowed=True,
                modified=False,
                tool_name=context.tool_name,
                original_params=context.tool_params,
                result_params=context.tool_params,
                message=f"Guardrail error: {e}",
                duration_ms=(time.time() - start) * 1000,
            )
    
    def _log_hit(self, context: ToolCallContext, match_result: MatchResult) -> None:
        """记录命中日志"""
        from datetime import datetime
        
        hit = GuardrailHit(
            timestamp=datetime.now().isoformat(),
            rule_id=match_result.rule.id if match_result.rule else None,
            rule_name=match_result.rule.name if match_result.rule else None,
            action=match_result.action,
            tool_name=context.tool_name,
            original_params=context.tool_params,
            result_params=match_result.result_params,
            message=match_result.message,
            session_key=context.session_key,
            phase=context.phase,
        )
        
        # 写入命中日志文件
        self._write_hit_log(hit)
    
    def _write_hit_log(self, hit: GuardrailHit) -> None:
        """写入命中日志到文件"""
        log_dir = Path.home() / ".openclaw" / "logs" / "anti-repeat-errors"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "guardrail_hits.jsonl"
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(hit.model_dump_json())
            f.write("\n")


def create_guardrail_hook(
    rules_dir: Optional[Path] = None,
    logger: Optional[InjectionLogger] = None,
) -> GuardrailHook:
    """创建 Guardrail Hook 的便捷函数"""
    return GuardrailHook(rules_dir=rules_dir, logger=logger)