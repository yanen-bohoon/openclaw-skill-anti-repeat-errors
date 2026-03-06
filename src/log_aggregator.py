"""
Anti-Repeat-Errors Skill - Log Aggregator

Aggregates logs from multiple sources for error pattern analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import re
from collections import Counter


@dataclass
class ErrorRecord:
    """标准化错误记录"""
    
    # 元数据
    timestamp: str
    source: str  # "injection" | "guardrail" | "external"
    log_type: str  # "injection_failed" | "tool_blocked" | "tool_warned" | "error"
    
    # 错误内容
    error_message: Optional[str] = None
    tool_name: Optional[str] = None
    original_params: dict[str, Any] = field(default_factory=dict)
    result_params: Optional[dict[str, Any]] = None
    
    # 上下文
    session_key: Optional[str] = None
    phase: Optional[int] = None
    task_type: Optional[str] = None
    rule_id: Optional[str] = None
    
    # 聚类特征
    error_signature: str = ""  # 用于聚类的特征签名
    normalized_command: str = ""  # 标准化命令
    
    def compute_signature(self) -> str:
        """计算错误特征签名（用于聚类）"""
        # 基于工具名和参数模式生成签名
        parts = [self.tool_name or "unknown"]
        
        # 提取参数关键特征
        if self.original_params:
            param_keys = sorted(self.original_params.keys())
            parts.append(",".join(param_keys))
            
            # 对于 exec 工具，提取命令基名
            if self.tool_name == "exec" and "command" in self.original_params:
                cmd = self.original_params["command"]
                # 提取命令基名（如 git, npm, python）
                cmd_base = cmd.split()[0] if cmd.split() else "unknown"
                parts.append(cmd_base)
        
        # 添加错误类型
        parts.append(self.log_type)
        
        self.error_signature = "|".join(parts)
        return self.error_signature
    
    def normalize_command(self) -> str:
        """标准化命令（去除具体参数值，保留模式）"""
        if self.tool_name == "exec" and "command" in self.original_params:
            cmd = self.original_params["command"]
            # 替换路径为占位符
            normalized = re.sub(r'/[\w/.-]+', '<PATH>', cmd)
            # 替换数字
            normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)
            # 替换 UUID
            normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '<UUID>', normalized, flags=re.IGNORECASE)
            self.normalized_command = normalized
        elif self.tool_name in ("write", "edit", "read") and "file_path" in self.original_params:
            # 保留文件扩展名模式
            fp = self.original_params["file_path"]
            ext = Path(fp).suffix or "<no-ext>"
            self.normalized_command = f"{self.tool_name}:*{ext}"
        else:
            self.normalized_command = f"{self.tool_name}:<params>"
        
        return self.normalized_command
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "log_type": self.log_type,
            "error_message": self.error_message,
            "tool_name": self.tool_name,
            "original_params": self.original_params,
            "session_key": self.session_key,
            "phase": self.phase,
            "task_type": self.task_type,
            "rule_id": self.rule_id,
            "error_signature": self.error_signature,
            "normalized_command": self.normalized_command,
        }


@dataclass
class AggregatedLogs:
    """聚合的日志数据"""
    
    # 时间窗口
    window_start: str
    window_end: str
    
    # 错误记录
    error_records: list[ErrorRecord] = field(default_factory=list)
    
    # 统计
    total_records: int = 0
    total_errors: int = 0
    total_guardrail_hits: int = 0
    unique_signatures: int = 0
    
    # 来源
    source_files: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "total_records": self.total_records,
            "total_errors": self.total_errors,
            "total_guardrail_hits": self.total_guardrail_hits,
            "unique_signatures": self.unique_signatures,
            "source_files": self.source_files,
        }


class LogAggregator:
    """
    日志聚合器
    
    从多个日志源收集错误数据并标准化。
    """
    
    DEFAULT_LOG_DIR = "~/.openclaw/logs/anti-repeat-errors"
    
    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path(self.DEFAULT_LOG_DIR)
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def aggregate(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        days: int = 7,
    ) -> AggregatedLogs:
        """
        聚合指定时间范围内的日志
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            days: 如果未指定时间，默认聚合最近 N 天
            
        Returns:
            AggregatedLogs 对象
        """
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(days=days)
        
        aggregated = AggregatedLogs(
            window_start=start_time.isoformat(),
            window_end=end_time.isoformat(),
        )
        
        # 1. 聚合 injection 日志
        injection_errors = self._aggregate_injection_logs(start_time, end_time)
        aggregated.error_records.extend(injection_errors)
        aggregated.source_files.append("injections.jsonl")
        
        # 2. 聚合 guardrail 命中日志
        guardrail_hits = self._aggregate_guardrail_logs(start_time, end_time)
        aggregated.error_records.extend(guardrail_hits)
        aggregated.source_files.append("guardrail_hits_*.jsonl")
        
        # 3. 计算统计
        aggregated.total_records = len(aggregated.error_records)
        aggregated.total_errors = sum(1 for r in aggregated.error_records if r.log_type == "error")
        aggregated.total_guardrail_hits = sum(1 for r in aggregated.error_records if r.source == "guardrail")
        
        # 4. 计算唯一签名
        signatures = set(r.error_signature for r in aggregated.error_records if r.error_signature)
        aggregated.unique_signatures = len(signatures)
        
        return aggregated
    
    def _aggregate_injection_logs(self, start_time: datetime, end_time: datetime) -> list[ErrorRecord]:
        """聚合 injection 日志"""
        records = []
        log_file = self.log_dir / "injections.jsonl"
        
        if not log_file.exists():
            return records
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # 解析时间戳
                        ts = data.get("timestamp", "")
                        try:
                            record_time = datetime.fromisoformat(ts)
                        except:
                            continue
                        
                        # 检查时间范围
                        if not (start_time <= record_time <= end_time):
                            continue
                        
                        # 只关注失败/跳过的注入
                        event = data.get("event", "")
                        if event not in ("injection_failed", "injection_skipped"):
                            continue
                        
                        record = ErrorRecord(
                            timestamp=ts,
                            source="injection",
                            log_type=event,
                            error_message=data.get("error") or data.get("skip_reason"),
                            tool_name=data.get("tool_name"),
                            original_params=data.get("original_params", {}),
                            session_key=data.get("session_key"),
                            phase=data.get("phase"),
                            task_type=data.get("task_type"),
                            rule_id=data.get("rule_id"),
                        )
                        record.compute_signature()
                        record.normalize_command()
                        records.append(record)
                        
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            pass
        
        return records
    
    def _aggregate_guardrail_logs(self, start_time: datetime, end_time: datetime) -> list[ErrorRecord]:
        """聚合 guardrail 命中日志"""
        records = []
        
        # 扫描所有 guardrail_hits_YYYY-MM-DD.jsonl 文件
        for log_file in sorted(self.log_dir.glob("guardrail_hits_*.jsonl")):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            
                            # 解析时间戳
                            ts = data.get("timestamp", "")
                            try:
                                record_time = datetime.fromisoformat(ts)
                            except:
                                continue
                            
                            # 检查时间范围
                            if not (start_time <= record_time <= end_time):
                                continue
                            
                            event_type = data.get("event_type", "")
                            
                            record = ErrorRecord(
                                timestamp=ts,
                                source="guardrail",
                                log_type=event_type,
                                error_message=data.get("message"),
                                tool_name=data.get("tool_name"),
                                original_params=data.get("original_params", {}),
                                result_params=data.get("result_params"),
                                session_key=data.get("session_key"),
                                phase=data.get("phase"),
                                task_type=data.get("task_type"),
                                rule_id=data.get("rule_id"),
                            )
                            record.compute_signature()
                            record.normalize_command()
                            records.append(record)
                            
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                continue
        
        return records
    
    def get_error_summary(self, aggregated: AggregatedLogs) -> dict:
        """
        获取错误摘要
        
        Returns:
            错误摘要字典
        """
        # 按签名分组统计
        signature_counts = Counter(r.error_signature for r in aggregated.error_records)
        
        # 按工具统计
        tool_counts = Counter(r.tool_name for r in aggregated.error_records if r.tool_name)
        
        # 按标准化命令统计
        cmd_counts = Counter(r.normalized_command for r in aggregated.error_records)
        
        return {
            "window": {
                "start": aggregated.window_start,
                "end": aggregated.window_end,
            },
            "totals": {
                "records": aggregated.total_records,
                "errors": aggregated.total_errors,
                "guardrail_hits": aggregated.total_guardrail_hits,
                "unique_signatures": aggregated.unique_signatures,
            },
            "top_signatures": dict(signature_counts.most_common(20)),
            "top_tools": dict(tool_counts.most_common(10)),
            "top_commands": dict(cmd_counts.most_common(10)),
        }


def create_aggregator(log_dir: Optional[Path] = None) -> LogAggregator:
    """创建聚合器的便捷函数"""
    return LogAggregator(log_dir=log_dir)