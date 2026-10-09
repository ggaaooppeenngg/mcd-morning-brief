"""Aggregate McDonald's MCP tool results into one :class:`Brief`."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .client import McdClient
from .models import (
    Brief,
    Coupon,
    LotteryInfo,
    PointsInfo,
    Campaign,
    extract_campaigns,
    extract_coupons,
    extract_lottery,
    extract_points,
    tool_error,
)

BRIEF_TOOLS: list[tuple[str, dict[str, Any] | None]] = [
    ("now-time-info", None),
    ("campaign-calendar", None),
    ("available-coupons", None),
    ("query-my-coupons", None),
    ("query-my-account", None),
    ("query-lottery-info", None),
]


async def build_brief(client: McdClient, *, window_days: int = 7, today: date | None = None) -> Brief:
    """Call every tool the brief needs over one session, then assemble."""
    data = await client.call_many(BRIEF_TOOLS)
    raw = {tool: data[(tool, args or {})] for tool, args in BRIEF_TOOLS}
    return brief_from_raw(raw, window_days=window_days, today=today)


def brief_from_raw(
    raw: dict[str, Any], *, window_days: int = 7, today: date | None = None
) -> Brief:
    today = today or _today_from(raw.get("now-time-info")) or datetime.now().date()
    brief = Brief(today=today)

    for tool, payload in raw.items():
        err = tool_error(payload)
        if err:
            brief.errors.append(f"{tool}: {err}")

    brief.campaigns = extract_campaigns(raw.get("campaign-calendar"))
    brief.claimable = extract_coupons(raw.get("available-coupons"))
    brief.my_coupons = extract_coupons(raw.get("query-my-coupons"))
    brief.points = extract_points(raw.get("query-my-account"))
    brief.lottery = extract_lottery(raw.get("query-lottery-info"))
    brief.window_days = window_days
    return brief


def _today_from(payload: Any) -> date | None:
    if isinstance(payload, dict):
        for key in ("date", "today", "currentDate", "time", "now", "datetime"):
            value = payload.get(key)
            if isinstance(value, str) and len(value) >= 10:
                from .models import _parse_date

                parsed = _parse_date(value[:10])
                if parsed:
                    return parsed
    return None


def expiring_coupons(brief: Brief, within_days: int = 7) -> list[Coupon]:
    """My coupons that expire within `within_days`, soonest first."""
    horizon = brief.today + timedelta(days=within_days)
    out = []
    for c in brief.my_coupons:
        if c.valid_until is not None and brief.today <= c.valid_until <= horizon:
            out.append(c)
    out.sort(key=lambda c: c.valid_until or brief.today)
    return out


def points_warning(brief: Brief, within_days: int = 7) -> str | None:
    """Human sentence for expiring points, if any within the window."""
    if not brief.points or not brief.points.expiring:
        return None
    when = brief.points.expiring_date
    if when is None or brief.today <= when <= brief.today + timedelta(days=30):
        suffix = f"（{when.isoformat()} 前）" if when else ""
        return f"⚠️ {brief.points.expiring} 积分即将过期{suffix}，别浪费啦"
    return None


def lottery_line(brief: Brief) -> str | None:
    lot = brief.lottery
    if not lot or not lot.active:
        return None
    name = lot.name or "积分抽奖活动"
    if lot.free_draws:
        return f"🎁 「{name}」进行中，你还有 {lot.free_draws} 次免费抽奖机会"
    return f"🎁 「{name}」进行中"


def sort_campaigns(brief: Brief, campaigns: list[Campaign]) -> list[Campaign]:
    """Ongoing first (by nearest end), then upcoming (by nearest start)."""

    def key(c: Campaign):
        status, until = c.status_asof(brief.today)
        ongoing = status == "进行中"
        return (
            0 if ongoing else 1,
            (c.end - brief.today).days if ongoing and c.end else 9999,
            (c.start - brief.today).days if not ongoing and c.start else 9999,
        )

    return sorted(campaigns, key=key)


__all__ = [
    "BRIEF_TOOLS",
    "Brief",
    "build_brief",
    "brief_from_raw",
    "expiring_coupons",
    "lottery_line",
    "points_warning",
    "sort_campaigns",
    "LotteryInfo",
    "PointsInfo",
]
