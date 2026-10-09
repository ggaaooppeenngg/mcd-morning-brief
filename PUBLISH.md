# 发布与报名指南（PUBLISH）

> 本项目代码与文档已就绪并通过本地测试。按下面步骤即可完成「发布 → 报名」。
> 全程约 10 分钟，其中需要你本人操作的只有：登录 GitHub、扫码/登录麦当劳开放平台、点几次网页按钮。

## 0. 发布前检查清单

- [x] `README.md`（项目介绍/安装/示例/目标用户）
- [x] `CONTEST_DECLARATION.md`（与官方仓库逐字节一致，**不可改动**）
- [x] `MCP_INTEGRATION.md`（Server/Tool/调用流程/业务价值）
- [x] `mcp-config.example.json`（仅环境变量占位符，无真实 Token）
- [x] 源代码（`mcd_brief/`、`skill/`、`tests/`、`examples/`）
- [x] 本地测试通过：`pytest`（16 用例）+ `--demo` 冒烟
- [ ] 确认仓库中无真实 Token：`grep -r "Bearer" --include="*.json" --include="*.md" .`（应只有占位符与协议示例）

## 1. 拿到你的麦当劳 MCP Token（可选但强烈建议）

1. 打开 <https://open.mcd.cn/mcp> → 右上角【登录】→ 手机号验证
2. 右上角【控制台】→【激活】→ 同意协议 → 复制 Token
3. 本地验证（不要把 Token 发到任何聊天/ issue 里）：
   ```bash
   export MCD_MCP_TOKEN=你的Token    # Windows PowerShell: $env:MCD_MCP_TOKEN="你的Token"
   python -m mcd_brief brief
   ```

## 2. 创建 GitHub 公开仓库

**注意：报名条件要求仓库创建时间在 2025-12-25 ~ 2026-10-25 之间，新建仓库天然满足。**

方式 A（网页，最简单）：
1. 登录 GitHub → New repository
2. Repository name：`mcd-morning-brief`
3. 选 **Public**，**不要**勾选任何初始化选项（README/.gitignore/license 都不要加）
4. Create repository

方式 B（CLI，装了 gh 的话）：
```bash
gh repo create mcd-morning-brief --public --source=. --push
```

## 3. 推送代码

```bash
cd mcd-morning-brief
git add -A
git commit -m "feat: 麦麦晨报 v0.1.0 —— 麦当劳活动与优惠晨报（MCP + Agent Skill + CLI）"
git branch -M main
git remote add origin https://github.com/<你的用户名>/mcd-morning-brief.git
git push -u origin main
```

> 推送时 Git Credential Manager 会弹出浏览器授权，登录你的 GitHub 账号即可。
> 提交身份请先配置（否则提交人显示不对）：
> ```bash
> git config --global user.name "你的GitHub用户名"
> git config --global user.email "你的GitHub用户名@users.noreply.github.com"
> ```

## 4. 提交报名 Issue（在活动仓库）

打开 <https://github.com/M-China/mcd-developer-innovation-challenge/issues> → New issue，
标题和正文按下面模板填（把仓库地址换成你的）：

**Issue 标题：**

```text
【参赛申请】麦麦晨报 —— 麦当劳活动与优惠早知道，可接入个人 Agent 晨报
```

**Issue 正文：**

```text
【参赛申请】
项目名称：麦麦晨报（mcd-morning-brief）
项目地址：https://github.com/<你的用户名>/mcd-morning-brief
项目简介：把麦当劳的活动日历、可领优惠券、即将过期的券与积分、抽奖机会，聚合成一条 30 秒读完的晨报，可直接作为个人 Agent 每日晨报的固定栏目。提供通用 Agent Skill（SKILL.md，适配 WorkBuddy/Cursor/Trae/Cherry Studio 等）与独立 Python CLI（支持 Markdown/纯文本/JSON/iCal 日历导出、crontab 定时推送），领券等写操作均需用户确认，纯只读生成晨报。
```

提交后等待系统在 Issue 下回复「报名成功」。若回复失败原因，按提示修改后重新提交 Issue 即可。

## 5. 报名成功后的涨 Star 建议（合规玩法）

- **时间就是 Star**：报名越早，被 Issue 列表曝光越久（榜单按 Star 排序，10-26 00:00 定榜）
- README 是转化率关键：已内置 demo 输出、三种接入方式、FAQ；可以再补一张晨报截图/GIF
- 分享到开发者社区：V2EX（分享创造节点）、掘金、即刻、小红书"麦门"话题、个人 Agent/晨报玩家社群
- 在晨报成品（你的推送/博客）里附仓库链接，形成自传播
- ⚠️ **切勿刷 Star / 互刷交换**：规则明确禁止操纵 Star 数据，违者取消资格

## 6. 时间线

| 事项 | 截止 |
|---|---|
| 报名及 Star 排名 | 2026-10-25 23:59（北京时间） |
| 定榜（以此时 Star 为准） | 2026-10-26 00:00 |
| 奖品信息提交 | 2026-11-14 |
