# anti-repeat-errors 使用指南

## 快速开始

### 1. 安装

Plugin 已集成到 OpenClaw，无需额外安装。

### 2. 启用

```bash
openclaw plugins enable anti-repeat-errors
openclaw gateway restart
```

### 3. 验证

```bash
openclaw plugins list | grep anti-repeat
# 应显示: anti-repeat-errors │ loaded
```

---

## 配置

编辑 `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "anti-repeat-errors": {
        "enabled": true,
        "config": {
          "enabled": true,
          "rulesDir": "~/.openclaw/extensions/anti-repeat-errors/rules",
          "logLevel": "info",
          "injectTimeout": 1000,
          "guardrailEnabled": true,
          "guardrailTimeout": 500
        }
      }
    }
  }
}
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | boolean | true | 总开关 |
| `rulesDir` | string | rules/ | 规则目录 |
| `logLevel` | string | "info" | 日志级别 |
| `injectTimeout` | number | 1000 | 注入超时 (ms) |
| `guardrailEnabled` | boolean | true | Guardrail 开关 |
| `guardrailTimeout` | number | 500 | 拦截超时 (ms) |

---

## 规则编写

### 注入规则 (Injection Rules)

位置: `rules/phases/`, `rules/task-types/`, `rules/global/`

```yaml
id: my-rule
name: "规则名称"
description: "规则描述"
content: |
  ## 规则内容
  
  这里的内容会被注入到 Prompt 中。
condition:
  phase: 1              # 可选: 匹配阶段
  task_type: coding     # 可选: 匹配任务类型
  files_matching:       # 可选: 匹配文件
    - "*.py"
    - "src/**/*.ts"
priority: 100           # 优先级，数字越大越优先
enabled: true
tags:
  - custom
```

### Guardrail 规则

位置: `rules/guardrails/`

```yaml
id: my-guard-rule
name: "拦截规则名称"
description: "拦截规则描述"
pattern:
  tool: exec                          # 工具名称
  param_patterns:                     # 参数匹配
    command: "^rm\\s+-rf"             # 正则匹配
action: block                         # block | rewrite | warn | log
block_message: |                      # BLOCK 时的消息
  禁止执行 rm -rf
priority: 100
enabled: true
```

### 四种动作

| 动作 | 效果 |
|------|------|
| `block` | 阻止执行，返回错误消息 |
| `rewrite` | 修改参数后继续执行 |
| `warn` | 允许执行但记录警告 |
| `log` | 仅记录日志 |

---

## 日志查看

### 注入日志

```bash
cat ~/.openclaw/logs/anti-repeat-errors/injections.jsonl
```

### 拦截日志

```bash
cat ~/.openclaw/logs/anti-repeat-errors/guardrail_hits.jsonl
```

### 日志查看工具

```bash
python ~/.openclaw/extensions/anti-repeat-errors/scripts/view_logs.py \
  --type injection \
  --session-key "agent:main:main" \
  --limit 10
```

---

## Cron 任务

### 初始化基线

```bash
python ~/.openclaw/extensions/anti-repeat-errors/scripts/baseline_init.py
```

### 生成候选规则

```bash
python ~/.openclaw/extensions/anti-repeat-errors/scripts/cron_generate_candidates.py
```

### 合并规则

```bash
python ~/.openclaw/extensions/anti-repeat-errors/scripts/cron_merge_candidates.py --dry-run
```

### 生成周报

```bash
python ~/.openclaw/extensions/anti-repeat-errors/scripts/cron_weekly_report.py
```

---

## 验证目标

项目目标: **重复错误率下降 80%**

```bash
# 检查当前错误率
python -c "
from src.error_rate_tracker import ErrorRateTracker
tracker = ErrorRateTracker()
print(f'当前重复错误率: {tracker.get_current_error_rate():.2f}%')
print(f'改善百分比: {tracker.get_improvement_percentage():.2f}%')
print(f'目标达成: {tracker.check_target_achieved(80.0)}')
"
```

---

## 故障排查

### Plugin 未加载

```bash
# 检查 Plugin 状态
openclaw plugins list | grep anti-repeat

# 如果显示 disabled，启用它
openclaw plugins enable anti-repeat-errors
openclaw gateway restart
```

### Hook 未触发

```bash
# 检查日志
cat ~/.openclaw/logs/gateway.log | grep -i "anti-repeat\|hook"

# 应看到:
# [plugins] Registered before_prompt_build hook
# [plugins] Registered before_tool_call hook
```

### 规则未生效

```bash
# 验证规则格式
python ~/.openclaw/extensions/anti-repeat-errors/scripts/validate_rules.py --verbose
```

---

## 最佳实践

1. **规则优先级**: 高风险操作设置高优先级 (如 100+)
2. **渐进式添加**: 先用 `warn` 观察，再切换到 `block`
3. **定期审查**: 查看 `guardrail_hits.jsonl` 了解拦截情况
4. **版本管理**: 使用 `changelog.yaml` 追踪规则变更