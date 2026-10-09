"""Offline tests for aggregation logic (no network, no token needed)."""

from datetime import date

from mcd_brief.aggregate import (
    brief_from_raw,
    expiring_coupons,
    lottery_line,
    points_warning,
    sort_campaigns,
)
from mcd_brief.models import (
    extract_campaigns,
    extract_coupons,
    extract_lottery,
    extract_points,
    normalize_payload,
)

import json
from importlib import resources


TODAY = date(2026, 10, 10)


def demo_payload() -> dict:
    return json.loads(
        resources.files("mcd_brief").joinpath("sample-data.json").read_text(encoding="utf-8")
    )


def make_brief(**kwargs):
    return brief_from_raw(demo_payload(), today=TODAY, **kwargs)


def test_brief_assembles_all_sections():
    brief = make_brief()
    assert brief.today == TODAY
    assert len(brief.campaigns) == 4
    assert len(brief.claimable) == 3
    assert len(brief.my_coupons) == 2
    assert brief.points is not None and brief.points.available == 1240
    assert brief.lottery is not None and brief.lottery.active
    assert brief.errors == []


def test_upcoming_window_filters_and_labels():
    brief = make_brief()
    upcoming = brief.upcoming(7)
    titles = [c.title for c in upcoming]
    # within window: ongoing today, starts tomorrow, in 3 days
    assert "10.10 麦乐畅享日 · 多款套餐第二份半价" in titles
    assert "国际拉花咖啡周 · M咖啡买一送一" in titles
    assert "会员日 · 麦金卡会员双倍积分" in titles
    # outside window / past excluded
    assert "万圣节怪怪堡上新" not in titles
    assert "国庆黄金周 · 桶半价" not in titles

    status, until = next(
        (c.status_asof(TODAY) for c in upcoming if "会员日" in c.title)
    )
    assert status == "即将开始" and until == 3


def test_sort_campaigns_ongoing_first():
    brief = make_brief()
    ordered = sort_campaigns(brief, brief.upcoming(7))
    statuses = [c.status_asof(TODAY)[0] for c in ordered]
    assert "已结束" not in statuses
    assert statuses[0] == "进行中"  # today's campaign ends first
    # among upcoming, nearest start first
    upcoming_only = [c for c in ordered if c.status_asof(TODAY)[0] == "即将开始"]
    days = [c.start and (c.start - TODAY).days for c in upcoming_only]
    assert days == sorted(days)


def test_expiring_coupons_within_7_days():
    brief = make_brief()
    expiring = expiring_coupons(brief)
    names = [c.name for c in expiring]
    assert "派 Day 派对券 · 香芋派免费券" in names  # expires tomorrow
    assert "麦旋风 5 元券" not in names  # 10 days away


def test_points_warning_sentence():
    brief = make_brief()
    warn = points_warning(brief)
    assert warn is not None and "300" in warn and "2026-10-31" in warn


def test_lottery_line_with_free_draws():
    brief = make_brief()
    line = lottery_line(brief)
    assert line is not None and "1 次" in line and "十月麦麦抽奖季" in line


def test_tool_error_is_recorded_not_fatal():
    payload = demo_payload()
    payload["query-my-account"] = {"__error__": "HTTP 500"}
    brief = brief_from_raw(payload, today=TODAY)
    assert any("query-my-account" in e for e in brief.errors)
    assert brief.points is None
    assert len(brief.claimable) == 3  # other sections survive


def test_multi_day_campaign_and_duplicate_coupons_are_merged():
    payload = demo_payload()
    payload["campaign-calendar"] = (
        "#### 2026年10月10日 今日\n\n-   **活动标题**：韩式蘸酱上新\n\n"
        "#### 2026年10月11日\n\n-   **活动标题**：韩式蘸酱上新\n\n"
        "#### 2026年10月12日\n\n-   **活动标题**：另一个活动\n"
    )
    payload["available-coupons"] = (
        "### 麦麦省优惠券列表：\n"
        "- 优惠券标题：薯薯任选 \\\n  状态：可领取\n"
        "- 优惠券标题：薯薯任选 \\\n  状态：可领取\n"
        "- 优惠券标题：薯薯任选 \\\n  状态：可领取\n"
        "- 优惠券标题：免费脆薯饼 \\\n  状态：可领取\n"
    )
    brief = brief_from_raw(payload, today=TODAY)
    titles = [c.title for c in brief.campaigns]
    assert titles == ["韩式蘸酱上新", "另一个活动"]  # multi-day listing merged, earliest kept
    assert brief.campaigns[0].start == date(2026, 10, 10)
    names = [c.name for c in brief.claimable]
    assert names == ["薯薯任选 ×3", "免费脆薯饼"]


