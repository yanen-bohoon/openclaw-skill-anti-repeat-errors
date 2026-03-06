# 规则文件编写指南

## 目录结构

```
rules/
├── schema.json              # JSON Schema 验证规则
├── phases/                  # 按阶段组织
│   ├── phase-1.yaml
│   ├── phase-2.yaml
│   └── phase-3.yaml
├── task-types/              # 按任务类型组织
│   ├── coding.yaml
│   ├── research.yaml
│   └── planning.yaml
└── global/                  # 全局规则（始终生效）
    └── core.yaml
```

## 规则文件格式

### 基本结构

```yaml
version: "1.0"
kind: phase | task-type | global
name: phase-1              # 规则集名称（文件级）
description: Phase 1 hook injection rules
enabled: true
rules:
  - id: rule-001           # 规则 ID（全局唯一）
    name: "规则名称"
    condition:             # 触发条件
      phase: 1
      task_type: coding
      files_matching:
        - "**/.openclaw/openclaw.json"
      tools:
        - exec
      keywords:
        - git
    content: |             # 规则内容（注入到上下文）
      规则的具体内容...
    priority: 100          # 优先级 0-100，高优先
    enabled: true
    tags:                  # 可选标签
      - security
      - git
```

### 规则类型 (kind)

| 类型 | 说明 | 存放目录 |
|------|------|----------|
| `phase` | 阶段特定规则，仅在指定阶段生效 | `phases/` |
| `task-type` | 任务类型规则，根据任务类型加载 | `task-types/` |
| `global` | 全局规则，始终生效 | `global/` |

### 条件字段 (condition)

| 字段 | 类型 | 说明 |
|------|------|------|
| `phase` | int | 匹配阶段编号 |
| `task_type` | str | 匹配任务类型 |
| `files_matching` | list[str] | 匹配文件路径模式 (glob) |
| `tools` | list[str] | 匹配工具名称 |
| `keywords` | list[str] | 匹配消息关键词 |

### 优先级 (priority)

- 范围: 0-100
- 默认: 50
- 高优先级的规则先被应用
- 建议:
  - 安全相关: 90-100
  - 重要约束: 70-89
  - 一般规则: 50-69
  - 提示性: 0-49

## 示例规则

### 阶段规则 (phase-1.yaml)

```yaml
version: "1.0"
kind: phase
name: phase-1
description: Phase 1 - 禁止直接 git 操作
enabled: true
rules:
  - id: phase-1-git-ban
    name: "禁止直接 git 操作"
    condition:
      phase: 1
    content: |
      当前阶段禁止直接 git 操作（含 status/add/commit/log/rm 等）。
      任何版本控制操作前必须先征求确认。
    priority: 100
    enabled: true
    tags:
      - git
      - security
```

### 任务类型规则 (coding.yaml)

```yaml
version: "1.0"
kind: task-type
name: coding
description: Coding task rules
enabled: true
rules:
  - id: coding-sensitive-config
    name: "敏感配置修改需备份"
    condition:
      files_matching:
        - "**/.openclaw/openclaw.json"
        - "**/gateway.env"
        - "**/cron/jobs.json"
    content: |
      修改敏感配置文件前必须：
      1. 先备份原文件
      2. 仅最小改动
      3. 改后运行健康检查
      4. 保留 before/after 证据
    priority: 90
    enabled: true
    tags:
      - config
      - backup
```

### 全局规则 (core.yaml)

```yaml
version: "1.0"
kind: global
name: core
description: Core rules that always apply
enabled: true
rules:
  - id: core-no-destructive
    name: "禁止破坏性操作"
    condition: {}
    content: |
      没有用户确认，不执行破坏性操作：
      - 删除文件或目录
      - 清空数据
      - 修改系统配置
    priority: 100
    enabled: true
```

## 规则 ID 命名规范

建议格式: `{kind}-{category}-{description}`

示例:
- `phase-1-git-ban`
- `coding-config-backup`
- `core-no-destructive`
- `research-cite-sources`

## 验证

使用验证脚本检查规则文件:

```bash
python scripts/validate_rules.py --rules-dir rules --verbose
```

验证内容包括:
- YAML 语法正确
- 必需字段存在
- 规则 ID 唯一
- 条件逻辑有效
- 优先级范围正确