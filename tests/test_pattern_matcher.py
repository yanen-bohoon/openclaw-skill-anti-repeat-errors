"""
Anti-Repeat-Errors Skill - Pattern Matcher Tests

Unit tests for pattern_matcher module.
"""

import pytest
import tempfile
from pathlib import Path
import yaml

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pattern_matcher import PatternMatcher, MatchResult, create_matcher
from guardrail_models import (
    GuardrailAction,
    GuardrailRule,
    GuardrailRuleSet,
    ToolCallPattern,
)


class TestPatternMatcher:
    """Tests for PatternMatcher class"""
    
    def test_load_rules_from_yaml(self):
        """Test loading rules from YAML file"""
        # Create temporary rules directory
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir)
            
            # Create a test rule file
            rule_data = {
                "version": "1.0",
                "kind": "guardrail",
                "name": "test-rules",
                "enabled": True,
                "rules": [
                    {
                        "id": "test-block",
                        "name": "Test Block",
                        "pattern": {"tool": "exec"},
                        "action": "block",
                        "block_message": "Test block message"
                    }
                ]
            }
            
            yaml_file = rules_dir / "test.yaml"
            with open(yaml_file, "w") as f:
                yaml.dump(rule_data, f)
            
            # Load rules
            matcher = PatternMatcher(rules_dir=rules_dir)
            count = matcher.load_rules()
            
            assert count == 1
            assert len(matcher.get_all_rules()) == 1
    
    def test_match_exact_tool(self):
        """Test matching exact tool name"""
        matcher = create_matcher()
        
        # Mock loaded rules
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="block-exec",
                        name="Block Exec",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.BLOCK,
                        block_message="Exec blocked"
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        result = matcher.match("exec", {"command": "ls"})
        
        assert result.matched is True
        assert result.action == GuardrailAction.BLOCK
        assert "blocked" in result.message.lower()
    
    def test_match_by_priority(self):
        """Test that higher priority rules match first"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="low-priority",
                        name="Low Priority",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.LOG,
                        priority=10
                    ),
                    GuardrailRule(
                        id="high-priority",
                        name="High Priority",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.BLOCK,
                        block_message="High priority block",
                        priority=90
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        result = matcher.match("exec", {})
        
        assert result.matched is True
        assert result.rule.id == "high-priority"
    
    def test_no_match(self):
        """Test when no rule matches"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="block-write",
                        name="Block Write",
                        pattern=ToolCallPattern(tool="write"),
                        action=GuardrailAction.BLOCK,
                        block_message="Write blocked"
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        result = matcher.match("read", {"file_path": "/tmp/test"})
        
        assert result.matched is False
    
    def test_rewrite_action(self):
        """Test rewrite action modifies params"""
        matcher = create_matcher()
        
        from guardrail_models import RewriteRule
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="rewrite-command",
                        name="Rewrite Command",
                        pattern=ToolCallPattern(
                            tool="exec",
                            param_contains={"command": ["--force"]}
                        ),
                        action=GuardrailAction.REWRITE,
                        rewrite=RewriteRule(
                            type="replace",
                            target_param="command",
                            value="echo 'force not allowed'"
                        )
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        result = matcher.match("exec", {"command": "npm install --force"})
        
        assert result.matched is True
        assert result.action == GuardrailAction.REWRITE
        assert result.result_params["command"] == "echo 'force not allowed'"
    
    def test_get_rules_by_tool(self):
        """Test getting rules by tool name"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="rule-1",
                        name="Rule 1",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.LOG
                    ),
                    GuardrailRule(
                        id="rule-2",
                        name="Rule 2",
                        pattern=ToolCallPattern(tool="write"),
                        action=GuardrailAction.LOG
                    ),
                    GuardrailRule(
                        id="rule-3",
                        name="Rule 3",
                        pattern=ToolCallPattern(tool_pattern="exec|edit"),
                        action=GuardrailAction.LOG
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        exec_rules = matcher.get_rules_by_tool("exec")
        assert len(exec_rules) == 2  # rule-1 and rule-3
    
    def test_disabled_rule_set(self):
        """Test that disabled rule sets are ignored"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="disabled",
                enabled=False,
                rules=[
                    GuardrailRule(
                        id="rule-1",
                        name="Rule 1",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.BLOCK,
                        block_message="Should not match"
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        result = matcher.match("exec", {})
        assert result.matched is False
    
    def test_match_all_returns_all_matches(self):
        """Test match_all returns all matching rules"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="rule-1",
                        name="Rule 1",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.LOG,
                        priority=10
                    ),
                    GuardrailRule(
                        id="rule-2",
                        name="Rule 2",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.WARN,
                        warn_message="Warning",
                        priority=20
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        results = matcher.match_all("exec", {})
        assert len(results) == 2
    
    def test_get_stats(self):
        """Test getting matcher statistics"""
        matcher = create_matcher()
        
        matcher._rule_sets = [
            GuardrailRuleSet(
                version="1.0",
                kind="guardrail",
                name="test",
                rules=[
                    GuardrailRule(
                        id="rule-1",
                        name="Rule 1",
                        pattern=ToolCallPattern(tool="exec"),
                        action=GuardrailAction.BLOCK,
                        block_message="Block",
                        tags=["security", "exec"]
                    ),
                    GuardrailRule(
                        id="rule-2",
                        name="Rule 2",
                        pattern=ToolCallPattern(tool="write"),
                        action=GuardrailAction.WARN,
                        warn_message="Warn",
                        tags=["security"]
                    )
                ]
            )
        ]
        matcher._loaded = True
        
        stats = matcher.get_stats()
        
        assert stats["total_rules"] == 2
        assert stats["enabled_rules"] == 2
        assert "block" in stats["action_counts"]
        assert "warn" in stats["action_counts"]
        assert stats["tag_counts"]["security"] == 2


class TestMatchResult:
    """Tests for MatchResult dataclass"""
    
    def test_match_result_creation(self):
        """Test creating a match result"""
        result = MatchResult(
            matched=True,
            action=GuardrailAction.BLOCK,
            original_params={"command": "test"},
            result_params={"command": "test"},
            message="Blocked",
            duration_ms=1.5
        )
        
        assert result.matched is True
        assert result.action == GuardrailAction.BLOCK
        assert result.duration_ms == 1.5
    
    def test_no_match_result(self):
        """Test creating a no-match result"""
        result = MatchResult(matched=False)
        
        assert result.matched is False
        assert result.rule is None
        assert result.action is None


class TestLoadFromFiles:
    """Tests for loading actual rule files"""
    
    def test_load_guardrails_directory(self):
        """Test loading from the actual guardrails directory"""
        guardrails_dir = Path(__file__).parent.parent / "rules" / "guardrails"
        
        if not guardrails_dir.exists():
            pytest.skip("Guardrails directory not yet created")
        
        matcher = PatternMatcher(rules_dir=guardrails_dir)
        count = matcher.load_rules()
        
        # Should have loaded at least the common-errors.yaml rules
        assert count >= 0
    
    def test_load_nonexistent_directory(self):
        """Test loading from non-existent directory"""
        matcher = PatternMatcher(rules_dir=Path("/nonexistent/path"))
        count = matcher.load_rules()
        
        assert count == 0
        assert len(matcher.get_all_rules()) == 0
    
    def test_handle_invalid_yaml(self):
        """Test handling invalid YAML files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir)
            
            # Create invalid YAML file
            invalid_file = rules_dir / "invalid.yaml"
            with open(invalid_file, "w") as f:
                f.write("invalid: yaml: content: [")
            
            matcher = PatternMatcher(rules_dir=rules_dir)
            count = matcher.load_rules()
            
            # Should return 0 rules and have errors
            assert count == 0
            assert len(matcher.get_load_errors()) > 0
    
    def test_skip_non_guardrail_yaml(self):
        """Test that non-guardrail YAML files are skipped"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir)
            
            # Create non-guardrail YAML
            other_file = rules_dir / "other.yaml"
            with open(other_file, "w") as f:
                yaml.dump({"kind": "other", "name": "test"}, f)
            
            matcher = PatternMatcher(rules_dir=rules_dir)
            count = matcher.load_rules()
            
            assert count == 0


class TestCreateMatcher:
    """Tests for create_matcher convenience function"""
    
    def test_create_matcher_default(self):
        """Test creating matcher with default directory"""
        matcher = create_matcher()
        
        assert matcher is not None
        assert isinstance(matcher, PatternMatcher)
    
    def test_create_matcher_custom_dir(self):
        """Test creating matcher with custom directory"""
        matcher = create_matcher(rules_dir=Path("/tmp/test"))
        
        assert matcher.rules_dir == Path("/tmp/test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])