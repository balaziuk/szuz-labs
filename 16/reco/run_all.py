"""Збирає взаємодії, метрики, пояснення, холодний старт і технічну записку."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reco.cold import new_item, new_user
from reco.data import build_interactions, load_docs, save
from reco.eval import evaluate
from reco.explain import control_failure, control_foreign, examples, paraphrase_eval
from reco.whitepaper import build_pdf


def main():
    docs = load_docs()
    rows = build_interactions(docs)
    meta = save(docs, rows)
    report = evaluate(docs, rows)
    user = report["filters"]["user"]
    shown = examples(docs, rows, user, limit=5)
    if len(shown) < 5:
        raise SystemExit(f"пояснень лише {len(shown)}")
    planted = control_failure(shown[0])
    foreign = control_foreign(shown[0], docs)
    if planted["ok"] or foreign["ok"] or not all(item["ok"] for item in shown):
        raise SystemExit("перевірка пояснень спрацювала не так, як очікувалось")
    llm_eval = paraphrase_eval(docs, rows, [f"u{n:02d}" for n in range(1, 7)])
    (ROOT / "data" / "explain_eval.json").write_text(json.dumps(llm_eval, ensure_ascii=False, indent=2), encoding="utf-8")
    cold = {"new_user": new_user(docs, rows), "new_item": new_item(docs, rows)}
    (ROOT / "data" / "cold.json").write_text(json.dumps(cold, ensure_ascii=False, indent=2), encoding="utf-8")
    _cold_md(shown, planted, foreign, llm_eval, cold)
    _claims(report, cold, shown, llm_eval)
    _log()
    pages = build_pdf(report, cold)
    print(json.dumps({"users": meta["users"], "rows": meta["rows"], "evaluated": report["users_evaluated"], "chosen": report["chosen"], "pages": pages, "cold": cold}, ensure_ascii=False))
    if not 8 <= pages <= 12:
        raise SystemExit(f"whitepaper має {pages} сторінок, потрібно 8–12")


def _cold_md(shown, planted, foreign, llm_eval, cold):
    lines = [
        "# Пояснення і холодний старт",
        "",
        "Пояснення будується у два кроки. Спершу код складає службове речення зі спільних вузлів графа документ–сутність (шлях користувач → вузол → документ). Потім LLM (qwen/qwen3.8-27b, temperature 0, seed 42, промпт explain_v1) лише перефразовує це речення; список дозволених назв їй передається явно.",
        "Перевірка має два рівні: (1) кожна назва в лапках «» — поверхнева форма вузла шляху; (2) у реченні немає жодної іншої сутності каталогу ЛР13, навіть без лапок. Назва самого рекомендованого документа дозволена: перша версія перевірки (v1, поле auto_check у перших записах llm_log/reco.jsonl) помилково вважала її чужою сутністю й відкинула 9 з 22 перефразувань; у v2 це виправлено. Перефразування, що не пройшло перевірку, не показується — користувач бачить службове речення шляху. Окремо подано два контрольні речення.",
        "",
        "## П'ять пояснень",
        "",
    ]
    for item in shown:
        path = ", ".join(item["path"])
        llm = item["llm"]
        llm_text = f" LLM: {llm['text']} Перевірка LLM: {'так' if llm['ok'] else 'ні'}." if llm else " LLM: немає (ключа й кешу немає)."
        lines.append(f"- {item['sentence']} Шлях: {path}. Перевірка шляху: {'так' if item['ok'] else 'ні'}.{llm_text}")
    rate = sum(item["ok"] for item in shown) / len(shown)
    lines += [
        "",
        f"Коректних пояснень: {sum(item['ok'] for item in shown)} з {len(shown)} ({rate:.3f}).",
        f"Контрольне речення з вигаданим вузлом у лапках відхилено: {planted['ok'] is False}. Текст: {planted['sentence']}",
        f"Контрольне речення з чужою сутністю каталогу без лапок («{foreign['planted']}») відхилено суворою перевіркою: {foreign['ok'] is False}. Текст: {foreign['sentence']}",
        "",
        "## Частка LLM-пояснень, що спираються на шлях",
        "",
        f"Користувачів {llm_eval['users']} (u01–u06), пояснень у топ-5 графа {llm_eval['explanations']}, з перефразуванням {llm_eval['llm_explanations']}. "
        + (f"Пройшли обидві перевірки: {llm_eval['llm_ok']} з {llm_eval['llm_explanations']} ({llm_eval['llm_rate']:.3f})." if llm_eval["llm_explanations"] else "Перефразувань немає."),
    ]
    for fail in llm_eval["failed"]:
        lines.append(f"- відхилено {fail['user']} {fail['doc']}: {fail['text']} Чужі сутності: {', '.join(fail['foreign']) or 'назва в лапках поза шляхом або порожня відповідь'}.")
    lines += [
        "",
        "## Новий користувач",
        "",
        "Історії немає. Заявлений інтерес — перший вузол із синтетичного поля interests. Документи з цим вузлом упорядковано за популярністю train інших користувачів.",
        f"Користувачів: {cold['new_user']['users']}. P@5: {cold['new_user']['p5']:.3f}.",
        "",
        "## Новий документ",
        "",
        "d19 має дату 2026-10-01, тому train-кліків по ньому немає. Для користувача зі спільним вузлом дивимось, чи граф ставить d19 у топ-5.",
        f"Користувачів зі спільним вузлом: {cold['new_item']['users_with_shared_node']}. У топ-5: {cold['new_item']['in_top5']}. Частка: {cold['new_item']['rate']:.3f}.",
        "",
    ]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "cold_start.md").write_text("\n".join(lines), encoding="utf-8")


def _interval_claim(report):
    left = report["ndcg_ci95"]["popularity"]
    right = report["ndcg_ci95"]["graph"]
    overlaps = left["low"] <= right["high"] and right["low"] <= left["high"]
    if overlaps:
        return "95% інтервали nDCG@10 популярності й графа перетинаються"
    return "95% інтервали nDCG@10 популярності й графа не перетинаються"


def _claims(report, cold, shown, llm_eval):
    import csv

    chosen = report["chosen"]
    metrics = report["configs"][chosen]
    rows = [
        ("C16-01", "fact", f"у розрахунку {report['users_evaluated']} користувачів після часового розбиття", "data/metrics.json", "V1", "verified", "train до 2026-08-01"),
        ("C16-02", "fact", f"P@5 обраної конфігурації {chosen} дорівнює {metrics['p5']:.3f}", "docs/reco_eval.md", "V4", "verified", ""),
        ("C16-03", "fact", f"R@5 обраної конфігурації {chosen} дорівнює {metrics['r5']:.3f}", "docs/reco_eval.md", "V4", "verified", ""),
        ("C16-04", "fact", f"nDCG@10 обраної конфігурації {chosen} дорівнює {metrics['ndcg10']:.3f}", "docs/reco_eval.md", "V4", "verified", ""),
        ("C16-05", "fact", f"coverage обраної конфігурації {chosen} дорівнює {metrics['coverage']:.3f}", "docs/reco_eval.md", "V4", "verified", ""),
        ("C16-06", "fact", f"novelty обраної конфігурації {chosen} дорівнює {metrics['novelty']:.3f}", "docs/reco_eval.md", "V4", "verified", ""),
        ("C16-07", "fact", "гібрид зібрано RRF з k=60", "reco/recommend.py", "V1", "verified", ""),
        ("C16-08", "fact", f"пояснення зі шляху: {sum(item['ok'] for item in shown)} з {len(shown)} пройшли перевірку", "docs/cold_start.md", "V2", "verified", ""),
        ("C16-09", "fact", "контрольне пояснення з вузлом поза шляхом відхилено", "docs/cold_start.md", "V2", "verified", ""),
        ("C16-10", "fact", f"холодний старт нового користувача, P@5 {cold['new_user']['p5']:.3f}", "docs/cold_start.md", "V4", "verified", f"n={cold['new_user']['users']}"),
        ("C16-11", "fact", f"новий документ d19 у топ-5 у {cold['new_item']['rate']:.3f} користувачів зі спільним вузлом", "docs/cold_start.md", "V4", "verified", ""),
        ("C16-12", "rule", "нотатка d22 не показується ролі public", "docs/reco_eval.md", "V2", "verified", "sensitivity=internal"),
        ("C16-13", "rule", "d20 відсіюється фільтром свіжості", "docs/reco_eval.md", "V2", "verified", "дата 2026-01-15"),
        (
            "C16-14",
            "fact",
            _interval_claim(report),
            "docs/reco_eval.md",
            "V4",
            "verified",
            "бутстреп користувачів, seed 42",
        ),
        ("C16-15", "fact", "користувачі синтетичні, seed 42", "data/interactions_meta.json", "V1", "verified", ""),
        ("C16-16", "fact", "embedding — хеш триграм, не нейромережа", "reco/recommend.py", "V1", "verified", ""),
        ("C16-17", "fact", "test-кліки не входять у популярність і профіль", "reco/recommend.py", "V1", "verified", ""),
        ("C16-18", "fact", f"LLM-перефразування пройшло обидві перевірки в {llm_eval['llm_ok']} з {llm_eval['llm_explanations']} пояснень", "data/explain_eval.json; llm_log/reco.jsonl", "V4", "verified", "u01–u06, топ-5 графа"),
        ("C16-19", "fact", "метод Б ЛР13: мікро-F1 test 0.945", "szuz-labs/13/docs/extraction_eval.md", "V1", "verified", "цифра з ЛР13, тут не перерахована"),
        ("C16-20", "fact", "метод А ЛР13: мікро-F1 test 0.889", "szuz-labs/13/docs/extraction_eval.md", "V1", "verified", "цифра з ЛР13, тут не перерахована"),
        ("C16-21", "hypothesis", "гібрид RRF дає найкращий nDCG@10", "docs/reco_eval.md", "V4", "rejected", f"граф {report['configs']['graph']['ndcg10']:.3f} проти гібрида {report['configs']['hybrid']['ndcg10']:.3f}: kNN і популярність тягнуть гібрид униз"),
        ("C16-22", "hypothesis", "триграмний kNN кращий за популярність за nDCG@10 статистично значуще", "docs/reco_eval.md", "V4", "rejected", "інтервал для kNN не рахувався; різниця середніх 0.044 без бутстрепу не доведена"),
        ("C16-23", "hypothesis", "LLM-перефразування можна показувати без перевірки", "data/explain_eval.json", "V3", "rejected", "перевірка обов'язкова: модель може додати назву поза шляхом; невдалі перефразування замінюються реченням шляху"),
    ]
    path = ROOT / "claims" / "claims.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "type", "claim", "source", "level", "status", "comment"])
        writer.writerows(rows)


def _log():
    path = ROOT / "llm_log" / "reco.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return
    path.write_text(
        json.dumps(
            {
                "model": "none",
                "temperature": None,
                "seed": 42,
                "prompt_version": "path-sentence-v1",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "reason": "пояснення є реченням шляху; перефразування моделлю не було",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
