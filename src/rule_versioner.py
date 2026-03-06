"""
Anti-Repeat-Errors Skill - Rule Versioner

Tracks rule version history and changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import yaml


@dataclass
class RuleVersion:
    """规则版本记录"""
    
    version_id: str  # 格式: v{timestamp}
    rule_id: str
    rule_name: str
    
    # 变更信息
    change_type: str  # "created" | "updated" | "enabled" | "disabled" | "deprecated"
    changed_at: str
    changed_by: str = "system"  # system | user:{name}
    
    # 变更内容
    previous_version: Optional[str] = None  # 前一版本 ID
    rule_snapshot: dict = field(default_factory=dict)
    change_summary: str = ""
    
    # 来源追溯
    source_cluster_id: Optional[str] = None
    source_merge_operation: Optional[str] = None  # add/update/deprecate
    
    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "change_type": self.change_type,
            "changed_at": self.changed_at,
            "changed_by": self.changed_by,
            "previous_version": self.previous_version,
            "rule_snapshot": self.rule_snapshot,
            "change_summary": self.change_summary,
            "source_cluster_id": self.source_cluster_id,
            "source_merge_operation": self.source_merge_operation,
        }


@dataclass
class VersionHistory:
    """版本历史"""
    
    rule_id: str
    versions: list[RuleVersion] = field(default_factory=list)
    
    def get_current_version(self) -> Optional[RuleVersion]:
        """获取当前版本（最新的）"""
        if not self.versions:
            return None
        return self.versions[-1]
    
    def get_version(self, version_id: str) -> Optional[RuleVersion]:
        """获取指定版本"""
        for v in self.versions:
            if v.version_id == version_id:
                return v
        return None
    
    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "version_count": len(self.versions),
            "versions": [v.to_dict() for v in self.versions],
        }


@dataclass
class ChangelogEntry:
    """变更日志条目"""
    
    timestamp: str
    operation: str  # merge | deprecate | manual
    summary: str
    
    # 变更详情
    rules_added: int = 0
    rules_updated: int = 0
    rules_deprecated: int = 0
    
    # 来源
    source_file: Optional[str] = None
    merge_result: Optional[dict] = None
    
    def to_dict(self) -> dict:
        result = {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "summary": self.summary,
            "rules_added": self.rules_added,
            "rules_updated": self.rules_updated,
            "rules_deprecated": self.rules_deprecated,
            "source_file": self.source_file,
        }
        if self.merge_result:
            result["merge_result"] = self.merge_result
        return result


class RuleVersioner:
    """
    规则版本追踪器
    
    记录规则变更历史，支持审计和回滚。
    """
    
    def __init__(self, rules_dir: Path):
        """
        初始化版本追踪器
        
        Args:
            rules_dir: 规则目录
        """
        self.rules_dir = Path(rules_dir)
        self.version_dir = self.rules_dir.parent / "versions"
        self.changelog_file = self.rules_dir / "guardrails" / "changelog.yaml"
        
        self.version_dir.mkdir(parents=True, exist_ok=True)
    
    def record_merge(self, merge_result: dict) -> ChangelogEntry:
        """
        记录合并操作的变更
        
        Args:
            merge_result: MergeResult.to_dict() 的结果
            
        Returns:
            ChangelogEntry 对象
        """
        entry = ChangelogEntry(
            timestamp=merge_result["merged_at"],
            operation="merge",
            summary=f"Merged {merge_result['rules_added']} rules, updated {merge_result['rules_updated']}, deprecated {merge_result['rules_deprecated']}",
            rules_added=merge_result["rules_added"],
            rules_updated=merge_result["rules_updated"],
            rules_deprecated=merge_result["rules_deprecated"],
            source_file=merge_result["source_file"],
            merge_result={
                "merged_at": merge_result["merged_at"],
                "target_file": merge_result["target_file"],
                "backup_file": merge_result.get("backup_file"),
            },
        )
        
        # 记录每个规则版本
        for op in merge_result.get("operations", []):
            self._record_version(op)
        
        # 写入变更日志
        self._append_changelog(entry)
        
        return entry
    
    def _record_version(self, operation: dict) -> RuleVersion:
        """记录单个操作为版本"""
        rule_id = operation["rule_id"]
        timestamp = datetime.now().isoformat()
        version_id = f"v{timestamp.replace(':', '-').replace('.', '-')}"
        
        # 确定变更类型
        op_type = operation["operation_type"]
        change_type_map = {
            "add": "created",
            "update": "updated",
            "deprecate": "deprecated",
        }
        change_type = change_type_map.get(op_type, "updated")
        
        # 加载版本历史
        history = self._load_version_history(rule_id)
        
        # 创建版本记录
        version = RuleVersion(
            version_id=version_id,
            rule_id=rule_id,
            rule_name=operation.get("rule_name", ""),
            change_type=change_type,
            changed_at=timestamp,
            previous_version=history.get_current_version().version_id if history.versions else None,
            rule_snapshot=operation.get("new_rule", operation.get("old_rule", {})),
            change_summary=operation.get("details", ""),
            source_cluster_id=operation.get("source_cluster_id"),
            source_merge_operation=op_type,
        )
        
        # 添加到历史
        history.versions.append(version)
        
        # 保存
        self._save_version_history(history)
        
        return version
    
    def _load_version_history(self, rule_id: str) -> VersionHistory:
        """加载规则的版本历史"""
        history_file = self.version_dir / f"{rule_id}.json"
        
        if not history_file.exists():
            return VersionHistory(rule_id=rule_id)
        
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        history = VersionHistory(rule_id=rule_id)
        for v in data.get("versions", []):
            history.versions.append(RuleVersion(
                version_id=v["version_id"],
                rule_id=v["rule_id"],
                rule_name=v["rule_name"],
                change_type=v["change_type"],
                changed_at=v["changed_at"],
                changed_by=v.get("changed_by", "system"),
                previous_version=v.get("previous_version"),
                rule_snapshot=v.get("rule_snapshot", {}),
                change_summary=v.get("change_summary", ""),
                source_cluster_id=v.get("source_cluster_id"),
                source_merge_operation=v.get("source_merge_operation"),
            ))
        
        return history
    
    def _save_version_history(self, history: VersionHistory) -> None:
        """保存版本历史"""
        history_file = self.version_dir / f"{history.rule_id}.json"
        
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _append_changelog(self, entry: ChangelogEntry) -> None:
        """追加变更日志"""
        # 加载现有变更日志
        changelog = self._load_changelog()
        
        # 添加条目
        changelog["entries"].append(entry.to_dict())
        
        # 保存
        self._save_changelog(changelog)
    
    def _load_changelog(self) -> dict:
        """加载变更日志"""
        if not self.changelog_file.exists():
            return {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "entries": [],
            }
        
        with open(self.changelog_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    
    def _save_changelog(self, changelog: dict) -> None:
        """保存变更日志"""
        self.changelog_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.changelog_file, "w", encoding="utf-8") as f:
            yaml.dump(changelog, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def get_rule_history(self, rule_id: str) -> VersionHistory:
        """获取规则的版本历史"""
        return self._load_version_history(rule_id)
    
    def get_changelog(self, limit: int = 50) -> list[ChangelogEntry]:
        """获取变更日志"""
        changelog = self._load_changelog()
        
        entries = []
        for e in changelog.get("entries", [])[-limit:]:
            entries.append(ChangelogEntry(
                timestamp=e["timestamp"],
                operation=e["operation"],
                summary=e["summary"],
                rules_added=e.get("rules_added", 0),
                rules_updated=e.get("rules_updated", 0),
                rules_deprecated=e.get("rules_deprecated", 0),
                source_file=e.get("source_file"),
            ))
        
        return entries
    
    def get_statistics(self) -> dict:
        """获取版本统计"""
        changelog = self._load_changelog()
        entries = changelog.get("entries", [])
        
        # 统计
        total_created = sum(e.get("rules_added", 0) for e in entries)
        total_updated = sum(e.get("rules_updated", 0) for e in entries)
        total_deprecated = sum(e.get("rules_deprecated", 0) for e in entries)
        
        # 按操作类型统计
        by_operation = {}
        for e in entries:
            op = e.get("operation", "unknown")
            by_operation[op] = by_operation.get(op, 0) + 1
        
        return {
            "total_entries": len(entries),
            "total_rules_created": total_created,
            "total_rules_updated": total_updated,
            "total_rules_deprecated": total_deprecated,
            "by_operation": by_operation,
            "first_entry": entries[0]["timestamp"] if entries else None,
            "last_entry": entries[-1]["timestamp"] if entries else None,
        }
    
    def rollback_rule(self, rule_id: str, target_version_id: str, target_file: Path) -> bool:
        """
        回滚规则到指定版本
        
        Args:
            rule_id: 规则 ID
            target_version_id: 目标版本 ID
            target_file: 规则文件路径
            
        Returns:
            是否成功
        """
        # 获取版本历史
        history = self._load_version_history(rule_id)
        target_version = history.get_version(target_version_id)
        
        if target_version is None:
            print(f"[error] Version {target_version_id} not found for rule {rule_id}")
            return False
        
        # 加载规则集
        if not target_file.exists():
            print(f"[error] Target file not found: {target_file}")
            return False
        
        with open(target_file, "r", encoding="utf-8") as f:
            ruleset = yaml.safe_load(f)
        
        if not ruleset:
            return False
        
        # 找到并更新规则
        for i, rule in enumerate(ruleset.get("rules", [])):
            if rule["id"] == rule_id:
                # 恢复到目标版本的快照
                ruleset["rules"][i] = target_version.rule_snapshot.copy()
                ruleset["rules"][i]["rolled_back_at"] = datetime.now().isoformat()
                ruleset["rules"][i]["rolled_back_from"] = target_version_id
                break
        else:
            print(f"[error] Rule {rule_id} not found in target file")
            return False
        
        # 保存
        with open(target_file, "w", encoding="utf-8") as f:
            yaml.dump(ruleset, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        # 记录回滚版本
        rollback_version = RuleVersion(
            version_id=f"v{datetime.now().isoformat().replace(':', '-').replace('.', '-')}",
            rule_id=rule_id,
            rule_name=target_version.rule_name,
            change_type="rollback",
            changed_at=datetime.now().isoformat(),
            changed_by="system",
            previous_version=history.get_current_version().version_id if history.versions else None,
            rule_snapshot=target_version.rule_snapshot,
            change_summary=f"Rolled back to version {target_version_id}",
        )
        history.versions.append(rollback_version)
        self._save_version_history(history)
        
        return True
    
    def generate_changelog_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """
        生成变更日志报告
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            Markdown 格式的报告
        """
        changelog = self._load_changelog()
        entries = changelog.get("entries", [])
        
        # 过滤日期范围
        if start_date:
            entries = [e for e in entries if e["timestamp"] >= start_date]
        if end_date:
            entries = [e for e in entries if e["timestamp"] <= end_date]
        
        lines = [
            "# Guardrail Rules Changelog",
            "",
            f"**Generated at:** {datetime.now().isoformat()}",
            f"**Total entries:** {len(entries)}",
            "",
            "## Summary",
            "",
        ]
        
        # 统计
        stats = self.get_statistics()
        lines.extend([
            f"- Rules created: {stats['total_rules_created']}",
            f"- Rules updated: {stats['total_rules_updated']}",
            f"- Rules deprecated: {stats['total_rules_deprecated']}",
            "",
            "## Entries",
            "",
        ])
        
        # 条目列表
        for e in reversed(entries[-50:]):  # 最近 50 条
            lines.extend([
                f"### {e['timestamp']}",
                "",
                f"**Operation:** {e['operation']}",
                f"**Summary:** {e['summary']}",
                "",
                f"- Added: {e.get('rules_added', 0)}",
                f"- Updated: {e.get('rules_updated', 0)}",
                f"- Deprecated: {e.get('rules_deprecated', 0)}",
                "",
            ])
        
        return "\n".join(lines)


def create_versioner(rules_dir: Path) -> RuleVersioner:
    """创建版本追踪器的便捷函数"""
    return RuleVersioner(rules_dir=rules_dir)