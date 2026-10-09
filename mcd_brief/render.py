"""Render a :class:`Brief` as a morning-brief (Markdown / text / JSON / iCal)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .aggregate import expiring_coupons, lottery_line, points_warning, sort_campaigns
from .models import Brief, Campaign, Coupon

WEEKDAYS = "一二三四五六日"

_EMOJI_RE = re.compile(
    "[\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]"
)


def _de_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def _header(brief: Brief) -> str:
    wd = WEEKDAYS[brief.today.weekday()]
    return f"## 🌅 麦麦晨报 · {brief.today.isoformat()} 周{wd}"


def _campaign_line(brief: Brief, c: Campaign) -> str:
    status, until = c.status_asof(brief.today)
    span = ""
    if c.start and c.end:
        span = f"（{c.start.strftime('%m.%d')} ~ {c.end.strftime('%m.%d')}）"
    elif c.start:
        span = f"（{c.start.strftime('%m.%d')} 起）"
    if status == "即将开始" and until is not None:
        badge = f"⏰ **{until} 天后开始**" if until else "⏰ **今天开始**"
    elif status == "进行中":
        badge = "🔥 **进行中**"
    else:
        badge = status
    return f"- {badge} {c.title}{span}"


def _coupon_line(c: Coupon) -> str:
    parts = [f"🎟️ **{c.name}**"]
    if c.benefit:
        parts.append(c.benefit)
    if c.valid_until:
        parts.append(f"有效期至 {c.valid_until.strftime('%m-%d')}")
    return "- " + "｜".join(parts)


def to_markdown(brief: Brief, *, window_days: int | None = None) -> str:
    window = window_days or brief.window_days
    lines: list[str] = [_header(brief), ""]

    campaigns = sort_campaigns(brief, brief.upcoming(window))
    lines.append(f"### 📅 近期活动（未来 {window} 天）")
    if campaigns:
        lines += [_campaign_line(brief, c) for c in campaigns]
    else:
        lines.append("- 今日暂无近期活动情报")
    lines.append("")

    if brief.claimable:
        lines.append(f"### 🎫 今日可领优惠券（{len(brief.claimable)} 张）")
        lines += [_coupon_line(c) for c in brief.claimable]
        lines.append("> 💡 回复「领券」或运行 `mcd-brief coupons --claim` 可一键领取")
        lines.append("")

    expiring = expiring_coupons(brief)
    if expiring:
        lines.append(f"### ⌛ 即将过期的券（{len(expiring)} 张）")
        lines += [_coupon_line(c) for c in expiring]
        lines.append("")

    if brief.points:
        lines.append("### 💰 积分")
        bits = []
        if brief.points.available is not None:
            bits.append(f"可用 **{brief.points.available:,}** 分")
        if brief.points.total is not None:
            bits.append(f"累计 {brief.points.total:,} 分")
        if bits:
            lines.append("- " + "｜".join(bits))
        warn = points_warning(brief)
        if warn:
            lines.append(f"- {warn}")
        lines.append("")

    line = lottery_line(brief)
    if line:
        lines.append("### 🎰 抽奖机会")
        lines.append(f"- {line}")
        lines.append("")

    if brief.errors:
        lines.append("### ⚠️ 数据源告警")
        lines += [f"- `{e}`" for e in brief.errors]
        lines.append("")

    lines.append("---")
    lines.append("> 数据来自麦当劳 MCP Server，仅供参考；餐品、价格与活动以麦当劳 APP / 门店实时信息为准。")
    return "\n".join(lines)


def to_text(brief: Brief, *, window_days: int | None = None) -> str:
    """Emoji-free, forward-friendly plain text (WeChat push / TTS etc.)."""
    window = window_days or brief.window_days
    fmt = "%Y-%m-%d (%a)"
    out = [f"[麦麦晨报 {brief.today.strftime(fmt)}]", ""]

    out.append(f"== 近期活动（未来 {window} 天）==")
    campaigns = sort_campaigns(brief, brief.upcoming(window))
    if campaigns:
        for c in campaigns:
            status, until = c.status_asof(brief.today)
            when = f"{until}天后开始" if status == "即将开始" and until is not None else status
            out.append(f"* [{when}] {c.title}")
    else:
        out.append("* 暂无")

    if brief.claimable:
        out += ["", f"== 可领优惠券 {len(brief.claimable)} 张 =="]
        out += [f"* {c.name}" + (f"（{c.benefit}）" if c.benefit else "") for c in brief.claimable]

    expiring = expiring_coupons(brief)
    if expiring:
        out += ["", "== 即将过期的券 =="]
        out += [f"* {c.name}（{c.valid_until} 到期）" for c in expiring]

    if brief.points:
        out += ["", "== 积分 =="]
        if brief.points.available is not None:
            out.append(f"* 可用 {brief.points.available} 分")
        warn = points_warning(brief)
        if warn:
            out.append(f"* {warn}")

    line = lottery_line(brief)
    if line:
        out += ["", "== 抽奖 ==", f"* {line}"]

    out += ["", "-- 数据来自麦当劳 MCP，仅供参考，以麦当劳 APP/门店为准。"]
    return _de_emoji("\n".join(out))


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def _strip_raw(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("raw", None)
        for value in node.values():
            _strip_raw(value)
    elif isinstance(node, list):
        for value in node:
            _strip_raw(value)


def to_json(brief: Brief, *, window_days: int | None = None, include_raw: bool = False) -> str:
    data = _jsonable(brief)
    data["upcoming_campaigns"] = [
        _jsonable(c) for c in sort_campaigns(brief, brief.upcoming(window_days or brief.window_days))
    ]
    if not include_raw:
        _strip_raw(data)
    return json.dumps(data, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------- iCal

def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545 §3.1: content lines SHOULD NOT be longer than 75 octets."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    out, cur = [], b""
    for ch in line:
        piece = ch.encode("utf-8")
        if len(cur) + len(piece) > 72:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += piece
    if cur.strip():
        out.append(cur.decode("utf-8"))
    return out


def to_ics(brief: Brief, *, calendar_name: str = "麦麦活动日历") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//mcd-morning-brief//CN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    for c in brief.campaigns:
        if c.start is None:
            continue
        end_exclusive = (c.end + timedelta(days=1)) if c.end else (c.start + timedelta(days=1))
        digest = hashlib.md5(f"{c.title}{c.start}{c.end}".encode("utf-8")).hexdigest()[:12]
        status, _ = c.status_asof(brief.today)
        desc = f"状态：{status}。来自麦麦晨报（麦当劳 MCP activity）。"
        lines += [
            "BEGIN:VEVENT",
            f"UID:mcd-brief-{digest}@mcd-morning-brief",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{c.start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape('🍔 ' + c.title)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold(line))
    return "\r\n".join(folded) + "\r\n"
