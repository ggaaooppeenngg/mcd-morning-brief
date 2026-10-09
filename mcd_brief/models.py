"""Typed models for the morning brief + tolerant extraction from MCP payloads.

The MCP tools' exact response schemas are not publicly documented, so every
extractor probes a list of candidate keys (case-insensitive, one nesting level
deep). Unknown shapes degrade to "empty section + recorded error", never a crash.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

Json = dict[str, Any] | list[Any] | str | int | float | bool | None

ERROR_KEY = "__error__"


@dataclass
class Campaign:
    title: str
    start: date | None
    end: date | None
    raw: Json = None

    def status_asof(self, today: date) -> tuple[str, int | None]:
        """Return (label, days_until_start) — days_until_start is None for ongoing."""
        if self.start is None and self.end is None:
            return ("未知", None)
        if self.start and self.start > today:
            return ("即将开始", (self.start - today).days)
        if self.end is None or self.end >= today:
            return ("进行中", None)
        return ("已结束", None)


@dataclass
class Coupon:
    name: str
    benefit: str | None = None
    valid_until: date | None = None
    raw: Json = None


@dataclass
class PointsInfo:
    available: int | None = None
    total: int | None = None
    frozen: int | None = None
    expiring: int | None = None
    expiring_date: date | None = None
    raw: Json = None


@dataclass
class LotteryInfo:
    name: str | None = None
    active: bool = False
    free_draws: int | None = None
    raw: Json = None


@dataclass
class Brief:
    today: date
    window_days: int = 7
    campaigns: list[Campaign] = field(default_factory=list)
    claimable: list[Coupon] = field(default_factory=list)
    my_coupons: list[Coupon] = field(default_factory=list)
    points: PointsInfo | None = None
    lottery: LotteryInfo | None = None
    errors: list[str] = field(default_factory=list)

    def upcoming(self, days: int) -> list[Campaign]:
        """Ongoing campaigns, plus campaigns starting within `days` days."""
        horizon = self.today + timedelta(days=days)
        out = []
        for c in self.campaigns:
            status, until = c.status_asof(self.today)
            if status == "进行中":
                out.append(c)
            elif status == "即将开始" and c.start is not None and c.start <= horizon:
                out.append(c)
        return out


# ---------------------------------------------------------------- extraction

def find_list(payload: Json, *container_keys: str) -> list[Json]:
    """Locate the main list in a payload: a bare list, or a list under any candidate key."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in container_keys:
            value = _lookup(payload, key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        for value in payload.values():  # last resort: first list of dicts anywhere
            if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
                return list(value)
    return []


def _lookup(data: Json, key: str, _depth: int = 0) -> Any:
    """Case/space-insensitive key lookup, one nesting level deep."""
    if not isinstance(data, dict) or _depth > 1:
        return None
    target = re.sub(r"[\s_]", "", key).lower()
    for k, v in data.items():
        if re.sub(r"[\s_]", "", str(k)).lower() == target:
            return v
    for v in data.values():
        found = _lookup(v, key, _depth + 1)
        if found is not None:
            return found
    return None


def _text(data: Json, *keys: str) -> str | None:
    for key in keys:
        value = _lookup(data, key)
        if value not in (None, "", []):
            return str(value)
    return None


def _int(data: Json, *keys: str) -> int | None:
    for key in keys:
        value = _lookup(data, key)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        m = re.search(r"-?\d[\d,，.]*", str(value))
        if m:
            try:
                return int(float(m.group().replace(",", "").replace("，", "")))
            except ValueError:
                continue
    return None


def _date(data: Json, *keys: str) -> date | None:
    for key in keys:
        value = _lookup(data, key)
        parsed = _parse_date(value)
        if parsed:
            return parsed
    return None


def _parse_date(value: Any) -> date | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    if isinstance(value, (int, float)):
        ts = value if value < 10**12 else value / 1000  # s vs ms epoch
        try:
            return datetime.fromtimestamp(ts).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d",
                "%Y年%m月%d日", "%m-%d", "%m.%d", "%Y%m%d"):
        try:
            dt = datetime.strptime(text.split("+")[0].strip(), fmt)
            if fmt in ("%m-%d", "%m.%d"):
                dt = dt.replace(year=datetime.now().year)
            return dt.date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return None


# ------------------------------------------------------------- section builders

def extract_campaigns(payload: Json) -> list[Campaign]:
    items = find_list(payload, "activities", "campaigns", "calendarList", "list", "data", "records")
    out = []
    for item in items:
        title = _text(item, "title", "name", "activityName", "campaignName", "description")
        if not title:
            continue
        out.append(Campaign(
            title=title,
            start=_date(item, "startDate", "startTime", "beginDate", "beginTime", "start", "activityStartDate"),
            end=_date(item, "endDate", "endTime", "finishDate", "end", "activityEndDate"),
            raw=item,
        ))
    return out


def extract_coupons(payload: Json) -> list[Coupon]:
    items = find_list(payload, "coupons", "couponList", "list", "data", "records", "result")
    out = []
    for item in items:
        name = _text(item, "couponName", "name", "title")
        if not name:
            continue
        out.append(Coupon(
            name=name,
            benefit=_text(item, "benefit", "discount", "discountDesc", "amount", "preferential", "subTitle", "description"),
            valid_until=_date(item, "validEndDate", "validEndTime", "expireTime", "expireDate", "endDate", "endTime"),
            raw=item,
        ))
    return out


def extract_points(payload: Json) -> PointsInfo | None:
    if not isinstance(payload, dict):
        return None
    info = PointsInfo(
        available=_int(payload, "availablePoints", "usablePoints", "canUsePoints", "points", "available"),
        total=_int(payload, "totalPoints", "cumulativePoints", "total"),
        frozen=_int(payload, "frozenPoints", "freezePoints", "frozen"),
        expiring=_int(payload, "expiringPoints", "soonExpirePoints", "aboutToExpirePoints", "willExpirePoints"),
        expiring_date=_date(payload, "expiringDate", "expireDate", "latestExpireTime", "soonExpireTime"),
        raw=payload,
    )
    return info if any(v is not None for k, v in vars(info).items() if k != "raw") else None


def extract_lottery(payload: Json) -> LotteryInfo | None:
    if not isinstance(payload, dict):
        return None
    status = _text(payload, "activityStatus", "status", "state")
    active = status in ("ONGOING", "GOING", "ACTIVITY_ONGOING", "进行中", "1") or _lookup(payload, "ongoing") is True
    free = _int(payload, "freeDrawTimes", "freeTimes", "remainFreeTimes", "userFreeTimes", "leftFreeTimes")
    if status is None and free is None and _text(payload, "activityName", "name", "title") is None:
        return None
    return LotteryInfo(
        name=_text(payload, "activityName", "name", "title"),
        active=active,
        free_draws=free,
        raw=payload,
    )


def tool_error(payload: Json) -> str | None:
    if isinstance(payload, dict) and ERROR_KEY in payload:
        return str(payload[ERROR_KEY])
    return None
