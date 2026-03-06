"""
Tests for Plan 03-03: Error Rate Weekly Report
"""

import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Import the new modules
import sys
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from error_rate_tracker import (
    ErrorRateSnapshot,
    Baseline,
    ErrorRateTrend,
    ErrorRateTracker,
    create_tracker,
)
from weekly_report import (
    WeeklyReportConfig,
    WeeklyReportGenerator,
    create_report_generator,
)


class TestErrorRateSnapshot:
    """Test ErrorRateSnapshot dataclass"""
    
    def test_create_snapshot(self):
        """Test creating a snapshot"""
        snapshot = ErrorRateSnapshot(
            timestamp=datetime.now().isoformat(),
            period_start="2026-02-27T00:00:00",
            period_end="2026-03-06T00:00:00",
            period_days=7,
            total_events=100,
            total_errors=50,
            total_guardrail_hits=30,
            unique_error_signatures=10,
            repeated_errors=5,
            repeat_error_instances=25,
        )
        
        assert snapshot.total_events == 100
        assert snapshot.total_errors == 50
        assert snapshot.period_days == 7
    
    def test_snapshot_to_dict(self):
        """Test snapshot serialization"""
        snapshot = ErrorRateSnapshot(
            timestamp="2026-03-06T00:00:00",
            period_start="2026-02-27T00:00:00",
            period_end="2026-03-06T00:00:00",
            period_days=7,
            total_events=100,
            total_errors=50,
            total_guardrail_hits=30,
            unique_error_signatures=10,
            repeated_errors=5,
            repeat_error_instances=25,
            error_rate=0.5,
            repeat_error_rate=0.5,
        )
        
        data = snapshot.to_dict()
        
        assert data["total_events"] == 100
        assert data["error_rate"] == 0.5
        assert data["period_days"] == 7


class TestBaseline:
    """Test Baseline dataclass"""
    
    def test_create_baseline(self):
        """Test creating a baseline"""
        snapshot = ErrorRateSnapshot(
            timestamp=datetime.now().isoformat(),
            period_start="2026-02-27T00:00:00",
            period_end="2026-03-06T00:00:00",
            period_days=7,
            total_events=100,
        )
        
        baseline = Baseline(
            baseline_id="test_baseline",
            created_at=datetime.now().isoformat(),
            description="Test baseline",
            snapshot=snapshot,
            baseline_error_rate=0.5,
            baseline_repeat_error_rate=0.5,
        )
        
        assert baseline.baseline_id == "test_baseline"
        assert baseline.baseline_repeat_error_rate == 0.5
    
    def test_baseline_to_dict(self):
        """Test baseline serialization"""
        snapshot = ErrorRateSnapshot(
            timestamp="2026-03-06T00:00:00",
            period_start="2026-02-27T00:00:00",
            period_end="2026-03-06T00:00:00",
            period_days=7,
            total_events=100,
        )
        
        baseline = Baseline(
            baseline_id="test_baseline",
            created_at="2026-03-06T00:00:00",
            description="Test baseline",
            snapshot=snapshot,
        )
        
        data = baseline.to_dict()
        
        assert data["baseline_id"] == "test_baseline"
        assert "snapshot" in data


class TestErrorRateTrend:
    """Test ErrorRateTrend dataclass"""
    
    def test_create_trend(self):
        """Test creating a trend"""
        trend = ErrorRateTrend(
            start_date="2026-02-27T00:00:00",
            end_date="2026-03-06T00:00:00",
            trend_direction="improving",
            improvement_pct=80.0,
        )
        
        assert trend.trend_direction == "improving"
        assert trend.improvement_pct == 80.0
    
    def test_trend_to_dict(self):
        """Test trend serialization"""
        trend = ErrorRateTrend(
            start_date="2026-02-27T00:00:00",
            end_date="2026-03-06T00:00:00",
            avg_error_rate=0.3,
            avg_repeat_error_rate=0.2,
            trend_direction="improving",
            improvement_pct=80.0,
        )
        
        data = trend.to_dict()
        
        assert data["trend_direction"] == "improving"
        assert data["improvement_pct"] == 80.0


