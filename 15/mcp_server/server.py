"""MCP-сервер хаба (офіційний SDK `mcp`, FastMCP, транспорт stdio).

Три інструменти, усі лише для читання (readOnlyHint=True, destructiveHint=False).
Роль сесії береться зі змінної LAB15_ROLE при запуску: analyst або public.

Запуск вручну:  python mcp_server/server.py
Підключення до Claude Code / Claude Desktop: див. `.mcp.json` у корені ЛР15.
"""

import os
import sys
from pathlib import Path
from typing import Annotated, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from agent import tools

ROLE = os.environ.get("LAB15_ROLE", "public")
if ROLE not in {"analyst", "public"}:
    ROLE = "public"

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SPEC = {spec["name"]: spec["description"] for spec in tools.TOOL_SPECS}

mcp = FastMCP("szuz-hub-lab15", log_level="WARNING")


@mcp.tool(description=SPEC["registry_lookup"], annotations=READ_ONLY)
def registry_lookup(query: Annotated[str, Field(max_length=200)]) -> dict:
    return tools.registry_lookup(query[:200])


@mcp.tool(description=SPEC["search_notes"], annotations=READ_ONLY)
def search_notes(query: Annotated[str, Field(max_length=200)]) -> dict:
    # Роль не є аргументом: модель не може її підмінити.
    return tools.search_notes(query[:200], role=ROLE)


@mcp.tool(description=SPEC["operations_query"], annotations=READ_ONLY)
def operations_query(
    month: Annotated[str | None, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")] = None,
    topic: Literal["rent", "utilities", "salary", "all"] | None = None,
    metric: Literal["list", "rent_share"] = "list",
) -> dict:
    return tools.operations_query(month, topic, metric)


if __name__ == "__main__":
    mcp.run()
