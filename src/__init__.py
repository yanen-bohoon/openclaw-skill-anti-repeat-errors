"""
Anti-Repeat-Errors Skill - Source Package
"""

from .models import LoadedRules, Rule, RuleCondition, RuleSet
from .rule_loader import RuleLoader, create_loader
from .guardrail_models import (
    GuardrailAction,
    GuardrailRule,
    GuardrailRuleSet,
    GuardrailHit,
    ToolCallPattern,
    RewriteRule,
)
from .pattern_matcher import PatternMatcher, MatchResult, create_matcher
from .guardrail_hook import (
    GuardrailHook,
    ToolCallContext,
    GuardrailResult,
    create_guardrail_hook,
)
from .hit_logger import (
    HitEventType,
    GuardrailHitRecord,
    HitLogger,
    get_hit_logger,
)
from .hit_replay import (
    ReplayTrace,
    HitReplay,
)
from .log_aggregator import (
    ErrorRecord,
    AggregatedLogs,
    LogAggregator,
    create_aggregator,
)
from .error_clusterer import (
    ErrorCluster,
    ClusteringResult,
    ErrorClusterer,
    create_clusterer,
)
from .rule_generator import (
    CandidateRule,
    GenerationResult,
    RuleGenerator,
    create_generator,
)
from .rule_merger import (
    MergeOperation,
    MergeResult,
    RuleMerger,
    create_merger,
)
from .rule_versioner import (
    RuleVersion,
    VersionHistory,
    ChangelogEntry,
    RuleVersioner,
    create_versioner,
)
from .error_rate_tracker import (
    ErrorRateSnapshot,
    Baseline,
    ErrorRateTrend,
    ErrorRateTracker,
    create_tracker,
)
from .weekly_report import (
    WeeklyReportConfig,
    WeeklyReportGenerator,
    create_report_generator,
)

__all__ = [
    # Phase 1 models
    "RuleCondition",
    "Rule",
    "RuleSet",
    "LoadedRules",
    "RuleLoader",
    "create_loader",
    # Phase 2 guardrail models
    "GuardrailAction",
    "GuardrailRule",
    "GuardrailRuleSet",
    "GuardrailHit",
    "ToolCallPattern",
    "RewriteRule",
    "PatternMatcher",
    "MatchResult",
    "create_matcher",
    # Phase 2 guardrail hook
    "GuardrailHook",
    "ToolCallContext",
    "GuardrailResult",
    "create_guardrail_hook",
    # Phase 2 hit logging
    "HitEventType",
    "GuardrailHitRecord",
    "HitLogger",
    "get_hit_logger",
    # Phase 2 hit replay
    "ReplayTrace",
    "HitReplay",
    # Phase 3 log aggregation
    "ErrorRecord",
    "AggregatedLogs",
    "LogAggregator",
    "create_aggregator",
    # Phase 3 error clustering
    "ErrorCluster",
    "ClusteringResult",
    "ErrorClusterer",
    "create_clusterer",
    # Phase 3 rule generation
    "CandidateRule",
    "GenerationResult",
    "RuleGenerator",
    "create_generator",
    # Phase 3 rule merge
    "MergeOperation",
    "MergeResult",
    "RuleMerger",
    "create_merger",
    # Phase 3 rule versioning
    "RuleVersion",
    "VersionHistory",
    "ChangelogEntry",
    "RuleVersioner",
    "create_versioner",
    # Phase 3 error rate tracking
    "ErrorRateSnapshot",
    "Baseline",
    "ErrorRateTrend",
    "ErrorRateTracker",
    "create_tracker",
    # Phase 3 weekly report
    "WeeklyReportConfig",
    "WeeklyReportGenerator",
    "create_report_generator",
]