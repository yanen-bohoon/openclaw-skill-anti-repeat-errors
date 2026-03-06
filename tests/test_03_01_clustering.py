"""
Test cases for Plan 03-01: Error Clustering & Rule Generation
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import json

# Import the modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from log_aggregator import LogAggregator, ErrorRecord, AggregatedLogs
from error_clusterer import ErrorClusterer, ErrorCluster, ClusteringResult
from rule_generator import RuleGenerator, CandidateRule, GenerationResult


class TestErrorRecord:
    """Test ErrorRecord class"""
    
    def test_compute_signature(self):
        """Test signature computation"""
        record = ErrorRecord(
            timestamp="2026-03-06T10:00:00",
            source="guardrail",
            log_type="tool_blocked",
            tool_name="exec",
            original_params={"command": "git push --force"}
        )
        
        sig = record.compute_signature()
        assert "exec" in sig
        assert "tool_blocked" in sig
        assert "command" in sig
    
    def test_normalize_command_exec(self):
        """Test command normalization for exec"""
        record = ErrorRecord(
            timestamp="2026-03-06T10:00:00",
            source="guardrail",
            log_type="tool_blocked",
            tool_name="exec",
            original_params={"command": "git push --force /some/path"}
        )
        
        normalized = record.normalize_command()
        assert "git" in normalized
        assert "<PATH>" in normalized
    
    def test_normalize_command_file_ops(self):
        """Test command normalization for file operations"""
        record = ErrorRecord(
            timestamp="2026-03-06T10:00:00",
            source="guardrail",
            log_type="tool_blocked",
            tool_name="write",
            original_params={"file_path": "/home/user/.openclaw/config.json"}
        )
        
        normalized = record.normalize_command()
        assert "write" in normalized
        assert ".json" in normalized


class TestLogAggregator:
    """Test LogAggregator class"""
    
    def test_aggregate_empty(self):
        """Test aggregation with no logs"""
        with tempfile.TemporaryDirectory() as tmpdir:
            aggregator = LogAggregator(log_dir=Path(tmpdir))
            result = aggregator.aggregate(days=7)
            
            assert result.total_records == 0
            assert result.unique_signatures == 0
    
    def test_aggregate_with_injection_log(self):
        """Test aggregation with injection log"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            
            # Create injection log
            injection_log = log_dir / "injections.jsonl"
            with open(injection_log, "w") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "event": "injection_failed",
                    "tool_name": "exec",
                    "original_params": {"command": "rm -rf /"},
                    "error": "Blocked by rule"
                }) + "\n")
            
            aggregator = LogAggregator(log_dir=log_dir)
            result = aggregator.aggregate(days=7)
            
            assert result.total_records == 1
            assert len(result.error_records) == 1
            assert result.error_records[0].tool_name == "exec"
    
    def test_aggregate_with_guardrail_log(self):
        """Test aggregation with guardrail hit log"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            
            # Create guardrail hit log
            today = datetime.now().strftime("%Y-%m-%d")
            guardrail_log = log_dir / f"guardrail_hits_{today}.jsonl"
            with open(guardrail_log, "w") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "event_type": "tool_blocked",
                    "tool_name": "exec",
                    "original_params": {"command": "git push --force"},
                    "rule_id": "block-force-push",
                    "message": "Force push blocked"
                }) + "\n")
            
            aggregator = LogAggregator(log_dir=log_dir)
            result = aggregator.aggregate(days=7)
            
            assert result.total_records == 1
            assert result.total_guardrail_hits == 1


class TestErrorClusterer:
    """Test ErrorClusterer class"""
    
    def test_cluster_empty(self):
        """Test clustering with no records"""
        clusterer = ErrorClusterer(min_cluster_size=1)
        
        aggregated = AggregatedLogs(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00"
        )
        
        result = clusterer.cluster(aggregated)
        assert result.total_clusters == 0
    
    def test_cluster_single_record(self):
        """Test clustering with single record"""
        clusterer = ErrorClusterer(min_cluster_size=1)
        
        record = ErrorRecord(
            timestamp="2026-03-06T10:00:00",
            source="guardrail",
            log_type="tool_blocked",
            tool_name="exec",
            original_params={"command": "git push --force"}
        )
        record.compute_signature()
        record.normalize_command()
        
        aggregated = AggregatedLogs(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            error_records=[record]
        )
        
        result = clusterer.cluster(aggregated)
        assert result.total_clusters == 1
        assert result.clusters[0].count == 1
        assert result.clusters[0].tool_name == "exec"
    
    def test_cluster_multiple_similar(self):
        """Test clustering with multiple similar records"""
        clusterer = ErrorClusterer(min_cluster_size=2)
        
        records = []
        for i in range(3):
            record = ErrorRecord(
                timestamp=f"2026-03-06T10:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "git push --force"}
            )
            record.compute_signature()
            record.normalize_command()
            records.append(record)
        
        aggregated = AggregatedLogs(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            error_records=records
        )
        
        result = clusterer.cluster(aggregated)
        assert result.total_clusters == 1
        assert result.clusters[0].count == 3
    
    def test_cluster_priority_calculation(self):
        """Test cluster priority calculation"""
        clusterer = ErrorClusterer(min_cluster_size=1)
        
        # Create records with blocked status
        records = []
        for i in range(5):
            record = ErrorRecord(
                timestamp=f"2026-03-06T10:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "rm -rf /"}
            )
            record.compute_signature()
            record.normalize_command()
            records.append(record)
        
        aggregated = AggregatedLogs(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            error_records=records
        )
        
        result = clusterer.cluster(aggregated)
        assert result.total_clusters == 1
        # 5 records * 5 = 25 frequency score + 5 * 5 = 25 block bonus + 10 sensitive + 50 base = 85
        # But capped at 100
        assert result.clusters[0].priority >= 70


class TestRuleGenerator:
    """Test RuleGenerator class"""
    
    def test_generate_empty(self):
        """Test generation with no clusters"""
        generator = RuleGenerator()
        
        clustering_result = ClusteringResult(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00"
        )
        
        result = generator.generate(clustering_result)
        assert result.total_candidates == 0
    
    def test_generate_from_cluster(self):
        """Test generation from single cluster"""
        generator = RuleGenerator()
        
        # Create a cluster with high priority
        records = []
        for i in range(5):
            record = ErrorRecord(
                timestamp=f"2026-03-06T10:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "rm -rf /"}
            )
            record.compute_signature()
            record.normalize_command()
            records.append(record)
        
        cluster = ErrorCluster(
            cluster_id="cluster_0000",
            cluster_signature="exec|command|rm|tool_blocked",
            count=5,
            records=records,
            tool_name="exec"
        )
        cluster.compute_priority()
        
        clustering_result = ClusteringResult(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            clusters=[cluster]
        )
        
        result = generator.generate(clustering_result)
        assert result.total_candidates == 1
        assert result.candidates[0].rule.pattern.tool == "exec"
    
    def test_generate_deduplication(self):
        """Test deduplication of similar rules"""
        generator = RuleGenerator()
        
        # Create two similar clusters
        records1 = []
        for i in range(3):
            record = ErrorRecord(
                timestamp=f"2026-03-06T10:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "rm -rf /"}
            )
            record.compute_signature()
            record.normalize_command()
            records1.append(record)
        
        records2 = []
        for i in range(3):
            record = ErrorRecord(
                timestamp=f"2026-03-06T11:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "rm -rf /"}
            )
            record.compute_signature()
            record.normalize_command()
            records2.append(record)
        
        cluster1 = ErrorCluster(
            cluster_id="cluster_0000",
            cluster_signature="sig1",
            count=3,
            records=records1,
            tool_name="exec"
        )
        cluster1.compute_priority()
        
        cluster2 = ErrorCluster(
            cluster_id="cluster_0001",
            cluster_signature="sig2",
            count=3,
            records=records2,
            tool_name="exec"
        )
        cluster2.compute_priority()
        
        clustering_result = ClusteringResult(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            clusters=[cluster1, cluster2]
        )
        
        result = generator.generate(clustering_result)
        # Should deduplicate to 1
        assert result.duplicates_removed == 1
        assert result.total_candidates == 1
    
    def test_generate_skip_existing(self):
        """Test skipping existing rules"""
        generator = RuleGenerator(existing_rule_ids={"auto-exec-cluster_0000"})
        
        records = []
        for i in range(3):
            record = ErrorRecord(
                timestamp=f"2026-03-06T10:0{i}:00",
                source="guardrail",
                log_type="tool_blocked",
                tool_name="exec",
                original_params={"command": "rm -rf /"}
            )
            record.compute_signature()
            record.normalize_command()
            records.append(record)
        
        cluster = ErrorCluster(
            cluster_id="cluster_0000",
            cluster_signature="exec|command|rm|tool_blocked",
            count=3,
            records=records,
            tool_name="exec"
        )
        cluster.compute_priority()
        
        clustering_result = ClusteringResult(
            window_start="2026-03-01T00:00:00",
            window_end="2026-03-06T00:00:00",
            clusters=[cluster]
        )
        
        result = generator.generate(clustering_result)
        assert result.existing_rules_skipped == 1
        assert result.total_candidates == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])