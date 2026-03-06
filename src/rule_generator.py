"""
Anti-Repeat-Errors Skill - Rule Generator

Generates candidate guardrail rules from error clusters.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from .error_clusterer import ErrorCluster, ClusteringResult
    from .guardrail_models import GuardrailAction, GuardrailRule, ToolCallPattern, RewriteRule
except ImportError:
    from error_clusterer import ErrorCluster, ClusteringResult
    from guardrail_models import GuardrailAction, GuardrailRule, ToolCallPattern, RewriteRule


@dataclass
class CandidateRule:
    """候选规则"""
    
    # 规则内容
    rule: GuardrailRule
    
    # 来源信息
    source_cluster_id: str
    source_cluster_count: int
    source_cluster_priority: int
    
    # 生成信息
    generated_at: str
    generator_version: str = "1.0"
    
    # 状态
    status: str = "candidate"  # candidate | approved | rejected | merged
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    
    # 去重
    fingerprint: str = ""
    
    def compute_fingerprint(self) -> str:
        """计算规则指纹（用于去重）"""
        # 基于规则的核心内容生成指纹
        parts = [
            self.rule.pattern.tool or "",
            self.rule.pattern.tool_pattern or "",
            str(sorted(self.rule.pattern.param_patterns or {})),
            str(sorted(self.rule.pattern.param_contains or {})),
            str(sorted(self.rule.pattern.param_paths or {})),
            self.rule.action.value,
        ]
        self.fingerprint = "|".join(parts)
        return self.fingerprint
    
    def to_dict(self) -> dict:
        return {
            "rule": self.rule.model_dump(),
            "source_cluster_id": self.source_cluster_id,
            "source_cluster_count": self.source_cluster_count,
            "source_cluster_priority": self.source_cluster_priority,
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "status": self.status,
            "fingerprint": self.fingerprint,
        }
    
    def to_yaml_dict(self) -> dict:
        """转换为 YAML 格式（用于规则文件）"""
        rule_dict = {
            "id": self.rule.id,
            "name": self.rule.name,
            "description": self.rule.description,
            "pattern": {},
            "action": self.rule.action.value,
            "priority": self.rule.priority,
            "enabled": False,  # 候选规则默认禁用
            "tags": self.rule.tags + ["auto-generated"],
        }
        
        # 模式
        if self.rule.pattern.tool:
            rule_dict["pattern"]["tool"] = self.rule.pattern.tool
        if self.rule.pattern.tool_pattern:
            rule_dict["pattern"]["tool_pattern"] = self.rule.pattern.tool_pattern
        if self.rule.pattern.param_patterns:
            rule_dict["pattern"]["param_patterns"] = self.rule.pattern.param_patterns
        if self.rule.pattern.param_contains:
            rule_dict["pattern"]["param_contains"] = self.rule.pattern.param_contains
        if self.rule.pattern.param_paths:
            rule_dict["pattern"]["param_paths"] = self.rule.pattern.param_paths
        
        # 动作特定字段
        if self.rule.action == GuardrailAction.BLOCK:
            rule_dict["block_message"] = self.rule.block_message
        elif self.rule.action == GuardrailAction.WARN:
            rule_dict["warn_message"] = self.rule.warn_message
        elif self.rule.action == GuardrailAction.REWRITE:
            rule_dict["rewrite"] = self.rule.rewrite.model_dump() if self.rule.rewrite else None
        
        return rule_dict


@dataclass
class GenerationResult:
    """规则生成结果"""
    
    window_start: str
    window_end: str
    generated_at: str
    
    # 候选规则
    candidates: list[CandidateRule] = field(default_factory=list)
    
    # 统计
    total_candidates: int = 0
    unique_candidates: int = 0  # 去重后
    high_priority_candidates: int = 0
    
    # 去重信息
    duplicates_removed: int = 0
    existing_rules_skipped: int = 0
    
    def get_candidates_by_action(self, action: GuardrailAction) -> list[CandidateRule]:
        """按动作类型获取候选规则"""
        return [c for c in self.candidates if c.rule.action == action]
    
    def to_dict(self) -> dict:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "generated_at": self.generated_at,
            "total_candidates": self.total_candidates,
            "unique_candidates": self.unique_candidates,
            "high_priority_candidates": self.high_priority_candidates,
            "duplicates_removed": self.duplicates_removed,
            "existing_rules_skipped": self.existing_rules_skipped,
        }


class RuleGenerator:
    """
    候选规则生成器
    
    从错误聚类生成候选 guardrail 规则。
    """
    
    def __init__(self, existing_rule_ids: Optional[set[str]] = None):
        """
        初始化生成器
        
        Args:
            existing_rule_ids: 已存在的规则 ID 集合（用于去重）
        """
        self.existing_rule_ids = existing_rule_ids or set()
    
    def generate(self, clustering_result: ClusteringResult) -> GenerationResult:
        """
        从聚类结果生成候选规则
        
        Args:
            clustering_result: 聚类结果
            
        Returns:
            GenerationResult 对象
        """
        result = GenerationResult(
            window_start=clustering_result.window_start,
            window_end=clustering_result.window_end,
            generated_at=datetime.now().isoformat(),
        )
        
        seen_fingerprints: set[str] = set()
        
        for cluster in clustering_result.clusters:
            # 只处理高优先级聚类
            if cluster.priority < 60:
                continue
            
            # 生成候选规则
            candidate = self._generate_rule_from_cluster(cluster)
            if candidate is None:
                continue
            
            # 计算指纹并去重
            fingerprint = candidate.compute_fingerprint()
            if fingerprint in seen_fingerprints:
                result.duplicates_removed += 1
                continue
            
            # 检查是否已存在
            if candidate.rule.id in self.existing_rule_ids:
                result.existing_rules_skipped += 1
                continue
            
            seen_fingerprints.add(fingerprint)
            result.candidates.append(candidate)
        
        # 计算统计
        result.total_candidates = len(result.candidates)
        result.unique_candidates = len(result.candidates)
        result.high_priority_candidates = sum(1 for c in result.candidates if c.rule.priority >= 80)
        
        return result
    
    def _generate_rule_from_cluster(self, cluster: ErrorCluster) -> Optional[CandidateRule]:
        """从单个聚类生成规则"""
        representative = cluster.get_representative_record()
        if not representative:
            return None
        
        # 确定工具名
        tool_name = representative.tool_name
        if not tool_name:
            return None
        
        # 生成规则 ID
        rule_id = f"auto-{tool_name}-{cluster.cluster_id}"
        
        # 生成模式
        pattern = self._generate_pattern(cluster, representative)
        if pattern is None:
            return None
        
        # 确定动作和内容
        action, action_content = self._determine_action(cluster, representative)
        
        # 创建规则
        rule = GuardrailRule(
            id=rule_id,
            name=f"自动生成: {tool_name} 错误防护",
            description=f"基于 {cluster.count} 次重复错误自动生成",
            pattern=pattern,
            action=action,
            **action_content,
            priority=cluster.priority,
            enabled=False,  # 候选规则默认禁用
            tags=["auto-generated", f"cluster:{cluster.cluster_id}"],
        )
        
        return CandidateRule(
            rule=rule,
            source_cluster_id=cluster.cluster_id,
            source_cluster_count=cluster.count,
            source_cluster_priority=cluster.priority,
            generated_at=datetime.now().isoformat(),
        )
    
    def _generate_pattern(self, cluster: ErrorCluster, representative: ErrorRecord) -> Optional[ToolCallPattern]:
        """生成匹配模式"""
        pattern_kwargs: dict[str, Any] = {}
        
        # 工具名
        if cluster.tool_name and cluster.tool_name != "multiple":
            pattern_kwargs["tool"] = cluster.tool_name
        
        # 根据工具类型生成参数模式
        if representative.tool_name == "exec":
            # 对于 exec，提取命令模式
            if "command" in representative.original_params:
                cmd = representative.original_params["command"]
                # 提取命令基名
                cmd_parts = cmd.split()
                if cmd_parts:
                    # 生成正则模式：匹配命令开头
                    base_cmd = cmd_parts[0]
                    pattern_kwargs["param_patterns"] = {
                        "command": f"^{re.escape(base_cmd)}\\b"
                    }
        
        elif representative.tool_name in ("write", "edit", "read"):
            # 对于文件操作，提取路径模式
            if "file_path" in representative.original_params:
                fp = representative.original_params["file_path"]
                # 提取扩展名模式
                ext = Path(fp).suffix
                if ext:
                    pattern_kwargs["param_paths"] = {
                        "file_path": [f"**/*{ext}"]
                    }
        
        if not pattern_kwargs:
            return None
        
        return ToolCallPattern(**pattern_kwargs)
    
    def _determine_action(self, cluster: ErrorCluster, representative: ErrorRecord) -> tuple[GuardrailAction, dict]:
        """确定规则动作"""
        # 默认使用 WARN
        action = GuardrailAction.WARN
        action_content: dict[str, Any] = {}
        
        # 根据错误类型和频率确定动作
        if cluster.count >= 5:
            # 高频错误，使用 BLOCK
            action = GuardrailAction.BLOCK
            action_content["block_message"] = self._generate_block_message(cluster, representative)
        elif cluster.count >= 3:
            # 中频错误，使用 WARN
            action = GuardrailAction.WARN
            action_content["warn_message"] = self._generate_warn_message(cluster, representative)
        else:
            # 低频错误，仅 LOG
            action = GuardrailAction.LOG
        
        return action, action_content
    
    def _generate_block_message(self, cluster: ErrorCluster, representative: ErrorRecord) -> str:
        """生成阻断消息"""
        tool = cluster.tool_name or "工具"
        return f"""⛔ 自动拦截: {tool} 操作

