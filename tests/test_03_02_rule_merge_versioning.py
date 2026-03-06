"""
Tests for Plan 03-02: Rule Merge & Versioning
"""

import pytest
from pathlib import Path
import tempfile
import yaml
import json

from src.rule_merger import RuleMerger, MergeOperation, MergeResult, create_merger
from src.rule_versioner import RuleVersioner, RuleVersion, VersionHistory, ChangelogEntry, create_versioner


class TestRuleMerger:
    """Tests for RuleMerger"""
    
    @pytest.fixture
    def temp_rules_dir(self, tmp_path):
        """Create a temporary rules directory"""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "guardrails").mkdir()
        (rules_dir.parent / "candidates").mkdir()
        (rules_dir.parent / "versions").mkdir()
        return rules_dir
    
    @pytest.fixture
    def sample_candidate_file(self, temp_rules_dir):
        """Create a sample candidate file"""
        candidates_dir = temp_rules_dir.parent / "candidates"
        candidate_file = candidates_dir / "candidates_test.yaml"
        
        content = {
            "version": "1.0",
            "kind": "guardrail",
            "name": "test-candidates",
            "rules": [
                {
                    "id": "test-rule-001",
                    "name": "Test Rule",
                    "description": "A test rule",
                    "pattern": {
                        "tool": "exec",
                        "param_patterns": {"command": "^test\\b"}
                    },
                    "action": "warn",
                    "warn_message": "Test warning",
                    "priority": 70,
                    "enabled": False,
                    "tags": ["test", "cluster:test-cluster"]
                }
            ]
        }
        
        with open(candidate_file, "w") as f:
            yaml.dump(content, f)
        
        return candidate_file
    
    def test_create_merger(self, temp_rules_dir):
        """Test creating a merger"""
        merger = create_merger(temp_rules_dir)
        assert merger.rules_dir == temp_rules_dir
        assert merger.auto_approve == False
        assert merger.backup_enabled == True
    
    def test_merge_candidates_dry_run(self, temp_rules_dir, sample_candidate_file):
        """Test merging candidates in dry-run mode"""
        merger = RuleMerger(temp_rules_dir, auto_approve=True)
        result = merger.merge_candidates(
            candidate_file=sample_candidate_file,
            dry_run=True
        )
        
        assert result.rules_added == 1
        assert result.rules_updated == 0
        assert len(result.operations) == 1
        assert result.operations[0].operation_type == "add"
    
    def test_merge_candidates_actual(self, temp_rules_dir, sample_candidate_file):
        """Test actually merging candidates"""
        merger = RuleMerger(temp_rules_dir, auto_approve=True, backup_enabled=False)
        result = merger.merge_candidates(
            candidate_file=sample_candidate_file,
            dry_run=False
        )
        
        assert result.rules_added == 1
        
        # Verify file was created
        target_file = temp_rules_dir / "guardrails" / "auto-generated.yaml"
        assert target_file.exists()
        
        with open(target_file) as f:
            data = yaml.safe_load(f)
        
        assert len(data["rules"]) == 1
        assert data["rules"][0]["id"] == "test-rule-001"
    
    def test_merge_update_existing(self, temp_rules_dir, sample_candidate_file):
        """Test updating existing rules"""
        merger = RuleMerger(temp_rules_dir, auto_approve=True, backup_enabled=False)
        
        # First merge
        result1 = merger.merge_candidates(candidate_file=sample_candidate_file, dry_run=False)
        assert result1.rules_added == 1
        
        # Modify candidate with same ID but different priority
        candidate_file = temp_rules_dir.parent / "candidates" / "candidates_test2.yaml"
        content = {
            "version": "1.0",
            "kind": "guardrail",
            "name": "test-candidates",
            "rules": [
                {
                    "id": "test-rule-001",
                    "name": "Test Rule Updated",
                    "description": "Updated description",
                    "pattern": {
                        "tool": "exec",
                        "param_patterns": {"command": "^test\\b"}
                    },
                    "action": "block",
                    "block_message": "Now blocking",
                    "priority": 80,  # Different priority
                    "enabled": False,
                    "tags": ["test", "cluster:test-cluster"]
                }
            ]
        }
        with open(candidate_file, "w") as f:
            yaml.dump(content, f)
        
        # Second merge should update
        result2 = merger.merge_candidates(candidate_file=candidate_file, dry_run=False)
        assert result2.rules_updated == 1
    
    def test_deprecate_rule(self, temp_rules_dir, sample_candidate_file):
        """Test deprecating a rule"""
        merger = RuleMerger(temp_rules_dir, auto_approve=True, backup_enabled=False)
        
        # First merge
        merger.merge_candidates(candidate_file=sample_candidate_file, dry_run=False)
        
        # Deprecate
        op = merger.deprecate_rule("test-rule-001", "Test deprecation", dry_run=False)
        
        assert op.operation_type == "deprecate"
        assert op.rule_id == "test-rule-001"


