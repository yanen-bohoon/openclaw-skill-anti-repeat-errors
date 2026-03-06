#!/usr/bin/env python3
"""
Anti-Repeat-Errors - Unit Tests for Rule Loader

Run with: pytest tests/test_rule_loader.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest
import yaml

# Setup path for imports
import sys

test_dir = Path(__file__).parent
skill_dir = test_dir.parent
sys.path.insert(0, str(skill_dir))

from src.models import LoadedRules, Rule, RuleCondition, RuleSet
from src.rule_loader import RuleLoader, create_loader


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def empty_rules_dir(tmp_path: Path) -> Path:
    """创建空规则目录"""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    return rules_dir


@pytest.fixture
def valid_rules_dir(tmp_path: Path) -> Path:
    """创建包含有效规则文件的目录"""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    # 创建子目录
    (rules_dir / "phases").mkdir()
    (rules_dir / "task-types").mkdir()
    (rules_dir / "global").mkdir()

    # Phase 1 规则
    phase1 = {
        "version": "1.0",
        "kind": "phase",
        "name": "phase-1",
        "description": "Phase 1 rules",
        "enabled": True,
        "rules": [
            {
                "id": "phase-1-git-ban",
                "name": "No direct git operations",
                "condition": {"phase": 1},
                "content": "Do not use git directly in phase 1.",
                "priority": 100,
                "enabled": True,
            },
            {
                "id": "phase-1-confirm",
                "name": "Require confirmation",
                "condition": {"phase": 1},
                "content": "Ask for confirmation before actions.",
                "priority": 90,
                "enabled": True,
            },
        ],
    }
    with open(rules_dir / "phases" / "phase-1.yaml", "w") as f:
        yaml.dump(phase1, f)

    # Phase 2 规则
    phase2 = {
        "version": "1.0",
        "kind": "phase",
        "name": "phase-2",
        "enabled": True,
        "rules": [
            {
                "id": "phase-2-commit-msg",
                "name": "Commit message format",
                "condition": {"phase": 2},
                "content": "Use conventional commits format.",
                "priority": 80,
                "enabled": True,
            }
        ],
    }
    with open(rules_dir / "phases" / "phase-2.yaml", "w") as f:
        yaml.dump(phase2, f)

    # Task-type 规则
    coding = {
        "version": "1.0",
        "kind": "task-type",
        "name": "coding",
        "enabled": True,
        "rules": [
            {
                "id": "coding-no-secrets",
                "name": "No hardcoded secrets",
                "condition": {"keywords": ["api_key", "password"]},
                "content": "Do not hardcode secrets.",
                "priority": 100,
                "enabled": True,
            },
            {
                "id": "coding-test-first",
                "name": "Test first",
                "condition": {"task_type": "coding"},
                "content": "Write tests first.",
                "priority": 70,
                "enabled": True,
            },
        ],
    }
    with open(rules_dir / "task-types" / "coding.yaml", "w") as f:
        yaml.dump(coding, f)

    # Global 规则
    core = {
        "version": "1.0",
        "kind": "global",
        "name": "core",
        "enabled": True,
        "rules": [
            {
                "id": "core-no-destructive",
                "name": "No destructive ops",
                "condition": {},
                "content": "Do not perform destructive operations without confirmation.",
                "priority": 100,
                "enabled": True,
            }
        ],
    }
    with open(rules_dir / "global" / "core.yaml", "w") as f:
        yaml.dump(core, f)

    return rules_dir


@pytest.fixture
def invalid_rules_dir(tmp_path: Path) -> Path:
    """创建包含无效规则文件的目录"""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "phases").mkdir()

    # 无效 YAML
    with open(rules_dir / "phases" / "invalid.yaml", "w") as f:
        f.write("version: 1.0\nkind: phase\nrules: [\n  {invalid syntax")

    # 缺少必需字段
    missing_fields = {
        "version": "1.0",
        "kind": "phase",
        # missing 'name' and 'rules'
    }
    with open(rules_dir / "phases" / "missing-fields.yaml", "w") as f:
        yaml.dump(missing_fields, f)

    # 有效规则（应该被加载）
    valid = {
        "version": "1.0",
        "kind": "phase",
        "name": "valid",
        "enabled": True,
        "rules": [
            {
                "id": "valid-rule-1",
                "name": "Valid rule",
                "content": "This is valid",
                "priority": 50,
                "enabled": True,
            }
        ],
    }
    with open(rules_dir / "phases" / "valid.yaml", "w") as f:
        yaml.dump(valid, f)

    return rules_dir


# ============================================================================
# Test RuleCondition
# ============================================================================


class TestRuleCondition:
    """测试 RuleCondition 模型"""

    def test_empty_condition_matches_all(self):
        """空条件匹配所有上下文"""
        cond = RuleCondition()
        assert cond.matches({})
        assert cond.matches({"phase": 1})
        assert cond.matches({"task_type": "coding"})

    def test_phase_condition(self):
        """阶段条件匹配"""
        cond = RuleCondition(phase=1)
        assert cond.matches({"phase": 1})
        assert not cond.matches({"phase": 2})
        assert not cond.matches({})

    def test_task_type_condition(self):
        """任务类型条件匹配"""
        cond = RuleCondition(task_type="coding")
        assert cond.matches({"task_type": "coding"})
        assert not cond.matches({"task_type": "research"})
        assert not cond.matches({})

    def test_keywords_condition(self):
        """关键词条件匹配"""
        cond = RuleCondition(keywords=["git", "commit"])
        assert cond.matches({"message": "please git commit this"})
        assert cond.matches({"message": "GIT STATUS"})
        assert not cond.matches({"message": "hello world"})

    def test_files_matching_condition(self):
        """文件匹配条件"""
        cond = RuleCondition(files_matching=["**/config.json", "*.yaml"])
        assert cond.matches({"files": ["config.json", "app.py"]})
        assert cond.matches({"files": ["src/config.json"]})
        assert cond.matches({"files": ["rules.yaml"]})
        assert not cond.matches({"files": ["app.py", "test.js"]})
        assert not cond.matches({})

    def test_tools_condition(self):
        """工具条件匹配"""
        cond = RuleCondition(tools=["exec", "write"])
        assert cond.matches({"tools": ["exec", "read"]})
        assert cond.matches({"tools": ["write"]})
        assert not cond.matches({"tools": ["read"]})

    def test_combined_conditions(self):
        """组合条件"""
        cond = RuleCondition(phase=1, task_type="coding")
        assert cond.matches({"phase": 1, "task_type": "coding"})
        assert not cond.matches({"phase": 1, "task_type": "research"})
        assert not cond.matches({"phase": 2, "task_type": "coding"})

    def test_phase_validation(self):
        """阶段必须 >= 1"""
        with pytest.raises(Exception):  # Pydantic ValidationError
            RuleCondition(phase=0)


# ============================================================================
# Test Rule
# ============================================================================


class TestRule:
    """测试 Rule 模型"""

    def test_valid_rule(self):
        """创建有效规则"""
        rule = Rule(
            id="test-rule",
            name="Test Rule",
            content="This is a test rule",
            priority=50,
        )
        assert rule.id == "test-rule"
        assert rule.name == "Test Rule"
        assert rule.enabled is True
        assert rule.priority == 50

    def test_default_values(self):
        """默认值"""
        rule = Rule(id="test", name="Test", content="Content")
        assert rule.priority == 50
        assert rule.enabled is True
        assert rule.tags == []

    def test_id_pattern_validation(self):
        """ID 格式验证"""
        # 有效 ID
        Rule(id="valid-id_123", name="Test", content="Content")

        # 无效 ID
        with pytest.raises(Exception):
            Rule(id="invalid id!", name="Test", content="Content")

    def test_priority_range(self):
        """优先级范围"""
        Rule(id="test", name="Test", content="Content", priority=0)
        Rule(id="test", name="Test", content="Content", priority=100)

        with pytest.raises(Exception):
            Rule(id="test", name="Test", content="Content", priority=-1)

        with pytest.raises(Exception):
            Rule(id="test", name="Test", content="Content", priority=101)

    def test_matches_context(self):
        """规则匹配上下文"""
        rule = Rule(
            id="test",
            name="Test",
            content="Content",
            condition=RuleCondition(phase=1),
        )
        assert rule.matches({"phase": 1})
        assert not rule.matches({"phase": 2})

    def test_disabled_rule_doesnt_match(self):
        """禁用的规则不匹配"""
        rule = Rule(
            id="test",
            name="Test",
            content="Content",
            enabled=False,
        )
        assert not rule.matches({})


# ============================================================================
# Test RuleSet
# ============================================================================


class TestRuleSet:
    """测试 RuleSet 模型"""

    def test_valid_ruleset(self):
        """创建有效规则集"""
        rs = RuleSet(
            kind="phase",
            name="test-phase",
            rules=[
                Rule(id="r1", name="Rule 1", content="Content 1"),
                Rule(id="r2", name="Rule 2", content="Content 2"),
            ],
        )
        assert rs.kind == "phase"
        assert len(rs.rules) == 2

    def test_version_validation(self):
        """版本格式验证"""
        RuleSet(kind="global", name="test", version="1.0")

        with pytest.raises(Exception):
            RuleSet(kind="global", name="test", version="v1")

    def test_get_enabled_rules(self):
        """获取启用的规则"""
        rs = RuleSet(
            kind="phase",
            name="test",
            enabled=True,
            rules=[
                Rule(id="r1", name="R1", content="C1", enabled=True),
                Rule(id="r2", name="R2", content="C2", enabled=False),
            ],
        )
        enabled = rs.get_enabled_rules()
        assert len(enabled) == 1
        assert enabled[0].id == "r1"

    def test_disabled_ruleset(self):
        """禁用的规则集"""
        rs = RuleSet(
            kind="phase",
            name="test",
            enabled=False,
            rules=[Rule(id="r1", name="R1", content="C1")],
        )
        assert rs.get_enabled_rules() == []


# ============================================================================
# Test LoadedRules
# ============================================================================


class TestLoadedRules:
    """测试 LoadedRules 模型"""

    def test_get_all_rules(self):
        """获取所有规则"""
        loaded = LoadedRules(
            rule_sets=[
                RuleSet(
                    kind="global",
                    name="g1",
                    rules=[Rule(id="g1-r1", name="G1R1", content="C")],
                ),
                RuleSet(
                    kind="phase",
                    name="p1",
                    rules=[Rule(id="p1-r1", name="P1R1", content="C")],
                ),
            ]
        )
        all_rules = loaded.get_all_rules()
        assert len(all_rules) == 2

    def test_get_rules_by_phase(self):
        """按阶段获取规则"""
        loaded = LoadedRules(
            rule_sets=[
                RuleSet(
                    kind="phase",
                    name="p1",
                    rules=[
                        Rule(
                            id="p1-r1",
                            name="P1R1",
                            content="C",
                            condition=RuleCondition(phase=1),
                            priority=50,
                        )
                    ],
                ),
                RuleSet(
                    kind="phase",
                    name="p2",
                    rules=[
                        Rule(
                            id="p2-r1",
                            name="P2R1",
                            content="C",
                            condition=RuleCondition(phase=2),
                            priority=50,
                        )
                    ],
                ),
            ]
        )
        phase1_rules = loaded.get_rules_by_phase(1)
        assert len(phase1_rules) == 1
        assert phase1_rules[0].id == "p1-r1"

    def test_get_matching_rules_priority_sort(self):
        """匹配规则按优先级排序"""
        loaded = LoadedRules(
            rule_sets=[
                RuleSet(
                    kind="global",
                    name="g1",
                    rules=[
                        Rule(id="r1", name="R1", content="C", priority=30),
                        Rule(id="r2", name="R2", content="C", priority=90),
                        Rule(id="r3", name="R3", content="C", priority=60),
                    ],
                )
            ]
        )
        matching = loaded.get_matching_rules({})
        assert matching[0].id == "r2"  # priority 90
        assert matching[1].id == "r3"  # priority 60
        assert matching[2].id == "r1"  # priority 30


# ============================================================================
# Test RuleLoader
# ============================================================================


class TestRuleLoader:
    """测试 RuleLoader"""

    def test_load_empty_rules_dir(self, empty_rules_dir: Path):
        """加载空目录"""
        loader = RuleLoader(empty_rules_dir)
        loaded = loader.load_all()

        assert loaded.total_rules == 0
        assert len(loaded.rule_sets) == 0
        assert len(loaded.source_files) == 0

    def test_load_valid_rules(self, valid_rules_dir: Path):
        """加载有效规则"""
        loader = RuleLoader(valid_rules_dir)
        loaded = loader.load_all()

        assert loaded.total_rules == 6  # 2 + 1 + 2 + 1
        assert len(loaded.rule_sets) == 4
        assert len(loaded.errors) == 0

    def test_load_invalid_yaml_skipped(self, invalid_rules_dir: Path):
        """无效 YAML 被跳过并记录错误"""
        loader = RuleLoader(invalid_rules_dir, fail_on_error=False)
        loaded = loader.load_all()

        # 应该加载有效文件
        assert len(loaded.rule_sets) == 1  # 只有 valid.yaml
        assert loaded.total_rules == 1

        # 应该有错误记录
        assert len(loaded.errors) > 0

    def test_filter_by_phase(self, valid_rules_dir: Path):
        """按阶段筛选"""
        loader = RuleLoader(valid_rules_dir)
        phase1_rules = loader.load_by_phase(1)

        assert len(phase1_rules) == 2
        assert all(r.condition.phase == 1 for r in phase1_rules)

    def test_filter_by_task_type(self, valid_rules_dir: Path):
        """按任务类型筛选"""
        loader = RuleLoader(valid_rules_dir)
        coding_rules = loader.load_by_task_type("coding")

        assert len(coding_rules) == 1
        assert coding_rules[0].id == "coding-test-first"

    def test_get_global_rules(self, valid_rules_dir: Path):
        """获取全局规则"""
        loader = RuleLoader(valid_rules_dir)
        global_rules = loader.get_global_rules()

        assert len(global_rules) == 1
        assert global_rules[0].id == "core-no-destructive"

    def test_cache(self, valid_rules_dir: Path):
        """缓存功能"""
        loader = RuleLoader(valid_rules_dir, cache_enabled=True, cache_ttl_seconds=60)

        # 第一次加载
        loaded1 = loader.load_all()
        cache_time = loader._cache_time

        # 第二次应该返回缓存
        loaded2 = loader.load_all()
        assert loader._cache_time == cache_time

        # 强制重载
        loaded3 = loader.reload()
        assert loader._cache_time > cache_time

    def test_cache_disabled(self, valid_rules_dir: Path):
        """禁用缓存"""
        loader = RuleLoader(valid_rules_dir, cache_enabled=False)

        loaded1 = loader.load_all()
        loaded2 = loader.load_all()

        # 每次都应该重新加载
        assert loader._cache is None

    def test_get_matching_rules(self, valid_rules_dir: Path):
        """获取匹配上下文的规则"""
        loader = RuleLoader(valid_rules_dir)

        # Phase 1 + coding context
        context = {"phase": 1, "task_type": "coding"}
        matching = loader.get_matching_rules(context)

        # 应该包含 phase 1 规则 + global 规则
        rule_ids = [r.id for r in matching]
        assert "phase-1-git-ban" in rule_ids
        assert "phase-1-confirm" in rule_ids
        assert "core-no-destructive" in rule_ids

        # 关键词匹配
        context = {"message": "please commit my api_key"}
        matching = loader.get_matching_rules(context)
        rule_ids = [r.id for r in matching]
        assert "coding-no-secrets" in rule_ids

    def test_get_rule_by_id(self, valid_rules_dir: Path):
        """根据 ID 获取规则"""
        loader = RuleLoader(valid_rules_dir)

        rule = loader.get_rule_by_id("phase-1-git-ban")
        assert rule is not None
        assert rule.name == "No direct git operations"

        rule = loader.get_rule_by_id("nonexistent")
        assert rule is None

    def test_get_all_rule_ids(self, valid_rules_dir: Path):
        """获取所有规则 ID"""
        loader = RuleLoader(valid_rules_dir)
        ids = loader.get_all_rule_ids()

        assert "phase-1-git-ban" in ids
        assert "phase-1-confirm" in ids
        assert "core-no-destructive" in ids


# ============================================================================
# Test create_loader
# ============================================================================


class TestCreateLoader:
    """测试 create_loader 便捷函数"""

    def test_default_path(self, tmp_path: Path, monkeypatch):
        """默认路径"""
        loader = create_loader(rules_dir=tmp_path / "rules")
        assert loader.rules_dir == tmp_path / "rules"
        assert loader.cache_enabled is True


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """集成测试"""

    def test_full_workflow(self, valid_rules_dir: Path):
        """完整工作流"""
        # 1. 创建加载器
        loader = RuleLoader(valid_rules_dir)

        # 2. 加载所有规则
        loaded = loader.load_all()
        assert loaded.total_rules > 0

        # 3. 获取特定上下文的规则
        context = {"phase": 1, "task_type": "coding", "tools": ["exec"]}
        matching = loader.get_matching_rules(context)

        # 4. 验证规则按优先级排序
        priorities = [r.priority for r in matching]
        assert priorities == sorted(priorities, reverse=True)

        # 5. 清除缓存并重新加载
        loader.clear_cache()
        loaded2 = loader.load_all()
        assert loaded2.total_rules == loaded.total_rules


if __name__ == "__main__":
    pytest.main([__file__, "-v"])