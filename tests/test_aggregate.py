"""Offline tests for aggregation logic (no network, no token needed)."""

from datetime import date

from mcd_brief.aggregate import (
    brief_from_raw,
    expiring_coupons,
    lottery_line,
    points_warning,
    sort_campaigns,
)
from mcd_brief.models import extract_campaigns, extract_coupons, extract_lottery, extract_points

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
    assert len(brief.campaigns) == 5
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
    assert warn is not None and "300" in warn and "2026-10-15" in warn


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
    pts = extract_points({"availablePoints": "1,240"})
    assert pts.available == 1240
    assert extract_points({"foo": 1}) is None


def test_extract_lottery_status_variants():
    assert extract_lottery({"status": "ONGOING", "activityName": "n"}).active
    assert extract_lottery({"activityStatus": "进行中", "activityName": "n"}).active
    assert not extract_lottery({"activityStatus": "ENDED", "activityName": "n"}).active
