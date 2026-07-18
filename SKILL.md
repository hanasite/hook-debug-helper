---
name: hook-debug-helper
description: >
  Claude Code 接入第三方模型时的 hook 问题排查工具。专门针对非 Anthropic 模型（DeepSeek、OpenAI 等）
  通过代理/cc-switch 接入 Claude Code 时出现的：hook 死循环、hook 回滚、hook 指令不遵循。
  **紧急触发**：用户描述 死循环/抽风/自主乱改/指令不遵循/越权决策/改完不停/自己做主 时，
  立即加载此 skill。
  第一步先询问用户是否使用第三方模型——如果是，执行诊断流程；如果不是，说明本 skill 专为
  第三方模型场景设计，建议另寻方法。
  触发词：死循环、抽风、不遵循指令、自主乱改、乱改代码、越权、自作主张、hook、
  ECONNREFUSED、settings.json 被覆盖、echo 循环。
---

# Hook Debug Helper

## 修改规则

**允许二次编辑，但必须：**
1. Read 确认当前内容 → Edit 精确替换 → 一次只改一个逻辑点
2. 改完后运行 `python3 scripts/check-cc-switch.py` 验证脚本未损坏
3. 验证无误才算完工——决不猜测

## 第零步：确认用户场景（诊断前必须先问）

**在做任何诊断之前，先用 `AskUserQuestion` 工具弹出确认对话框：**

调用 `AskUserQuestion`，参数：

```
questions: [{
  question: "你在用什么模型接入 Claude Code？",
  header: "模型来源",
  options: [
    {label: "第三方模型", description: "DeepSeek、OpenAI 等，通过 cc-switch 或代理接入"},
    {label: "Anthropic 官方", description: "直接使用 Anthropic API，没用代理/切换工具"}
  ]
}]
```

**根据回答分流：**

| 用户选择 | 处理方式 |
|---------|---------|
| **第三方模型** | 继续下面的问题确认（第二步）。 |
| **Anthropic 官方** | 诚恳告知：本 skill 专门针对第三方模型接入场景，我没有官方模型的 hook 调试经验。建议查 Claude Code 官方文档或社区。诊断结束。 |

### 第零点五步：确认具体症状（第三方模型才走这步）

**模型来源确认后，继续用 `AskUserQuestion` 让用户勾选遇到的问题：**

```
questions: [{
  question: "你遇到了什么问题？（可多选，都不是的话在 Other 描述）",
  header: "问题症状",
  multiSelect: true,
  options: [
    {label: "死循环", description: "反复执行 echo/done/同样的命令，停不下来"},
    {label: "自主乱改代码", description: "改完不停、自动加注释、自己决定重写文件、做用户没要求的事"},
    {label: "指令不遵循", description: "说了\"停\"/\"好\"/\"就这样\"还继续，规则不遵守"},
    {label: "hook 连接错误", description: "反复出现 ECONNREFUSED、hook error、超时等错误消息"},
    {label: "反复弹窗", description: "task-notifier 或其他通知反复弹出，关不掉"},
    {label: "settings.json 回滚", description: "改好的 hook 配置过一会又变回去了"}
  ]
}]
```

**根据回答分诊（不预判，根据实际勾选组合输出）：**

| 勾选组合 | 优先排查方向 |
|---------|-------------|
| 死循环 | 重点查 hook matcher 是否 `""` + Pre/PostToolUse 是否捕获自身命令 |
| 自主乱改代码 / 指令不遵循 | 重点查 hook 事件数是否过多 + 是否第三方模型（这是本 skill 专攻的场景） |
| hook 连接错误 / ECONNREFUSED | 重点查 Hook 指向的端口存活状态 + 是否存在僵尸配置 |
| 反复弹窗 | 重点查通知类 hook 是否形成 Bash→hook→Bash 闭环 |
| settings.json 回滚 | 重点查 cc-switch/代理工具持久化存储 + Clawd backup 文件 |
| 全选 / 多个 | 多源并存的可能性最高——先砍到只剩一个来源再排查 |
| Other: [用户描述] | 先执行紧急诊断四步，再根据诊断结果分析 |

