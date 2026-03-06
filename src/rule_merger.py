"""
Anti-Repeat-Errors Skill - Rule Merger

Merges candidate rules into the shared rule library.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import yaml
import json

try:
    from .guardrail_models import GuardrailRule, GuardrailRuleSet, GuardrailAction, RewriteRule, ToolCallPattern
    from .rule_generator import CandidateRule
except ImportError:
    from guardrail_models import GuardrailRule, GuardrailRuleSet, GuardrailAction, RewriteRule, ToolCallPattern
    from rule_generator import CandidateRule


@dataclass
class MergeOperation:
    """单个合并操作"""
    
    operation_type: str  # "add" | "update" | "deprecate" | "skip"
    rule_id: str
    rule_name: str
    
    # 操作详情
    details: str = ""
    
    # 变更内容
    old_rule: Optional[dict] = None
    new_rule: Optional[dict] = None
    
    # 来源
    source_cluster_id: Optional[str] = None
    candidate_fingerprint: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "operation_type": self.operation_type,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "details": self.details,
            "old_rule": self.old_rule,
            "new_rule": self.new_rule,
            "source_cluster_id": self.source_cluster_id,
            "candidate_fingerprint": self.candidate_fingerprint,
        }


@dataclass
class MergeResult:
    """合并结果"""
    
    merged_at: str
    source_file: str
    target_file: str
    
    # 操作统计
    operations: list[MergeOperation] = field(default_factory=list)
    
    # 统计
    rules_added: int = 0
    rules_updated: int = 0
    rules_deprecated: int = 0
    rules_skipped: int = 0
    
    # 备份
    backup_file: Optional[str] = None
    
    def get_operations_by_type(self, op_type: str) -> list[MergeOperation]:
        """按类型获取操作"""
        return [op for op in self.operations if op.operation_type == op_type]
    
    def to_dict(self) -> dict:
        return {
            "merged_at": self.merged_at,
            "source_file": self.source_file,
            "target_file": self.target_file,
            "rules_added": self.rules_added,
            "rules_updated": self.rules_updated,
            "rules_deprecated": self.rules_deprecated,
            "rules_skipped": self.rules_skipped,
            "backup_file": self.backup_file,
            "operations": [op.to_dict() for op in self.operations],
        }


class RuleMerger:
    """
    规则合并器
    
    将候选规则安全地合并到共享规则库。
    """
    
    def __init__(
        self,
        rules_dir: Path,
        auto_approve: bool = False,
        backup_enabled: bool = True,
    ):
        """
        初始化合并器
        
        Args:
            rules_dir: 规则目录
            auto_approve: 是否自动批准候选规则（否则需要人工确认）
            backup_enabled: 是否在合并前备份
        """
        self.rules_dir = Path(rules_dir)
        self.guardrails_dir = self.rules_dir / "guardrails"
        self.candidates_dir = self.rules_dir.parent / "candidates"
        self.auto_approve = auto_approve
        self.backup_enabled = backup_enabled
        self._merged_at = datetime.now().isoformat()
        
        # 确保目录存在
        self.guardrails_dir.mkdir(parents=True, exist_ok=True)
        self.candidates_dir.mkdir(parents=True, exist_ok=True)
    
    def merge_candidates(
        self,
        candidate_file: Optional[Path] = None,
        target_file: Optional[Path] = None,
        candidate_ids: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> MergeResult:
        """
        合并候选规则到共享规则库
        
        Args:
            candidate_file: 候选规则文件（YAML），默认使用最新的
            target_file: 目标规则文件，默认使用 auto-generated.yaml
            candidate_ids: 只合并指定的规则 ID
            dry_run: 仅预览，不实际修改
            
        Returns:
            MergeResult 对象
        """
        self._merged_at = datetime.now().isoformat()
        
        # 确定源文件
        if candidate_file is None:
            candidate_file = self._get_latest_candidates_file()
            if candidate_file is None:
                return MergeResult(
                    merged_at=self._merged_at,
                    source_file="",
                    target_file="",
                )
        
        # 确定目标文件
        if target_file is None:
            target_file = self.guardrails_dir / "auto-generated.yaml"
        
        result = MergeResult(
            merged_at=self._merged_at,
            source_file=str(candidate_file),
            target_file=str(target_file),
        )
        
        # 加载候选规则
        candidates = self._load_candidates(candidate_file)
        if not candidates:
            return result
        
        # 加载现有规则集
        existing_ruleset = self._load_ruleset(target_file)
        existing_rules = {r["id"]: r for r in existing_ruleset.get("rules", [])}
        
        # 备份
        if self.backup_enabled and not dry_run and target_file.exists():
            backup_file = self._backup_ruleset(target_file)
            result.backup_file = str(backup_file)
        
        # 处理每个候选规则
        for candidate in candidates:
            # 过滤指定的规则 ID
            if candidate_ids and candidate.rule.id not in candidate_ids:
                continue
            
            operation = self._merge_single_candidate(
                candidate=candidate,
                existing_rules=existing_rules,
                dry_run=dry_run,
            )
            result.operations.append(operation)
        
        # 更新统计
        for op in result.operations:
            if op.operation_type == "add":
                result.rules_added += 1
            elif op.operation_type == "update":
                result.rules_updated += 1
            elif op.operation_type == "deprecate":
                result.rules_deprecated += 1
            else:
                result.rules_skipped += 1
        
        # 写入文件
        if not dry_run and (result.rules_added > 0 or result.rules_updated > 0):
            self._write_ruleset(target_file, existing_ruleset, existing_rules)
        
        return result
    
    def _get_latest_candidates_file(self) -> Optional[Path]:
        """获取最新的候选规则文件"""
        if not self.candidates_dir.exists():
            return None
        
        # 优先使用 YAML 文件
        yaml_files = list(self.candidates_dir.glob("candidates_*.yaml"))
        if yaml_files:
            # 按时间戳排序，返回最新的
            return sorted(yaml_files)[-1]
        
        # 如果没有 YAML，使用 JSON 文件
        json_files = list(self.candidates_dir.glob("candidates_*.json"))
        if json_files:
            return sorted(json_files)[-1]
        
        return None
    
    def _load_candidates(self, candidate_file: Path) -> list[CandidateRule]:
        """加载候选规则"""
        with open(candidate_file, "r", encoding="utf-8") as f:
            if candidate_file.suffix == ".json":
                data = json.load(f)
                rules_data = data.get("candidates", [])
                # 提取规则列表
                rules_list = [r.get("rule", r) for r in rules_data]
            else:
                data = yaml.safe_load(f)
                rules_data = data.get("rules", [])
                rules_list = rules_data
        
        candidates = []
        for rule_data in rules_list:
            # 检查是否已批准
            if not self.auto_approve and not rule_data.get("_approved", False):
                # 默认跳过未批准的规则，除非 auto_approve=True
                continue
            
            try:
                # 重建 GuardrailRule
                pattern_data = rule_data.get("pattern", {})
                pattern = self._build_pattern(pattern_data)
                
                # 收集所有规则字段
                rule_kwargs = {
                    "id": rule_data["id"],
                    "name": rule_data["name"],
                    "description": rule_data.get("description"),
                    "pattern": pattern,
                    "action": GuardrailAction(rule_data["action"]),
                    "priority": rule_data.get("priority", 50),
                    "enabled": rule_data.get("enabled", False),
                    "tags": rule_data.get("tags", []),
                }
                
                # 添加动作特定字段（在创建时传入，避免验证错误）
                action = rule_kwargs["action"]
                if action == GuardrailAction.BLOCK:
                    rule_kwargs["block_message"] = rule_data.get("block_message")
                elif action == GuardrailAction.WARN:
                    rule_kwargs["warn_message"] = rule_data.get("warn_message")
                elif action == GuardrailAction.REWRITE:
                    if "rewrite" in rule_data and rule_data["rewrite"]:
                        rule_kwargs["rewrite"] = RewriteRule(**rule_data["rewrite"])
                
                rule = GuardrailRule(**rule_kwargs)
                
                # 提取来源信息
                source_cluster_id = ""
                for tag in rule.tags:
                    if tag.startswith("cluster:"):
                        source_cluster_id = tag.replace("cluster:", "")
                        break
                
                candidate = CandidateRule(
                    rule=rule,
                    source_cluster_id=source_cluster_id,
                    source_cluster_count=0,
                    source_cluster_priority=rule.priority,
                    generated_at=self._merged_at,
                )
                
                # 计算指纹
                candidate.compute_fingerprint()
                candidates.append(candidate)
                
            except Exception as e:
                print(f"[warn] Failed to load candidate rule {rule_data.get('id')}: {e}")
        
        return candidates
    
    def _build_pattern(self, pattern_data: dict) -> ToolCallPattern:
        """构建 ToolCallPattern"""
        return ToolCallPattern(
            tool=pattern_data.get("tool"),
            tool_pattern=pattern_data.get("tool_pattern"),
            param_patterns=pattern_data.get("param_patterns"),
            param_contains=pattern_data.get("param_contains"),
            param_paths=pattern_data.get("param_paths"),
        )
    
    def _load_ruleset(self, target_file: Path) -> dict:
        """加载现有规则集"""
        if not target_file.exists():
            return {
                "version": "1.0",
                "kind": "guardrail",
                "name": "auto-generated",
                "description": "Auto-generated guardrail rules",
                "enabled": True,
                "rules": [],
            }
        
        with open(target_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    
    def _backup_ruleset(self, target_file: Path) -> Path:
        """备份规则集"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.rules_dir.parent / "backups" / "rules"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_file = backup_dir / f"{target_file.stem}_{timestamp}.yaml"
        shutil.copy2(target_file, backup_file)
        
        return backup_file
    
    def _serialize_rule(self, rule: GuardrailRule) -> dict:
        """序列化规则为可 YAML 序列化的字典"""
        rule_dict = rule.model_dump()
        # 转换枚举为字符串值
        if "action" in rule_dict and hasattr(rule_dict["action"], "value"):
            rule_dict["action"] = rule_dict["action"].value
        return rule_dict
    
    def _merge_single_candidate(
        self,
        candidate: CandidateRule,
        existing_rules: dict[str, dict],
        dry_run: bool,
    ) -> MergeOperation:
        """合并单个候选规则"""
        rule_id = candidate.rule.id
        rule_dict = self._serialize_rule(candidate.rule)
        
        if rule_id in existing_rules:
            # 规则已存在，检查是否需要更新
            existing = existing_rules[rule_id]
            
            # 比较关键字段
            if self._should_update(existing, rule_dict):
                # 更新规则
                old_rule = existing.copy()
                if not dry_run:
                    existing_rules[rule_id] = rule_dict
                
                return MergeOperation(
                    operation_type="update",
                    rule_id=rule_id,
                    rule_name=candidate.rule.name,
                    details="Rule updated with new pattern/action",
                    old_rule=old_rule,
                    new_rule=rule_dict,
                    source_cluster_id=candidate.source_cluster_id,
                    candidate_fingerprint=candidate.fingerprint,
                )
            else:
                # 无需更新
                return MergeOperation(
                    operation_type="skip",
                    rule_id=rule_id,
                    rule_name=candidate.rule.name,
                    details="Rule already exists and unchanged",
                )
        else:
            # 新规则
            if not dry_run:
                existing_rules[rule_id] = rule_dict
            
            return MergeOperation(
                operation_type="add",
                rule_id=rule_id,
                rule_name=candidate.rule.name,
                details="New rule added from cluster",
                new_rule=rule_dict,
                source_cluster_id=candidate.source_cluster_id,
                candidate_fingerprint=candidate.fingerprint,
            )
    
    def _should_update(self, existing: dict, new: dict) -> bool:
        """判断是否需要更新"""
        # 比较关键字段
        keys_to_compare = ["pattern", "action", "priority", "block_message", "warn_message"]
        for key in keys_to_compare:
            existing_val = existing.get(key)
            new_val = new.get(key)
            # 处理 pattern 字段的比较
            if key == "pattern":
                if self._compare_patterns(existing_val, new_val):
                    return True
            elif existing_val != new_val:
                return True
        return False
    
    def _compare_patterns(self, existing: Any, new: Any) -> bool:
        """比较两个 pattern 是否不同"""
        if existing is None and new is None:
            return False
        if existing is None or new is None:
            return True
        
        # 如果是 dict，逐字段比较
        if isinstance(existing, dict) and isinstance(new, dict):
            all_keys = set(existing.keys()) | set(new.keys())
            for key in all_keys:
                if existing.get(key) != new.get(key):
                    return True
            return False
        
        return existing != new
    
    def _write_ruleset(self, target_file: Path, ruleset: dict, rules: dict[str, dict]) -> None:
        """写入规则集"""
        ruleset["rules"] = list(rules.values())
        
        with open(target_file, "w", encoding="utf-8") as f:
            yaml.dump(ruleset, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def deprecate_rule(
        self,
        rule_id: str,
        reason: str,
        target_file: Optional[Path] = None,
        dry_run: bool = False,
    ) -> MergeOperation:
        """
        停用规则
        
        Args:
            rule_id: 规则 ID
            reason: 停用原因
            target_file: 规则文件
            dry_run: 仅预览
            
        Returns:
            MergeOperation 对象
        """
        if target_file is None:
            target_file = self.guardrails_dir / "auto-generated.yaml"
        
        ruleset = self._load_ruleset(target_file)
        existing_rules = {r["id"]: r for r in ruleset.get("rules", [])}
        
        if rule_id not in existing_rules:
            return MergeOperation(
                operation_type="skip",
                rule_id=rule_id,
                rule_name="",
                details=f"Rule {rule_id} not found",
            )
        
        old_rule = existing_rules[rule_id].copy()
        
        if not dry_run:
            # 标记为停用
            existing_rules[rule_id]["enabled"] = False
            existing_rules[rule_id]["deprecated_at"] = datetime.now().isoformat()
            existing_rules[rule_id]["deprecated_reason"] = reason
            
            self._write_ruleset(target_file, ruleset, existing_rules)
        
        return MergeOperation(
            operation_type="deprecate",
            rule_id=rule_id,
            rule_name=old_rule.get("name", ""),
            details=f"Rule deprecated: {reason}",
            old_rule=old_rule,
            new_rule=existing_rules[rule_id] if not dry_run else None,
        )
    
    def get_merge_preview(self, candidate_file: Optional[Path] = None) -> dict:
        """
        获取合并预览（dry-run 结果）
        
        Args:
            candidate_file: 候选规则文件
            
        Returns:
            预览结果字典
        """
        result = self.merge_candidates(
            candidate_file=candidate_file,
            dry_run=True,
        )
        
        preview = {
            "source_file": result.source_file,
            "target_file": result.target_file,
            "summary": {
                "rules_added": result.rules_added,
                "rules_updated": result.rules_updated,
                "rules_deprecated": result.rules_deprecated,
                "rules_skipped": result.rules_skipped,
            },
            "operations": [],
        }
        
        for op in result.operations:
            preview["operations"].append({
                "type": op.operation_type,
                "rule_id": op.rule_id,
                "rule_name": op.rule_name,
                "details": op.details,
            })
        
        return preview


def create_merger(
    rules_dir: Path,
    auto_approve: bool = False,
    backup_enabled: bool = True,
) -> RuleMerger:
    """创建合并器的便捷函数"""
    return RuleMerger(
        rules_dir=rules_dir,
        auto_approve=auto_approve,
        backup_enabled=backup_enabled,
    )