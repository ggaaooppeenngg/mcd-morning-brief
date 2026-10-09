"""mcd-brief command line interface."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Optional

import typer

from .aggregate import build_brief, brief_from_raw, points_warning
from .client import McdAuthError, McdClient, McdMcpError
from .models import Brief, _parse_date, extract_campaigns, extract_coupons
from .render import to_ics, to_json, to_markdown, to_text

app = typer.Typer(add_completion=False, help="麦麦晨报 —— 麦当劳活动与优惠早知道（基于麦当劳 MCP）")

DEMO_DATA = "sample-data.json"


def _echo_out(text: str, out: Optional[Path]) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        typer.echo(f"已写入 {out}")
    else:
        typer.echo(text)


def _fail(exc: BaseException) -> None:
    typer.secho(f"✖ {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2)


def _client(demo: bool) -> Optional[McdClient]:
    if demo:
        return None
    try:
        return McdClient()
    except McdAuthError as exc:
        _fail(exc)
        return None


def _demo_payload() -> dict:
    return json.loads(resources.files("mcd_brief").joinpath(DEMO_DATA).read_text(encoding="utf-8"))


def _demo_today(payload: dict) -> datetime.date:
    info = payload.get("now-time-info")
    if isinstance(info, dict):
        for key in ("date", "today", "currentDate", "datetime", "time", "now"):
            value = info.get(key)
            if isinstance(value, str) and len(value) >= 10:
                parsed = _parse_date(value[:10])
                if parsed:
                    return parsed
    return datetime.now().date()


@app.command()
def brief(
    format: str = typer.Option("md", "--format", "-f", help="输出格式：md | text | json"),
    days: int = typer.Option(7, "--days", "-d", min=1, max=31, help="活动预告窗口（天）"),
    demo: bool = typer.Option(False, "--demo", help="离线演示模式：内置样例数据，不需要 MCP Token"),
    include_raw: bool = typer.Option(False, "--include-raw", help="json 格式时附带工具原始返回"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="写入文件（默认打印）"),
) -> None:
    """生成今天的麦麦晨报（活动 + 优惠券 + 积分 + 抽奖）。"""
    if demo:
        brief_obj = brief_from_raw(_demo_payload(), window_days=days)
    else:
        client = _client(demo)
        assert client is not None
        try:
            brief_obj = asyncio.run(build_brief(client, window_days=days))
        except McdMcpError as exc:
            _fail(exc)
            return

    if format == "text":
        _echo_out(to_text(brief_obj, window_days=days), out)
    elif format == "json":
        _echo_out(to_json(brief_obj, include_raw=include_raw), out)
    elif format == "md":
        _echo_out(to_markdown(brief_obj, window_days=days), out)
    else:
        _fail(ValueError(f"未知格式：{format}（可选 md / text / json）"))


@app.command()
def calendar(
    demo: bool = typer.Option(False, "--demo", help="离线演示模式"),
    ics: Optional[Path] = typer.Option(None, "--ics", help="同时导出 .ics 日历文件（可导入手机日历）"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="写入文件"),
) -> None:
    """查看当月活动日历，可导出 .ics 订阅到手机日历。"""
    if demo:
        payload = _demo_payload()
        brief_obj = Brief(today=_demo_today(payload),
                          campaigns=extract_campaigns(payload.get("campaign-calendar")))
    else:
        client = _client(demo)
        assert client is not None
        try:
            data = asyncio.run(client.call_many([("now-time-info", None), ("campaign-calendar", None)]))
        except McdMcpError as exc:
            _fail(exc)
            return
        today = _parse_date(_first_date_value(data.get("now-time-info")))
        brief_obj = Brief(today=today or datetime.now().date(),
                          campaigns=extract_campaigns(data.get("campaign-calendar")))

    if ics:
        Path(ics).write_text(to_ics(brief_obj), encoding="utf-8")
        typer.secho(f"✔ 日历已导出：{ics}", fg=typer.colors.GREEN)
    brief_obj.claimable, brief_obj.my_coupons, brief_obj.points, brief_obj.lottery = [], [], None, None
    _echo_out(to_markdown(brief_obj), out)


def _first_date_value(payload: object) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("date", "today", "currentDate", "datetime", "time", "now"):
            value = payload.get(key)
            if isinstance(value, str) and len(value) >= 10:
                return value[:10]
    return None


@app.command()
def coupons(
    demo: bool = typer.Option(False, "--demo", help="离线演示模式（不执行真实领券）"),
    claim: bool = typer.Option(False, "--claim", help="展示后一键领取所有可领优惠券"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认（用于自动化场景）"),
) -> None:
    """查看麦麦省可领优惠券；--claim 一键领取。"""
    if demo:
        payload = _demo_payload()
        for c in extract_coupons(payload.get("available-coupons")):
            typer.echo(f"🎟️ {c.name}" + (f"｜{c.benefit}" if c.benefit else ""))
        if claim:
            typer.secho("（演示模式不执行真实领券）", fg=typer.colors.YELLOW)
        return

    client = _client(demo)
    assert client is not None
    try:
        data = asyncio.run(client.call_many([("available-coupons", None)]))
        available = extract_coupons(data.get("available-coupons"))
    except McdMcpError as exc:
        _fail(exc)
        return

    if not available:
        typer.echo("今天没有可领取的优惠券。")
        return
    for c in available:
        typer.echo(f"🎟️ {c.name}" + (f"｜{c.benefit}" if c.benefit else ""))

    if not claim:
        return
    if not yes and not typer.confirm(f"确认一键领取以上 {len(available)} 张优惠券？"):
        typer.echo("已取消。")
        return
    try:
        result = asyncio.run(client.call("auto-bind-coupons"))
    except McdMcpError as exc:
        _fail(exc)
        return
    typer.secho("✔ 领取完成", fg=typer.colors.GREEN)
    typer.echo(json.dumps(result, ensure_ascii=False)[:500])


@app.command()
def points(demo: bool = typer.Option(False, "--demo", help="离线演示模式")) -> None:
    """查询积分账户与过期提醒。"""
    if demo:
        payload = _demo_payload()
        brief_obj = brief_from_raw({"now-time-info": payload.get("now-time-info"),
                                    "query-my-account": payload.get("query-my-account")})
    else:
        client = _client(demo)
        assert client is not None
        try:
            data = asyncio.run(client.call_many([("now-time-info", None), ("query-my-account", None)]))
            payload = {"now-time-info": data.get("now-time-info"),
                       "query-my-account": data.get("query-my-account")}
            brief_obj = brief_from_raw(payload)
        except McdMcpError as exc:
            _fail(exc)
            return

    p = brief_obj.points
    if not p:
        typer.echo("暂未获取到积分信息")
        return
    if p.available is not None:
        typer.echo(f"💰 可用积分：{p.available:,}")
    if p.total is not None:
        typer.echo(f"累计积分：{p.total:,}")
    if p.expiring:
        typer.echo(points_warning(brief_obj) or f"⚠️ 即将过期：{p.expiring} 分")


if __name__ == "__main__":
    app()
