"""Консольна перевірка MCP-сервера: tools/list, кілька tools/call і ізоляція ролі.

python agent/mcp_probe.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.backend import McpBackend  # noqa: E402

CALLS = [
    ("registry_lookup", {"query": "Роботодавець ЄДРПОУ"}),
    ("search_notes", {"query": "комунальні жовтень 2026"}),
    ("operations_query", {"metric": "rent_share"}),
    ("operations_query", {"month": "жовтень"}),
]


def main():
    analyst = McpBackend("analyst")
    tools = analyst.list_tools()
    print(f"server={analyst.server_name} role=analyst transport=stdio")
    print(f"tools/list -> {len(tools)}")
    for tool in tools:
        params = ", ".join(tool["parameters"].get("properties", {}).keys())
        print(f"  {tool['name']:<18} readOnly={tool['read_only']}  ({params})")
    for name, arguments in CALLS:
        result = analyst.call(name, arguments)
        print(f"tools/call {name} {json.dumps(arguments, ensure_ascii=False)}")
        hits = result.get("hits", [])
        if not hits:
            error = " ".join(str(result.get("error")).split())
            print("  -> відмова сервера: " + error.split(" For further")[0].replace("Error executing tool ", "")[:100])
        for hit in hits[:2]:
            print(f"  -> {hit['id']}: {hit['quote'][:80]}")
    analyst.close()
    public = McpBackend("public")
    hidden = public.call("search_notes", {"query": "комунальні жовтень 2026"})
    public.close()
    ids = [hit["id"] for hit in hidden["hits"]]
    print(f"role=public search_notes -> {ids}; d22 {'є' if 'd22' in ids else 'прихована'}")


if __name__ == "__main__":
    main()
