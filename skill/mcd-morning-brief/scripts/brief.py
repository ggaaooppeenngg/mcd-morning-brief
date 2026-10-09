#!/usr/bin/env python3
"""麦麦晨报 · 单文件运行时（Agent Skill 内置脚本）。

生成麦当劳活动与优惠晨报（Markdown/纯文本/JSON）。不依赖本仓库其他代码，
只需官方 MCP SDK：pip install "mcp>=1.9"，Token 从环境变量 MCD_MCP_TOKEN 读取。
用法：
    python brief.py                 # 真实数据
    python brief.py --demo          # 内置样例数据离线演示
    python brief.py --format text --days 14
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

MCP_URL = "https://mcp.mcd.cn"
TOKEN_ENV = "MCD_MCP_TOKEN"
BRIEF_TOOLS = [
    "now-time-info",
    "campaign-calendar",
    "available-coupons",
    "query-my-coupons",
    "query-my-account",
    "query-lottery-info",
]
WEEKDAYS = "一二三四五六日"

# ---------------------------------------------------------------- MCP 客户端

try:  # MCP python-sdk 1.x
    from mcp.client.streamable_http import streamablehttp_client as _client_v1
    _SDK_V2 = False
except ImportError:  # 2.x：改名 + headers 移入 http client
    from mcp.client.streamable_http import (
        create_mcp_http_client,
        streamable_http_client as _client_v2,
    )
    _SDK_V2 = True

from contextlib import asynccontextmanager
from mcp import ClientSession


@asynccontextmanager
async def _open_session(token: str, timeout: float = 30.0):
    headers = {"Authorization": f"Bearer {token}"}
    if _SDK_V2:
        http = create_mcp_http_client(headers=headers)
        async with _client_v2(MCP_URL, http_client=http) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    else:
        async with _client_v1(MCP_URL, headers=headers, timeout=timeout) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()
                yield s


def _unwrap(exc):
    if isinstance(exc, BaseExceptionGroup):
        return _unwrap(exc.exceptions[0])
    return exc


def _friendly(exc, token):
    inner, text = _unwrap(exc), str(_unwrap(exc))
    if "401" in text or "unauthorized" in text.lower():
        return RuntimeError("Token 无效或已过期（HTTP 401）：请到 https://open.mcd.cn/mcp 控制台重新复制。")
    if "429" in text or "rate" in text.lower():
        return RuntimeError("触发限流（HTTP 429）：每 Token 每分钟最多 600 次，请稍后再试。")
    if isinstance(inner, (asyncio.TimeoutError, TimeoutError)):
        return RuntimeError("连接麦当劳 MCP 超时，请检查网络。")
    if token:  # SDK 吞掉了状态码，直接探测一次
        try:
            import urllib.error
            import urllib.request
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "mcd-brief", "version": "0.1.0"}}}).encode()
            req = urllib.request.Request(MCP_URL, data=body, method="POST", headers={
                "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = resp.status
            except urllib.error.HTTPError as e:
                status = e.code
            if status == 401:
                return RuntimeError("Token 无效或已过期（HTTP 401）：请到控制台重新复制并更新 MCD_MCP_TOKEN。")
            if status == 403:
                return RuntimeError("服务端拒绝访问（HTTP 403）：请确认 MCD_MCP_TOKEN 已设置。")
            if status == 429:
                return RuntimeError("触发限流（HTTP 429），请稍后再试。")
        except Exception:
            pass
    return RuntimeError(f"调用麦当劳 MCP 失败：{text}")


async def _call_tools(token, tools):
    results = {}
    async with asyncio.timeout(60):
        async with _open_session(token) as session:
            for tool in tools:
                try:
                    res = await session.call_tool(tool, {})
                    payload = None
                    structured = getattr(res, "structuredContent", None)
                    if structured is not None:
                        payload = structured
                    else:
                        raw = "\n".join(b.text for b in (res.content or [])
                                        if getattr(b, "type", "") == "text").strip()
                        if raw:
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError:
                                payload = raw
                    if getattr(res, "isError", False):
                        payload = {"__error__": str(payload)[:200]}
                    results[tool] = payload
                except Exception as exc:
                    results[tool] = {"__error__": str(exc)[:200]}
    return results

# ---------------------------------------------------------------- 容错解析

_MARKERS = ("## Original Response", "Original Response", "原始响应")


def _balanced(text, start=0):
    start = text.find("{", start)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _norm(payload):
    if not isinstance(payload, str):
        return payload
    chunks = [payload.split(m, 1)[1] for m in _MARKERS if m in payload]
    chunks += re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", payload, re.S)
    chunks.append(payload)
    for chunk in chunks:
        blob = _balanced(chunk)
        if blob is not None:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                continue
    return payload


def _pick(data, *keys):
    target = {re.sub(r"[\s_]", "", k).lower() for k in keys}
    stack = [data]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        for k, v in node.items():
            if re.sub(r"[\s_]", "", str(k)).lower() in target and v not in (None, "", []):
                return v
        stack.extend(node.values())
    return None


def _int_of(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"-?\d[\d,，.]*", str(value))
    if m:
        try:
            return int(float(m.group().replace(",", "").replace("，", "")))
        except ValueError:
            return None
    return None


def _date_of(value):
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value if value < 10**12 else value / 1000).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("T", " ").split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


_CAM_HDR = re.compile(r"#{3,4}\s*(\d{4})年(\d{1,2})月(\d{1,2})日[ \t]*([^\n#]*)")
_CAM_TTL = re.compile(r"\*\*活动标题\*\*[：:]\s*([^\\\n]+)")
_CPN_TTL = re.compile(r"优惠券标题[：:]\s*([^\\\n]+)")
_CPN_VAL = re.compile(r"有效期[^：:\n\d]*[：:]?\s*(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}[日]?|\d{1,2}[-./]\d{1,2})")


def campaigns_of(payload, today):
    payload = _norm(payload)
    out = []
    if isinstance(payload, str):
        headers, cursor = list(_CAM_HDR.finditer(payload)), 0
        for tm in _CAM_TTL.finditer(payload):
            owner = None
            while cursor < len(headers) and headers[cursor].start() < tm.start():
                owner = headers[cursor]
                cursor += 1
            if owner and not any(w in (owner[4] or "") for w in ("往期", "已结束")):
                out.append({"title": tm[1].strip(), "start": date(int(owner[1]), int(owner[2]), int(owner[3]))})
    else:
        stack, seen_list = [payload], []
        while stack:
            node = stack.pop()
            if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
                seen_list.extend(node)
            elif isinstance(node, dict):
                stack.extend(node.values())
        for item in seen_list:
            title = _pick(item, "title", "name", "activityName")
            if title:
                out.append({"title": str(title), "start": _date_of(_pick(item, "startDate", "startTime", "beginDate"))})
    seen, uniq = set(), []
    for c in out:
        if c["title"] not in seen:
            seen.add(c["title"])
            uniq.append(c)
    for c in uniq:
        c["status"] = ("进行中" if c["start"] <= today else "即将开始") if c["start"] else "未知"
    return uniq


def coupons_of(payload):
    payload = _norm(payload)
    out = []
    if isinstance(payload, str):
        if "暂无" in payload:
            return out
        blocks = list(_CPN_TTL.finditer(payload))
        for i, m in enumerate(blocks):
            seg = payload[m.end(): blocks[i + 1].start() if i + 1 < len(blocks) else len(payload)]
            v = _CPN_VAL.search(seg)
            out.append({"name": m[1].strip(), "valid": _date_of(v[1]) if v else None})
    else:
        stack, flat = [payload], []
        while stack:
            node = stack.pop()
            if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
                flat.extend(node)
            elif isinstance(node, dict):
                stack.extend(node.values())
        for item in flat:
            name = _pick(item, "couponName", "name", "title")
            if name:
                out.append({"name": str(name), "valid": _date_of(_pick(item, "validEndDate", "expireTime", "endDate"))})
    counts, order = {}, []
    for c in out:
        counts[c["name"]] = counts.get(c["name"], 0) + 1
        if counts[c["name"]] == 1:
            order.append(c)
    for c in order:
        if counts[c["name"]] > 1:
            c["name"] += f" ×{counts[c['name']]}"
    return order


def points_of(payload, today):
    payload = _norm(payload)
    if not isinstance(payload, dict):
        return None
    cur, nxt = _int_of(_pick(payload, "currentMouthExpirePoint", "currentMonthExpirePoint")), \
        _int_of(_pick(payload, "nextMouthExpirePoint", "nextMonthExpirePoint"))
    expiring = cur or nxt
    expiring_date = None
    if today and expiring:
        total = today.month - 1 + (0 if cur else 1)
        year, month = today.year + total // 12, total % 12 + 1
        expiring_date = date(year, 12, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    pts = {
        "available": _int_of(_pick(payload, "availablePoint", "availablePoints", "usablePoints")),
        "total": _int_of(_pick(payload, "accumulativePoint", "totalPoints", "cumulativePoints")),
        "expiring": expiring,
        "expiring_date": expiring_date.isoformat() if expiring_date else None,
    }
    return pts if any(v is not None for v in pts.values()) else None


def lottery_of(payload):
    payload = _norm(payload)
    if not isinstance(payload, dict):
        return None
    status_text = _pick(payload, "activityStatusText")
    free = _int_of(_pick(payload, "availableTimes", "freeDrawTimes"))
    draw_type, draw_point = _pick(payload, "drawTypeText"), _int_of(_pick(payload, "drawPoint"))
    if status_text is None and free is None and _pick(payload, "activityName") is None:
        return None
    cost = None if draw_type == "无" else (f"{draw_point} 积分/次" if draw_point and draw_type and "积分" in str(draw_type) else draw_type)
    return {"name": _pick(payload, "activityName", "name"), "active": status_text in ("进行中", "ongoing"),
            "free": free, "cost": cost}

# ---------------------------------------------------------------- 渲染

def render(brief, fmt="md", window=7):
    today = datetime.strptime(brief["today"], "%Y-%m-%d").date()
    horizon = today + timedelta(days=window)
    campaigns = [c for c in brief["campaigns"]
                 if c["status"] == "进行中" or (c["start"] and c["start"] <= horizon)]
    if fmt == "json":
        return json.dumps(brief, ensure_ascii=False, indent=2)
    if fmt == "text":
        lines = [f"[麦麦晨报 {brief['today']}]", "", f"== 近期活动（未来 {window} 天）=="]
        lines += [f"* [{c['status']}] {c['title']}" for c in campaigns] or ["* 暂无"]
        if brief["claimable"]:
            lines += [f"", f"== 可领优惠券 {len(brief['claimable'])} 张 =="]
            lines += [f"* {c['name']}" for c in brief["claimable"]]
        if brief["points"]:
            p = brief["points"]
            if p["available"] is not None:
                lines += ["", f"== 积分 ==", f"* 可用 {p['available']} 分"]
            if p["expiring"]:
                lines.append(f"* {p['expiring']} 积分即将过期（{p['expiring_date'] or '近期'}前）")
        if brief["lottery"] and brief["lottery"]["active"]:
            lot = brief["lottery"]
            head = f"「{lot['name']}」进行中"
            tail = f"，剩余 {lot['free']} 次免费机会" if lot["free"] else (f"（{lot['cost']}）" if lot["cost"] else "")
            lines += ["", "== 抽奖 ==", f"* {head}{tail}"]
        lines += ["", "-- 数据来自麦当劳 MCP，仅供参考，以麦当劳 APP/门店为准。"]
        return "\n".join(lines)
    wd = WEEKDAYS[today.weekday()]
    lines = [f"## 🌅 麦麦晨报 · {brief['today']} 周{wd}", "",
             f"### 📅 近期活动（未来 {window} 天）"]
    for c in campaigns:
        badge = "🔥 **进行中**" if c["status"] == "进行中" else f"⏰ **{(c['start'] - today).days} 天后开始**"
        span = f"（{c['start'].strftime('%m.%d')} 起）" if c["start"] else ""
        lines.append(f"- {badge} {c['title']}{span}")
    if not campaigns:
        lines.append("- 今日暂无近期活动情报")
    lines.append("")
    if brief["claimable"]:
        lines.append(f"### 🎫 今日可领优惠券（{len(brief['claimable'])} 张）")
        for c in brief["claimable"]:
            until = f"｜有效期至 {c['valid'].strftime('%m-%d')}" if c.get("valid") else ""
            lines.append(f"- 🎟️ **{c['name']}**{until}")
        lines.append("> 💡 回复「领券」可一键领取（需确认）")
        lines.append("")
    expiring = [c for c in brief["my_coupons"]
                if c.get("valid") and today <= c["valid"] <= today + timedelta(days=7)]
    if expiring:
        lines.append(f"### ⌛ 即将过期的券（{len(expiring)} 张）")
        lines += [f"- 🎟️ **{c['name']}**｜有效期至 {c['valid'].strftime('%m-%d')}" for c in expiring]
        lines.append("")
    if brief["points"]:
        p = brief["points"]
        lines.append("### 💰 积分")
        if p["available"] is not None:
            total = f"｜累计 {p['total']:,} 分" if p["total"] is not None else ""
            lines.append(f"- 可用 **{p['available']:,}** 分{total}")
        if p["expiring"]:
            lines.append(f"- ⚠️ {p['expiring']} 积分即将过期（{p['expiring_date'] or '近期'} 前），别浪费啦")
        lines.append("")
    lot = brief["lottery"]
    if lot and lot["active"]:
        if lot["free"]:
            line = f"- 🎁 「{lot['name']}」进行中，你还有 {lot['free']} 次免费抽奖机会"
        elif lot["cost"]:
            line = f"- 🎁 「{lot['name']}」进行中（{lot['cost']}）"
        else:
            line = f"- 🎁 「{lot['name']}」进行中"
        lines += ["### 🎰 抽奖机会", line, ""]
    lines += ["---", "> 数据来自麦当劳 MCP Server，仅供参考；餐品、价格与活动以麦当劳 APP / 门店实时信息为准。"]
    return "\n".join(lines)

# ---------------------------------------------------------------- 入口

DEMO = {
    "campaign-calendar": {"activities": [
        {"activityName": "10.10 麦乐畅享日 · 多款套餐第二份半价", "startDate": "2026-10-10"},
        {"activityName": "国际拉花咖啡周 · M咖啡买一送一", "startDate": "2026-10-11"},
        {"activityName": "会员日 · 麦金卡会员双倍积分", "startDate": "2026-10-13"},
    ]},
    "available-coupons": {"coupons": [
        {"couponName": "早晨加油包", "validEndDate": "2026-10-31"},
        {"couponName": "板烧鸡腿堡买一送一", "validEndDate": "2026-10-12"},
        {"couponName": "麦乐送满 49 减 12", "validEndDate": "2026-10-18"},
    ]},
    "query-my-coupons": {"coupons": [
        {"couponName": "香芋派免费券", "validEndDate": "2026-10-11"},
    ]},
    "query-my-account": {"data": {"availablePoint": "1240", "accumulativePoint": "3580",
                                  "currentMouthExpirePoint": "300", "nextMouthExpirePoint": "0"}},
    "query-lottery-info": {"data": {"activityName": "十月麦麦抽奖季", "activityStatusText": "进行中",
                                    "drawTypeText": "无", "availableTimes": 1}},
}


def main():
    ap = argparse.ArgumentParser(description="麦麦晨报 —— 麦当劳活动与优惠早知道")
    ap.add_argument("--format", choices=["md", "text", "json"], default="md")
    ap.add_argument("--days", type=int, default=7, help="活动预告窗口（天）")
    ap.add_argument("--demo", action="store_true", help="离线演示：内置样例数据")
    args = ap.parse_args()

    if args.demo:
        raw = dict(DEMO)
        raw["now-time-info"] = {"data": {"date": "2026-10-10"}}
    else:
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            sys.exit(f"未找到 Token：请设置环境变量 {TOKEN_ENV}"
                     f"（申请：https://open.mcd.cn/mcp），或用 --demo 离线演示。")
        try:
            raw = asyncio.run(_call_tools(token, BRIEF_TOOLS))
        except BaseException as exc:
            sys.exit(str(_friendly(exc, token)))

    today = _date_of(_pick(raw.get("now-time-info"), "date", "today")) or datetime.now().date()
    brief = {
        "today": today.isoformat(),
        "campaigns": campaigns_of(raw.get("campaign-calendar"), today),
        "claimable": coupons_of(raw.get("available-coupons")),
        "my_coupons": coupons_of(raw.get("query-my-coupons")),
        "points": points_of(raw.get("query-my-account"), today),
        "lottery": lottery_of(raw.get("query-lottery-info")),
    }
    print(render(brief, args.format, args.days))


if __name__ == "__main__":
    main()