**如果用户选了"自主乱改代码"或"指令不遵循"：**

额外告知：
> 这两个症状在第三方模型上是高频问题。根因通常是 hook 碎片注入上下文 → 非 Anthropic 模型未做相关 RLHF → 采样到"主动做事"路径。
>
> **最快的验证方式**：临时把 `"hooks": {}` 设为空，用一两天。如果问题消失，就确认是 hook 的锅。之后可以精简到只保留 PermissionRequest + 2-3 个核心事件。

## 紧急诊断（触发时首先执行）

用户抱怨死循环/抽风/自主乱改时，**立即执行下面四步，不做任何其他事**：

### 第一步：读取 settings.json 并列出所有 hook 来源

```bash
python3 -c "
import json, os, sys
path = os.path.expanduser('~/.claude/settings.json')
try:
    with open(path) as f:
        s = json.load(f)
except:
    print('ERROR: settings.json 不存在或格式错误')
    sys.exit(1)

hooks = s.get('hooks', {})
seen = set()
lines = []
for event, entries in hooks.items():
    for entry in entries:
        for h in entry.get('hooks', []):
            cmd = h.get('command') or ''
            url = h.get('url') or ''
            typ = h.get('type','?')
            matcher = entry.get('matcher','')
            # 提取来源标识：可执行文件名、脚本路径中的关键词、URL host
            parts = []
            if cmd:
                # 提取脚本文件名
                script = cmd.split('\"')[1] if cmd.count('\"') >= 2 else cmd.split()[-1] if ' ' in cmd else cmd
                parts.append(script)
            if url:
                parts.append(url)
            key = ' | '.join(parts) if parts else f'empty-{typ}-hook'
            if key not in seen:
                seen.add(key)
                lines.append(f'  [{event}] matcher=\"{matcher[:40]}\" type={typ} source={key[:120]}')
print(f'Hook 事件数: {len(hooks)}')
print('明细:')
for l in lines[:40]:
    print(l)
if len(lines) > 40:
    print(f'...还有 {len(lines)-40} 条')
" 2>&1
```

### 第二步：扫描后台可疑进程（不预设名称）

```bash
# 所有正在监听的 TCP 端口——重点关注 127.0.0.1
powershell -Command "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { \$_.LocalAddress -eq '127.0.0.1' -or \$_.LocalAddress -eq '0.0.0.0' } | Select-Object LocalPort, OwningProcess | Sort-Object LocalPort | ForEach-Object { \$proc = Get-Process -Id \$_.OwningProcess -ErrorAction SilentlyContinue; Write-Host \"PORT \$(\$_.LocalPort) -> PID \$(\$_.OwningProcess) (\$(\$proc.ProcessName))\" }" 2>/dev/null | head -50
```

```bash
# 可能与 Claude Code hook 相关的进程：node.exe / python / powershell 子进程
powershell -Command "Get-Process | Where-Object { \$_.ProcessName -match 'node|python|ruby|java|pwsh' } | Select-Object Id, ProcessName, @{N='CmdLine';E={ (Get-WmiObject Win32_Process -Filter \\\"ProcessId=\$(\$_.Id)\\\" -ErrorAction SilentlyContinue).CommandLine -replace '.*\\\\', '' }} | Format-Table -AutoSize -Wrap" 2>/dev/null | head -30
```

```bash
# Windows 后台/托盘进程（GUI 应用，可能是桌宠或代理工具）
powershell -Command "Get-Process | Where-Object { \$_.MainWindowTitle -ne '' -or \$_.ProcessName -match 'clawd|switch|pet|desk|pixie|buddy|mate|side|dock|bar' } | Select-Object Id, ProcessName, MainWindowTitle | Format-Table -AutoSize" 2>/dev/null | head -20
```

### 第三步：交叉分析 + 询问用户

根据第一步（hook 配置来源）和第二步（后台进程/端口），建立交叉表：

