"""
Anti-Repeat-Errors Skill - Guardrail Models Tests

Unit tests for guardrail_models module.
"""

import pytest
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from guardrail_models import (
    GuardrailAction,
    ToolCallPattern,
    RewriteRule,
    GuardrailRule,
    GuardrailRuleSet,
    GuardrailHit,
)


class TestToolCallPattern:
    """Tests for ToolCallPattern model"""
    
    def test_exact_tool_match(self):
        """Test exact tool name matching"""
        pattern = ToolCallPattern(tool="exec")
        
        matched, reason = pattern.matches("exec", {"command": "ls"})
        assert matched is True
        
        matched, reason = pattern.matches("write", {"file_path": "/tmp/test.txt"})
        assert matched is False
    
    def test_tool_pattern_match(self):
        """Test regex tool name matching"""
        pattern = ToolCallPattern(tool_pattern="exec|write|edit")
        
        matched, _ = pattern.matches("exec", {})
        assert matched is True
        
        matched, _ = pattern.matches("write", {})
        assert matched is True
        
        matched, _ = pattern.matches("read", {})
        assert matched is False
    
    def test_param_patterns(self):
        """Test parameter regex matching"""
        pattern = ToolCallPattern(
            tool="exec",
            param_patterns={"command": r"^git\s+(status|add|commit)"}
        )
        
        matched, _ = pattern.matches("exec", {"command": "git status"})
        assert matched is True
        
        matched, _ = pattern.matches("exec", {"command": "git log"})
        assert matched is False
    
    def test_param_contains(self):
        """Test parameter keyword containment"""
        pattern = ToolCallPattern(
            tool="exec",
            param_contains={"command": ["--force", "-f", "--yes"]}
        )
        
        matched, _ = pattern.matches("exec", {"command": "npm install --force"})
        assert matched is True
        
        matched, _ = pattern.matches("exec", {"command": "npm install -f"})
        assert matched is True
        
        matched, _ = pattern.matches("exec", {"command": "npm install"})
        assert matched is False
    
    def test_param_paths(self):
        """Test parameter path glob matching"""
        pattern = ToolCallPattern(
            tool="write",
            param_paths={
                "file_path": [
                    "**/.openclaw/openclaw.json",
                    "**/gateway.env"
                ]
            }
        )
        
        matched, _ = pattern.matches("write", {"file_path": "/home/user/.openclaw/openclaw.json"})
        assert matched is True
        
        matched, _ = pattern.matches("write", {"file_path": "/etc/gateway.env"})
        assert matched is True
        
        matched, _ = pattern.matches("write", {"file_path": "/tmp/test.txt"})
        assert matched is False
    
    def test_invalid_regex_pattern(self):
        """Test that invalid regex patterns are rejected"""
        with pytest.raises(Exception):  # ValidationError
            ToolCallPattern(tool_pattern="[invalid(regex")
    
    def test_combined_conditions(self):
        """Test combining multiple conditions"""
        pattern = ToolCallPattern(
            tool="exec",
            param_patterns={"command": r"^npm"},
            param_contains={"command": ["--force"]}
        )
        
        matched, _ = pattern.matches("exec", {"command": "npm install --force"})
        assert matched is True
        
        matched, _ = pattern.matches("exec", {"command": "npm install"})
        assert matched is False


class TestRewriteRule:
    """Tests for RewriteRule model"""
    
    def test_replace_rewrite(self):
        """Test replace type rewrite"""
        rule = RewriteRule(
            type="replace",
            target_param="command",
            value="npm install"
        )
        
        result = rule.apply({"command": "npm install --force", "cwd": "/app"})
        assert result["command"] == "npm install"
        assert result["cwd"] == "/app"
    
    def test_prepend_rewrite(self):
        """Test prepend type rewrite"""
        rule = RewriteRule(
            type="prepend",
            target_param="command",
            value="echo 'Starting...' && "
        )
        
        result = rule.apply({"command": "npm test"})
        assert result["command"] == "echo 'Starting...' && npm test"
    
    def test_append_rewrite(self):
        """Test append type rewrite"""
        rule = RewriteRule(
            type="append",
            target_param="command",
            value=" --no-verify"
        )
        
        result = rule.apply({"command": "git commit"})
        assert result["command"] == "git commit --no-verify"
    
    def test_template_rewrite(self):
        """Test template type rewrite"""
        rule = RewriteRule(
            type="template",
            target_param="message",
            value="Original: {original}, New: {value}",
            template_vars={
                "original": "$command",
                "value": "$file_path"
            }
        )
        
        result = rule.apply({
            "command": "git status",
            "file_path": "/app/test.txt"
        })
        assert result["message"] == "Original: git status, New: /app/test.txt"


