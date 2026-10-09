# mcp.mcd.cn 工具真实返回格式（2026-10 实测）

工具返回**面向 LLM 的内容**，不是裸 JSON。三类形态：

## 形态 1：说明 + 内嵌 JSON（now-time-info / query-my-account / query-lottery-info）

先给一段 "## Response Structure" 字段说明，原始数据在 **"## Original Response"**
小节之后，是一行标准 JSON，`data` 字段才是业务数据：

```
# API Response Information
...
## Original Response

{"success":true,"code":200,"data":{"availablePoint":"111", ...}}
```

### now-time-info → data

| 字段 | 说明 |
|---|---|
| `date` | `yyyy-MM-dd`，晨报用它锚定"今天" |
| `datetime` / `formatted` | ISO / 可读格式 |
| `dayOfWeek` | `FRIDAY` 等英文星期 |

### query-my-account → data（注意：值是字符串，可能带小数点）

| 字段 | 说明 |
|---|---|
| `availablePoint` | 可用积分 |
| `accumulativePoint` | 累计积分 |
| `currentMouthExpirePoint` | **本月将过期积分**（麦当劳原文拼作 Mouth） |
| `nextMouthExpirePoint` | 下月将过期积分 |
| `frozenPoint` | 冻结积分 |

过期日期工具不直接给：`currentMouthExpirePoint > 0` 视为当月末到期，
否则看 `nextMouthExpirePoint`（下月末）。

### query-lottery-info → data

| 字段 | 说明 |
|---|---|
| `activityName` / `activityStatusText` | 活动名 / 状态（未开始·进行中·已结束） |
| `drawTypeText` | 消耗规则：无 / 消耗积分抽奖 / 消耗任务完成次数 / 先次数后积分 |
| `drawPoint` | 单次消耗积分 |
| `availableTimes` | 剩余可抽次数（消耗次数类才有） |
| `status` | **是对象** `{"code":"SUCCESS"}`，别当字符串处理 |

## 形态 2：纯 Markdown 分节（campaign-calendar）

```
### 当前时间：2026-10-09 15:25:50
### 活动列表：
#### 2026年10月7日 往期回顾
#### 2026年10月9日 今日
-   **活动标题**：超值9.9元早餐两件套陪你开工啦
    **活动内容介绍**：10月8日至10月21日 …
#### 2026年10月10日
-   **活动标题**：…
```

要点：`#### YYYY年M月D日 [今日|往期回顾|空]` 为日期节；"往期回顾/已结束"节的
活动直接跳过；同一活动会出现在它运行期间的**每一天**的节里（按标题去重，
保留最早日期，当天节即"进行中"）。

## 形态 3：纯 Markdown 分块（available-coupons / query-my-coupons）

```
### 麦麦省优惠券列表：
- 优惠券标题：麦旋风任选 \
  状态：可领取 \
  优惠券图片：\
    <img src="https://img.mcd.cn/...">
```

要点：块以 `优惠券标题：` 开始，反斜杠 `\` 是换行续接；可出现
`状态：可领取`、`优惠内容：`、`有效期至：2026-10-21` 等行；
`query-my-coupons` 空时返回 `# 您的优惠券列表\n\n暂无可用优惠券`。

## 错误与限流

| 现象 | 含义 | 处理 |
|---|---|---|
| HTTP 401 | Token 无效/过期 | 回 open.mcd.cn/mcp 控制台重新复制 |
| HTTP 403 | 未携带/空 Token | 检查 Authorization 配置 |
| HTTP 429 | 超 600 次/分钟 | 稍后再试 |
| 工具返回 `{"__error__": ...}` | 单工具失败 | 该栏目写"暂未获取到"，不要中断整份晨报 |
