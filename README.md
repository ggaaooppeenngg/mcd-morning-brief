<div align="center">

# 🌅 麦麦晨报 mcd-morning-brief

**麦当劳活动与优惠早知道 —— 可直接接入个人 Agent 晨报的麦当劳情报栏目**

基于 [麦当劳官方 MCP Server](https://github.com/M-China/mcd-mcp-server) · 麦当劳程序员创意开发大赛参赛作品

`活动日历` `优惠券提醒` `积分过期预警` `iCal 订阅` `MCP` `Agent Skill`

</div>

---

## 这是什么？

麦当劳的优惠信息散落在 APP 首页、开屏弹窗、麦麦省、会员日历七八个入口里——
**第二份半价悄悄开始、500 积分月底悄悄清零**，你总是事后才知道。

**麦麦晨报**每天把麦当劳的活动、可领优惠券、即将过期的券和积分、抽奖机会
聚合成一条 30 秒读完的简报，塞进你个人 Agent 的晨报里（天气和日程之间）：

```markdown
## 🌅 麦麦晨报 · 2026-10-10 周六

### 📅 近期活动（未来 7 天）
- 🔥 **进行中** 10.10 麦乐畅享日 · 多款套餐第二份半价（10.10 ~ 10.10）
- ⏰ **1 天后开始** 国际拉花咖啡周 · M咖啡买一送一（10.11 ~ 10.17）
- ⏰ **3 天后开始** 会员日 · 麦金卡会员双倍积分（10.13 ~ 10.13）

### 🎫 今日可领优惠券（3 张）
- 🎟️ **早晨加油包**｜早晨套餐立省 6 元｜有效期至 10-31
- 🎟️ **板烧鸡腿堡买一送一**｜每日 10:30 后可用｜有效期至 10-12
- 🎟️ **麦乐送满 49 减 12**｜外送专用｜有效期至 10-18

### ⌛ 即将过期的券（1 张）
- 🎟️ **派 Day 派对券 · 香芋派免费券**｜凭券免费兑换香芋派一个｜有效期至 10-11

### 💰 积分
- 可用 **1,240** 分｜累计 3,580 分
- ⚠️ 300 积分即将过期（2026-10-15 前），别浪费啦

### 🎰 抽奖机会
- 🎁 「十月麦麦抽奖季」进行中，你还有 1 次免费抽奖机会

---
> 数据来自麦当劳 MCP Server，仅供参考；餐品、价格与活动以麦当劳 APP / 门店实时信息为准。
```

*(↑ 由 `--demo` 模式用内置样例数据生成，完整样例见 [examples/](./examples/))*

## ✨ 特性

| | 特性 | 说明 |
|---|---|---|
| 📅 | **活动日历** | 自动筛选"进行中"与"未来 7 天开始"的活动，带倒计时提醒 |
| 🎫 | **领券情报** | 汇报麦麦省可领的券；回复一句"领券"，**确认后**才一键领取 |
| ⌛ | **过期预警** | 7 天内到期的券、即将清零的积分，提前止损 |
| 🎰 | **抽奖提醒** | 有免费抽奖次数时才打扰你 |
| 📆 | **iCal 导出** | 活动导出 `.ics`，订阅进手机日历，开始前系统自动提醒 |
| 🤖 | **Agent Skill** | 一份 `SKILL.md` 剧本，WorkBuddy / Cursor / Trae / Cherry Studio / Claude Code 通用 |
| 🖥️ | **独立 CLI** | 没有付费 AI 客户端也能用：纯 Python，crontab 定时跑，推到微信/飞书/邮件 |
| 🔌 | **多种输出** | Markdown（晨报/博客）/ 纯文本（推送）/ JSON（程序集成）/ iCal（日历） |
| 🛟 | **零门槛体验** | `--demo` 内置样例数据，**没有 MCP Token 也能跑通全部功能** |
| 🛡️ | **只读安全设计** | 生成晨报全程只读；领券、抽奖等写操作必须二次确认，绝不自动下单 |

## 🚀 快速开始

### 0. 准备 MCP Token（2 分钟）

1. 打开 [open.mcd.cn/mcp](https://open.mcd.cn/mcp)，手机号验证登录
2. 右上角「控制台」→「激活」→ 同意协议 → 复制 **MCP Token**

> 没有 Token？先跳过，下面的命令都可以加 `--demo` 离线体验。

### 方式 A：接入个人 Agent 晨报（推荐）🤖

把 MCP Server 加进你的 AI 客户端（配置即 [`mcp-config.example.json`](./mcp-config.example.json)，
把 `${MCD_MCP_TOKEN}` 换成你的 Token）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer 你的Token" }
    }
  }
}
```

| 客户端 | 配置入口 |
|---|---|
| WorkBuddy | 连接器 → 自定义连接器 → 配置 MCP |
| Cursor | `~/.cursor/mcp.json` |
| Trae | 设置 → MCP → 手动添加 |
| Cherry Studio | 设置 → MCP → 从 JSON 导入 |
| Claude Code | `claude mcp add` 或 `.mcp.json` |

然后把本仓库 [`skill/mcd-morning-brief/`](./skill/mcd-morning-brief/) 作为技能安装给客户端——
目录已符合 Agent Skill 规范（`SKILL.md` + `references/` + `scripts/`），拷进去即可用：

```bash
# ZCode / Claude Code 等支持技能目录的客户端：
cp -r skill/mcd-morning-brief ~/.agents/skills/    # 用户级，所有项目可用
```

Cursor/Trae 用户也可以直接把 SKILL.md 内容粘进 Rules。
之后在晨报提示词里加一句 **"附上麦麦晨报栏目"**，或直接问：

```text
给我来份今天的麦麦晨报
```

Agent 会按剧本调 MCP 工具、按模板渲染，并处理"领券""我的积分""抽一下"等追问。

### 方式 B：独立 CLI 🖥️

```bash
git clone https://github.com/<you>/mcd-morning-brief.git
cd mcd-morning-brief
pip install -r requirements.txt

