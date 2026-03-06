"""
Anti-Repeat-Errors Skill - Error Rate Tracker

Tracks repeat error rates for effectiveness measurement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from collections import Counter


@dataclass
class ErrorRateSnapshot:
    """错误率快照"""
    
    # 时间
    timestamp: str
    period_start: str
    period_end: str
    period_days: int
    
    # 总量统计
    total_events: int = 0
    total_errors: int = 0
    total_guardrail_hits: int = 0
    
    # 重复错误统计
    unique_error_signatures: int = 0
    repeated_errors: int = 0  # 出现 2 次以上的错误数
    repeat_error_instances: int = 0  # 重复错误的总实例数
    
    # 错误率指标
    error_rate: float = 0.0  # errors / events
    repeat_error_rate: float = 0.0  # repeat_error_instances / total_errors
    unique_error_rate: float = 0.0  # unique_errors / total_errors
    
    # 防护效果
    blocked_errors: int = 0
    warned_errors: int = 0
    rewritten_errors: int = 0
    
    # Top 错误
    top_error_signatures: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_days": self.period_days,
            "total_events": self.total_events,
            "total_errors": self.total_errors,
            "total_guardrail_hits": self.total_guardrail_hits,
            "unique_error_signatures": self.unique_error_signatures,
            "repeated_errors": self.repeated_errors,
            "repeat_error_instances": self.repeat_error_instances,
            "error_rate": round(self.error_rate, 4),
            "repeat_error_rate": round(self.repeat_error_rate, 4),
            "unique_error_rate": round(self.unique_error_rate, 4),
            "blocked_errors": self.blocked_errors,
            "warned_errors": self.warned_errors,
            "rewritten_errors": self.rewritten_errors,
            "top_error_signatures": self.top_error_signatures[:10],
        }


@dataclass
class Baseline:
    """基线数据"""
    
    # 元数据
    baseline_id: str
    created_at: str
    description: str
    
    # 基线快照
    snapshot: ErrorRateSnapshot
    
    # 基线指标
    baseline_error_rate: float = 0.0
    baseline_repeat_error_rate: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "baseline_id": self.baseline_id,
            "created_at": self.created_at,
            "description": self.description,
            "snapshot": self.snapshot.to_dict(),
            "baseline_error_rate": round(self.baseline_error_rate, 4),
            "baseline_repeat_error_rate": round(self.baseline_repeat_error_rate, 4),
        }


@dataclass
class ErrorRateTrend:
    """错误率趋势"""
    
    # 时间范围
    start_date: str
    end_date: str
    
    # 数据点
    data_points: list[ErrorRateSnapshot] = field(default_factory=list)
    
    # 趋势统计
    avg_error_rate: float = 0.0
    avg_repeat_error_rate: float = 0.0
    trend_direction: str = "stable"  # "improving" | "stable" | "worsening"
    
    # 相对基线
    baseline_id: Optional[str] = None
    baseline_repeat_error_rate: float = 0.0
    current_repeat_error_rate: float = 0.0
    improvement_pct: float = 0.0  # 改善百分比（正数表示下降）
    
    def to_dict(self) -> dict:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "data_point_count": len(self.data_points),
            "avg_error_rate": round(self.avg_error_rate, 4),
            "avg_repeat_error_rate": round(self.avg_repeat_error_rate, 4),
            "trend_direction": self.trend_direction,
            "baseline_id": self.baseline_id,
            "baseline_repeat_error_rate": round(self.baseline_repeat_error_rate, 4),
            "current_repeat_error_rate": round(self.current_repeat_error_rate, 4),
            "improvement_pct": round(self.improvement_pct, 2),
        }


class ErrorRateTracker:
    """
    错误率追踪器
    
    计算和追踪重复错误率，用于验证 80% 下降目标。
    """
    
    DEFAULT_DATA_DIR = "~/.openclaw/logs/anti-repeat-errors"
    
    def __init__(
        self,
        data_dir: Optional[Path] = None,
        baseline_dir: Optional[Path] = None,
    ):
        """
        初始化追踪器
        
        Args:
            data_dir: 日志数据目录
            baseline_dir: 基线存储目录
        """
        if data_dir is None:
            data_dir = Path(self.DEFAULT_DATA_DIR)
        
        self.data_dir = Path(data_dir).expanduser()
        self.baseline_dir = baseline_dir or (self.data_dir / "baselines")
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
    
    def calculate_snapshot(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        days: int = 7,
    ) -> ErrorRateSnapshot:
        """
        计算指定时间范围的错误率快照
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            days: 如果未指定时间，默认计算最近 N 天
            
        Returns:
            ErrorRateSnapshot 对象
        """
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(days=days)
        
        # 使用 LogAggregator 聚合日志
        try:
            from .log_aggregator import LogAggregator
        except ImportError:
            from log_aggregator import LogAggregator
        aggregator = LogAggregator(log_dir=self.data_dir)
        aggregated = aggregator.aggregate(start_time=start_time, end_time=end_time)
        
        # 构建快照
        snapshot = ErrorRateSnapshot(
            timestamp=datetime.now().isoformat(),
            period_start=start_time.isoformat(),
            period_end=end_time.isoformat(),
            period_days=days,
            total_events=aggregated.total_records,
            total_errors=aggregated.total_errors,
            total_guardrail_hits=aggregated.total_guardrail_hits,
            unique_error_signatures=aggregated.unique_signatures,
        )
        
        # 统计签名频率
        signature_counts = Counter(r.error_signature for r in aggregated.error_records if r.error_signature)
        
        # 计算重复错误
        for sig, count in signature_counts.items():
            if count >= 2:
                snapshot.repeated_errors += 1
                snapshot.repeat_error_instances += count
        
        # 计算错误率
        if snapshot.total_events > 0:
            snapshot.error_rate = snapshot.total_errors / snapshot.total_events
        
        if snapshot.total_errors > 0:
            snapshot.repeat_error_rate = snapshot.repeat_error_instances / snapshot.total_errors
            snapshot.unique_error_rate = snapshot.unique_error_signatures / snapshot.total_errors
        
        # 统计防护效果
        for record in aggregated.error_records:
            if record.log_type == "tool_blocked":
                snapshot.blocked_errors += 1
            elif record.log_type == "tool_warned":
                snapshot.warned_errors += 1
            elif record.log_type == "tool_rewritten":
                snapshot.rewritten_errors += 1
        
        # Top 错误签名
        snapshot.top_error_signatures = [
            {"signature": sig, "count": count}
            for sig, count in signature_counts.most_common(10)
        ]
        
        return snapshot
    
    def create_baseline(
        self,
        description: str = "Initial baseline",
        days: int = 7,
    ) -> Baseline:
        """
        创建基线
        
        Args:
            description: 基线描述
            days: 基线数据天数
            
        Returns:
            Baseline 对象
        """
        snapshot = self.calculate_snapshot(days=days)
        
        baseline = Baseline(
            baseline_id=f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            created_at=datetime.now().isoformat(),
            description=description,
            snapshot=snapshot,
            baseline_error_rate=snapshot.error_rate,
            baseline_repeat_error_rate=snapshot.repeat_error_rate,
        )
        
        # 保存基线
        self._save_baseline(baseline)
        
        return baseline
    
    def _save_baseline(self, baseline: Baseline) -> None:
        """保存基线到文件"""
        baseline_file = self.baseline_dir / f"{baseline.baseline_id}.json"
        with open(baseline_file, "w", encoding="utf-8") as f:
            json.dump(baseline.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_baseline(self, baseline_id: str) -> Optional[Baseline]:
        """加载基线"""
        baseline_file = self.baseline_dir / f"{baseline_id}.json"
        if not baseline_file.exists():
            return None
        
        with open(baseline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return Baseline(
            baseline_id=data["baseline_id"],
            created_at=data["created_at"],
            description=data["description"],
            snapshot=self._dict_to_snapshot(data["snapshot"]),
            baseline_error_rate=data["baseline_error_rate"],
            baseline_repeat_error_rate=data["baseline_repeat_error_rate"],
        )
    
    def _dict_to_snapshot(self, data: dict) -> ErrorRateSnapshot:
        """将字典转换为 ErrorRateSnapshot"""
        return ErrorRateSnapshot(
            timestamp=data["timestamp"],
            period_start=data["period_start"],
            period_end=data["period_end"],
            period_days=data["period_days"],
            total_events=data["total_events"],
            total_errors=data["total_errors"],
            total_guardrail_hits=data["total_guardrail_hits"],
            unique_error_signatures=data["unique_error_signatures"],
            repeated_errors=data["repeated_errors"],
            repeat_error_instances=data["repeat_error_instances"],
            error_rate=data["error_rate"],
            repeat_error_rate=data["repeat_error_rate"],
            unique_error_rate=data["unique_error_rate"],
            blocked_errors=data["blocked_errors"],
            warned_errors=data["warned_errors"],
            rewritten_errors=data["rewritten_errors"],
            top_error_signatures=data.get("top_error_signatures", []),
        )
    
    def get_latest_baseline(self) -> Optional[Baseline]:
        """获取最新的基线"""
        baseline_files = sorted(self.baseline_dir.glob("baseline_*.json"), reverse=True)
        if not baseline_files:
            return None
        
        baseline_id = baseline_files[0].stem
        return self.load_baseline(baseline_id)
    
    def list_baselines(self) -> list[dict]:
        """
        列出所有基线
        
        Returns:
            基线摘要列表
        """
        baselines = []
        for baseline_file in sorted(self.baseline_dir.glob("baseline_*.json"), reverse=True):
            try:
                with open(baseline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                baselines.append({
                    "baseline_id": data["baseline_id"],
                    "created_at": data["created_at"],
                    "description": data["description"],
                    "baseline_repeat_error_rate": data["baseline_repeat_error_rate"],
                })
            except Exception:
                continue
        return baselines
    
    def calculate_trend(
        self,
        baseline: Optional[Baseline] = None,
        days: int = 7,
    ) -> ErrorRateTrend:
        """
        计算错误率趋势
        
        Args:
            baseline: 对比的基线，默认使用最新基线
            days: 当前数据天数
            
        Returns:
            ErrorRateTrend 对象
        """
        if baseline is None:
            baseline = self.get_latest_baseline()
        
        # 计算当前快照
        current_snapshot = self.calculate_snapshot(days=days)
        
        # 构建趋势
        trend = ErrorRateTrend(
            start_date=current_snapshot.period_start,
            end_date=current_snapshot.period_end,
            data_points=[current_snapshot],
            current_repeat_error_rate=current_snapshot.repeat_error_rate,
        )
        
        if baseline:
            trend.baseline_id = baseline.baseline_id
            trend.baseline_repeat_error_rate = baseline.baseline_repeat_error_rate
            
            # 计算改善百分比
            if baseline.baseline_repeat_error_rate > 0:
                # 改善 = (基线 - 当前) / 基线 * 100
                # 正数表示下降（改善），负数表示上升（恶化）
                trend.improvement_pct = (
                    (baseline.baseline_repeat_error_rate - current_snapshot.repeat_error_rate)
                    / baseline.baseline_repeat_error_rate * 100
                )
            
            # 判断趋势方向
            if trend.improvement_pct >= 10:
                trend.trend_direction = "improving"
            elif trend.improvement_pct <= -10:
                trend.trend_direction = "worsening"
            else:
                trend.trend_direction = "stable"
        
        trend.avg_error_rate = current_snapshot.error_rate
        trend.avg_repeat_error_rate = current_snapshot.repeat_error_rate
        
        return trend
    
    def check_target_achieved(
        self,
        target_improvement_pct: float = 80.0,
        baseline: Optional[Baseline] = None,
    ) -> tuple[bool, dict]:
        """
        检查是否达到目标
        
        Args:
            target_improvement_pct: 目标改善百分比（默认 80%）
            baseline: 对比的基线
            
        Returns:
            (是否达成, 详情字典)
        """
        trend = self.calculate_trend(baseline=baseline)
        
        achieved = trend.improvement_pct >= target_improvement_pct
        
        details = {
            "target_improvement_pct": target_improvement_pct,
            "actual_improvement_pct": trend.improvement_pct,
            "baseline_repeat_error_rate": trend.baseline_repeat_error_rate,
            "current_repeat_error_rate": trend.current_repeat_error_rate,
            "achieved": achieved,
            "gap_pct": target_improvement_pct - trend.improvement_pct if not achieved else 0,
        }
        
        return achieved, details


def create_tracker(
    data_dir: Optional[Path] = None,
    baseline_dir: Optional[Path] = None,
) -> ErrorRateTracker:
    """创建追踪器的便捷函数"""
    return ErrorRateTracker(data_dir=data_dir, baseline_dir=baseline_dir)