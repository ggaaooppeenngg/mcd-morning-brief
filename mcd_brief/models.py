"""Typed models for the morning brief + tolerant extraction from MCP payloads.

The mcp.mcd.cn tools return LLM-oriented content rather than bare JSON: some
tools embed the original JSON after a "## Original Response" heading
(now-time-info / query-my-account / query-lottery-info), others return pure
Markdown (campaign-calendar / available-coupons / query-my-coupons). Every
extractor therefore (1) tries to pull an embedded JSON object out of a string
payload, (2) falls back to Markdown section parsing, and (3) probes a list of
candidate keys / line patterns. Unknown shapes degrade to "empty section +
recorded error", never a crash.
"""

from __future__ import annotations

import json
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
    cost: str | None = None
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

_ORIGINAL_RESPONSE_MARKERS = ("## Original Response", "Original Response", "原始响应")


def normalize_payload(payload: Json) -> Json:
    """String payloads: pull out the embedded JSON object when one exists."""
    if not isinstance(payload, str):
        return payload
    chunks: list[str] = []
    for marker in _ORIGINAL_RESPONSE_MARKERS:
        if marker in payload:
            chunks.append(payload.split(marker, 1)[1])
    chunks.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", payload, re.S))
    chunks.append(payload)
    for chunk in chunks:
        blob = _balanced_json(chunk)
        if blob is not None:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                continue
    return payload


def _balanced_json(text: str) -> str | None:
    start = text.find("{")
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
                return text[start : i + 1]
    return None


_CAM_HEADER = re.compile(r"#{3,4}\s*(\d{4})年(\d{1,2})月(\d{1,2})日[ \t]*([^\n#]*)")
_CAM_TITLE = re.compile(r"\*\*活动标题\*\*[：:]\s*([^\\\n]+)")
_CPN_TITLE = re.compile(r"优惠券标题[：:]\s*([^\\\n]+)")
_CPN_BENEFIT = re.compile(r"优惠(?:内容|说明|力度|信息)[：:]\s*([^\\\n]+)")
_CPN_VALID = re.compile(r"有效期[^：:\n\d]*[：:]?\s*(\d{4}[-./年]\d{1,2}[-./月]\d{1,2}[日]?|\d{1,2}[-./]\d{1,2})")


def _campaigns_from_markdown(text: str) -> list[Campaign]:
    headers = list(_CAM_HEADER.finditer(text))
    out: list[Campaign] = []
    cursor = 0
    for tm in _CAM_TITLE.finditer(text):
        owner = None  # nearest date heading before this title line
        while cursor < len(headers) and headers[cursor].start() < tm.start():
            owner = headers[cursor]
            cursor += 1
        if owner is None:
            continue
        year, month, day = int(owner[1]), int(owner[2]), int(owner[3])
        label = (owner[4] or "").strip()
        if "往期" in label or "已结束" in label:
            continue
        out.append(Campaign(
            title=tm[1].strip(), start=date(year, month, day), end=None,
            raw={"section": label},
        ))
    return out


def _coupons_from_markdown(text: str) -> list[Coupon]:
    titles = list(_CPN_TITLE.finditer(text))
    out: list[Coupon] = []
    for i, m in enumerate(titles):
        segment = text[m.end() : titles[i + 1].start() if i + 1 < len(titles) else len(text)]
        benefit = _CPN_BENEFIT.search(segment)
        valid = _CPN_VALID.search(segment)
        out.append(Coupon(
            name=m[1].strip(),
            benefit=benefit[1].strip() if benefit else None,
            valid_until=_parse_date(valid[1]) if valid else None,
            raw={"segment": segment[:300]},
        ))
    return out


def extract_campaigns(payload: Json) -> list[Campaign]:
    payload = normalize_payload(payload)
    if isinstance(payload, str):
        return _campaigns_from_markdown(payload)
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
    payload = normalize_payload(payload)
    if isinstance(payload, str):
        return _coupons_from_markdown(payload)
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


def _month_end(today: date, plus_months: int) -> date:
    total = today.month - 1 + plus_months
    year, month = today.year + total // 12, total % 12 + 1
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def extract_points(payload: Json, today: date | None = None) -> PointsInfo | None:
    payload = normalize_payload(payload)
    if not isinstance(payload, dict):
        return None
    expiring = _int(payload, "currentMouthExpirePoint", "currentMonthExpirePoint",
                    "expiringPoints", "soonExpirePoints", "aboutToExpirePoints", "willExpirePoints")
    expiring_next = _int(payload, "nextMouthExpirePoint", "nextMonthExpirePoint")
    expiring_date = None
    if today is not None:
        if expiring:
            expiring_date = _month_end(today, 0)
        elif expiring_next:
            expiring_date = _month_end(today, 1)
    info = PointsInfo(
        available=_int(payload, "availablePoint", "availablePoints", "usablePoints", "canUsePoints", "points"),
        total=_int(payload, "accumulativePoint", "totalPoints", "cumulativePoints", "total"),
        frozen=_int(payload, "frozenPoint", "frozenPoints", "freezePoints", "frozen"),
        expiring=expiring if expiring else expiring_next,
        expiring_date=expiring_date,
        raw=payload,
    )
    return info if any(v is not None for k, v in vars(info).items() if k != "raw") else None


_ACTIVE_LABELS = ("进行中", "ongoing")


def extract_lottery(payload: Json) -> LotteryInfo | None:
    payload = normalize_payload(payload)
    if not isinstance(payload, dict):
        return None
    status_text = _text(payload, "activityStatusText")
    status = _lookup(payload, "status")
    if isinstance(status, dict):  # e.g. {"code": "SUCCESS", "message": ...}
        status = _text(status, "code")
    active = (status_text in _ACTIVE_LABELS
              or (status_text is None and (status in _ACTIVE_LABELS or status in ("ONGOING", "GOING", "1"))))
    name = _text(payload, "activityName", "name", "title")
    free = _int(payload, "availableTimes", "freeDrawTimes", "freeTimes", "remainFreeTimes", "userFreeTimes")
    draw_type = _text(payload, "drawTypeText")
    draw_point = _int(payload, "drawPoint")
    if status_text is None and status is None and free is None and name is None:
        return None
    if draw_type == "无":
        cost = None
    elif draw_point and draw_type and "积分" in draw_type:
        cost = f"{draw_point} 积分/次"
    else:
        cost = draw_type
    return LotteryInfo(
        name=name,
        active=active,
        free_draws=free,
        cost=cost,
        raw=payload,
    )


def tool_error(payload: Json) -> str | None:
    if isinstance(payload, dict) and ERROR_KEY in payload:
        return str(payload[ERROR_KEY])
    return None
