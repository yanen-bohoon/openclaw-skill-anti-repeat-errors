# anti-repeat-errors 架构详解

## 项目背景

**问题**: Agent 容易重复犯错，同样的错误反复出现。

**根因**: 存储不等于使用，建议不等于强制。规则写在文件里，但 Agent 不一定会遵循。

**目标**: 将重复错误率下降 80%。

---

## 整体架构

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway                          │
├─────────────────────────────────────────────────────────────┤
│  Plugin: anti-repeat-errors                                 │
│  │                                                          │
│  ├── Hook 1: before_prompt_build                            │
│  │   └── 功能: 规则注入                                      │
│  │       └── 实现: TypeScript → Python CLI                  │
│  │                                                          │
│  └── Hook 2: before_tool_call                               │
│      └── 功能: 拦截改写                                      │
│          └── 实现: TypeScript → Python CLI                  │
│                                                              │
│  Phase 3: Closed Loop (Cron)                                │
│  ├── 每日: 日志聚合 → 候选规则生成                           │
│  ├── 每周: 规则合并 → 版本记录                               │
│  └── 每周: 错误率统计 → 周报输出                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Hook Injection Foundation

### 目标

让关键规则在每轮 Prompt 构建前稳定注入。

### 实现方式

```
before_prompt_build Hook
         │
         ▼
┌─────────────────────────────────────────┐
│           TypeScript Hook                │
│  (hook.ts)                               │
│                                          │
│  1. 读取配置                             │
│  2. 构建上下文                           │
│     - session_key                        │
│     - phase (当前阶段)                   │
│     - task_type (任务类型)               │
│     - recent_tools                       │
│     - recent_files                       │
│  3. 调用 Python CLI                      │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│           Python Injector                │
│  (injector_cli.py)                       │
│                                          │
│  1. RuleLoader 加载规则                  │
│     - rules/phases/*.yaml                │
│     - rules/task-types/*.yaml            │
│     - rules/global/*.yaml                │
│                                          │
│  2. 匹配规则                             │
│     - phase 匹配                         │
│     - task_type 匹配                     │
│     - files_matching 匹配                │
│                                          │
│  3. 格式化注入内容                       │
│     - prependContext = 规则文本          │
│                                          │
│  4. 返回结果                             │
│     - injected: true/false               │
│     - rules_count: 匹配数量              │
│     - content: 注入内容                  │
│     - skipped_reason: 未匹配原因         │
└─────────────────────────────────────────┘
```

### 规则文件结构

```
rules/
├── phases/                 # 按阶段划分
│   ├── phase-1.yaml       # Phase 1 规则
│   ├── phase-2.yaml       # Phase 2 规则
│   └── phase-3.yaml       # Phase 3 规则
│
├── task-types/            # 按任务类型划分
│   ├── coding.yaml        # 编程任务规则
│   ├── planning.yaml      # 规划任务规则
│   └── research.yaml      # 研究任务规则
│
├── global/                # 全局规则
│   └── core.yaml          # 核心规则
│
├── schema.json            # JSON Schema 验证
└── README.md              # 规则编写指南
```

### 规则格式示例

```yaml
id: phase-1-git-ban
name: "禁止 Git 操作"
description: "当前阶段禁止直接 git 操作"
content: |
  ⛔ Git 操作已拦截
  
  当前阶段禁止直接使用 git 命令。
  如需版本控制操作，请先与用户确认。
condition:
  phase: 1
priority: 100
enabled: true
tags:
  - git
  - version-control
```

---

## Phase 2: Deterministic Guardrail

### 目标

让高频错误在工具调用前被确定性处理。

### 实现方式

```
before_tool_call Hook
         │
         ▼
┌─────────────────────────────────────────┐
│           TypeScript Hook                │
│  (guardrail_hook.ts)                     │
│                                          │
│  1. 获取工具调用信息                     │
│     - tool_name: "exec"                  │
│     - arguments: { command: "..." }      │
│                                          │
│  2. 调用 Python CLI                      │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│           Python Guardrail               │
│  (guardrail_cli.py)                      │
│                                          │
│  1. PatternMatcher 加载规则              │
│     - rules/guardrails/*.yaml            │
│                                          │
│  2. 匹配规则                             │
│     - tool 匹配 (精确/正则/通配)         │
│     - param_patterns 匹配                │
│                                          │
│  3. 执行动作                             │
│     - BLOCK: 阻止执行                    │
│     - REWRITE: 修改参数                  │
│     - WARN: 警告但允许                   │
│     - LOG: 仅记录                        │
│                                          │
│  4. 返回结果                             │
│     - allowed: true/false                │
│     - modified: true/false               │
│     - result_params: 修改后参数          │
│     - message: 说明消息                  │
└─────────────────────────────────────────┘
```

### 四种动作

