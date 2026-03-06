"""
Anti-Repeat-Errors Skill - Error Clusterer

Clusters similar errors to identify patterns.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from .log_aggregator import ErrorRecord, AggregatedLogs
except ImportError:
    from log_aggregator import ErrorRecord, AggregatedLogs


@dataclass
class ErrorCluster:
    """错误聚类"""
    
    # 聚类标识
    cluster_id: str
    cluster_signature: str
    
    # 聚类统计
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    
    # 聚类内容
    records: list[ErrorRecord] = field(default_factory=list)
    
    # 聚类特征
    tool_name: Optional[str] = None
    normalized_commands: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    
    # 优先级（用于规则生成）
    priority: int = 50
    
    def compute_priority(self) -> int:
        """计算聚类优先级（越高越优先）"""
        # 基于频率和影响计算优先级
        # 频率越高，优先级越高
        frequency_score = min(self.count * 5, 40)
        
        # 如果是 BLOCK 类型，额外加分
        block_bonus = sum(1 for r in self.records if r.log_type == "tool_blocked") * 5
        
        # 如果涉及敏感操作，额外加分
        sensitive_tools = {"exec", "write", "edit"}
        sensitive_bonus = 10 if self.tool_name in sensitive_tools else 0
        
        self.priority = min(frequency_score + block_bonus + sensitive_bonus + 50, 100)
        return self.priority
    
    def get_representative_record(self) -> Optional[ErrorRecord]:
        """获取代表性记录（最新的）"""
        if not self.records:
            return None
        return max(self.records, key=lambda r: r.timestamp)
    
    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "cluster_signature": self.cluster_signature,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "tool_name": self.tool_name,
            "normalized_commands": list(set(self.normalized_commands)),
            "error_messages": list(set(self.error_messages))[:5],  # 只保留前5条
            "priority": self.priority,
        }


@dataclass
class ClusteringResult:
    """聚类结果"""
    
    window_start: str
    window_end: str
    
    # 聚类
    clusters: list[ErrorCluster] = field(default_factory=list)
    
    # 统计
    total_clusters: int = 0
    total_records: int = 0
    high_priority_clusters: int = 0
    
    # 配置
    min_cluster_size: int = 2
    
    def get_high_priority_clusters(self, min_priority: int = 70) -> list[ErrorCluster]:
        """获取高优先级聚类"""
        return [c for c in self.clusters if c.priority >= min_priority]
    
    def to_dict(self) -> dict:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "total_clusters": self.total_clusters,
            "total_records": self.total_records,
            "high_priority_clusters": self.high_priority_clusters,
            "min_cluster_size": self.min_cluster_size,
            "clusters": [c.to_dict() for c in self.clusters[:20]],  # 只输出前20个
        }


class ErrorClusterer:
    """
    错误聚类器
    
    将相似的错误记录聚合成错误簇，用于识别高频重复模式。
    """
    
    def __init__(self, min_cluster_size: int = 2):
        """
        初始化聚类器
        
        Args:
            min_cluster_size: 最小聚类大小，小于此值的错误不形成聚类
        """
        self.min_cluster_size = min_cluster_size
    
    def cluster(self, aggregated: AggregatedLogs) -> ClusteringResult:
        """
        对聚合的日志进行聚类
        
        Args:
            aggregated: 聚合的日志数据
            
        Returns:
            ClusteringResult 对象
        """
        result = ClusteringResult(
            window_start=aggregated.window_start,
            window_end=aggregated.window_end,
            min_cluster_size=self.min_cluster_size,
        )
        
        # 按签名分组
        signature_groups: dict[str, list[ErrorRecord]] = defaultdict(list)
        for record in aggregated.error_records:
            if record.error_signature:
                signature_groups[record.error_signature].append(record)
        
        # 创建聚类
        cluster_id = 0
        for signature, records in signature_groups.items():
            if len(records) < self.min_cluster_size:
                continue
            
            cluster = ErrorCluster(
                cluster_id=f"cluster_{cluster_id:04d}",
                cluster_signature=signature,
                count=len(records),
                records=records,
            )
            
            # 提取聚类特征
            timestamps = [r.timestamp for r in records]
            cluster.first_seen = min(timestamps)
            cluster.last_seen = max(timestamps)
            
            # 提取工具名
            tools = set(r.tool_name for r in records if r.tool_name)
            cluster.tool_name = tools.pop() if len(tools) == 1 else "multiple"
            
            # 提取标准化命令
            cluster.normalized_commands = [r.normalized_command for r in records]
            
            # 提取错误消息
            cluster.error_messages = [r.error_message for r in records if r.error_message]
            
            # 计算优先级
            cluster.compute_priority()
            
            result.clusters.append(cluster)
            cluster_id += 1
        
        # 按优先级排序
        result.clusters.sort(key=lambda c: -c.priority)
        
        # 计算统计
        result.total_clusters = len(result.clusters)
        result.total_records = sum(c.count for c in result.clusters)
        result.high_priority_clusters = len(result.get_high_priority_clusters())
        
        return result
    
    def get_top_clusters(self, result: ClusteringResult, limit: int = 10) -> list[ErrorCluster]:
        """获取 top N 聚类"""
        return result.clusters[:limit]
    
    def export_clusters(self, result: ClusteringResult, output_path: Path) -> None:
        """导出聚类结果到 JSON 文件"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)


def create_clusterer(min_cluster_size: int = 2) -> ErrorClusterer:
    """创建聚类器的便捷函数"""
    return ErrorClusterer(min_cluster_size=min_cluster_size)