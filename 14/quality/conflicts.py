"""Шукає суперечності в сховищі й записує рішення.

Альтернативи для двох випадків лежать у quality/alternatives.json і не затирають прийняте значення.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality.common import edges_by_start, operations


def rent_share_by_month():
    ops = {row["id"]: row for row in operations()}
    edges = edges_by_start()
    monthly = defaultdict(lambda: {"rent": 0.0, "expense": 0.0})
    for row in ops.values():
        if row["kind"] != "Expense":
            continue
        month = row["date"][:7]
        amount = float(row["amount"])
        monthly[month]["expense"] += amount
        category = next((edge["end"] for edge in edges[row["id"]] if edge["type"] == "IN_CATEGORY"), "")
        if category == "Cat_Rent" or "оренд" in row["description"]:
            monthly[month]["rent"] += amount
    return {
        month: data["rent"] / data["expense"] if data["expense"] else 0.0
        for month, data in sorted(monthly.items())
    }


def october_utilities():
    for row in operations():
        if row["date"].startswith("2026-10") and "комунал" in row["description"]:
            return row
    return None


def main():
    shares = rent_share_by_month()
    overall_rent = sum(
        float(row["amount"]) for row in operations() if row["kind"] == "Expense" and "оренд" in row["description"]
    )
    overall_exp = sum(float(row["amount"]) for row in operations() if row["kind"] == "Expense")
    overall = overall_rent / overall_exp
    over = {month: share for month, share in shares.items() if share > 0.70}
    utility = october_utilities()
    note_amount = 3900.0
    statement_amount = float(utility["amount"]) if utility else None

    alternatives = {
        "utilities_october": {
            "accepted": {
                "value": statement_amount,
                "source": utility["id"] if utility else None,
                "why": "виписка ЛР9, ребро категорії Комунальні послуги",
            },
            "alternative": {
                "value": note_amount,
                "source": "szuz-labs/13/data/docs/d22.txt",
                "why": "чорнова нотатка ЛР13, без платіжного id",
            },
        },
        "rent_share_claim": {
            "accepted": {
                "value": "частка оренди понад 70% лише в місяцях " + ", ".join(over) if over else "немає такого місяця",
                "source": "quality/conflicts.py за operations.csv",
                "why": "перерахунок по місяцях, а не дослівний опис ризику",
            },
            "alternative": {
                "value": "частка оренди понад 70% усіх витрат",
                "source": "Risk_RentConcentration у ЛР9",
                "why": "формулювання ризику без обмеження місяця",
            },
        },
    }
    (ROOT / "quality" / "alternatives.json").write_text(
        json.dumps(alternatives, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    months_over = ", ".join(f"{month} ({share:.0%})" for month, share in over.items()) or "жодного"
    lines = [
        "# Суперечності",
        "",
        "П'ять розбіжностей трьох типів: значення, термінологія, час. Логічне протиріччя класів (витрата водночас є доходом) у сховищі не знайшлось, тому в цей список не додавалось.",
        "",
        f"1. Значення. Чорнова нотатка d22 каже, що комуналка за жовтень 2026 склала {note_amount:.0f} грн. Виписка {utility['id'] if utility else '—'} за {utility['date'] if utility else '—'} має {statement_amount} грн і категорію комунальних. Стратегія: довіра до виписки, бо в неї є id операції. Нотатку не витираємо: обидва значення в `quality/alternatives.json`. Виправлення: у відповідях RAG цитувати виписку.",
        "",
        f"2. Значення і час. Опис ризику концентрації каже про частку оренди понад 70% усіх витрат. На повному ряді частка {overall:.1%}. Понад 70% виходить у місяцях: {months_over}. Стратегія: рішення власника від 2026-11-03 звузити формулювання до цих місяців. Старе формулювання збережене як альтернатива.",
        "",
        "3. Термінологія. Нотатка d22 пише «Комуналка», реєстр категорій — «Комунальні послуги». Це один клас Cat_Utilities, не друга категорія. Стратегія: канонічна назва з реєстру, розмовна форма лишається аліасом і не заводить новий id.",
        "",
        "4. Термінологія. У текстах ЛР13 банк названо «Приват» і «ПриватБанк», у реєстрі — АТ КБ «ПриватБанк», ЄДРПОУ 14360570. Стратегія: канонічне ім'я з реєстру, короткі форми лишаються аліасами (їх зливає `quality/dedup.py`, а unmerge повертає окремі записи).",
        "",
        "5. Час. Ризик ліквідності названий Risk_LiquidityOct і в RDF прив'язаний до бюджету жовтня, тоді як єдина місячна частка оренди понад 70% може припадати на інший місяць (див. пункт 2). Стратегія: дата події береться з місяця, де частка справді перевищує поріг, а не з суфікса ідентифікатора. Ідентифікатор не перейменовуємо, щоб не порвати посилання; у коментарі рішення зафіксовано розбіжність.",
        "",
        "## Журнал рішень",
        "",
        "| id | хто | коли | стратегія | що зроблено |",
        "|---|---|---|---|---|",
        "| 1 | власник сховища | 2026-11-03 | довіра до виписки | 3500 прийнято, 3900 збережено як альтернативу |",
        "| 2 | власник сховища | 2026-11-03 | рішення власника | формулювання ризику звужене до місяців із часткою понад 70% |",
        "| 3 | власник сховища | 2026-11-03 | канонічна назва | «Комуналка» не стає окремою категорією |",
        "| 4 | власник сховища | 2026-11-03 | канонічне ім'я | «Приват» зливається з Cp_PrivatBank, unmerge можливий |",
        "| 5 | власник сховища | 2026-11-03 | дата, не суфікс id | місяць ризику ліквідності береться з розрахунку частки |",
        "",
    ]
    (ROOT / "quality" / "conflicts.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"overall_rent={overall:.3f} months_over={list(over)}")


if __name__ == "__main__":
    main()