```yaml
# 1. BLOCK - 阻止执行
- id: block-git-force
  pattern:
    tool: exec
    param_patterns:
      command: "^git\\s+push\\s+--force"
  action: block
  block_message: "Force push is not allowed"

# 2. REWRITE - 修改参数
- id: rewrite-echo
  pattern:
    tool: exec
    param_patterns:
      command: "^echo\\s+(.+)"
  action: rewrite
  rewrite_rules:
    - target_arg: command
      rewrite_type: replace
      rewrite_value: "printf '%s\\n' '$1'"

# 3. WARN - 警告但允许
- id: warn-sensitive-config
  pattern:
    tool: write
    param_patterns:
      file_path: "(\\.env|config\\.json|credentials)"
  action: warn
  warn_message: "Modifying sensitive config file"

# 4. LOG - 仅记录
- id: log-read-operations
  pattern:
    tool: read
  action: log
```

### 内置规则

| 规则 ID | 动作 | 匹配内容 |
|---------|------|----------|
| guard-git-operations | BLOCK | `git status/add/commit/push/pull/log/rm` |
| guard-sensitive-config | WARN | `.env`, `config.json`, `credentials` |
| guard-force-commands | BLOCK | `rm -rf`, `chmod 777`, `> /dev/` |
| guard-hardcoded-secrets | WARN | API keys, passwords, tokens |
| guard-path-traversal | BLOCK | `../`, `/etc/`, `/root/` |

---

## Phase 3: Closed Loop & Metrics

### 目标

建立错误数据驱动的规则自动迭代闭环与效果评估。