# ------------------------------------------------------------ extractors

def test_extract_campaigns_tolerates_bare_list_and_alt_keys():
    payload = [{"activityName": "A", "startTime": "2026.10.01", "endTime": "2026.10.02"}]
    campaigns = extract_campaigns(payload)
    assert len(campaigns) == 1
    assert campaigns[0].start == date(2026, 10, 1)
    assert campaigns[0].end == date(2026, 10, 2)


def test_extract_coupons_chinese_date_and_amount_text():
    coupons = extract_coupons(
        {"couponList": [{"couponName": "X", "discount": "立减6元", "validEndDate": "2026年10月31日"}]}
    )
    assert coupons[0].valid_until == date(2026, 10, 31)
    assert "6" in coupons[0].benefit


def test_extract_points_handles_commas_and_missing():
    pts = extract_points({"availablePoints": "1,240"}, today=TODAY)
    assert pts.available == 1240
    assert extract_points({"foo": 1}) is None


def test_extract_points_real_mcd_fields_with_month_end_expiry():
    """Real field names observed from mcp.mcd.cn (currentMouthExpirePoint etc.)."""
    payload = {
        "success": True, "code": 200,
        "data": {
            "availablePoint": "111", "accumulativePoint": "4862.5",
            "currentMouthExpirePoint": "0", "nextMouthExpirePoint": "300",
            "frozenPoint": "0",
        },
    }
    pts = extract_points(payload, today=TODAY)
    assert pts.available == 111
    assert pts.total == 4862  # float string truncates to int
    assert pts.expiring == 300  # falls back to next-month when current-month is 0
    assert pts.expiring_date == date(2026, 11, 30)


def test_extract_points_expiring_this_month():
    pts = extract_points({"availablePoint": "10", "currentMouthExpirePoint": "300"}, today=TODAY)
    assert pts.expiring == 300
    assert pts.expiring_date == date(2026, 10, 31)


def test_extract_lottery_status_variants():
    assert extract_lottery({"status": "ONGOING", "activityName": "n"}).active
    assert extract_lottery({"activityStatusText": "进行中", "activityName": "n"}).active
    assert not extract_lottery({"activityStatusText": "已结束", "activityName": "n"}).active
    # real shape: status is an object {"code": "SUCCESS"} — must not be treated as a text label
    lot = extract_lottery({"status": {"code": "SUCCESS", "message": "ok"},
                           "activityStatusText": "进行中", "activityName": "n",
                           "drawTypeText": "消耗积分抽奖", "drawPoint": "50"})
    assert lot.active
    assert lot.cost == "50 积分/次"


def test_extract_campaigns_from_real_markdown():
    md = (
        "### 当前时间：2026-10-09 15:25:50\n\n### 活动列表：\n\n"
        "#### 2026年10月7日 往期回顾\n\n-   **活动标题**：过期活动\n    **活动内容介绍**：略\n\n"
        "#### 2026年10月9日 今日\n\n-   **活动标题**：今日活动 A\n    **活动内容介绍**：略\n\n"
        "#### 2026年10月12日\n\n-   **活动标题**：未来活动 B\n    **活动内容介绍**：略\n"
    )
    campaigns = extract_campaigns(md)
    titles = [c.title for c in campaigns]
    assert titles == ["今日活动 A", "未来活动 B"]
    assert campaigns[0].start == date(2026, 10, 9)
    assert campaigns[1].start == date(2026, 10, 12)


def test_extract_coupons_from_real_markdown():
    md = (
        "### 麦麦省优惠券列表：\n"
        "- 优惠券标题：麦旋风任选 \\\n  状态：可领取 \\\n"
        "  优惠券图片：\\\n    <img src=\"x.png\">\n"
        "- 优惠券标题：早餐两件套 \\\n  状态：可领取 \\\n"
        "  优惠内容：9.9 元两件套 \\\n  有效期至：2026-10-21\n"
    )
    coupons = extract_coupons(md)
    assert [c.name for c in coupons] == ["麦旋风任选", "早餐两件套"]
    assert coupons[1].benefit == "9.9 元两件套"
    assert coupons[1].valid_until == date(2026, 10, 21)
    assert coupons[0].valid_until is None


def test_normalize_payload_pulls_embedded_json():
    text = (
        "# API Response Information\n\n## Response Structure\n\n- **data**: 服务器时间信息\n\n"
        "## Original Response\n\n"
        '{"success":true,"data":{"date":"2026-10-09","dayOfWeek":"FRIDAY"}}\n'
    )
    payload = normalize_payload(text)
    assert isinstance(payload, dict)
    assert payload["data"]["date"] == "2026-10-09"
