"""Offline tests for renderers."""

import json
from datetime import date

from mcd_brief.aggregate import brief_from_raw
from mcd_brief.render import to_ics, to_json, to_markdown, to_text
from importlib import resources


TODAY = date(2026, 10, 10)


def make_brief(**kwargs):
    payload = json.loads(
        resources.files("mcd_brief").joinpath("sample-data.json").read_text(encoding="utf-8")
    )
    return brief_from_raw(payload, today=TODAY, **kwargs)


def test_markdown_sections_and_countdown():
    md = to_markdown(make_brief())
    assert md.startswith("## 🌅 麦麦晨报 · 2026-10-10 周六")
    assert "### 📅 近期活动（未来 7 天）" in md
    assert "⏰ **3 天后开始**" in md
    assert "🔥 **进行中**" in md
    assert "### 🎫 今日可领优惠券（3 张）" in md
    assert "### ⌛ 即将过期的券（1 张）" in md
    assert "可用 **1,240** 分" in md
    assert "免费抽奖" in md
    assert "以麦当劳 APP / 门店实时信息为准" in md


def test_markdown_window_widening_pulls_far_campaign():
    md = to_markdown(make_brief(), window_days=30)
    assert "万圣节怪怪堡上新" in md


def test_text_has_no_emoji():
    text = to_text(make_brief())
    assert "[麦麦晨报 2026-10-10 (Sat)]" in text
    assert not any(ch in text for ch in "🌅🎫💰🎰⏰🔥🎟️⌛")


def test_json_roundtrip_and_raw_stripped():
    data = json.loads(to_json(make_brief()))
    assert data["today"] == "2026-10-10"
    assert len(data["upcoming_campaigns"]) == 3
    assert "raw" not in data["points"]
    assert "raw" not in data["claimable"][0]


def test_ics_structure_and_escaping():
    ics = to_ics(make_brief())
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.endswith("END:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" in ics
    assert "DTSTART;VALUE=DATE:20261010" in ics
    assert "UID:mcd-brief-" in ics
    # comma in campaign title must be escaped
    assert "第二份半价" in ics
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