### 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      日志数据源                              │
├─────────────────────────────────────────────────────────────┤
│  injections.jsonl          # 注入日志                       │
│  guardrail_hits.jsonl      # 拦截日志                       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│            Cron: 每日 02:00                                  │
│            候选规则生成                                      │
├─────────────────────────────────────────────────────────────┤
│  1. LogAggregator          # 聚合日志                       │
│  2. ErrorClusterer         # 聚类相似错误                   │
│  3. RuleGenerator          # 生成候选规则                   │
│                                                             │
│  输出: candidates/*.json, candidates/*.yaml                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│            Cron: 每周一 02:30                                │
│            规则合并                                          │
├─────────────────────────────────────────────────────────────┤
│  1. RuleMerger             # 合并到规则库                   │
│     - 冲突检测                                              │
│     - 去重处理                                              │
│                                                             │
│  2. RuleVersioner          # 版本记录                       │
│     - 版本号生成                                            │
│     - 变更历史                                              │
│     - 版本回滚                                              │
│                                                             │
│  输出: rules/guardrails/*.yaml, changelog.yaml              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│            Cron: 每周一 08:00                                │
│            周报输出                                          │
├─────────────────────────────────────────────────────────────┤
│  1. ErrorRateTracker       # 错误率追踪                     │
│     - 基线管理                                              │
│     - 计算当前错误率                                        │
│     - 趋势分析                                              │
│                                                             │
│  2. WeeklyReportGenerator  # 周报生成                       │
│     - Markdown 格式                                         │
│     - 目标验证 (80% 下降)                                   │
│                                                             │
│  输出: reports/*.md → 飞书通知                              │
└─────────────────────────────────────────────────────────────┘
```

### 关键指标

```python
# 错误率计算
error_rate = (repeat_errors / total_errors) * 100

# 改善百分比
improvement = ((baseline_rate - current_rate) / baseline_rate) * 100

# 目标验证
target_achieved = improvement >= 80.0
```

---

## 文件结构

```
/Users/yanen/.openclaw/extensions/anti-repeat-errors/
│
├── index.ts                    # Plugin 入口
├── openclaw.plugin.json        # Plugin 清单
├── SKILL.md                    # Skill 描述
├── requirements.txt            # Python 依赖
│
├── src/
│   │
│   │   # Phase 1: 注入基础
│   ├── models.py               # Pydantic 数据模型
│   ├── rule_loader.py          # 规则加载器
│   ├── injector.py             # 注入逻辑
│   ├── injector_cli.py         # 注入 CLI
│   ├── logger.py               # 日志系统
│   ├── metrics.py              # 指标收集
│   ├── phase_tracker.py        # Phase 追踪
│   │
│   │   # Phase 2: Guardrail
│   ├── guardrail_models.py     # Guardrail 数据模型
│   ├── pattern_matcher.py      # 模式匹配引擎
│   ├── guardrail_hook.py       # Hook 处理器
│   ├── guardrail_cli.py        # Guardrail CLI
│   ├── hit_logger.py           # 命中日志
│   ├── hit_replay.py           # 回放模块
│   │
│   │   # Phase 3: 闭环
│   ├── log_aggregator.py       # 日志聚合
│   ├── error_clusterer.py      # 错误聚类
│   ├── rule_generator.py       # 规则生成
│   ├── rule_merger.py          # 规则合并
│   ├── rule_versioner.py       # 版本管理
│   ├── error_rate_tracker.py   # 错误率追踪
│   └── weekly_report.py        # 周报生成
│
├── rules/
│   ├── phases/                 # 阶段规则 (3 files, 6 rules)
│   ├── task-types/             # 任务类型规则 (3 files, 7 rules)
│   ├── global/                 # 全局规则 (1 file, 3 rules)
│   ├── guardrails/             # Guardrail 规则 (5 rules)
│   ├── schema.json             # JSON Schema
│   └── README.md               # 规则编写指南
│
├── scripts/
│   ├── validate_rules.py       # 规则验证
│   ├── verify_injection.py     # 注入验证
│   ├── view_logs.py            # 日志查看
│   ├── replay_guardrail_hits.py
│   ├── generate_hit_report.py
│   ├── baseline_init.py        # 基线初始化
│   ├── cron_generate_candidates.py
│   ├── cron_merge_candidates.py
│   └── cron_weekly_report.py
│
├── tests/                      # 147 tests
│   ├── test_rule_loader.py
│   ├── test_guardrail_models.py
│   ├── test_pattern_matcher.py
│   ├── test_guardrail_hook.py
│   ├── test_03_01_clustering.py
│   ├── test_03_02_rule_merge_versioning.py
│   └── test_03_03_error_rate_weekly_report.py
│
├── candidates/                 # 候选规则输出
├── reports/                    # 周报输出
├── versions/                   # 版本记录
└── baselines/                  # 基线数据
```

---

## 配置选项

```json
{
  "enabled": true,
  "rulesDir": "~/.openclaw/skills/anti-repeat-errors/rules",
  "logLevel": "info",
  "injectTimeout": 1000,
  "cacheEnabled": true,
  "cacheTtlSeconds": 300,
  "guardrailEnabled": true,
  "guardrailTimeout": 500,
  "guardrailRulesDir": "~/.openclaw/skills/anti-repeat-errors/rules/guardrails"
}
```

---

## 日志格式

### 注入日志 (injections.jsonl)

```json
{
  "timestamp": "2026-03-06T10:00:00.000Z",
  "event": "injection",
  "session_key": "agent:main:main",
  "phase": 1,
  "task_type": "coding",
  "rules_matched": ["phase-1-git-ban", "coding-test-first"],
  "rules_count": 2,
  "duration_ms": 45,
  "skipped_reason": null
}
```

### 拦截日志 (guardrail_hits.jsonl)

```json
{
  "timestamp": "2026-03-06T10:00:00.000Z",
  "rule_id": "guard-git-operations",
  "rule_name": "禁止 Git 操作",
  "action": "block",
  "tool_name": "exec",
  "original_params": { "command": "git status" },
  "result_params": { "command": "git status" },
  "message": "Git 操作已拦截",
  "session_key": "agent:main:main",
  "phase": 1
}
```

---

## 部署步骤

```bash
# 1. 重启 Gateway 使 Plugin 生效
openclaw gateway restart

# 2. 启用 Plugin
openclaw plugins enable anti-repeat-errors

# 3. 初始化基线
cd ~/.openclaw/extensions/anti-repeat-errors
python scripts/baseline_init.py

# 4. 验证 Hook 注册
openclaw plugins list | grep anti-repeat
```

---

## 开发时间线

| 时间 | 里程碑 |
|------|--------|
| 2026-03-05 | 项目初始化，需求分析 |
| 2026-03-06 08:00 | Phase 1 规划完成 |
| 2026-03-06 08:30 | Phase 1 执行完成 |
| 2026-03-06 09:40 | Phase 2 规划完成 |
| 2026-03-06 10:00 | Phase 2 执行完成 |
| 2026-03-06 10:10 | Phase 3 规划完成 |
| 2026-03-06 11:05 | Phase 3 执行完成 |
| 2026-03-06 11:10 | Gateway 重启，Hook 生效 |
| 2026-03-06 12:12 | GitHub 仓库创建 |
| 2026-03-06 13:05 | Plugin 修复并运行 |

**总耗时**: ~5 小时

---

## 测试覆盖

```
tests/
├── test_rule_loader.py              # 34 tests
├── test_guardrail_models.py         # 28 tests
├── test_pattern_matcher.py          # 17 tests
├── test_guardrail_hook.py           # 17 tests
├── test_03_01_clustering.py         # 14 tests
├── test_03_02_rule_merge_versioning.py  # 10 tests
└── test_03_03_error_rate_weekly_report.py  # 27 tests

Total: 147 tests
Status: All passing ✅
```

---

## 后续优化方向

1. **规则质量评估** - 根据命中率和效果自动调整优先级
2. **智能聚类** - 使用 ML 改进错误聚类准确性
3. **跨 Session 学习** - 持久化并共享规则库
4. **可视化面板** - 提供规则管理和效果监控 UI
5. **规则市场** - 支持导入社区贡献的规则包

---

## 参考

- [OpenClaw Plugin SDK](https://docs.openclaw.ai/plugins)
- [OpenClaw Hooks](https://docs.openclaw.ai/hooks)
- 项目仓库: https://github.com/yanen-bohoon/openclaw-skill-anti-repeat-errors