class TestGuardrailRule:
    """Tests for GuardrailRule model"""
    
    def test_block_rule(self):
        """Test block action rule"""
        rule = GuardrailRule(
            id="test-block",
            name="Test Block Rule",
            pattern=ToolCallPattern(tool="exec"),
            action=GuardrailAction.BLOCK,
            block_message="Blocked for testing"
        )
        
        matched, _ = rule.matches("exec", {})
        assert matched is True
        
        action, params, msg = rule.execute("exec", {"command": "test"})
        assert action == GuardrailAction.BLOCK
        assert "Blocked for testing" in msg
    
    def test_warn_rule(self):
        """Test warn action rule"""
        rule = GuardrailRule(
            id="test-warn",
            name="Test Warn Rule",
            pattern=ToolCallPattern(tool="write"),
            action=GuardrailAction.WARN,
            warn_message="Warning for testing"
        )
        
        action, params, msg = rule.execute("write", {"file_path": "/tmp/test"})
        assert action == GuardrailAction.WARN
        assert "Warning" in msg
    
    def test_rewrite_rule(self):
        """Test rewrite action rule"""
        rule = GuardrailRule(
            id="test-rewrite",
            name="Test Rewrite Rule",
            pattern=ToolCallPattern(tool="exec"),
            action=GuardrailAction.REWRITE,
            rewrite=RewriteRule(
                type="replace",
                target_param="command",
                value="echo 'rewritten'"
            )
        )
        
        action, params, msg = rule.execute("exec", {"command": "rm -rf /"})
        assert action == GuardrailAction.REWRITE
        assert params["command"] == "echo 'rewritten'"
    
    def test_log_rule(self):
        """Test log action rule"""
        rule = GuardrailRule(
            id="test-log",
            name="Test Log Rule",
            pattern=ToolCallPattern(tool="read"),
            action=GuardrailAction.LOG
        )
        
        action, params, msg = rule.execute("read", {"file_path": "/tmp/test"})
        assert action == GuardrailAction.LOG
        assert "Logged" in msg
    
    def test_disabled_rule(self):
        """Test that disabled rules don't match"""
        rule = GuardrailRule(
            id="test-disabled",
            name="Test Disabled Rule",
            pattern=ToolCallPattern(tool="exec"),
            action=GuardrailAction.BLOCK,
            block_message="Should not block",
            enabled=False
        )
        
        matched, reason = rule.matches("exec", {})
        assert matched is False
        assert "disabled" in reason.lower()
    
    def test_priority_ordering(self):
        """Test rule priority"""
        rule1 = GuardrailRule(
            id="low-priority",
            name="Low Priority",
            pattern=ToolCallPattern(tool="exec"),
            action=GuardrailAction.LOG,
            priority=10
        )
        
        rule2 = GuardrailRule(
            id="high-priority",
            name="High Priority",
            pattern=ToolCallPattern(tool="exec"),
            action=GuardrailAction.BLOCK,
            block_message="Blocked by high priority",
            priority=90
        )
        
        assert rule2.priority > rule1.priority
    
    def test_validation_rewrite_requires_rewrite_field(self):
        """Test that REWRITE action requires rewrite field"""
        with pytest.raises(Exception):  # ValidationError
            GuardrailRule(
                id="invalid-rewrite",
                name="Invalid Rewrite",
                pattern=ToolCallPattern(tool="exec"),
                action=GuardrailAction.REWRITE
            )
    
    def test_validation_block_requires_message(self):
        """Test that BLOCK action requires block_message field"""
        with pytest.raises(Exception):  # ValidationError
            GuardrailRule(
                id="invalid-block",
                name="Invalid Block",
                pattern=ToolCallPattern(tool="exec"),
                action=GuardrailAction.BLOCK
            )