# 没有 Token？离线体验：
python -m mcd_brief brief --demo

# 配置 Token 后使用真实数据：
export MCD_MCP_TOKEN=你的Token        # Windows: set MCD_MCP_TOKEN=你的Token
python -m mcd_brief brief             # Markdown 晨报
python -m mcd_brief brief -f text     # 纯文本（适合推送）
python -m mcd_brief brief -f json     # JSON（适合程序）
python -m mcd_brief calendar --ics mcd.ics   # 活动导出手机日历
python -m mcd_brief coupons --claim   # 一键领券（会先让你确认）
python -m mcd_brief points            # 积分与过期提醒
```

**每天早上 8:30 自动生成晨报**（crontab 示例）：

```cron
30 8 * * * cd /path/to/mcd-morning-brief && python -m mcd_brief brief -f text >> ~/mcd-brief.log
```

或用 GitHub Actions 定时跑并推送到飞书/企业微信（Token 存为仓库 Secret `MCD_MCP_TOKEN`）：

```yaml
name: mcd-morning-brief
on:
  schedule: [{ cron: "30 0 * * *" }]   # UTC 00:30 = 北京时间 08:30
  workflow_dispatch:
jobs:
  brief:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: |
          python -m mcd_brief brief -f text > brief.txt
          cat brief.txt
        env:
          MCD_MCP_TOKEN: ${{ secrets.MCD_MCP_TOKEN }}
      # 在此追加你喜欢的推送步骤（Server酱 / 飞书 webhook / SMTP 均可）