class TestErrorRateTracker:
    """Test ErrorRateTracker class"""
    
    def test_create_tracker(self):
        """Test creating a tracker"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            assert tracker.data_dir.exists()
            assert tracker.baseline_dir.exists()
    
    def test_create_tracker_convenience(self):
        """Test create_tracker convenience function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = create_tracker(data_dir=Path(tmpdir))
            assert isinstance(tracker, ErrorRateTracker)
    
    def test_calculate_snapshot(self):
        """Test calculating a snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            snapshot = tracker.calculate_snapshot(days=7)
            
            assert snapshot.period_days == 7
            assert isinstance(snapshot, ErrorRateSnapshot)
    
    def test_create_and_load_baseline(self):
        """Test creating and loading a baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            # Create baseline
            baseline = tracker.create_baseline(description="Test baseline")
            
            assert baseline.baseline_id.startswith("baseline_")
            assert baseline.description == "Test baseline"
            
            # Load baseline
            loaded = tracker.load_baseline(baseline.baseline_id)
            
            assert loaded is not None
            assert loaded.baseline_id == baseline.baseline_id
            assert loaded.description == "Test baseline"
    
    def test_get_latest_baseline(self):
        """Test getting the latest baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            # No baseline initially
            assert tracker.get_latest_baseline() is None
            
            # Create baseline
            baseline = tracker.create_baseline(description="Test baseline")
            
            # Get latest
            latest = tracker.get_latest_baseline()
            assert latest is not None
            assert latest.baseline_id == baseline.baseline_id
    
    def test_list_baselines(self):
        """Test listing all baselines"""
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            # Create multiple baselines with delay to ensure different timestamps
            tracker.create_baseline(description="Baseline 1")
            time.sleep(0.01)  # Small delay to ensure different timestamp
            tracker.create_baseline(description="Baseline 2")
            
            baselines = tracker.list_baselines()
            assert len(baselines) == 2
    
    def test_calculate_trend(self):
        """Test calculating trend"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            # Create baseline
            baseline = tracker.create_baseline(description="Test baseline")
            
            # Calculate trend
            trend = tracker.calculate_trend(baseline=baseline)
            
            assert trend.baseline_id == baseline.baseline_id
            assert trend.trend_direction in ["improving", "stable", "worsening"]
    
    def test_check_target_achieved_no_baseline(self):
        """Test target check with no baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            achieved, details = tracker.check_target_achieved()
            
            # No baseline means no improvement can be measured
            assert achieved is False
            assert details["actual_improvement_pct"] == 0.0
    
    def test_check_target_achieved_with_baseline(self):
        """Test target check with baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            
            # Create baseline
            baseline = tracker.create_baseline(description="Test baseline")
            
            # Check target
            achieved, details = tracker.check_target_achieved(
                target_improvement_pct=80.0,
                baseline=baseline,
            )
            
            assert "actual_improvement_pct" in details
            assert "target_improvement_pct" in details
            assert details["target_improvement_pct"] == 80.0


class TestWeeklyReportConfig:
    """Test WeeklyReportConfig dataclass"""
    
    def test_default_config(self):
        """Test default configuration"""
        config = WeeklyReportConfig()
        
        assert config.title == "Anti-Repeat-Errors 周报"
        assert config.target_improvement_pct == 80.0
        assert config.include_top_errors == 10
    
    def test_custom_config(self):
        """Test custom configuration"""
        config = WeeklyReportConfig(
            title="Custom Report",
            target_improvement_pct=90.0,
            include_top_errors=5,
        )
        
        assert config.title == "Custom Report"
        assert config.target_improvement_pct == 90.0
        assert config.include_top_errors == 5


class TestWeeklyReportGenerator:
    """Test WeeklyReportGenerator class"""
    
    def test_create_generator(self):
        """Test creating a generator"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            generator = WeeklyReportGenerator(tracker=tracker)
            
            assert generator.tracker is tracker
    
    def test_create_generator_convenience(self):
        """Test create_report_generator convenience function"""
        generator = create_report_generator()
        assert isinstance(generator, WeeklyReportGenerator)
    
    def test_generate_report_no_baseline(self):
        """Test generating report without baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            generator = WeeklyReportGenerator(tracker=tracker)
            
            report = generator.generate(days=7)
            
            assert "Anti-Repeat-Errors 周报" in report
            assert "无基线数据" in report
    
    def test_generate_report_with_baseline(self):
        """Test generating report with baseline"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            generator = WeeklyReportGenerator(tracker=tracker)
            
            # Create baseline
            baseline = tracker.create_baseline(description="Test baseline")
            
            # Generate report
            report = generator.generate(baseline=baseline, days=7)
            
            assert "Anti-Repeat-Errors 周报" in report
            assert baseline.baseline_id in report
    
    def test_generate_report_to_file(self):
        """Test generating report to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            generator = WeeklyReportGenerator(tracker=tracker)
            
            output_path = Path(tmpdir) / "reports" / "test_report.md"
            report = generator.generate(days=7, output_path=output_path)
            
            assert output_path.exists()
            assert output_path.read_text() == report
    
    def test_report_sections(self):
        """Test report contains all expected sections"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ErrorRateTracker(data_dir=Path(tmpdir))
            generator = WeeklyReportGenerator(tracker=tracker)
            
            report = generator.generate(days=7)
            
            # Check for expected sections
            assert "执行摘要" in report
            assert "关键指标" in report
            assert "防护效果" in report
            assert "建议" in report


class TestImprovementCalculation:
    """Test improvement percentage calculation"""
    
    def test_improvement_calculation_logic(self):
        """Test the improvement calculation logic"""
        # improvement = (baseline - current) / baseline * 100
        
        # 80% reduction: baseline=50%, current=10%
        # improvement = (0.5 - 0.1) / 0.5 * 100 = 80%
        
        baseline_rate = 0.5
        current_rate = 0.1
        improvement = (baseline_rate - current_rate) / baseline_rate * 100
        
        assert improvement == 80.0
    
    def test_no_improvement(self):
        """Test no improvement scenario"""
        baseline_rate = 0.5
        current_rate = 0.5
        improvement = (baseline_rate - current_rate) / baseline_rate * 100
        
        assert improvement == 0.0
    
    def test_worsening(self):
        """Test worsening scenario"""
        baseline_rate = 0.5
        current_rate = 0.8  # Got worse
        improvement = (baseline_rate - current_rate) / baseline_rate * 100
        
        assert improvement == pytest.approx(-60.0)  # Negative means worsening
    
    def test_full_elimination(self):
        """Test 100% improvement scenario"""
        baseline_rate = 0.5
        current_rate = 0.0  # Eliminated all errors
        improvement = (baseline_rate - current_rate) / baseline_rate * 100
        
        assert improvement == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])