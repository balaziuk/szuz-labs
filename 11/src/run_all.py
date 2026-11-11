import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate import (
    abstains, build_tests, category_counts, citation_accuracy, cohen_kappa, context_recall,
    faithfulness_heuristic, mean, save_tests, summarize,
)
from graph_context import QUESTIONS, Graph
from judge import judge_faithfulness
from llm import log_row
from rag import ask, ask_with_graph, load_searcher, verdict

DOCS = ROOT / "docs"
LOG = ROOT / "llm_log" / "rag.jsonl"
HUMAN = ROOT / "eval" / "human_review.jsonl"
DIGIT_GAP = re.compile(r"(?<=\d)[\s  ]+(?=\d)")
MIN_CHANGED = 2

FAILURES = [
    "Q08 на v1, причина: генерація. У підсумку є твердження про «контроль» і «прозоре управління», яких немає у фрагментах. Суддя і людина тут згодні. Виправлення: у промпті заборонити власний підсумок без цитати.",
    "C3 на обох промптах, причина: генерація. Питання згадує квітень, а в обох нотатках місяця немає, і модель переносить уточнення з питання у твердження. Виправлення: правило «не додавай до значення уточнення з питання, якщо їх немає в джерелі» і питання без місяця в тесті.",
    "Q19 на v2, причина: генерація. Фрагмент каже «у 90-х роках», модель написала «у 1990-х». Евристика і людина це ловлять, суддя ні. Виправлення: додати в рубрику судді приклад про розшифрування дат, лишити v1.",
    "G11 лише текст, причина: пошук. Хто отримує оренду, записано ребром графа, а не абзацом статті, тому в контексті відповіді немає. Виправлення: для питань про зв'язки додавати підграф, а не збільшувати k.",
    "G01 з підграфом, причина: політика. Перевірка цитат відхилила правильну відповідь, бо в цитаті був невидимий символ U+200B. Виправлено: `cited_ids` прибирає такі символи перед розбором.",
]


def template(version):
    return (ROOT / "prompts" / f"{version}.md").read_text(encoding="utf-8")