```

### 方式 C：订阅到手机日历 📆

```bash
python -m mcd_brief calendar --ics mcd.ics
```

把生成的 `mcd.ics` 导入 iOS/Android 日历（或放进任意静态托管做成订阅源），
每个活动开始当天就是一条全天日程，**苹果日历也能提醒你吃巨无霸**。

## 🎯 目标用户

- **个人 Agent / 晨报玩家**：用 WorkBuddy、Cursor、Cherry Studio 等搭了每日晨报，想多一个生活情报栏目
- **麦当劳重度用户**：常点麦，不想错过任何半价、买一送一和会员日
- **积分/羊毛党**：在意积分清零和优惠券过期，需要止损提醒
- **自动化爱好者**：想要一个 cron 一行就能跑、输出标准 Markdown/JSON 的麦当劳情报源

## 🧱 工作原理

```
个人 Agent 晨报任务 ──┐
crontab / CI 定时 ────┼──> mcd-brief（Skill 剧本 或 Python CLI）
手机日历订阅 ─────────┘         │
                                │ 6 个只读工具（单会话批量调用）
                                ▼
                     麦当劳官方 MCP Server (mcp.mcd.cn)
                     now-time-info / campaign-calendar /
                     available-coupons / query-my-coupons /
                     query-my-account / query-lottery-info
                                │
                                ▼
                     聚合 + 窗口过滤 + 过期预警
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
                 Markdown     纯文本       JSON / iCal
                （晨报栏目）（推送/LLM）（程序 / 手机日历）
```

- 聚合与容错解析：[`mcd_brief/aggregate.py`](./mcd_brief/aggregate.py)、[`mcd_brief/models.py`](./mcd_brief/models.py)
- 渲染器（md/text/json/ics）：[`mcd_brief/render.py`](./mcd_brief/render.py)
- MCP 客户端（官方 SDK + 双版本兼容 + 401/429 精确诊断）：[`mcd_brief/client.py`](./mcd_brief/client.py)
- Agent 剧本（工具编排 + 模板 + 后续意图 + 安全守则）：[`skill/mcd-morning-brief/SKILL.md`](./skill/mcd-morning-brief/SKILL.md)
- 工具清单与调用时序：[`MCP_INTEGRATION.md`](./MCP_INTEGRATION.md)

## ✅ 测试

```bash
pip install -r requirements-dev.txt
pytest          # 22 个离线用例：聚合、窗口过滤、过期计算、容错解析、4 种渲染、真实格式回归
```

真实链路验证：`export MCD_MCP_TOKEN=... && python -m mcd_brief brief`
（对无效 Token，客户端会探测到服务端 HTTP 401 并给出可操作的提示。）

## ❓ FAQ

<details>
<summary><b>必须用 AI 客户端才能用吗？</b></summary>
不用。CLI 模式完全不依赖任何 AI，pip 装好就能跑；AI 客户端 + SKILL.md 只是更自然的对话入口。
</details>

<details>
<summary><b>会自动帮我下单吗？</b></summary>
不会。晨报生成本身是纯只读的；领券、抽奖需要你在对话里明确发起并二次确认。项目刻意不碰下单与支付。
</details>

<details>
<summary><b>Token 会泄露吗？</b></summary>
Token 只从环境变量 <code>MCD_MCP_TOKEN</code> 读取，不落盘、不入库（<code>.env</code> 已在 .gitignore）；
仓库内配置文件只有占位符。CI 里请用 GitHub Secrets。
</details>

<details>
<summary><b>和直接刷麦当劳 APP 有什么区别？</b></summary>
APP 要你自己想起来打开、自己翻入口；晨报主动找你，而且把"券快过期、积分快清零"这类
<strong>静默损失</strong>挑出来报警——这是刷 APP 最容易漏掉的部分。
</details>

<details>
<summary><b>限流怎么办？</b></summary>
官方限制 600 次/分钟/Token。生成一份晨报只调用 6 次，随便用。
</details>

## 🙏 致谢与声明

- 感谢 [麦当劳中国](https://open.mcd.cn/mcp) 开放的 MCP Server 与本次 [程序员创意开发大赛](https://github.com/M-China/mcd-developer-innovation-challenge)
- 本项目为参赛者独立开发的个人工具，**非麦当劳官方产品**；输出仅供参考，
  餐品、价格、活动规则以麦当劳 APP / 门店实时信息为准
- 本项目不代下单、不代支付；领券/抽奖均需用户显式确认

## License

[MIT](./LICENSE)
