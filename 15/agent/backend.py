"""Звідки агент бере інструменти: напряму з Python або через MCP-сервер (stdio).

Роль задається при запуску сервера (змінна LAB15_ROLE), а не аргументом від моделі,
тому модель не може «підвищити» собі права.
"""

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

from agent.tools import TOOL_SPECS, call_tool

ROOT = Path(__file__).resolve().parents[1]


class DirectBackend:
    kind = "direct"

    def __init__(self, role="analyst"):
        self.role = role

    def list_tools(self):
        return [dict(spec) for spec in TOOL_SPECS]

    def call(self, name, arguments):
        return call_tool(name, arguments, role=self.role)

    def close(self):
        pass


class McpBackend:
    """Тримає одну stdio-сесію з mcp_server/server.py у фоновому потоці."""

    kind = "mcp"

    def __init__(self, role="analyst"):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self.role = role
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop = None
        self._session = None
        self._error = None
        env = {**os.environ, "LAB15_ROLE": role, "PYTHONIOENCODING": "utf-8"}
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")], env=env, cwd=str(ROOT))

        async def main():
            self._stop = asyncio.Event()
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        info = await session.initialize()
                        self.server_name = info.serverInfo.name
                        self._session = session
                        self._ready.set()
                        await self._stop.wait()
            except Exception as error:  # noqa: BLE001 — віддаємо помилку в основний потік
                self._error = error
                self._ready.set()

        self._thread = threading.Thread(target=self._loop.run_until_complete, args=(main(),), daemon=True)
        self._thread.start()
        self._ready.wait(60)
        if self._error or self._session is None:
            raise RuntimeError(f"MCP-сервер не піднявся: {self._error}")

    def _run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(60)

    def list_tools(self):
        result = self._run(self._session.list_tools())
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
                "read_only": bool(tool.annotations and tool.annotations.readOnlyHint),
            }
            for tool in result.tools
        ]

    def call(self, name, arguments):
        result = self._run(self._session.call_tool(name, arguments or {}))
        if result.isError:
            text = " ".join(getattr(block, "text", "") for block in result.content)
            return {"tool": name, "error": text[:300], "hits": []}
        if result.structuredContent:
            data = result.structuredContent
            return data.get("result", data) if isinstance(data, dict) else data
        text = "".join(getattr(block, "text", "") for block in result.content)
        return json.loads(text)

    def close(self):
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
            self._thread.join(10)
