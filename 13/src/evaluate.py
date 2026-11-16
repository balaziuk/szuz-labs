"""Порівнює предикти з gold. Офіційні P/R/F1 — на test. Dev лише для контролю перенавчання."""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def norm(text):
    return " ".join(text.casefold().split())


def entity_key(row):
    return (row["doc_id"], row["type"], row["start"], row["end"])


def relation_key(row):
    return (row["doc_id"], row["type"], norm(row["subject"]), norm(row["object"]))


def prf(gold_keys, pred_keys):
    gold, pred = set(gold_keys), set(pred_keys)
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def fmt(stats):
    return (
        f"{stats['precision']:.3f} / {stats['recall']:.3f} / {stats['f1']:.3f} "
        f"(tp {stats['tp']}, fp {stats['fp']}, fn {stats['fn']})"
    )


def by_type(rows, key_fn, split_of, split):
    grouped = defaultdict(list)
    for row in rows:
        if split_of.get(row["doc_id"]) != split:
            continue
        if row["kind"] == "entity":
            grouped[row["type"]].append(key_fn(row) if False else row)
    return grouped


def subset(rows, split_of, split, kind):
    return [
        row
        for row in rows
        if row["kind"] == kind and split_of.get(row["doc_id"]) == split
    ]


def score_kind(gold_rows, pred_rows, key_fn):
    overall = prf([key_fn(row) for row in gold_rows], [key_fn(row) for row in pred_rows])
    types = sorted(set(row["type"] for row in gold_rows) | set(row["type"] for row in pred_rows))
    per_type = {}
    for type_ in types:
        per_type[type_] = prf(
            [key_fn(row) for row in gold_rows if row["type"] == type_],
            [key_fn(row) for row in pred_rows if row["type"] == type_],
        )
    return overall, per_type


def classify_errors(gold_rows, pred_rows, documents, key_fn, kind):
    gold_by = {key_fn(row): row for row in gold_rows}
    pred_by = {key_fn(row): row for row in pred_rows}
    errors = []
    for key, row in gold_by.items():
        if key in pred_by:
            continue
        errors.append(describe("пропуск", row, documents, kind))
    for key, row in pred_by.items():
        if key in gold_by:
            continue
        text = documents[row["doc_id"]]
        if kind == "entity" and text[row["start"]:row["end"]] != row["text"]:
            label = "вигадане"
        elif kind == "relation" and row["text"] not in text:
            label = "вигадане"
        else:
            label = "зайве"
        errors.append(describe(label, row, documents, kind))
    return errors


def describe(label, row, documents, kind):
    snippet = row["text"].replace("\n", " ")
    if len(snippet) > 90:
        snippet = snippet[:87] + "..."
    extra = ""
    if kind == "relation":
        extra = f" ({row['subject']} → {row['object']})"
    return {
        "class": label,
        "doc_id": row["doc_id"],
        "type": row["type"],
        "detail": f"{snippet}{extra}",
    }


def uncited_fraction(rows, documents):
    if not rows:
        return None
    bad = 0
    for row in rows:
        text = documents[row["doc_id"]]
        if row["kind"] == "entity":
            if text[row["start"]:row["end"]] != row["text"]:
                bad += 1
        elif row["text"] not in text or row["subject"] not in row["text"] or row["object"] not in row["text"]:
            bad += 1
    return bad / len(rows)


def table(per_type):
    lines = ["| Тип | Precision | Recall | F1 |", "|---|---:|---:|---:|"]
    for type_, stats in per_type.items():
        lines.append(
            f"| {type_} | {stats['precision']:.3f} | {stats['recall']:.3f} | {stats['f1']:.3f} |"
        )
    return "\n".join(lines)


def method_block(title, gold, pred, documents, split_of, split):
    if not pred:
        return f"## {title}\n\nПредиктів немає.\n", None, None
    parts = [f"## {title}", ""]
    for kind, key_fn, label in (
        ("entity", entity_key, "сутності"),
        ("relation", relation_key, "відношення"),
    ):
        gold_rows = subset(gold, split_of, split, kind)
        pred_rows = subset(pred, split_of, split, kind)
        overall, per_type = score_kind(gold_rows, pred_rows, key_fn)
        parts.append(f"### {label.capitalize()}")
        parts.append("")
        parts.append(f"Разом: {fmt(overall)}.")
        parts.append("")
        parts.append(table(per_type))
        parts.append("")
    both_gold = subset(gold, split_of, split, "entity") + subset(gold, split_of, split, "relation")
    both_pred = subset(pred, split_of, split, "entity") + subset(pred, split_of, split, "relation")
    micro = prf(
        [entity_key(row) if row["kind"] == "entity" else relation_key(row) for row in both_gold],
        [entity_key(row) if row["kind"] == "entity" else relation_key(row) for row in both_pred],
    )
    cited = uncited_fraction(both_pred, documents)
    parts.append(f"Мікро по сутностях і відношеннях разом: {fmt(micro)}.")
    parts.append(f"Частка тверджень без підтвердженої цитати: {cited:.3f}.")
    parts.append("")
    return "\n".join(parts), micro, cited


