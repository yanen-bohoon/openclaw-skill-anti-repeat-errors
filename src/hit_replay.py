"""
Anti-Repeat-Errors Skill - Hit Replay

Replay guardrail hits for analysis and debugging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .hit_logger import HitLogger, GuardrailHitRecord, HitEventType


@dataclass
class ReplayTrace:
    """
    单次命中的完整追溯链
    
    展示: 原输入 → 命中规则 → 处理后输入
    """
    
    hit_id: str
    timestamp: str
    tool_name: str
    
    # 原输入
    original_params: dict[str, Any]
    
    # 命中规则
    rule_id: str
    rule_name: str
    rule_priority: int
    rule_tags: list[str]
    action: str  # block/rewrite/warn/log
    
    # 处理后输入
    result_params: Optional[dict[str, Any]]
    
    # 消息
    message: Optional[str]
    
    # 变更 diff（仅 REWRITE）
    param_changes: Optional[dict[str, dict[str, Any]]] = None
    
    def format_trace(self, style: str = "text") -> str:
        """
        格式化追溯链
        
        Args:
            style: 输出风格 (text/markdown/json)
            
        Returns:
            格式化后的字符串
        """
        if style == "json":
            return json.dumps(self.__dict__, indent=2, ensure_ascii=False)
        
        lines = []
        
        if style == "markdown":
            lines.append(f"## Guardrail Hit Trace: `{self.hit_id}`")
            lines.append(f"")
            lines.append(f"**Timestamp:** {self.timestamp}")
            lines.append(f"**Tool:** `{self.tool_name}`")
            lines.append(f"**Action:** `{self.action}`")
            lines.append(f"")
            
            lines.append("### Original Input")
            lines.append("```json")
            lines.append(json.dumps(self.original_params, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")
            
            lines.append("### Matched Rule")
            lines.append(f"- **ID:** `{self.rule_id}`")
            lines.append(f"- **Name:** {self.rule_name}")
            lines.append(f"- **Priority:** {self.rule_priority}")
            if self.rule_tags:
                lines.append(f"- **Tags:** {', '.join(self.rule_tags)}")
            lines.append("")
            
            if self.action == "rewrite":
                lines.append("### Result Input (After Rewrite)")
                lines.append("```json")
                lines.append(json.dumps(self.result_params, indent=2, ensure_ascii=False))
                lines.append("```")
                lines.append("")
                
                if self.param_changes:
                    lines.append("### Parameter Changes")
                    for param_name, change in self.param_changes.items():
                        lines.append(f"- **{param_name}:**")
                        lines.append(f"  - Before: `{change['before']}`")
                        lines.append(f"  - After: `{change['after']}`")
                    lines.append("")
            
            if self.message:
                lines.append("### Message")
                lines.append(self.message)
            
        else:  # text
            lines.append(f"{'='*60}")
            lines.append(f"Guardrail Hit Trace: {self.hit_id}")
            lines.append(f"{'='*60}")
            lines.append(f"Timestamp: {self.timestamp}")
            lines.append(f"Tool: {self.tool_name}")
            lines.append(f"Action: {self.action}")
            lines.append(f"")
            
            lines.append(f"--- Original Input ---")
            lines.append(json.dumps(self.original_params, indent=2, ensure_ascii=False))
            lines.append(f"")
            
            lines.append(f"--- Matched Rule ---")
            lines.append(f"ID: {self.rule_id}")
            lines.append(f"Name: {self.rule_name}")
            lines.append(f"Priority: {self.rule_priority}")
            if self.rule_tags:
                lines.append(f"Tags: {', '.join(self.rule_tags)}")
            lines.append(f"")
            
            if self.action == "rewrite":
                lines.append(f"--- Result Input (After Rewrite) ---")
                lines.append(json.dumps(self.result_params, indent=2, ensure_ascii=False))
                lines.append(f"")
                
                if self.param_changes:
                    lines.append(f"--- Parameter Changes ---")
                    for param_name, change in self.param_changes.items():
                        lines.append(f"{param_name}:")
                        lines.append(f"  Before: {change['before']}")
                        lines.append(f"  After:  {change['after']}")
                    lines.append("")
            
            if self.message:
                lines.append(f"--- Message ---")
                lines.append(self.message)
            
            lines.append(f"{'='*60}")
        
        return "\n".join(lines)


class HitReplay:
    """
    命中回放器
    
    用于分析和调试 guardrail 命中
    """
    
    def __init__(self, logger: Optional[HitLogger] = None):
        self.logger = logger or HitLogger()
    
    def replay_hit(self, hit_id: str) -> Optional[ReplayTrace]:
        """
        回放单次命中
        
        Args:
            hit_id: 命中 ID
            
        Returns:
            ReplayTrace 或 None
        """
        hit = self.logger.get_hit_by_id(hit_id)
        if not hit:
            return None
        
        return self._build_trace(hit)
    
    def replay_session(self, session_key: str, limit: int = 100) -> list[ReplayTrace]:
        """
        回放会话中的所有命中
        
        Args:
            session_key: 会话标识
            limit: 最大数量
            
        Returns:
            ReplayTrace 列表
        """
        hits = self.logger.read_hits(session_key=session_key, limit=limit)
        return [self._build_trace(hit) for hit in hits]
    
    def replay_date(
        self,
        date: str,
        rule_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list[ReplayTrace]:
        """
        回放指定日期的命中
        
        Args:
            date: 日期 (YYYY-MM-DD)
            rule_id: 规则 ID 过滤
            tool_name: 工具名称过滤
            action: 动作过滤 (block/rewrite/warn/log)
            limit: 最大数量
            
        Returns:
            ReplayTrace 列表
        """
        event_type = None
        if action:
            event_type = HitEventType(f"tool_{action}")
        
        hits = self.logger.read_hits(
            date=date,
            rule_id=rule_id,
            tool_name=tool_name,
            event_type=event_type,
            limit=limit,
        )
        
        return [self._build_trace(hit) for hit in hits]
    
    def _build_trace(self, hit: GuardrailHitRecord) -> ReplayTrace:
        """构建追溯链"""
        # 计算参数变更（仅 REWRITE）
        param_changes = None
        if hit.event_type == HitEventType.TOOL_REWRITTEN and hit.result_params:
            param_changes = {}
            all_keys = set(hit.original_params.keys()) | set(hit.result_params.keys())
            for key in all_keys:
                orig_val = hit.original_params.get(key)
                new_val = hit.result_params.get(key)
                if orig_val != new_val:
                    param_changes[key] = {
                        "before": orig_val,
                        "after": new_val,
                    }
        
        return ReplayTrace(
            hit_id=hit.hit_id,
            timestamp=hit.timestamp,
            tool_name=hit.tool_name,
            original_params=hit.original_params,
            rule_id=hit.rule_id,
            rule_name=hit.rule_name,
            rule_priority=hit.rule_priority,
            rule_tags=hit.rule_tags,
            action=hit.event_type.value.replace("tool_", ""),
            result_params=hit.result_params,
            message=hit.message,
            param_changes=param_changes,
        )
    
    def generate_report(
        self,
        date: Optional[str] = None,
        output_format: str = "markdown",
    ) -> str:
        """
        生成命中报告
        
        Args:
            date: 日期，默认今天
            output_format: 输出格式 (markdown/text/json)
            
        Returns:
            报告字符串
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        stats = self.logger.get_statistics(date=date)
        
        if output_format == "json":
            return json.dumps(stats, indent=2, ensure_ascii=False)
        
        lines = []
        
        if output_format == "markdown":
            lines.append(f"# Guardrail Hit Report: {date}")
            lines.append(f"")
            lines.append(f"## Summary")
            lines.append(f"")
            lines.append(f"- **Total Hits:** {stats['total_hits']}")
            lines.append(f"- **Avg Duration:** {stats['avg_duration_ms']:.2f}ms")
            lines.append(f"")
            
            lines.append(f"## By Event Type")
            lines.append(f"")
            for event_type, count in stats["by_event_type"].items():
                lines.append(f"- **{event_type}:** {count}")
            lines.append(f"")
            
            lines.append(f"## Top Rules")
            lines.append(f"")
            for rule_id, count in list(stats["by_rule"].items())[:10]:
                lines.append(f"- `{rule_id}`: {count} hits")
            lines.append(f"")
            
            lines.append(f"## Top Tools")
            lines.append(f"")
            for tool_name, count in list(stats["by_tool"].items())[:10]:
                lines.append(f"- `{tool_name}`: {count} hits")
            
        else:  # text
            lines.append(f"{'='*60}")
            lines.append(f"Guardrail Hit Report: {date}")
            lines.append(f"{'='*60}")
            lines.append(f"")
            lines.append(f"Summary:")
            lines.append(f"  Total Hits: {stats['total_hits']}")
            lines.append(f"  Avg Duration: {stats['avg_duration_ms']:.2f}ms")
            lines.append(f"")
            lines.append(f"By Event Type:")
            for event_type, count in stats["by_event_type"].items():
                lines.append(f"  {event_type}: {count}")
            lines.append(f"")
            lines.append(f"Top Rules:")
            for rule_id, count in list(stats["by_rule"].items())[:10]:
                lines.append(f"  {rule_id}: {count} hits")
            lines.append(f"")
            lines.append(f"Top Tools:")
            for tool_name, count in list(stats["by_tool"].items())[:10]:
                lines.append(f"  {tool_name}: {count} hits")
        
        return "\n".join(lines)