# Hook Debug Helper

Claude Code 接入**第三方模型**（DeepSeek、OpenAI 等）时的 hook 问题排查工具。

## 适用场景

- 你通过 cc-switch 或代理用 DeepSeek/OpenAI 模型跑 Claude Code
- Claude Code 出现死循环、自主乱改代码、指令不遵循、hook 连接错误等问题
- settings.json 的 hook 配置反复被覆盖/回滚

> **注意**：如果你用的是 Anthropic 官方模型，本 skill 不适用。

## 安装

将本仓库放入 `~/.claude/skills/hook-debug-helper/`。

## 触发方式

在对话中描述问题时，skill 会自动触发。触发词包括：死循环、抽风、不遵循指令、自主乱改、hook、ECONNREFUSED、settings.json 被覆盖、echo 循环等。

## 工作流程

1. **第零步** — 弹出确认框，询问是否使用第三方模型
2. **第零点五步** — 弹出多选症状，让用户勾选遇到的具体问题
3. **紧急诊断** — 读取 settings.json 提取 hook 来源 → 扫描后台进程和端口 → 交叉对比
4. **第四步** — 提供三种修复方案：临时禁用 / 彻底修复 / 只备份不动

修复前自动备份到 `~/.claude/settings.json.bak`。

## 文件结构

```
hook-debug-helper/
├── SKILL.md                         # 完整诊断流程 + 踩坑记录
└── scripts/
    └── check-cc-switch.py           # cc-switch 数据库检查/修复脚本
```

## 踩坑记录

SKILL.md 内含 6 个真实踩坑记录：回滚链、多源并存的死循环、上下文注入源、第三方模型 hook 碎片化、HTTP hook 阻塞炸弹、通知回环。

## License

MIT