```
Hook 来源 → 对应端口 → 对应进程 → 用户命名
```

**对每个无法自动识别的 hook 来源，问用户：**

> 我在 settings.json 里发现 hook 来源引用了：
> - `[脚本路径/URL]`（事件: [PreToolUse/PostToolUse/...]）
>
> 同时后台检测到：端口 [PORT] 被进程 [ProcessName] (PID [ID]) 占用。
>
> 这个是什么？是你主动安装的吗？

### 第四步：判定

| 证据 | 结论 |
|------|------|
| Hook 指向的端口对应进程不在运行 → ECONNREFUSED | 该 hook 是僵尸配置，需要删 |
| 多个 hook 源指向不同的端口/进程 | 多源并存，互相干扰 |
| Hook 源不是用户主动安装的 | 可能是某个项目的 CLAUDE.md 自动部署的 |
| 事件数 > 10 + 用户说"抽风/乱改" | hook 过多，碎片化影响指令遵循 |
| 用户不认得的 hook 来源 | **立即建议删除** |

### 如果判断需要停止当前对话

**不要说"让我帮你改"——直接打印下面这段：**

> 诊断完成：当前 Claude Code 配置了 [N] 个 hook 事件，来自 [M] 个不同来源：[列出名称]。
> [如果有多源] 多个来源同时生效是导致行为异常的根因。
>
> **立即操作：**
> 1. 关掉所有可能注册 hook 的三方工具
> 2. 打开 `~/.claude/settings.json`，把 `"hooks"` 整段替换为 `"hooks": {}`
> 3. 完全退出并重启 Claude Code
> 4. 确认行为正常后，**只开一个**你信任的工具（比如 Clawd），它会自动注册干净的 hook
> 5. 不要再同时开多个桌宠/代理/IDE 集成——它们每个都会往 settings.json 塞 hook
>
> 如果不需要三方工具的状态联动，最安全的方式是保持 `"hooks": {}`。

## 速查流程

按以下顺序排查 hook 问题：

### 1. 定位当前 hook 配置

```bash
python3 -c "
import json
with open('C:/Users/kakun/.claude/settings.json') as f:
    s = json.load(f)
hooks = s.get('hooks', {})
for event, entries in hooks.items():
    for entry in entries:
        for h in entry.get('hooks', []):
            print(f'{event}: type={h[\"type\"]} async={h.get(\"async\",\"sync\")} url={h.get(\"url\",\"\")} cmd={h.get(\"command\",\"\")[:60]}')
" 2>&1 | head -50
```

关注点：
- `type: http` → 同步阻塞 hook，挂了会报 ECONNREFUSED
- `async` 为 false/缺失 → 可能阻塞对话 30s
- 同一个 event 下有多个条目 → 多源并存
- **任何来源的用户都应该能辨认** → 不认得的 = 可疑

### 2. 检查配置文件备份

```bash
ls -la ~/.claude/settings.json.* 2>/dev/null
```

任何备份文件都可能成为回滚源。删掉不再需要的。

### 3. 检查第三方代理/管理器持久化存储

cc-switch（SQLite DB）是最常见的隐蔽回滚源，但它不唯一。原则上任何能写 settings.json 的工具都可能存了旧配置：

```bash
python3 ~/.claude/skills/hook-debug-helper/scripts/check-cc-switch.py
```

对其他工具：检查其数据目录是否存在配置快照、备份或 template。

### 4. 检查上下文注入源

```bash
grep -rl "hook\|settings\.json\|mcp\.json" \
  ~/.claude/webui/CLAUDE.md \
  ~/.claude/projects/C--Users-kakun/memory/ \
  ~/.claude/projects/*/session-memory/ \
  2>/dev/null
```

任何 CLAUDE.md 或 Memory 文件中写了 hook/MCP 配置的，都会被注入到上下文，模型可能按指令自动部署。

### 5. 检查自启动