def load_human():
    rows = [json.loads(ln) for ln in HUMAN.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return {(r["id"], r["prompt_version"]): r for r in rows}


def journal(rows, human):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for row in rows:
            auto = "reject" if row["rejected"] else "accept"
            reason = "цитата поза контекстом або її немає" if row["rejected"] else "цитати в контексті або це відмова"
            review = human.get((row["id"], row["prompt_version"]))
            decision = None if review is None else ("accept" if review["human"] == 1 else "reject")
            f.write(json.dumps(log_row(row, auto, reason, decision), ensure_ascii=False) + "\n")


def run_test(searcher, test, version, tmpl):
    out = ask(searcher, test["question"], tmpl, role="analyst", k=5, extra=test.get("pair"))
    raw = out["raw_answer"]
    out["id"] = test["id"]
    out["category"] = test["category"]
    out["prompt_version"] = version
    out["faithfulness_heuristic"] = faithfulness_heuristic(raw, out["context_chunks"])
    out["faithfulness"], out["judge_reason"], out["judge_model"], out["judge_tokens"] = None, None, None, 0
    if not abstains(raw):
        verdict = judge_faithfulness(raw, out["context_chunks"])
        out["faithfulness"], out["judge_reason"] = verdict["score"], verdict["reason"]
        out["judge_model"] = verdict["model"]
        out["judge_tokens"] = (verdict["tokens_in"] or 0) + (verdict["tokens_out"] or 0)
    out["citation_accuracy"] = citation_accuracy(raw, set(out["sources"]))
    out["context_recall"] = context_recall(test, out["context_chunks"])
    out["abstained"] = 1.0 if abstains(raw) else 0.0
    if test["category"] == "conflict":
        flat = DIGIT_GAP.sub("", raw)
        out["conflict_ok"] = 1.0 if (
            all(v in flat for v in test["values"]) and all(p["chunk_id"] in out["cited"] for p in test["pair"])
        ) else 0.0
    out["leak"] = "CANARY-LAB11" in raw
    return out


def slim(row):
    skip = {"prompt", "context_chunks", "graph_text", "source_meta"}
    return {k: v for k, v in row.items() if k not in skip}


def review_pairs(rows_by_version, human):
    pairs, excluded = [], []
    for (test_id, version), review in human.items():
        row = next((r for r in rows_by_version[version] if r["id"] == test_id), None)
        if row is None:
            continue
        if row["faithfulness"] is None:
            excluded.append(test_id)
            continue
        pairs.append({"id": test_id, "version": version, "human": review["human"], "judge": int(row["faithfulness"])})
    return pairs, excluded


def human_faithfulness(rows, human):
    scores = [human[(r["id"], r["prompt_version"])]["human"] for r in rows
              if r["faithfulness"] is not None and (r["id"], r["prompt_version"]) in human]
    return mean(scores), len(scores)


def write_eval(tests, rows_by_version, summary, human):
    rows = rows_by_version["rag_v1"]
    human_score, human_n = human_faithfulness(rows, human)
    pairs, excluded = review_pairs(rows_by_version, human)
    kappa = cohen_kappa([(p["human"], p["judge"]) for p in pairs])
    agree = round(sum(p["human"] == p["judge"] for p in pairs) / len(pairs), 3)
    cell = lambda h, j: sum(p["human"] == h and p["judge"] == j for p in pairs)
    judge_model = next(r["judge_model"] for r in rows if r["judge_model"])
    lines = ["# Оцінка RAG", "",
             f"Тестів: {len(tests)}. Категорії: {category_counts(tests)}.",
             "Роль аналітика (усі рівні доступу). Пошук — hybrid + rerank, k=5, промпт rag_v1.",
             "",
             "| Метрика | Значення |",
             "|---|---|",
             f"| faithfulness (суддя, {summary['faithfulness_n']} відповідей без відмов) | {summary['faithfulness']} |",
             f"| faithfulness (людина, {human_n} відповідей) | {human_score} |",
             f"| faithfulness (евристика: числа і спільні слова) | {summary['faithfulness_heuristic']} |",
             f"| context recall | {summary['context_recall']} |",
             f"| citation accuracy | {summary['citation_accuracy']} |",
             f"| abstention rate (без відповіді + ін'єкції) | {summary['abstention_rate']} |",
             f"| конфлікт названо з обома id | {summary['conflict_both']} |",
             f"| відповідей відхилено перевіркою цитат | {summary['rejected']} |",
             f"| затримка p50 / p95, мс | {summary['latency_p50']} / {summary['latency_p95']} |",
             f"| токени вхід / вихід | {summary['tokens_in']} / {summary['tokens_out']} |",
             f"| токенів на запит | {round((summary['tokens_in'] + summary['tokens_out']) / summary['n'])} |",
             f"| токени судді | {summary['judge_tokens']} |",
             "",
             "Вартість у грошах — 0: ключ на безкоштовному тарифі. Порівняння вартості — у токенах.",
             f"Модель відповіді — {rows[0]['model']}, суддя — {judge_model}, temperature 0, seed 42.",
             "Відмови судді не оцінюються: у них немає тверджень. Їх перевіряє abstention rate.",
             "",
             "## П'ять провалів",
             ""]
    lines += [f"- {item}" for item in FAILURES]
    lines += ["",
              "Попередня citation accuracy 0.967 була помилкою перерахунку: регулярний вираз губив фрагмент D08-F003, хоча він був у контексті Q15. "
              "Тепер джерела беруться прямо з конвеєра.",
              "",
              "## Ручна перевірка",
              "",
              f"Оцінки людини — `eval/human_review.jsonl`. Порівняно із суддею: {len(pairs)}. "
              f"Не порівнювались відмови без оцінки судді: {', '.join(excluded) or 'немає'}.",
              "",
              "| | суддя = 1 | суддя = 0 |",
              "|---|---|---|",
              f"| людина = 1 | {cell(1, 1)} | {cell(1, 0)} |",
              f"| людина = 0 | {cell(0, 1)} | {cell(0, 0)} |",
              "",
              f"Згода p₀ = {agree}, κ Коена = {kappa}.",
              ""]
    drafted = sum(r.get("origin") == "ai_draft_confirmed" for r in human.values())
    if drafted:
        lines += [f"Оцінок, де людина підтвердила чернетку ШІ без змін: {drafted} із {len(human)} "
                  "(`origin` у `eval/human_review.jsonl`). Це треба задекларувати у звіті.", ""]
    (DOCS / "rag_eval.md").write_text("\n".join(lines), encoding="utf-8")
    return {"agree": agree, "kappa": kappa, "n": len(pairs)}


def write_optimization(rows_by_version, before, after, human):
    human_v1, _ = human_faithfulness(rows_by_version["rag_v1"], human)
    human_v2, _ = human_faithfulness(rows_by_version["rag_v2"], human)
    lines = ["# Оптимізація RAG", "",
             "Гіпотеза: якщо в промпті вимагати дослівну цитату (rag_v2, правило 5), "
             "зросте faithfulness за оцінкою судді, бо відповідь частіше повторює слова контексту. "
             "Інші фактори не змінювались: той самий пошук, k=5, та сама модель, temperature 0, seed 42.",
             "",
             "| | rag_v1 | rag_v2 |",
             "|---|---|---|",
             f"| faithfulness (суддя) | {before['faithfulness']} | {after['faithfulness']} |",
             f"| faithfulness (людина) | {human_v1} | {human_v2} |",
             f"| faithfulness (евристика) | {before['faithfulness_heuristic']} | {after['faithfulness_heuristic']} |",
             f"| context recall | {before['context_recall']} | {after['context_recall']} |",
             f"| citation accuracy | {before['citation_accuracy']} | {after['citation_accuracy']} |",
             f"| abstention rate | {before['abstention_rate']} | {after['abstention_rate']} |",
             f"| конфлікт з обома джерелами | {before['conflict_both']} | {after['conflict_both']} |",
             f"| p50, мс | {before['latency_p50']} | {after['latency_p50']} |",
             f"| p95, мс | {before['latency_p95']} | {after['latency_p95']} |",
             f"| p95 без запитів з очікуванням повтору, мс | {before['latency_p95_no_wait']} | {after['latency_p95_no_wait']} |",
             f"| запитів з очікуванням повтору | {before['waited']} | {after['waited']} |",
             f"| токени вхід+вихід | {before['tokens_in'] + before['tokens_out']} | {after['tokens_in'] + after['tokens_out']} |",
             ""]
    d_f = round((after["faithfulness"] or 0) - (before["faithfulness"] or 0), 3)
    d_t = (after["tokens_in"] + after["tokens_out"]) - (before["tokens_in"] + before["tokens_out"])
    v1 = {r["id"]: r["faithfulness"] for r in rows_by_version["rag_v1"]}
    v2 = {r["id"]: r["faithfulness"] for r in rows_by_version["rag_v2"]}
    changed = [f"{i} ({v1[i]} → {v2[i]})" for i in v1 if v1[i] != v2.get(i)]
    total = before["tokens_in"] + before["tokens_out"]
    out_growth = round((after["tokens_out"] - before["tokens_out"]) / before["tokens_out"] * 100)
    lines += [
        f"Faithfulness судді змінився на {d_f}. Оцінка змінилась у: {', '.join(changed) or 'жодному питанні'}. "
        f"Токенів більше на {d_t} ({round(d_t / total * 100, 1)}%), вихідних — на {out_growth}%. "
        "Запити з очікуванням повтору після обмеження провайдера (затримка понад 30 с) "
        "спотворюють p95, тому наведено і p95 без них: без очікування затримка практично однакова. "
        "Грошова вартість на безкоштовному тарифі лишається 0. "
        + (f"Зміна стосується {len(changed)} питань із {before['faithfulness_n']}, це вже можна вважати ефектом, промпт v2 лишаємо."
           if d_f > 0 and len(changed) >= MIN_CHANGED else
           f"Зміна стосується {len(changed)} питання з {before['faithfulness_n']}, а за оцінкою людини v1 {human_v1}, v2 {human_v2}. "
           "Такого приросту замало, щоб платити більшою кількістю токенів: гіпотезу не підтверджено, лишаємо v1."),
        "",
    ]
    (DOCS / "rag_optimization.md").write_text("\n".join(lines), encoding="utf-8")


def write_graph(rows, backend):
    id_rows = [r for r in rows if not r["no_id"]]
    word_rows = [r for r in rows if r["no_id"]]
    text_tokens = sum(r["text_tokens"] for r in rows)
    graph_tokens = sum(r["graph_tokens"] for r in rows)
    growth = round((graph_tokens - text_tokens) / text_tokens * 100)
    lines = ["# Текст проти тексту з підграфом", "",
             f"Шістнадцять питань про зв'язки графа ЛР9. Джерело графа: {backend}. "
             "Entity linking — за назвою, синонімом і id. Підграф — 2 кроки, не більше 24 ребер і 5 операцій на категорію. "
             "Обидва режими йдуть у той самий промпт rag_v1 і ту саму модель. "
             "G01–G10 просять id вузла, якого в статтях немає. G11–G16 питають звичайними словами, щоб порівняння не залежало від id.",
             "",
             "| Показник | лише текст | текст + підграф |",
             "|---|---|---|",
             f"| правильно, питання з id ({len(id_rows)}) | {mean([r['text_hit'] for r in id_rows])} | {mean([r['graph_hit'] for r in id_rows])} |",
             f"| правильно, питання без id ({len(word_rows)}) | {mean([r['text_hit'] for r in word_rows])} | {mean([r['graph_hit'] for r in word_rows])} |",
             f"| контекст містить відповідь | {mean([r['text_ctx'] for r in rows])} | {mean([r['graph_ctx'] for r in rows])} |",
             f"| відповідь цитує вузол графа (пояснюваність) | — | {mean([r['graph_cited'] for r in rows])} |",
             f"| відхилено перевіркою цитат | {sum(r['text_rejected'] for r in rows)} | {sum(r['graph_rejected'] for r in rows)} |",
             f"| токени промпта | {text_tokens} | {graph_tokens} |",
             "",
             "| id | питання | текст | текст+граф | токени тексту | токени з графом |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['question']} | {r['text_hit']} | {r['graph_hit']} | "
                     f"{r['text_tokens']} | {r['graph_tokens']} |")
    lines += ["",
              f"Висновок. На питаннях без id частка правильних зросла з {mean([r['text_hit'] for r in word_rows])} "
              f"до {mean([r['graph_hit'] for r in word_rows])}, на питаннях з id — з {mean([r['text_hit'] for r in id_rows])} "
              f"до {mean([r['graph_hit'] for r in id_rows])}. Ціна — на {growth}% більше токенів промпта "
              f"({text_tokens} проти {graph_tokens}). Вузол графа цитує частка {mean([r['graph_cited'] for r in rows])} відповідей, "
              "тож зв'язок можна перевірити за id. Питання з id майже нічого не доводять самі по собі: цих id у статтях немає.",
              ""]
    (DOCS / "graph_vs_text.md").write_text("\n".join(lines), encoding="utf-8")
    (DOCS / "graph_raw.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_demo(rows):
    lines = ["# Демо конвеєра, 5 запитів", ""]
    for r in rows:
        lines += [f"## {r['id']}", "", r["question"], "", r["answer"], "",
                  f"Джерела: {', '.join(r['sources'][:5])}. Цитати: {', '.join(r['cited']) or 'немає'}. "
                  f"Невалідні: {', '.join(r['invalid_citations']) or 'немає'}. "
                  f"Токени {r['tokens_in']}+{r['tokens_out']}, {r['latency_ms']} мс.",
                  ""]
    (DOCS / "rag_demo.md").write_text("\n".join(lines), encoding="utf-8")


def write_api(demo):
    lines = ["# REST API", "",
             "FastAPI: `POST /ask`, `GET /health`, `GET /sources/{id}`.",
             "Ключ у заголовку `X-API-Key`. Локальні демо-ключі (не секрети зовнішніх сервісів): "
             "`demo-public` (лише sensitivity=public, без підграфа) і `demo-analyst` (усі рівні і підграф).",
             "Ліміт сервера — 30 запитів на хвилину на ключ, у перевірці нижче — 5. Далі код 429.",
             "Вхід `POST /ask` — JSON `{question}` від 3 до 500 символів, інакше 422.",
             "Якщо цитата поза контекстом або цитат немає, `/ask` повертає `rejected: true` і відмову замість відповіді моделі.",
             "",
             "```powershell",
             "..\\10\\.venv\\Scripts\\python -m uvicorn api.serve:app --port 8000",
             "curl.exe http://127.0.0.1:8000/health",
             "curl.exe -H \"X-API-Key: demo-public\" -H \"Content-Type: application/json\" "
             "--data-binary \"@docs/ask_example.json\" http://127.0.0.1:8000/ask",
             "curl.exe -H \"X-API-Key: demo-analyst\" http://127.0.0.1:8000/sources/D30-F001",
             "```",
             "",
             "Тіло запиту лежить у файлі, бо PowerShell 5.1 псує лапки й кирилицю в `-d`.",
             "",
             "Перевірка TestClient:",
             ""]
    lines += [f"- {item}" for item in demo]
    lines.append("")
    (DOCS / "api.md").write_text("\n".join(lines), encoding="utf-8")


def write_claims(summary_v1, summary_v2, graph_rows, api_ok, rejected_ok, review, leaks, human_scores):
    words = [r for r in graph_rows if r["no_id"]]
    text_hit, graph_hit = mean([r["text_hit"] for r in words]), mean([r["graph_hit"] for r in words])
    rows = [
        ("C01", "Конвеєр відхиляє відповідь із цитатою поза контекстом", "rule", "src/rag.py", "V4",
         "verified" if rejected_ok else "rejected",
         f"перевірка із заглушкою моделі: чужий id і відповідь без цитат дають rejected=true; у реальних прогонах відхилень {summary_v1['rejected'] + summary_v2['rejected']}"),
        ("C02", "Підграф підвищує частку правильних відповідей на питання без id", "hypothesis", "src/graph_context.py", "V4",
         "verified" if graph_hit > text_hit else "rejected", f"текст {text_hit}, текст+граф {graph_hit} на {len(words)} питаннях"),
        ("C03", "Публічна роль не бачить внутрішні джерела і підграф", "rule", "api/main.py", "V4",
         "verified" if api_ok else "rejected", "public лише public, без вузлів графа; чужий фрагмент дає 403"),
        ("C04", "Промпт із дослівною цитатою підвищує faithfulness", "hypothesis", "prompts/rag_v2.md", "V3",
         "rejected" if human_scores[1] <= human_scores[0] else "pending",
         f"суддя: v1 {summary_v1['faithfulness']}, v2 {summary_v2['faithfulness']}; людина: v1 {human_scores[0]}, v2 {human_scores[1]}"),
        ("C05", "Модель не відтворює маркер CANARY-LAB11", "rule", "prompts/rag_v1.md", "V4",
         "verified" if leaks == 0 else "rejected", f"витоків на обох промптах: {leaks}"),
        ("C06", "Оцінки судді узгоджуються з ручною перевіркою", "hypothesis", "src/judge.py", "V3",
         "verified" if (review["kappa"] or 0) >= 0.6 else "rejected", f"p0 {review['agree']}, kappa {review['kappa']}, n {review['n']}"),
    ]
    path = ROOT / "claims" / "claims.csv"
    path.parent.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["id", "claim", "type", "source", "verification_level", "status", "comment"])
        writer.writerows(rows)


def compare_graph(searcher, graph, v1):
    rows, logged = [], []
    for q in QUESTIONS:
        seeds, text, gids = graph.linearize(q["question"])
        plain = ask(searcher, q["question"], v1, role="analyst", k=5)
        rich = ask(searcher, q["question"], v1, role="analyst", k=5, graph_text=text, graph_ids=gids)
        for label, out in (("text", plain), ("graph", rich)):
            out["prompt_version"] = "rag_v1"
            out["id"] = q["id"] + "-" + label
        logged += [plain, rich]

        def hit(answer):
            flat = DIGIT_GAP.sub("", answer)
            return 1.0 if all(e in flat for e in q["expect"]) else 0.0

        rows.append({
            "id": q["id"], "question": q["question"], "seeds": seeds, "no_id": q.get("no_id", False),
            "text_hit": hit(plain["answer"]), "graph_hit": hit(rich["answer"]),
            "text_ctx": hit(plain["prompt"]), "graph_ctx": hit(rich["prompt"]),
            "graph_cited": 1.0 if set(rich["cited"]) & gids else 0.0,
            "text_rejected": plain["rejected"], "graph_rejected": rich["rejected"],
            "text_tokens": plain["tokens_in"] or 0, "graph_tokens": rich["tokens_in"] or 0,
        })
        print(q["id"], "text", rows[-1]["text_hit"], "graph", rows[-1]["graph_hit"], flush=True)
    return rows, logged


def check_api(searcher, graph, chunks, v1):
    from fastapi.testclient import TestClient

    sys.path.insert(0, str(ROOT))
    from api.main import create_app

    app = create_app(lambda question, role: ask_with_graph(searcher, graph, question, v1, role), chunks, limit=5)
    client = TestClient(app)
    public, analyst = {"X-API-Key": "demo-public"}, {"X-API-Key": "demo-analyst"}
    question = "частка витрат на оренду у фінансовій моделі"
    notes = []
    r = client.get("/health")
    notes.append(f"GET /health -> {r.status_code} {r.json()}")
    notes.append(f"POST /ask без ключа і з короткою стрічкою -> {client.post('/ask', json={'question': 'що'}).status_code}")
    notes.append(f"POST /ask без ключа -> {client.post('/ask', json={'question': 'Що таке гривня?'}).status_code}")
    pub = client.post("/ask", headers=public, json={"question": question}).json()
    ana = client.post("/ask", headers=analyst, json={"question": question}).json()
    pub_s = {s["sensitivity"] for s in pub["sources"]}
    ana_s = {s["sensitivity"] for s in ana["sources"]}
    notes.append(f"public sources {sorted(pub_s)}, вузлів графа {len(pub['graph_nodes'])}; "
                 f"analyst sources {sorted(ana_s)}, вузлів графа {len(ana['graph_nodes'])}")
    hidden = next(c for c in chunks.values() if c["sensitivity"] != "public")
    denied = client.get(f"/sources/{hidden['chunk_id']}", headers=public).status_code
    allowed = client.get(f"/sources/{hidden['chunk_id']}", headers=analyst).status_code
    missing = client.get("/sources/NO-SUCH", headers=analyst).status_code
    notes.append(f"GET приховане public -> {denied}, analyst -> {allowed}, немає -> {missing}")

    def stub_answer(raw):
        answer, _, _, rejected = verdict(raw, {"D01-F001"})
        return {"answer": answer, "rejected": rejected, "source_meta": [], "graph_nodes": []}

    outcomes = []
    for label, raw in (("чужий id", "Текст [D99-F999]"), ("без цитат", "Текст"), ("дійсний id", "Текст [D01-F001]")):
        stub = TestClient(create_app(lambda question, role, raw=raw: stub_answer(raw), chunks))
        outcomes.append((label, stub.post("/ask", headers=analyst, json={"question": "тестове питання"}).json()["rejected"]))
    notes.append("POST /ask із заглушкою моделі: " + ", ".join(f"{label} -> rejected={value}" for label, value in outcomes))
    code = None
    for _ in range(6):
        code = client.get(f"/sources/{next(iter(chunks))}", headers=public).status_code
    notes.append(f"шостий GET /sources для demo-public -> {code}")
    (DOCS / "openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    write_api(notes)
    api_ok = denied == 403 and allowed == 200 and pub_s == {"public"} and not pub["graph_nodes"]
    return api_ok, [value for _, value in outcomes] == [True, True, False]


def main():
    DOCS.mkdir(exist_ok=True)
    if LOG.exists():
        LOG.unlink()
    tests = build_tests()
    save_tests(tests)
    print("tests", len(tests), category_counts(tests), flush=True)
    searcher, chunks = load_searcher()
    graph = Graph()
    print("index ready", len(chunks), "graph", graph.backend, len(graph.nodes), len(graph.edges), flush=True)
    v1, v2 = template("rag_v1"), template("rag_v2")
    human = load_human()

    rows = {"rag_v1": [], "rag_v2": []}
    for version, tmpl in (("rag_v1", v1), ("rag_v2", v2)):
        for test in tests:
            row = run_test(searcher, test, version, tmpl)
            rows[version].append(row)
            print(version, test["id"], "judge", row["faithfulness"], "recall", row["context_recall"], flush=True)
        journal(rows[version], human)
    summary_v1, summary_v2 = summarize(rows["rag_v1"]), summarize(rows["rag_v2"])

    by_id = {r["id"]: r for r in rows["rag_v1"]}
    write_demo([by_id[i] for i in ["Q02", "Q14", "Q66", "Q08", "Q10"]])

    graph_rows, graph_log = compare_graph(searcher, graph, v1)
    journal(graph_log, human)
    write_graph(graph_rows, graph.backend)

    review = write_eval(tests, rows, summary_v1, human)
    write_optimization(rows, summary_v1, summary_v2, human)
    (DOCS / "eval_raw.json").write_text(json.dumps({
        "v1": {"summary": summary_v1, "rows": [slim(r) for r in rows["rag_v1"]]},
        "v2": {"summary": summary_v2, "rows": [slim(r) for r in rows["rag_v2"]]},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    api_ok, rejected_ok = check_api(searcher, graph, chunks, v1)
    leaks = sum(r["leak"] for r in rows["rag_v1"] + rows["rag_v2"])
    human_scores = [human_faithfulness(rows[v], human)[0] for v in ("rag_v1", "rag_v2")]
    write_claims(summary_v1, summary_v2, graph_rows, api_ok, rejected_ok, review, leaks, human_scores)
    print("v1", summary_v1, flush=True)
    print("v2", summary_v2, flush=True)
    print("review", review, "api", api_ok, "rejected", rejected_ok, "leaks", leaks, flush=True)


if __name__ == "__main__":
    main()
