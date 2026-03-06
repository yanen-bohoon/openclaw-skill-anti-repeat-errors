"""
Anti-Repeat-Errors Skill - Hit Logger

Structured logging for guardrail hits with traceability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import threading
import fcntl


class HitEventType(str, Enum):
    """命中事件类型"""
    TOOL_BLOCKED = "tool_blocked"
    TOOL_REWRITTEN = "tool_rewritten"
    TOOL_WARNED = "tool_warned"
    TOOL_LOGGED = "tool_logged"


@dataclass
class GuardrailHitRecord:
    """
    完整的命中记录
    
    包含所有追溯所需信息：
    - 原始工具调用
    - 命中的规则
    - 处理结果
    - 上下文
    """
    
    # 元数据
    hit_id: str  # 唯一标识: {timestamp}_{rule_id}_{tool_name}
    timestamp: str
    event_type: HitEventType
    
    # 规则信息
    rule_id: str
    rule_name: str
    rule_priority: int
    rule_tags: list[str]
    
    # 工具调用
    tool_name: str
    original_params: dict[str, Any]
    result_params: Optional[dict[str, Any]] = None  # REWRITE 时有值
    
    # 消息
    message: Optional[str] = None
    
    # 上下文
    session_key: Optional[str] = None
    phase: Optional[int] = None
    task_type: Optional[str] = None
    
    # 性能
    duration_ms: float = 0.0
    
    def to_jsonl(self) -> str:
        """转换为 JSONL 格式"""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return json.dumps(data, ensure_ascii=False)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data
    
    @classmethod
    def from_jsonl(cls, line: str) -> "GuardrailHitRecord":
        """从 JSONL 解析"""
        data = json.loads(line)
        data["event_type"] = HitEventType(data["event_type"])
        return cls(**data)


class HitLogger:
    """
    命中日志记录器
    
    特点：
    - JSONL 格式，便于流式读取
    - 线程安全
    - 自动轮转（按日期）
    """
    
    DEFAULT_LOG_DIR = "~/.openclaw/logs/anti-repeat-errors"
    
    def __init__(
        self,
        log_dir: Optional[Path] = None,
        auto_rotate: bool = True,
    ):
        """
        初始化命中日志记录器
        
        Args:
            log_dir: 日志目录
            auto_rotate: 是否按日期自动轮转
        """
        if log_dir is None:
            log_dir = Path(self.DEFAULT_LOG_DIR)
        
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.auto_rotate = auto_rotate
        
        self._lock = threading.Lock()
        self._current_file: Optional[Path] = None
        self._current_date: Optional[str] = None
        
        self._logger = logging.getLogger("anti-repeat-errors.hit_logger")
    
    def _get_log_file(self) -> Path:
        """获取当前日志文件路径"""
        if not self.auto_rotate:
            return self.log_dir / "guardrail_hits.jsonl"
        
        today = datetime.now().strftime("%Y-%m-%d")
        if self._current_date != today:
            self._current_date = today
            self._current_file = self.log_dir / f"guardrail_hits_{today}.jsonl"
        
        return self._current_file
    
    def record_hit(
        self,
        event_type: HitEventType,
        rule_id: str,
        rule_name: str,
        tool_name: str,
        original_params: dict[str, Any],
        result_params: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
        session_key: Optional[str] = None,
        phase: Optional[int] = None,
        task_type: Optional[str] = None,
        duration_ms: float = 0.0,
        rule_priority: int = 50,
        rule_tags: Optional[list[str]] = None,
    ) -> GuardrailHitRecord:
        """
        记录一次命中
        
        Args:
            event_type: 事件类型
            rule_id: 规则 ID
            rule_name: 规则名称
            tool_name: 工具名称
            original_params: 原始参数
            result_params: 处理后参数（REWRITE 时）
            message: 消息
            session_key: 会话标识
            phase: 阶段
            task_type: 任务类型
            duration_ms: 处理耗时
            rule_priority: 规则优先级
            rule_tags: 规则标签
            
        Returns:
            创建的命中记录
        """
        timestamp = datetime.now().isoformat()
        hit_id = f"{timestamp.replace(':', '-')}_{rule_id}_{tool_name}"
        
        record = GuardrailHitRecord(
            hit_id=hit_id,
            timestamp=timestamp,
            event_type=event_type,
            rule_id=rule_id,
            rule_name=rule_name,
            rule_priority=rule_priority,
            rule_tags=rule_tags or [],
            tool_name=tool_name,
            original_params=original_params,
            result_params=result_params,
            message=message,
            session_key=session_key,
            phase=phase,
            task_type=task_type,
            duration_ms=duration_ms,
        )
        
        # 写入日志文件（线程安全）
        with self._lock:
            self._write_record(record)
        
        return record
    
    def _write_record(self, record: GuardrailHitRecord) -> None:
        """写入记录到文件"""
        log_file = self._get_log_file()
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                # 文件锁（防止多进程并发写入冲突）
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(record.to_jsonl())
                    f.write("\n")
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            self._logger.error(f"Failed to write hit record: {e}")
    
    def read_hits(
        self,
        date: Optional[str] = None,
        rule_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        event_type: Optional[HitEventType] = None,
        session_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[GuardrailHitRecord]:
        """
        读取命中记录
        
        Args:
            date: 日期过滤 (YYYY-MM-DD)
            rule_id: 规则 ID 过滤
            tool_name: 工具名称过滤
            event_type: 事件类型过滤
            session_key: 会话过滤
            limit: 最大返回数量
            
        Returns:
            命中记录列表
        """
        hits = []
        
        if date:
            log_file = self.log_dir / f"guardrail_hits_{date}.jsonl"
            files = [log_file] if log_file.exists() else []
        else:
            files = sorted(self.log_dir.glob("guardrail_hits_*.jsonl"), reverse=True)
        
        for log_file in files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            hit = GuardrailHitRecord.from_jsonl(line)
                            
                            # 应用过滤
                            if rule_id and hit.rule_id != rule_id:
                                continue
                            if tool_name and hit.tool_name != tool_name:
                                continue
                            if event_type and hit.event_type != event_type:
                                continue
                            if session_key and hit.session_key != session_key:
                                continue
                            
                            hits.append(hit)
                            
                            if len(hits) >= limit:
                                return hits
                                
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                self._logger.error(f"Failed to read {log_file}: {e}")
        
        return hits
    
    def get_hit_by_id(self, hit_id: str) -> Optional[GuardrailHitRecord]:
        """根据 ID 获取命中记录"""
        # 从 ID 中提取日期
        # ID 格式: {timestamp}_{rule_id}_{tool_name}
        # timestamp 格式: YYYY-MM-DDTHH-MM-SS...
        try:
            date_part = hit_id[:10]  # YYYY-MM-DD
            hits = self.read_hits(date=date_part, limit=1000)
            for hit in hits:
                if hit.hit_id == hit_id:
                    return hit
        except Exception:
            pass
        return None
    
    def get_statistics(self, date: Optional[str] = None) -> dict:
        """
        获取命中统计
        
        Args:
            date: 日期过滤
            
        Returns:
            统计字典
        """
        hits = self.read_hits(date=date, limit=10000)
        
        stats = {
            "total_hits": len(hits),
            "by_event_type": {},
            "by_rule": {},
            "by_tool": {},
            "avg_duration_ms": 0.0,
        }
        
        if not hits:
            return stats
        
        # 按事件类型统计
        event_counts = {}
        for hit in hits:
            event_counts[hit.event_type.value] = event_counts.get(hit.event_type.value, 0) + 1
        stats["by_event_type"] = event_counts
        
        # 按规则统计
        rule_counts = {}
        for hit in hits:
            rule_counts[hit.rule_id] = rule_counts.get(hit.rule_id, 0) + 1
        stats["by_rule"] = dict(sorted(rule_counts.items(), key=lambda x: -x[1]))
        
        # 按工具统计
        tool_counts = {}
        for hit in hits:
            tool_counts[hit.tool_name] = tool_counts.get(hit.tool_name, 0) + 1
        stats["by_tool"] = dict(sorted(tool_counts.items(), key=lambda x: -x[1]))
        
        # 平均耗时
        durations = [h.duration_ms for h in hits if h.duration_ms > 0]
        if durations:
            stats["avg_duration_ms"] = sum(durations) / len(durations)
        
        return stats


# 全局实例
_logger_instance: Optional[HitLogger] = None


def get_hit_logger(log_dir: Optional[Path] = None) -> HitLogger:
    """获取全局命中日志记录器"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = HitLogger(log_dir=log_dir)
    return _logger_instance