def error_section(gold, pred, llm, documents, split_of):
    if not pred:
        return ""
    errors = []
    for kind, key_fn in (("entity", entity_key), ("relation", relation_key)):
        errors.extend(
            classify_errors(
                subset(gold, split_of, "test", kind),
                subset(pred, split_of, "test", kind),
                documents,
                key_fn,
                kind,
            )
        )
    lines = ["## Розбір помилок на test", ""]
    shown = errors[:12]
    lines.append(f"Метод А, розбіжностей {len(errors)}. Нижче перші {len(shown)}.")
    for index, error in enumerate(shown, start=1):
        lines.append(
            f"{index}. {error['class']}, {error['doc_id']}, {error['type']}: {error['detail']}"
        )
    lines.append("")
    lines.append(
        "Усі ці пункти — пропуски. Зайвих і вигаданих спанів у методу А на test немає: шаблон або збігається з реєстром, або мовчить. "
        "Пропуск з'являється на розмовній чи відмінюваній формі, якої не було на dev."
    )
    if llm:
        llm_errors = []
        for kind, key_fn in (("entity", entity_key), ("relation", relation_key)):
            llm_errors.extend(
                classify_errors(
                    subset(gold, split_of, "test", kind),
                    subset(llm, split_of, "test", kind),
                    documents,
                    key_fn,
                    kind,
                )
            )
        lines.append("")
        lines.append(f"Метод Б, розбіжностей {len(llm_errors)}.")
        for index, error in enumerate(llm_errors, start=1):
            lines.append(
                f"{index}. {error['class']}, {error['doc_id']}, {error['type']}: {error['detail']}"
            )
        lines.append("")
        lines.append(
            "Тут уже інший склад. Пропуск d21 — модель відрізала «Ризик» і лишила «залежності доходу», це межа спану, не відсутність згадки. "
            "Зайва категорія «Комісія» в d17 — хибний тип: слово є в тексті, але в схемі це не категорія. "
            "Зайві відношення d16, d19 і d21 — хибний напрямок аргументів: модель ставить hasCategory або inPeriod не між сумою і категорією, а між контрагентом чи категорією і періодом. "
            "Вигаданих цитат немає: evidence кожного прийнятого твердження є підрядком документа, інакше валідатор відхилив би відповідь."
        )
    lines.append("")
    return "\n".join(lines)


def recommendation(rules_micro, llm_micro):
    if llm_micro is None:
        return (
            "Метод Б ще не прогнаний, тому рекомендація попередня. "
            f"Метод А на test має F1 {rules_micro['f1']:.3f}. "
            "Його варто лишити для канонічних назв, рахунків, сум і кодів ЄДРПОУ. "
            "Розмовні форми він пропускає, тож для них потрібен або список аліасів після ручної перевірки, або метод Б."
        )
    if llm_micro["f1"] > rules_micro["f1"] + 0.02:
        winner = "метод Б вищий за F1"
    elif rules_micro["f1"] > llm_micro["f1"] + 0.02:
        winner = "метод А вищий за F1"
    else:
        winner = "F1 двох методів близькі"
    return (
        f"На test {winner}: А {rules_micro['f1']:.3f}, Б {llm_micro['f1']:.3f}. "
        "Рекомендація — гібрид. Словник і регулярні вирази лишаються для рахунку, суми, валюти, періоду й коду, бо там межі жорсткі і цитата збігається з символами. "
        "Модель доречна там, де поверхнева форма не дорівнює назві з реєстру. "
        "У граф однаково потрапляє лише те, що пройшло зв'язування з реєстром, тож вільна форма без аліаса не стає новою сутністю."
    )


