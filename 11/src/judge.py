import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_OBJECT = re.compile(r"\{.*\}", re.S)
THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_verdict(raw):
    match = JSON_OBJECT.search(THINK.sub("", raw or ""))
    if not match:
        return None, "відповідь судді без JSON"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "зламаний JSON судді"
    score = data.get("score")
    if score not in (0, 1):
        return None, f"невідомий score: {score}"
    return float(score), data.get("reason", "")


def judge_faithfulness(answer, chunks, graph_text=""):
    from rag import cached_call, render

    template = (ROOT / "prompts" / "judge_v1.md").read_text(encoding="utf-8")
    context, _ = render(chunks, graph_text)
    raw, tokens_in, tokens_out, model, _, _ = cached_call(template.format(context=context, answer=answer), judge=True)
    score, reason = parse_verdict(raw)
    return {"score": score, "reason": reason, "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out}