class TestRuleVersioner:
    """Tests for RuleVersioner"""
    
    @pytest.fixture
    def temp_rules_dir(self, tmp_path):
        """Create a temporary rules directory"""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "guardrails").mkdir()
        (rules_dir.parent / "versions").mkdir()
        return rules_dir
    
    def test_create_versioner(self, temp_rules_dir):
        """Test creating a versioner"""
        versioner = create_versioner(temp_rules_dir)
        assert versioner.rules_dir == temp_rules_dir
    
    def test_record_merge(self, temp_rules_dir):
        """Test recording a merge operation"""
        versioner = RuleVersioner(temp_rules_dir)
        
        merge_result = {
            "merged_at": "2026-03-06T10:00:00",
            "source_file": "/test/candidates.yaml",
            "target_file": "/test/rules.yaml",
            "rules_added": 1,
            "rules_updated": 0,
            "rules_deprecated": 0,
            "operations": [
                {
                    "operation_type": "add",
                    "rule_id": "test-rule-001",
                    "rule_name": "Test Rule",
                    "details": "New rule",
                    "new_rule": {"id": "test-rule-001", "name": "Test Rule"},
                    "source_cluster_id": "cluster-001",
                }
            ]
        }
        
        entry = versioner.record_merge(merge_result)
        
        assert entry.rules_added == 1
        assert entry.operation == "merge"
    
    def test_get_rule_history(self, temp_rules_dir):
        """Test getting rule history"""
        versioner = RuleVersioner(temp_rules_dir)
        
        # Record a merge
        merge_result = {
            "merged_at": "2026-03-06T10:00:00",
            "source_file": "/test/candidates.yaml",
            "target_file": "/test/rules.yaml",
            "rules_added": 1,
            "rules_updated": 0,
            "rules_deprecated": 0,
            "operations": [
                {
                    "operation_type": "add",
                    "rule_id": "test-rule-001",
                    "rule_name": "Test Rule",
                    "details": "New rule",
                    "new_rule": {"id": "test-rule-001"},
                    "source_cluster_id": "cluster-001",
                }
            ]
        }
        versioner.record_merge(merge_result)
        
        # Get history
        history = versioner.get_rule_history("test-rule-001")
        
        assert len(history.versions) == 1
        assert history.versions[0].change_type == "created"
    
    def test_get_statistics(self, temp_rules_dir):
        """Test getting statistics"""
        versioner = RuleVersioner(temp_rules_dir)
        
        # Record multiple merges
        for i in range(3):
            merge_result = {
                "merged_at": f"2026-03-06T10:0{i}:00",
                "source_file": f"/test/candidates{i}.yaml",
                "target_file": "/test/rules.yaml",
                "rules_added": 1,
                "rules_updated": 0,
                "rules_deprecated": 0,
                "operations": [
                    {
                        "operation_type": "add",
                        "rule_id": f"test-rule-{i:03d}",
                        "rule_name": f"Test Rule {i}",
                        "details": "New rule",
                        "new_rule": {"id": f"test-rule-{i:03d}"},
                        "source_cluster_id": f"cluster-{i}",
                    }
                ]
            }
            versioner.record_merge(merge_result)
        
        stats = versioner.get_statistics()
        
        assert stats["total_entries"] == 3
        assert stats["total_rules_created"] == 3
        assert stats["by_operation"]["merge"] == 3
    
    def test_generate_changelog_report(self, temp_rules_dir):
        """Test generating changelog report"""
        versioner = RuleVersioner(temp_rules_dir)
        
        # Record a merge
        merge_result = {
            "merged_at": "2026-03-06T10:00:00",
            "source_file": "/test/candidates.yaml",
            "target_file": "/test/rules.yaml",
            "rules_added": 1,
            "rules_updated": 0,
            "rules_deprecated": 0,
            "operations": [
                {
                    "operation_type": "add",
                    "rule_id": "test-rule-001",
                    "rule_name": "Test Rule",
                    "details": "New rule",
                    "new_rule": {"id": "test-rule-001"},
                    "source_cluster_id": "cluster-001",
                }
            ]
        }
        versioner.record_merge(merge_result)
        
        report = versioner.generate_changelog_report()
        
        assert "# Guardrail Rules Changelog" in report
        assert "Rules created: 1" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])