#!/usr/bin/env python3
"""
Cron 任务: 合并候选规则

用法:
    python scripts/cron_merge_candidates.py [--candidates-file path] [--auto-approve] [--dry-run]

功能:
    1. 加载候选规则
    2. 合并到共享规则库
    3. 记录版本历史
    4. 生成变更日志
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到路径
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from rule_merger import RuleMerger, MergeResult
from rule_versioner import RuleVersioner, ChangelogEntry


def main():
    parser = argparse.ArgumentParser(description="合并候选规则")
    parser.add_argument("--candidates-file", type=str, default=None, help="候选规则文件路径")
    parser.add_argument("--target-file", type=str, default=None, help="目标规则文件路径")
    parser.add_argument("--auto-approve", action="store_true", help="自动批准所有候选规则")
    parser.add_argument("--rules-dir", type=str, default=None, help="规则目录")
    parser.add_argument("--candidate-ids", type=str, nargs="*", default=None, help="只合并指定的规则 ID")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 确定路径
    skill_root = Path(__file__).parent.parent
    rules_dir = Path(args.rules_dir) if args.rules_dir else skill_root / "rules"
    
    print(f"[cron_merge_candidates] Starting...")
    print(f"  - Rules dir: {rules_dir}")
    print(f"  - Auto approve: {args.auto_approve}")
    print(f"  - Dry run: {args.dry_run}")
    
    # 初始化组件
    merger = RuleMerger(
        rules_dir=rules_dir,
        auto_approve=args.auto_approve,
        backup_enabled=True,
    )
    versioner = RuleVersioner(rules_dir=rules_dir)
    
    # 确定候选文件
    candidates_file = None
    if args.candidates_file:
        candidates_file = Path(args.candidates_file)
    else:
        candidates_file = merger._get_latest_candidates_file()
    
    if candidates_file is None:
        print("\n[warn] No candidates file found")
        return 1
    
    print(f"  - Candidates file: {candidates_file}")
    
    # 合并候选规则
    print("\n[1/2] Merging candidate rules...")
    result = merger.merge_candidates(
        candidate_file=candidates_file,
        candidate_ids=args.candidate_ids,
        dry_run=args.dry_run,
    )
    
    # 输出结果
    print(f"\n  Rules added: {result.rules_added}")
    print(f"  Rules updated: {result.rules_updated}")
    print(f"  Rules deprecated: {result.rules_deprecated}")
    print(f"  Rules skipped: {result.rules_skipped}")
    
    if result.backup_file:
        print(f"  Backup: {result.backup_file}")
    
    if args.verbose:
        print("\n  Operations:")
        for op in result.operations:
            print(f"    - [{op.operation_type}] {op.rule_id}: {op.details}")
    
    # 记录版本历史
    if not args.dry_run and (result.rules_added > 0 or result.rules_updated > 0 or result.rules_deprecated > 0):
        print("\n[2/2] Recording version history...")
        entry = versioner.record_merge(result.to_dict())
        print(f"  Changelog entry created: {entry.timestamp}")
    else:
        print("\n[2/2] Skipping version history (dry-run or no changes)")
    
    # 输出摘要
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Candidates file: {result.source_file}")
    print(f"Target file: {result.target_file}")
    print(f"Rules added: {result.rules_added}")
    print(f"Rules updated: {result.rules_updated}")
    print(f"Rules deprecated: {result.rules_deprecated}")
    print(f"Rules skipped: {result.rules_skipped}")
    
    if result.rules_added > 0 or result.rules_updated > 0:
        print("\n✅ Rules merged successfully")
        return 0
    else:
        print("\n⚠️ No rules merged")
        return 1


if __name__ == "__main__":
    sys.exit(main())