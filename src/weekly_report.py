"""
Anti-Repeat-Errors Skill - Weekly Report Generator

Generates weekly reports for repeat error rate metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from .error_rate_tracker import (
        ErrorRateTracker,
        ErrorRateSnapshot,
        ErrorRateTrend,
        Baseline,
    )
except ImportError:
    from error_rate_tracker import (
        ErrorRateTracker,
        ErrorRateSnapshot,
        ErrorRateTrend,
        Baseline,
    )


@dataclass
class WeeklyReportConfig:
    """周报配置"""
    
    title: str = "Anti-Repeat-Errors 周报"
    target_improvement_pct: float = 80.0
    include_top_errors: int = 10
    include_trend_chart: bool = True
    language: str = "zh-CN"


class WeeklyReportGenerator:
    """
    周报生成器
    
    生成 Markdown 格式的错误率周报。
    """
    
    def __init__(
        self,
        tracker: ErrorRateTracker,
        config: Optional[WeeklyReportConfig] = None,
    ):
        """
        初始化生成器
        
        Args:
            tracker: 错误率追踪器
            config: 周报配置
        """
        self.tracker = tracker
        self.config = config or WeeklyReportConfig()
    
    def generate(
        self,
        baseline: Optional[Baseline] = None,
        days: int = 7,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        生成周报
        
        Args:
            baseline: 对比的基线
            days: 数据天数
            output_path: 输出文件路径
            
        Returns:
            Markdown 格式的周报
        """
        # 获取数据
        if baseline is None:
            baseline = self.tracker.get_latest_baseline()
        
        trend = self.tracker.calculate_trend(baseline=baseline, days=days)
        current_snapshot = trend.data_points[0] if trend.data_points else None
        
        # 检查目标达成
        achieved, details = self.tracker.check_target_achieved(
            target_improvement_pct=self.config.target_improvement_pct,
            baseline=baseline,
        )
        
        # 生成报告
        lines = []
        
        # 标题
        lines.extend(self._generate_header(trend))
        
        # 执行摘要
        lines.extend(self._generate_executive_summary(trend, achieved, details))
        
        # 关键指标
        lines.extend(self._generate_key_metrics(current_snapshot, trend))
        
        # 基线对比
        if baseline:
            lines.extend(self._generate_baseline_comparison(baseline, trend))
        
        # 防护效果
        if current_snapshot:
            lines.extend(self._generate_protection_effect(current_snapshot))
        
        # Top 错误
        if current_snapshot and current_snapshot.top_error_signatures:
            lines.extend(self._generate_top_errors(current_snapshot))
        
        # 建议
        lines.extend(self._generate_recommendations(trend, achieved))
        
        # 页脚
        lines.extend(self._generate_footer())
        
        report = "\n".join(lines)
        
        # 保存到文件
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
        
        return report
    
    def _generate_header(self, trend: ErrorRateTrend) -> list[str]:
        """生成报告头部"""
        period_start = datetime.fromisoformat(trend.start_date).strftime("%Y-%m-%d")
        period_end = datetime.fromisoformat(trend.end_date).strftime("%Y-%m-%d")
        
        return [
            f"# {self.config.title}",
            "",
            f"**报告周期:** {period_start} ~ {period_end}",
            f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
        ]
    
    def _generate_executive_summary(
        self,
        trend: ErrorRateTrend,
        achieved: bool,
        details: dict,
    ) -> list[str]:
        """生成执行摘要"""
        lines = [
            "## 📊 执行摘要",
            "",
        ]
        
        if trend.baseline_id:
            if achieved:
                lines.append(f"✅ **目标已达成!** 重复错误率下降 **{details['actual_improvement_pct']:.1f}%**，超过目标 {self.config.target_improvement_pct}%。")
            else:
                gap = details.get('gap_pct', 0)
                lines.append(f"⚠️ **目标未达成。** 当前下降 **{details['actual_improvement_pct']:.1f}%**，距离目标还差 **{gap:.1f}%**。")
        else:
            lines.append("ℹ️ **无基线数据。** 请先创建基线以便对比。")
        
        lines.append("")
        
        # 趋势方向
        direction_emoji = {
            "improving": "📉",
            "stable": "➡️",
            "worsening": "📈",
        }
        lines.append(f"**趋势方向:** {direction_emoji.get(trend.trend_direction, '➡️')} {trend.trend_direction}")
        lines.append("")
        
        return lines
    
    def _generate_key_metrics(
        self,
        snapshot: Optional[ErrorRateSnapshot],
        trend: ErrorRateTrend,
    ) -> list[str]:
        """生成关键指标"""
        lines = [
            "## 📈 关键指标",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
        ]
        
        if snapshot:
            lines.extend([
                f"| 总事件数 | {snapshot.total_events} |",
                f"| 总错误数 | {snapshot.total_errors} |",
                f"| 错误率 | {snapshot.error_rate * 100:.2f}% |",
                f"| 唯一错误签名 | {snapshot.unique_error_signatures} |",
                f"| 重复错误率 | {snapshot.repeat_error_rate * 100:.2f}% |",
            ])
        else:
            lines.append("| 无数据 | - |")
        
        lines.append("")
        
        return lines
    
    def _generate_baseline_comparison(
        self,
        baseline: Baseline,
        trend: ErrorRateTrend,
    ) -> list[str]:
        """生成基线对比"""
        lines = [
            "## 📊 基线对比",
            "",
            f"**基线 ID:** `{baseline.baseline_id}`",
            f"**基线日期:** {baseline.created_at[:10]}",
            "",
            "| 指标 | 基线 | 当前 | 变化 |",
            "|------|------|------|------|",
        ]
        
        baseline_rate = baseline.baseline_repeat_error_rate
        current_rate = trend.current_repeat_error_rate
        
        # 计算变化
        if baseline_rate > 0:
            change_pct = (current_rate - baseline_rate) / baseline_rate * 100
            change_str = f"{'↓' if change_pct < 0 else '↑'} {abs(change_pct):.1f}%"
        else:
            change_str = "N/A"
        
        lines.extend([
            f"| 重复错误率 | {baseline_rate * 100:.2f}% | {current_rate * 100:.2f}% | {change_str} |",
            "",
        ])
        
        # 改善进度条
        improvement = trend.improvement_pct
        target = self.config.target_improvement_pct
        
        lines.append("### 目标进度")
        lines.append("")
        
        # 进度条（使用 Unicode 方块字符）
        progress = min(improvement / target, 1.0) if target > 0 else 0
        filled = int(progress * 20)
        empty = 20 - filled
        bar = "█" * filled + "░" * empty
        
        lines.append(f"```\n[{bar}] {progress * 100:.0f}% ({improvement:.1f}% / {target:.0f}%)\n```")
        lines.append("")
        
        return lines
    
    def _generate_protection_effect(self, snapshot: ErrorRateSnapshot) -> list[str]:
        """生成防护效果"""
        lines = [
            "## 🛡️ 防护效果",
            "",
            "| 动作 | 数量 |",
            "|------|------|",
            f"| 🚫 阻断 | {snapshot.blocked_errors} |",
            f"| ⚠️ 警告 | {snapshot.warned_errors} |",
            f"| ✏️ 改写 | {snapshot.rewritten_errors} |",
            "",
        ]
        
        total_protected = snapshot.blocked_errors + snapshot.warned_errors + snapshot.rewritten_errors
        if total_protected > 0:
            lines.append(f"**总防护次数:** {total_protected}")
        else:
            lines.append("**暂无防护记录**")
        
        lines.append("")
        
        return lines
    
    def _generate_top_errors(self, snapshot: ErrorRateSnapshot) -> list[str]:
        """生成 Top 错误列表"""
        lines = [
            f"## 🔥 Top {self.config.include_top_errors} 错误签名",
            "",
            "| 排名 | 错误签名 | 出现次数 |",
            "|------|----------|----------|",
        ]
        
        for i, err in enumerate(snapshot.top_error_signatures[:self.config.include_top_errors], 1):
            # 截断过长的签名
            sig = err["signature"]
            if len(sig) > 50:
                sig = sig[:47] + "..."
            lines.append(f"| {i} | `{sig}` | {err['count']} |")
        
        lines.append("")
        
        return lines
    
    def _generate_recommendations(
        self,
        trend: ErrorRateTrend,
        achieved: bool,
    ) -> list[str]:
        """生成建议"""
        lines = [
            "## 💡 建议",
            "",
        ]
        
        if not trend.baseline_id:
            lines.append("1. **创建基线:** 使用 `python scripts/baseline_init.py` 创建初始基线，以便追踪效果。")
        elif not achieved:
            lines.extend([
                "1. **增加规则覆盖:** 检查 Top 错误签名，为高频错误添加 guardrail 规则。",
                "2. **优化现有规则:** 审查已停用的规则，考虑重新启用或调整参数。",
                "3. **运行候选生成:** 使用 `python scripts/cron_generate_candidates.py` 自动生成候选规则。",
            ])
        else:
            lines.extend([
                "1. **保持现状:** 当前规则配置效果良好，继续保持。",
                "2. **扩展监控:** 考虑增加新的错误模式监控。",
                "3. **分享经验:** 将有效规则分享给团队或社区。",
            ])
        
        lines.append("")
        
        return lines
    
    def _generate_footer(self) -> list[str]:
        """生成页脚"""
        return [
            "---",
            "",
            f"*此报告由 anti-repeat-errors skill 自动生成*",
            "",
        ]


def create_report_generator(
    tracker: Optional[ErrorRateTracker] = None,
    config: Optional[WeeklyReportConfig] = None,
) -> WeeklyReportGenerator:
    """创建周报生成器的便捷函数"""
    if tracker is None:
        tracker = ErrorRateTracker()
    return WeeklyReportGenerator(tracker=tracker, config=config)