"""Асоціативні правила за кошиками документів.

Кошик — множина канонічних контрагентів, категорій і ризиків, зв'язаних у цьому документі.
Суми, валюти, періоди й коди ЄДРПОУ в кошик не входять: вони є майже скрізь і дають тривіальні пари.
"""

import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MECHANISM = {
    frozenset({"Cp_Employer", "Cat_Salary"}): "зарплата приходить від одного роботодавця, це власне визначення категорії",
    frozenset({"Cp_Orendodavets", "Cat_Rent"}): "орендна плата йде орендодавцю за категорією Оренда",
    frozenset({"Cp_Utility", "Cat_Utilities"}): "комунальні рахунки виставляє АТ «Київські комунальні»",
    frozenset({"Cp_Silpo", "Cat_Food"}): "магазин продуктів відповідає категорії Харчування",
    frozenset({"Cp_ATB", "Cat_Food"}): "другий магазин продуктів теж відповідає категорії Харчування",
    frozenset({"Cp_Kyivstar", "Cat_Telecom"}): "рахунок зв'язку виставляє Київстар",
    frozenset({"Cp_Uklon", "Cat_Transport"}): "таксі Уклон сидить у категорії Транспорт",
    frozenset({"Risk_RentConcentration", "Cat_Rent"}): "ризик описаний саме як частка оренди",
    frozenset({"Risk_LiquidityOct", "Cat_Rent"}): "ризик ліквідності в реєстрі прив'язаний до оренди",
    frozenset({"Risk_RentIncrease", "Cat_Rent"}): "ризик ціни стосується орендної плати",
    frozenset({"Risk_UtilitiesSeasonal", "Cat_Utilities"}): "сезонний ризик описаний для комунальних платежів",
    frozenset({"Risk_IncomeDependency", "Cat_Salary"}): "залежність доходу стосується зарплатної категорії",
    frozenset({"Risk_CurrencyFreelance", "Cat_Freelance"}): "валютний ризик у реєстрі стосується фрилансу в USD",
    frozenset({"Cp_Prometheus", "Cat_Education"}): "освітні витрати в реєстрі віднесені до ГО «Прометеус»",
}


def baskets():
    linked = json.loads((ROOT / "data" / "linked.json").read_text(encoding="utf-8"))
    split = {}
    with (ROOT / "data" / "gold.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            split[row["doc_id"]] = row["split"]
    grouped = defaultdict(set)
    for row in linked:
        if row["canonical_type"] in {"Counterparty", "Category", "Risk"}:
            grouped[row["doc_id"]].add(row["canonical_id"])
    return grouped, split


def metrics(grouped):
    docs = list(grouped)
    n = len(docs)
    support_item = defaultdict(int)
    support_pair = defaultdict(int)
    for items in grouped.values():
        for item in items:
            support_item[item] += 1
        for left, right in combinations(sorted(items), 2):
            support_pair[frozenset({left, right})] += 1
    rules = []
    for pair, both in support_pair.items():
        left, right = sorted(pair)
        for antecedent, consequent in ((left, right), (right, left)):
            confidence = both / support_item[antecedent]
            base = support_item[consequent] / n
            lift = confidence / base if base else 0
            rules.append(
                {
                    "antecedent": antecedent,
                    "consequent": consequent,
                    "both": both,
                    "support": both / n,
                    "confidence": confidence,
                    "lift": lift,
                    "dev": sum(
                        1
                        for doc, items in grouped.items()
                        if split_has(doc, items, pair, "dev")
                    ),
                    "test": sum(
                        1
                        for doc, items in grouped.items()
                        if split_has(doc, items, pair, "test")
                    ),
                }
            )
    return n, rules


def split_has(doc, items, pair, wanted):
    return SPLIT.get(doc) == wanted and pair <= items


SPLIT = {}


def decide(rule):
    pair = frozenset({rule["antecedent"], rule["consequent"]})
    mechanism = MECHANISM.get(pair)
    stable = rule["dev"] > 0 and rule["test"] > 0 and rule["both"] >= 3
    chance = rule["lift"] >= 1.5
    if mechanism and stable and chance:
        return "у знання", mechanism, "пара є і в dev, і в test, lift помітно вищий за 1, механізм збігається з реєстром"
    reasons = []
    if not mechanism:
        reasons.append("окремого механізму в реєстрі немає, пара може бути сусідством у нотатці")
    if not stable:
        reasons.append("пара тримається менше ніж на трьох документах або лише в одній частині корпусу")
    if not chance:
        reasons.append("lift близький до 1, тобто спільна поява схожа на випадкову")
    return "відхилити", mechanism or "немає", "; ".join(reasons)


def main():
    global SPLIT
    grouped, SPLIT = baskets()
    n, rules = metrics(grouped)
    ranked = sorted(rules, key=lambda rule: (-rule["lift"], -rule["both"], rule["antecedent"]))
    accepted = []
    rejected = []
    seen_pairs = set()
    for rule in ranked:
        pair = frozenset({rule["antecedent"], rule["consequent"]})
        if pair in seen_pairs:
            continue
        # лишаємо напрямок із вищою впевненістю: перший у відсортованому списку
        seen_pairs.add(pair)
        decision, mechanism, why = decide(rule)
        packed = {**rule, "decision": decision, "mechanism": mechanism, "why": why}
        if decision == "у знання":
            accepted.append(packed)
        else:
            rejected.append(packed)
    chosen = accepted[:3]
    if rejected:
        chosen.append(rejected[0])
    lines = [
        "# Патерни",
        "",
        f"Кошиків (документів зі зв'язаними сутностями): {n}. Рахуються пари контрагент / категорія / ризик. "
        "Support — частка документів із обома елементами. Confidence — частка документів антецедента, де є консеквент. "
        "Lift — confidence, поділена на частку документів із консеквентом.",
        "",
        "Поріг прийняття: щонайменше 3 документи, обидві частини корпусу, lift ≥ 1.5 і зрозумілий механізм з реєстру. Інакше правило відхиляється і в знання не йде.",
        "",
    ]
    for index, rule in enumerate(chosen, start=1):
        lines += [
            f"## Правило {index}. {rule['antecedent']} → {rule['consequent']}",
            "",
            f"Support {rule['support']:.3f} ({rule['both']} із {n}), confidence {rule['confidence']:.3f}, lift {rule['lift']:.3f}. "
            f"Документів dev: {rule['dev']}, test: {rule['test']}.",
            "",
            f"Випадковість. Lift {rule['lift']:.3f}. Значення близько до 1 означало б, що консеквент і так частий. Тут поріг прийняття 1.5.",
            "",
            f"Механізм. {rule['mechanism']}.",
            "",
            f"Стійкість. Пара {'є' if rule['dev'] and rule['test'] else 'не є'} в обох частинах корпусу, разом документів {rule['both']}.",
            "",
            f"Рішення: {rule['decision']}. {rule['why']}.",
            "",
        ]
    if len([rule for rule in chosen if rule["decision"] == "у знання"]) < 3:
        raise SystemExit("прийнятих правил менше за 3")
    (ROOT / "docs" / "patterns.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"accepted={len(accepted)} rejected_candidates={len(rejected)} written={len(chosen)}")


if __name__ == "__main__":
    main()
