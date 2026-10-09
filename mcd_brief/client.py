"""McDonald's MCP (mcp.mcd.cn) client — thin async wrapper over the official MCP SDK."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession

try:  # MCP python-sdk 1.x
    from mcp.client.streamable_http import streamablehttp_client as _http_client_v1

    _SDK_V2 = False
except ImportError:  # MCP python-sdk 2.x renamed the transport and moved headers into the http client
    from mcp.client.streamable_http import (
        create_mcp_http_client,
        streamable_http_client as _http_client_v2,
    )

    _SDK_V2 = True

MCP_URL = "https://mcp.mcd.cn"
TOKEN_ENV = "MCD_MCP_TOKEN"


@asynccontextmanager
async def _open_session(url: str, token: str, timeout: float) -> AsyncIterator[ClientSession]:
    """Initialize a ClientSession over Streamable HTTP, on either SDK major version."""
    headers = {"Authorization": f"Bearer {token}"}
    if _SDK_V2:
        http_client = create_mcp_http_client(headers=headers)
        async with _http_client_v2(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        async with _http_client_v1(url, headers=headers, timeout=timeout) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


class McdMcpError(RuntimeError):
    """Base error with user-facing guidance."""


class McdAuthError(McdMcpError):
    pass


class McdRateLimitError(McdMcpError):
    pass


class McdToolError(McdMcpError):
    pass


def _unwrap(exc: BaseException) -> BaseException:
    if isinstance(exc, BaseExceptionGroup):
        return _unwrap(exc.exceptions[0])
    return exc


def _probe_status(url: str, token: str) -> int | None:
    """Direct HTTP status probe — the SDK layers swallow the status code on failures."""
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "mcd-brief-probe", "version": "0.0.1"},
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def _friendly(exc: BaseException, url: str = "", token: str = "") -> McdMcpError:
    inner = _unwrap(exc)
    text = str(inner)
    if "401" in text or "unauthorized" in text.lower() or "invalid_token" in text.lower():
        return McdAuthError(
            "MCP Token 无效或未提供（HTTP 401）。"
            f"请设置环境变量 {TOKEN_ENV}（申请地址：https://open.mcd.cn/mcp）。"
        )
    if "429" in text or "rate" in text.lower():
        return McdRateLimitError("触发限流（HTTP 429）：每个 Token 每分钟最多 600 次请求，请稍后再试。")
    if isinstance(inner, (asyncio.TimeoutError, TimeoutError)):
        return McdMcpError("连接麦当劳 MCP 超时，请检查网络后重试。")
    if isinstance(inner, McdMcpError):
        return inner
    if url and token:  # refine generic SDK errors with the real HTTP status
        status = _probe_status(url, token)
        if status == 401:
            return McdAuthError(
                "MCP Token 无效或已过期（HTTP 401）。请到 https://open.mcd.cn/mcp 控制台"
                f"重新复制 Token，并更新环境变量 {TOKEN_ENV}。"
            )
        if status == 403:
            return McdAuthError(
                "服务端拒绝访问（HTTP 403）：常见于未携带 Token 或 Token 为空，"
                f"请确认环境变量 {TOKEN_ENV} 已正确设置。"
            )
        if status == 429:
            return McdRateLimitError("触发限流（HTTP 429）：每个 Token 每分钟最多 600 次请求，请稍后再试。")
    return McdMcpError(f"调用麦当劳 MCP 失败：{text}")


class McdClient:
    """Async client for one MCP endpoint; reuse one instance for several calls."""

    def __init__(self, token: str | None = None, url: str = MCP_URL, timeout: float = 30.0):
        token = token or os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            raise McdAuthError(
                f"未找到 MCP Token：请设置环境变量 {TOKEN_ENV} 后重试"
                "（Token 申请：https://open.mcd.cn/mcp，手机号登录 → 控制台 → 激活）。"
                "没有 Token 也可以先用 --demo 模式离线体验。"
            )
        self.url = url
        self.token = token
        self.timeout = timeout

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        """Call one tool in a fresh session."""
        return (await self.call_many([(tool, args)]))[tool]

    async def call_many(
        self, calls: list[tuple[str, dict[str, Any] | None]]
    ) -> dict[str, Any]:
        """Call several tools over a single session (fewer handshakes, friendlier to rate limits).

        Per-tool errors are returned as ``{"__error__": "..."}`` instead of aborting the batch.
        Duplicate tool names: the last call wins.
        """
        results: dict[str, Any] = {}
        try:
            async with asyncio.timeout(self.timeout * max(len(calls), 1)):
                async with _open_session(self.url, self.token, self.timeout) as session:
                    for tool, args in calls:
                        try:
                            results[tool] = await self._call(session, tool, args or {})
                        except McdMcpError as exc:
                            results[tool] = {"__error__": str(exc)}
            return results
        except McdMcpError:
            raise
        except BaseException as exc:  # anyio wraps failures in ExceptionGroups
            raise _friendly(exc, self.url, self.token) from exc

    async def _call(self, session: ClientSession, tool: str, args: dict[str, Any]) -> Any:
        result = await session.call_tool(tool, args)
        payload: Any
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            payload = structured
        else:
            texts = [
                getattr(block, "text", "")
                for block in (result.content or [])
                if getattr(block, "type", "") == "text"
            ]
            raw = "\n".join(t for t in texts if t).strip()
            if not raw:
                payload = None
            else:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
        if getattr(result, "isError", False):
            raise McdToolError(f"工具 {tool} 返回错误：{_short(payload)}")
        return payload


def _short(payload: Any, limit: int = 300) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return text[:limit] + ("…" if len(text) > limit else "")