```bash
schtasks /query /fo LIST 2>/dev/null | grep -i "claude\|clawd\|aemeath\|desk\|pet\|switch"
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" 2>/dev/null
ls -la ~/AppData/Roaming/Microsoft/Windows/Start\ Menu/Programs/Startup/ 2>/dev/null
```

开机自启动的工具可能在用户不知情时重新注册 hook。

## 踩坑记录（通用版）

以下来自真实调试经历，去掉了特定工具的名称。

### 坑 1: 第三方代理/管理器是回滚的总开关

代理/配置管理工具可能在本地 SQLite/JSON 文件里持久化了 settings.json 的快照。每次工具启动或热切换时用它覆盖真实配置。

**教训**: 回滚排查不能只看 Claude Code 自己的文件。找到所有能读写 `~/.claude/settings.json` 的三方工具，检查它们的数据目录。

### 坑 2: 多个工具互不感知地修改同一文件

工具 A 写入自己的 hook → 工具 B 启动发现缺了 B 的 hook → B 补上但不删 A 的 → backup 记录了 A+B 的混合态 → 下次 A 恢复又带回旧版本。

**通用回滚链**:

```
第三方配置快照（含旧 hook）
    ↓ 启动时覆盖
settings.json = 旧 hook + 新 hook 并存
    ↓ 每个工具各自创建 backup
backup 文件们（互相矛盾）
    ↓ 任何一个工具重启都可能恢复任一版本
无限循环
```

**斩断方法**:
1. 关闭所有可能操作 settings.json 的工具
2. 删除所有 backup 文件
3. 修改所有工具的持久化存储中的 hook 配置
4. 修改 settings.json
5. 全量确认无残留
6. 只启动一个工具

### 坑 3: 上下文注入源（CLAUDE.md / Memory）让模型自动部署

CLAUDE.md 或 Memory 文件中记录了"部署时需要注册 hook"的指令。每次对话启动时这些被注入上下文，模型按指令执行——把旧 hook 写回去。

**清理方法**: 搜索所有含 `hook` 或 `settings.json` 关键字的 CLAUDE.md 和 Memory 文件，删除或改写其中的"自动部署"指令。

### 坑 4: Hook 碎片影响非 Anthropic 模型

每个 hook 事件的 stdout/stderr 痕迹注入模型上下文，在非 Anthropic 模型（DeepSeek、OpenAI 等）上形成噪声层。这些模型未针对 Claude Code hook 注入做 RLHF，更易采样到"主动做事"的路径。

**症状**: 改完代码后自主加注释、继续分析、自动优化、用户说"停"还继续。

**快速验证**: 临时设 `"hooks": {}` 用一两天，观察指令遵循改善。

### 坑 5: HTTP hook + sync 阻塞 + matcher 空字符串 = 性能炸弹

- `type: http` 默认同步阻塞，超时 30s
- `matcher: ""` 匹配所有工具调用
- 指向的服务挂了 → 每个工具调用都卡 30s → 十几个 hook error 堆在上下文

**原则**: 永远不要用同步 HTTP hook 做状态通知。只给双向通信（如 PermissionRequest）用 HTTP hook。

### 坑 6: 通知类 hook 与桌面通知的回环

hook 通知执行了一个 Bash 命令 → 这个 Bash 调用又被 hook 捕获 → 再次通知 → 死循环。

**原则**: PreToolUse/PostToolUse 的 matcher 必须排除自身使用的命令（如 `echo`、`notify.ps1`）。

## 良性 hook 配置的特征

- 所有 command hook: `"async": true` + `"timeout": 5-10`
- PreToolUse/PostToolUse 有 matcher 过滤心跳/通知命令
- 事件数 ≤ 8
- HTTP hook 仅用于 PermissionRequest
- 同一个 event 下只有一种来源
- 所有来源用户能清楚说出是什么

## 创建/删除内容时用通用名称

本 skill 不预设任何特定工具名称（Clawd/Aemeath/cc-switch 等）。诊断时从 json 中**读**出来源，从进程中**扫描**出来源，**问用户**是什么，再做判断。