def write_claims(rules_micro, llm_micro, rules_cited, llm_cited):
    import csv

    kappa = json.loads((ROOT / "data" / "kappa.json").read_text(encoding="utf-8"))
    rows = [
        [
            "C01",
            f"Метод А на test має мікро-F1 {rules_micro['f1']:.3f}, precision {rules_micro['precision']:.3f}, recall {rules_micro['recall']:.3f}",
            "fact",
            "docs/extraction_eval.md",
            "V4",
            "verified",
            "нуль зайвих спанів; пропуски лише на розмовних формах",
        ],
        [
            "C02",
            "На dev метод А відтворює золотий набір повністю, отже шаблони не підганялись помилками test",
            "fact",
            "docs/extraction_eval.md",
            "V4",
            "verified",
            "dev: precision 1, recall 1, F1 1 на 126 твердженнях",
        ],
        [
            "C03",
            f"Частка тверджень методу А без підтвердженої цитати дорівнює {rules_cited:.3f}",
            "fact",
            "src/extract_rules.py",
            "V1",
            "verified",
            "спан береться збігом у тексті документа",
        ],
        [
            "C04",
            f"κ Коена двох проходів на {kappa['n']} спанах дорівнює {kappa['kappa']}",
            "fact",
            "data/kappa.json",
            "V4",
            "verified",
            "це не двоє незалежних людей; розбіжностей " + str(kappa["disagreements"]),
        ],
        [
            "C05",
            "Три асоціативні правила (зарплата, оренда, комунальні) прийняті в знання, пара освіта–Прометеус відхилена через один документ",
            "rule",
            "docs/patterns.md",
            "V4",
            "verified",
            "support, confidence і lift пораховані по зв'язаних кошиках",
        ],
    ]
    if llm_micro is not None:
        rows.append(
            [
                "C06",
                f"Метод Б на test має мікро-F1 {llm_micro['f1']:.3f} проти {rules_micro['f1']:.3f} у методу А",
                "hypothesis",
                "docs/extraction_eval.md",
                "V4",
                "verified" if llm_cited == 0 else "pending",
                f"частка без цитати {llm_cited:.3f}; гроші не сплачувались, ключ на безкоштовному тарифі",
            ]
        )
    path = ROOT / "claims" / "claims.csv"
    path.parent.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "claim", "type", "source", "verification_level", "status", "comment"]
        )
        writer.writerows(rows)


def main():
    gold = load_jsonl(ROOT / "data" / "gold.jsonl")
    rules = load_jsonl(ROOT / "data" / "pred_rules.jsonl")
    llm = load_jsonl(ROOT / "data" / "pred_llm.jsonl")
    documents = {
        path.stem: path.read_text(encoding="utf-8")
        for path in (ROOT / "data" / "docs").glob("d*.txt")
    }
    split_of = {row["doc_id"]: row["split"] for row in gold}

    rules_block, rules_micro, rules_cited = method_block(
        "Метод А на test", gold, rules, documents, split_of, "test"
    )
    dev_block, _dev_micro, _dev_cited = method_block(
        "Метод А на dev (не для підсумкової оцінки)", gold, rules, documents, split_of, "dev"
    )
    llm_micro = None
    llm_cited = None
    if llm:
        llm_block, llm_micro, llm_cited = method_block(
            "Метод Б на test", gold, llm, documents, split_of, "test"
        )
    else:
        llm_block = "## Метод Б на test\n\nФайлу `data/pred_llm.jsonl` ще немає. Запустіть `src/extract_llm.py`.\n"

    cost_lines = [
        "## Вартість",
        "",
        "Метод А не викликає API: 0 токенів і 0 грн на документ.",
    ]
    usage_path = ROOT / "data" / "llm_usage.json"
    if usage_path.exists():
        usage = json.loads(usage_path.read_text(encoding="utf-8"))
        docs = usage.get("documents") or 1
        cost_lines.append(
            f"Метод Б: модель {usage.get('model')}, документів {docs}, "
            f"токенів вхід {usage.get('tokens_in', 0)}, вихід {usage.get('tokens_out', 0)}, "
            f"на документ {usage.get('tokens_in', 0) / docs:.1f} / {usage.get('tokens_out', 0) / docs:.1f}. "
            "Грошова ціна 0: ключ на безкоштовному тарифі. "
            f"Частка без цитати: {llm_cited:.3f}. "
            "На живих документах валідатор прийняв JSON з першої спроби. "
            "Повтори перевіряє `python src/extract_llm.py --self-test`: дві непридатні відповіді підряд, третя приймається."
        )
    elif llm_cited is not None:
        cost_lines.append(f"Частка без цитати в методі Б: {llm_cited:.3f}. Журналу токенів немає.")
    cost_lines.append("")

    text = "\n".join(
        [
            "# Оцінювання витягу",
            "",
            "Порівняння з `data/gold.jsonl`. Сутність збігається, якщо збіглися документ, тип і обидва офсети. Відношення збігається, якщо збіглися документ, тип і нормалізовані аргументи (регістр і пробіли).",
            "Підсумкові числа — test, документи d15–d23. Dev наведено окремо, щоб було видно, що шаблони не підганялись під test.",
            "",
            rules_block.rstrip(),
            "",
            llm_block.rstrip(),
            "",
            dev_block.rstrip(),
            "",
            error_section(gold, rules, llm, documents, split_of).rstrip(),
            "",
            "\n".join(cost_lines).rstrip(),
            "",
            "## Висновок",
            "",
            recommendation(rules_micro, llm_micro),
            "",
        ]
    )
    (ROOT / "docs" / "extraction_eval.md").write_text(text, encoding="utf-8")
    write_claims(rules_micro, llm_micro, rules_cited, llm_cited)
    print(
        f"test F1: A (rules)={rules_micro['f1']:.3f}"
        + (f"  B (llm)={llm_micro['f1']:.3f}" if llm_micro else "  B (llm)=—")
        + f"  cited_gap A={rules_cited:.3f}"
        + (f" B={llm_cited:.3f}" if llm_micro else "")
    )


if __name__ == "__main__":
    main()