class TestGuardrailRuleSet:
    """Tests for GuardrailRuleSet model"""
    
    def test_rule_set_creation(self):
        """Test creating a rule set"""
        rule_set = GuardrailRuleSet(
            version="1.0",
            kind="guardrail",
            name="test-rules",
            rules=[
                GuardrailRule(
                    id="rule-1",
                    name="Rule 1",
                    pattern=ToolCallPattern(tool="exec"),
                    action=GuardrailAction.LOG,
                    priority=50
                )
            ]
        )
        
        assert len(rule_set.rules) == 1
        assert rule_set.get_enabled_rules()[0].id == "rule-1"
    
    def test_disabled_rule_set(self):
        """Test that disabled rule sets return no rules"""
        rule_set = GuardrailRuleSet(
            version="1.0",
            kind="guardrail",
            name="disabled-rules",
            enabled=False,
            rules=[
                GuardrailRule(
                    id="rule-1",
                    name="Rule 1",
                    pattern=ToolCallPattern(tool="exec"),
                    action=GuardrailAction.LOG
                )
            ]
        )
        
        assert len(rule_set.get_enabled_rules()) == 0
    
    def test_get_matching_rule(self):
        """Test getting matching rule"""
        rule_set = GuardrailRuleSet(
            version="1.0",
            kind="guardrail",
            name="test-rules",
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
                    block_message="Blocked",
                    priority=90
                )
            ]
        )
        
        matching = rule_set.get_matching_rule("exec", {})
        assert matching is not None
        assert matching.id == "high-priority"  # Higher priority wins
    
    def test_no_matching_rule(self):
        """Test when no rule matches"""
        rule_set = GuardrailRuleSet(
            version="1.0",
            kind="guardrail",
            name="test-rules",
            rules=[
                GuardrailRule(
                    id="rule-1",
                    name="Rule 1",
                    pattern=ToolCallPattern(tool="write"),
                    action=GuardrailAction.LOG
                )
            ]
        )
        
        matching = rule_set.get_matching_rule("exec", {})
        assert matching is None


class TestGuardrailHit:
    """Tests for GuardrailHit model"""
    
    def test_hit_creation(self):
        """Test creating a guardrail hit record"""
        hit = GuardrailHit(
            timestamp="2024-01-01T00:00:00Z",
            rule_id="test-rule",
            rule_name="Test Rule",
            action=GuardrailAction.BLOCK,
            tool_name="exec",
            original_params={"command": "rm -rf /"},
            message="Blocked dangerous command"
        )
        
        assert hit.rule_id == "test-rule"
        assert hit.action == GuardrailAction.BLOCK
        assert hit.original_params["command"] == "rm -rf /"


class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_empty_tool_params(self):
        """Test matching with empty parameters"""
        pattern = ToolCallPattern(tool="exec")
        matched, _ = pattern.matches("exec", {})
        assert matched is True
    
    def test_missing_param_in_pattern(self):
        """Test when param is missing from tool_params"""
        pattern = ToolCallPattern(
            tool="exec",
            param_patterns={"command": "test"}
        )
        matched, _ = pattern.matches("exec", {})
        assert matched is False
    
    def test_case_insensitive_param_contains(self):
        """Test that param_contains is case insensitive"""
        pattern = ToolCallPattern(
            tool="exec",
            param_contains={"command": ["FORCE"]}
        )
        
        matched, _ = pattern.matches("exec", {"command": "npm install --force"})
        assert matched is True
    
    def test_id_validation(self):
        """Test that invalid IDs are rejected"""
        with pytest.raises(Exception):  # ValidationError
            GuardrailRule(
                id="invalid id!",
                name="Invalid ID Rule",
                pattern=ToolCallPattern(tool="exec"),
                action=GuardrailAction.LOG
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])