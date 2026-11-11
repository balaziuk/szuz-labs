import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.main import create_app
from graph_context import Graph
from rag import ask_with_graph, load_searcher

searcher, chunks = load_searcher()
graph = Graph()
template = (ROOT / "prompts" / "rag_v1.md").read_text(encoding="utf-8")

app = create_app(lambda question, role: ask_with_graph(searcher, graph, question, template, role), chunks)