此操作已被自动生成的规则拦截。

原因: 在过去一段时间内检测到 {cluster.count} 次相似错误。
聚类 ID: {cluster.cluster_id}

如果这是误判，请联系管理员审核此规则。"""
    
    def _generate_warn_message(self, cluster: ErrorCluster, representative: ErrorRecord) -> str:
        """生成警告消息"""
        tool = cluster.tool_name or "工具"
        return f"""⚠️ 自动警告: {tool} 操作

此操作触发了自动生成的警告规则。

原因: 在过去一段时间内检测到 {cluster.count} 次相似错误。
聚类 ID: {cluster.cluster_id}

请确认此操作是否正确。"""
    
    def export_candidates(self, result: GenerationResult, output_path: Path) -> None:
        """导出候选规则到 JSON 文件"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": result.to_dict(),
                "candidates": [c.to_dict() for c in result.candidates],
            }, f, indent=2, ensure_ascii=False)
    
    def export_to_yaml(self, result: GenerationResult, output_path: Path) -> None:
        """导出候选规则到 YAML 文件（用于规则库）"""
        import yaml
        
        yaml_content = {
            "version": "1.0",
            "kind": "guardrail",
            "name": "auto-generated-candidates",
            "description": "自动生成的候选规则（需要人工审核后启用）",
            "enabled": False,  # 整个规则集默认禁用
            "rules": [c.to_yaml_dict() for c in result.candidates],
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_content, f, allow_unicode=True, default_flow_style=False)


def create_generator(existing_rule_ids: Optional[set[str]] = None) -> RuleGenerator:
    """创建生成器的便捷函数"""
    return RuleGenerator(existing_rule_ids=existing_rule_ids)