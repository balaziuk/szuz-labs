"""Збирає корпус, золотий набір А і контрольний прохід В.

Запуск з каталогу szuz-labs/13: python src/build_corpus.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kappa import cohen_kappa
from schema import ALIASES, gazetteer

# Другий прохід інакше ставить мітку на цих спанах. Решта збігається з А.
OVERRIDES = {
    ("d01", "UAH", 0): "O",
    ("d01", "2026-04", 0): "Date",
    ("d02", "87654321", 0): "Account",
    ("d03", "грн", 0): "O",
    ("d05", "2026-04", 0): "Date",
}


def locate(text, surface, occ=0):
    start = 0
    found = -1
    seen = 0
    while True:
        index = text.find(surface, start)
        if index < 0:
            break
        if seen == occ:
            found = index
            break
        seen += 1
        start = index + 1
    if found < 0:
        raise SystemExit(f"не знайдено {surface!r} occ={occ}, знайдено входжень: {seen}")
    return found, found + len(surface)


def line_bounds(text, pos):
    begin = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return begin, end


def entity(surface, type_, occ=0):
    return {"surface": surface, "type": type_, "occ": occ}


def relation(type_, subject, object_, subject_occ=0, object_occ=0):
    return {
        "type": type_,
        "subject": subject,
        "object": object_,
        "subject_occ": subject_occ,
        "object_occ": object_occ,
    }


DOCS = [
    {
        "id": "d01",
        "split": "dev",
        "title": "Виписка поточного рахунку за квітень 2026",
        "source": "Виписка хаба за даними ЛР9 (Op_00002 зарплата 30000, Op_00003 оренда 15000)",
        "source_kind": "statement",
        "date": "2026-04-30",
        "text": (
            "Виписка внутрішнього хаба за квітень.\n"
            "Поточний рахунок UA123456789 має валюту UAH.\n"
            "1 квітня зараховано 30000.00 грн від ТОВ «Роботодавець», категорія Заробітна плата, період 2026-04.\n"
            "2 квітня сплачено 15000.00 грн контрагенту ТОВ «Орендодавець», категорія Оренда, період 2026-04.\n"
        ),
        "entities": [
            entity("UA123456789", "Account"),
            entity("UAH", "Currency"),
            entity("30000.00", "Amount"),
            entity("грн", "Currency"),
            entity("ТОВ «Роботодавець»", "Counterparty"),
            entity("Заробітна плата", "Category"),
            entity("2026-04", "Period"),
            entity("15000.00", "Amount"),
            entity("грн", "Currency", 1),
            entity("ТОВ «Орендодавець»", "Counterparty"),
            entity("Оренда", "Category"),
            entity("2026-04", "Period", 1),
        ],
        "relations": [
            relation("receivedFrom", "30000.00", "ТОВ «Роботодавець»"),
            relation("hasCategory", "30000.00", "Заробітна плата"),
            relation("inPeriod", "30000.00", "2026-04"),
            relation("paidTo", "15000.00", "ТОВ «Орендодавець»"),
            relation("hasCategory", "15000.00", "Оренда"),
            relation("inPeriod", "15000.00", "2026-04", 0, 1),
        ],
    },
    {
        "id": "d02",
        "split": "dev",
        "title": "Картка роботодавця",
        "source": "Реєстр контрагентів ЛР9, Cp_Employer",
        "source_kind": "registry",
        "date": "2026-04-01",
        "text": (
            "Картка контрагента з реєстру хаба.\n"
            "ТОВ «Роботодавець» має код ЄДРПОУ 87654321 і тип клієнт.\n"
            "Щомісяця від цього контрагента очікується дохід категорії Заробітна плата.\n"
        ),
        "entities": [
            entity("ТОВ «Роботодавець»", "Counterparty"),
            entity("87654321", "Edrpou"),
            entity("Заробітна плата", "Category"),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Роботодавець»", "87654321"),
        ],
    },
    {
        "id": "d03",
        "split": "dev",
        "title": "Пам'ятка до договору оренди",
        "source": "Реєстр ЛР9, Cp_Orendodavets, ліміт категорії Оренда 15000",
        "source_kind": "policy",
        "date": "2026-04-01",
        "text": (
            "Пам'ятка до договору оренди житла.\n"
            "Контрагент ТОВ «Орендодавець», код ЄДРПОУ 12345678.\n"
            "Ліміт категорії Оренда становить 15000.00 грн на період 2026-04.\n"
        ),
        "entities": [
            entity("ТОВ «Орендодавець»", "Counterparty"),
            entity("12345678", "Edrpou"),
            entity("Оренда", "Category"),
            entity("15000.00", "Amount"),
            entity("грн", "Currency"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Орендодавець»", "12345678"),
            relation("hasBudgetLimit", "Оренда", "15000.00"),
        ],
    },
    {
        "id": "d04",
        "split": "dev",
        "title": "Політика бюджетів",
        "source": "Картки категорій ЛР9: ліміт комунальних 4000, харчування без ліміту",
        "source_kind": "policy",
        "date": "2026-04-01",
        "text": (
            "Політика бюджетів домогосподарства, затверджена для хаба.\n"
            "Ліміт категорії Комунальні послуги становить 4000.00 грн.\n"
            "Окремого ліміту для категорії Харчування у картці бюджету немає.\n"
            "Період дії політики: 2026-04.\n"
            "Рахунки за комунальні послуги надходять від АТ «Київські комунальні».\n"
        ),
        "entities": [
            entity("Комунальні послуги", "Category"),
            entity("4000.00", "Amount"),
            entity("грн", "Currency"),
            entity("Харчування", "Category"),
            entity("2026-04", "Period"),
            entity("АТ «Київські комунальні»", "Counterparty"),
        ],
        "relations": [
            relation("hasBudgetLimit", "Комунальні послуги", "4000.00"),
        ],
    },
    {
        "id": "d05",
        "split": "dev",
        "title": "Чеки продуктів",
        "source": "Виписка ЛР9: Op_00004 продукти 1690, Op_00009 продукти 850; реєстр Сільпо й АТБ",
        "source_kind": "receipt",
        "date": "2026-04-15",
        "text": (
            "Чеки продуктів за квітень.\n"
            "У ТОВ «Сільпо-Фуд» (ЄДРПОУ 40720198) сплачено 1690.00 грн, категорія Харчування, період 2026-04.\n"
            "У ТОВ «АТБ-Маркет» (ЄДРПОУ 30487219) сплачено 850.00 грн, категорія Харчування.\n"
        ),
        "entities": [
            entity("ТОВ «Сільпо-Фуд»", "Counterparty"),
            entity("40720198", "Edrpou"),
            entity("1690.00", "Amount"),
            entity("грн", "Currency"),
            entity("Харчування", "Category"),
            entity("2026-04", "Period"),
            entity("ТОВ «АТБ-Маркет»", "Counterparty"),
            entity("30487219", "Edrpou"),
            entity("850.00", "Amount"),
            entity("грн", "Currency", 1),
            entity("Харчування", "Category", 1),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Сільпо-Фуд»", "40720198"),
            relation("paidTo", "1690.00", "ТОВ «Сільпо-Фуд»"),
            relation("hasCategory", "1690.00", "Харчування"),
            relation("inPeriod", "1690.00", "2026-04"),
            relation("identifiedBy", "ТОВ «АТБ-Маркет»", "30487219"),
            relation("paidTo", "850.00", "ТОВ «АТБ-Маркет»"),
            relation("hasCategory", "850.00", "Харчування", 0, 1),
        ],
    },
    {
        "id": "d06",
        "split": "dev",
        "title": "Рахунок за зв'язок",
        "source": "Виписка ЛР9 Op_00007, 250 грн; реєстр Cp_Kyivstar",
        "source_kind": "receipt",
        "date": "2026-04-05",
        "text": (
            "Рахунок за зв'язок.\n"
            "Контрагенту ПрАТ «Київстар» (ЄДРПОУ 21673832) сплачено 250.00 грн, категорія Зв'язок та інтернет, період 2026-04.\n"
        ),
        "entities": [
            entity("ПрАТ «Київстар»", "Counterparty"),
            entity("21673832", "Edrpou"),
            entity("250.00", "Amount"),
            entity("грн", "Currency"),
            entity("Зв'язок та інтернет", "Category"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "ПрАТ «Київстар»", "21673832"),
            relation("paidTo", "250.00", "ПрАТ «Київстар»"),
            relation("hasCategory", "250.00", "Зв'язок та інтернет"),
            relation("inPeriod", "250.00", "2026-04"),
        ],
    },
    {
        "id": "d07",
        "split": "dev",
        "title": "Поїздки таксі",
        "source": "Виписка ЛР9 Op_00006, таксі 145 грн; реєстр Cp_Uklon",
        "source_kind": "receipt",
        "date": "2026-04-03",
        "text": (
            "Поїздки таксі.\n"
            "Контрагенту ТОВ «Уклон» (ЄДРПОУ 39932340) сплачено 145.00 грн, категорія Транспорт, період 2026-04.\n"
        ),
        "entities": [
            entity("ТОВ «Уклон»", "Counterparty"),
            entity("39932340", "Edrpou"),
            entity("145.00", "Amount"),
            entity("грн", "Currency"),
            entity("Транспорт", "Category"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Уклон»", "39932340"),
            relation("paidTo", "145.00", "ТОВ «Уклон»"),
            relation("hasCategory", "145.00", "Транспорт"),
            relation("inPeriod", "145.00", "2026-04"),
        ],
    },
    {
        "id": "d08",
        "split": "dev",
        "title": "Аптека",
        "source": "Картка Cp_Apteka з реєстру ЛР9; сума 320 грн є нотаткою категорії, окремого Op у виписці немає",
        "source_kind": "note",
        "date": "2026-04-18",
        "text": (
            "Аптека.\n"
            "Контрагенту ТОВ «Аптека АНЦ» (ЄДРПОУ 36151140) сплачено 320.00 грн, категорія Здоров'я, період 2026-04.\n"
        ),
        "entities": [
            entity("ТОВ «Аптека АНЦ»", "Counterparty"),
            entity("36151140", "Edrpou"),
            entity("320.00", "Amount"),
            entity("грн", "Currency"),
            entity("Здоров'я", "Category"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Аптека АНЦ»", "36151140"),
            relation("paidTo", "320.00", "ТОВ «Аптека АНЦ»"),
            relation("hasCategory", "320.00", "Здоров'я"),
            relation("inPeriod", "320.00", "2026-04"),
        ],
    },
    {
        "id": "d09",
        "split": "dev",
        "title": "Фриланс-оплата",
        "source": "Виписка ЛР9 Op_00013, 8000 USD; реєстр Cp_FreelanceClient",
        "source_kind": "statement",
        "date": "2026-04-13",
        "text": (
            "Оплата за проєкт.\n"
            "Від ФОП Іваненко (ЄДРПОУ 99887766) зараховано 8000.00 USD, категорія Фриланс, період 2026-04.\n"
        ),
        "entities": [
            entity("ФОП Іваненко", "Counterparty"),
            entity("99887766", "Edrpou"),
            entity("8000.00", "Amount"),
            entity("USD", "Currency"),
            entity("Фриланс", "Category"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "ФОП Іваненко", "99887766"),
            relation("receivedFrom", "8000.00", "ФОП Іваненко"),
            relation("hasCategory", "8000.00", "Фриланс"),
            relation("inPeriod", "8000.00", "2026-04"),
        ],
    },
    {
        "id": "d10",
        "split": "dev",
        "title": "Накопичувальний рахунок",
        "source": "Рахунок UA987654321 і категорії Відсотки та Переказ на накопичення з ЛР9; 42.50 грн — нотатка, не рядок виписки",
        "source_kind": "statement",
        "date": "2026-04-20",
        "text": (
            "Накопичувальний рахунок UA987654321, валюта UAH.\n"
            "Зараховано відсотки 42.50 грн, категорія Відсотки за депозитом, період 2026-04.\n"
            "Окремо виконано переказ 3000.00 грн, категорія Переказ на накопичення.\n"
        ),
        "entities": [
            entity("UA987654321", "Account"),
            entity("UAH", "Currency"),
            entity("42.50", "Amount"),
            entity("грн", "Currency"),
            entity("Відсотки за депозитом", "Category"),
            entity("2026-04", "Period"),
            entity("3000.00", "Amount"),
            entity("грн", "Currency", 1),
            entity("Переказ на накопичення", "Category"),
        ],
        "relations": [
            relation("hasCategory", "42.50", "Відсотки за депозитом"),
            relation("inPeriod", "42.50", "2026-04"),
            relation("hasCategory", "3000.00", "Переказ на накопичення"),
        ],
    },
    {
        "id": "d11",
        "split": "dev",
        "title": "Картка студії",
        "source": "Реєстр ЛР9, Cp_DigitalStudio",
        "source_kind": "registry",
        "date": "2026-05-01",
        "text": (
            "Картка клієнта студії.\n"
            "Контрагент ТОВ «Діджитал Студіо» має код ЄДРПОУ 41122334.\n"
            "Очікуваний дохід відносять до категорії Фриланс.\n"
        ),
        "entities": [
            entity("ТОВ «Діджитал Студіо»", "Counterparty"),
            entity("41122334", "Edrpou"),
            entity("Фриланс", "Category"),
        ],
        "relations": [
            relation("identifiedBy", "ТОВ «Діджитал Студіо»", "41122334"),
        ],
    },
    {
        "id": "d12",
        "split": "dev",
        "title": "Ризик концентрації витрат",
        "source": "Реєстр ризиків ЛР9, Risk_RentConcentration",
        "source_kind": "risk_register",
        "date": "2026-04-30",
        "text": (
            "Реєстр ризиків хаба, період 2026-04.\n"
            "Ризик концентрації витрат стосується категорії Оренда.\n"
        ),
        "entities": [
            entity("2026-04", "Period"),
            entity("Ризик концентрації витрат", "Risk"),
            entity("Оренда", "Category"),
        ],
        "relations": [
            relation("concerns", "Ризик концентрації витрат", "Оренда"),
        ],
    },
    {
        "id": "d13",
        "split": "dev",
        "title": "Ризик ліквідності",
        "source": "Реєстр ризиків ЛР9, Risk_LiquidityOct",
        "source_kind": "risk_register",
        "date": "2026-10-01",
        "text": (
            "Ризик ліквідності стосується категорії Оренда у періоді 2026-10.\n"
            "Опис: значні витрати на оренду при коливанні доходів.\n"
        ),
        "entities": [
            entity("Ризик ліквідності", "Risk"),
            entity("Оренда", "Category"),
            entity("2026-10", "Period"),
        ],
        "relations": [
            relation("concerns", "Ризик ліквідності", "Оренда"),
            relation("inPeriod", "Ризик ліквідності", "2026-10"),
        ],
    },
    {
        "id": "d14",
        "split": "dev",
        "title": "Валютний ризик",
        "source": "Реєстр ризиків ЛР9, Risk_CurrencyFreelance",
        "source_kind": "risk_register",
        "date": "2026-04-13",
        "text": (
            "Валютний ризик стосується категорії Фриланс у періоді 2026-04.\n"
            "Надходження позначені валютою USD.\n"
        ),
        "entities": [
            entity("Валютний ризик", "Risk"),
            entity("Фриланс", "Category"),
            entity("2026-04", "Period"),
            entity("USD", "Currency"),
        ],
        "relations": [
            relation("concerns", "Валютний ризик", "Фриланс"),
            relation("inPeriod", "Валютний ризик", "2026-04"),
        ],
    },
    {
        "id": "d15",
        "split": "test",
        "title": "Платіжка за житло",
        "source": "Виписка ЛР9 Op_00010, комунальні 4200; реєстр Cp_Utility",
        "source_kind": "receipt",
        "date": "2026-04-10",
        "text": (
            "Платіжка за житло.\n"
            "Контрагенту АТ «Київські комунальні» (ЄДРПОУ 33445566) сплачено 4200.00 грн, категорія Комунальні послуги, період 2026-04.\n"
        ),
        "entities": [
            entity("АТ «Київські комунальні»", "Counterparty"),
            entity("33445566", "Edrpou"),
            entity("4200.00", "Amount"),
            entity("грн", "Currency"),
            entity("Комунальні послуги", "Category"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("identifiedBy", "АТ «Київські комунальні»", "33445566"),
            relation("paidTo", "4200.00", "АТ «Київські комунальні»"),
            relation("hasCategory", "4200.00", "Комунальні послуги"),
            relation("inPeriod", "4200.00", "2026-04"),
        ],
    },
    {
        "id": "d16",
        "split": "test",
        "title": "Картка Прометеус",
        "source": "Реєстр ЛР9, Cp_Prometheus",
        "source_kind": "registry",
        "date": "2026-06-01",
        "text": (
            "Картка постачальника навчання.\n"
            "Витрати на ГО «Прометеус» (ЄДРПОУ 39185340) відносять до категорії Освіта.\n"
        ),
        "entities": [
            entity("ГО «Прометеус»", "Counterparty"),
            entity("39185340", "Edrpou"),
            entity("Освіта", "Category"),
        ],
        "relations": [
            relation("identifiedBy", "ГО «Прометеус»", "39185340"),
        ],
    },
    {
        "id": "d17",
        "split": "test",
        "title": "Комісія банку",
        "source": "Реєстр ЛР9, Cp_PrivatBank; 15 грн — нотатка про комісію, не рядок виписки",
        "source_kind": "note",
        "date": "2026-04-28",
        "text": (
            "Комісія банку.\n"
            "У Приват сплачено 15.00 грн за обслуговування рахунку UA123456789, період 2026-04.\n"
            "Повна назва в реєстрі — АТ КБ «ПриватБанк», код ЄДРПОУ 14360570.\n"
        ),
        "entities": [
            entity("Приват", "Counterparty"),
            entity("15.00", "Amount"),
            entity("грн", "Currency"),
            entity("UA123456789", "Account"),
            entity("2026-04", "Period"),
            entity("АТ КБ «ПриватБанк»", "Counterparty"),
            entity("14360570", "Edrpou"),
        ],
        "relations": [
            relation("paidTo", "15.00", "Приват"),
            relation("inPeriod", "15.00", "2026-04"),
            relation("identifiedBy", "АТ КБ «ПриватБанк»", "14360570"),
        ],
    },
    {
        "id": "d18",
        "split": "test",
        "title": "Глосарій категорій",
        "source": "Категорії ЛР9: Заробітна плата, Оренда з лімітом 15000, Транспорт без ліміту",
        "source_kind": "glossary",
        "date": "2026-04-01",
        "text": (
            "Глосарій категорій хаба.\n"
            "Категорія Заробітна плата належить до доходів.\n"
            "Категорія Оренда є витратою з лімітом 15000.00 грн.\n"
            "Категорія Транспорт не має окремого ліміту в картці.\n"
        ),
        "entities": [
            entity("Заробітна плата", "Category"),
            entity("Оренда", "Category"),
            entity("15000.00", "Amount"),
            entity("грн", "Currency"),
            entity("Транспорт", "Category"),
        ],
        "relations": [
            relation("hasBudgetLimit", "Оренда", "15000.00"),
        ],
    },
    {
        "id": "d19",
        "split": "test",
        "title": "Ризик зростання ціни",
        "source": "Реєстр ризиків ЛР9, Risk_RentIncrease, і Cp_Orendodavets",
        "source_kind": "risk_register",
        "date": "2026-10-01",
        "text": (
            "Ризик зростання ціни стосується категорії Оренда у періоді 2026-10.\n"
            "Можливе підвищення орендної плати контрагентом ТОВ «Орендодавець».\n"
        ),
        "entities": [
            entity("Ризик зростання ціни", "Risk"),
            entity("Оренда", "Category"),
            entity("2026-10", "Period"),
            entity("ТОВ «Орендодавець»", "Counterparty"),
        ],
        "relations": [
            relation("concerns", "Ризик зростання ціни", "Оренда"),
            relation("inPeriod", "Ризик зростання ціни", "2026-10"),
        ],
    },
    {
        "id": "d20",
        "split": "test",
        "title": "Сезонний ризик",
        "source": "Реєстр ризиків ЛР9, Risk_UtilitiesSeasonal, і Cp_Utility",
        "source_kind": "risk_register",
        "date": "2026-01-15",
        "text": (
            "Сезонний ризик стосується категорії Комунальні послуги у періоді 2026-01.\n"
            "Контрагент АТ «Київські комунальні» (ЄДРПОУ 33445566) виставляє ці рахунки.\n"
        ),
        "entities": [
            entity("Сезонний ризик", "Risk"),
            entity("Комунальні послуги", "Category"),
            entity("2026-01", "Period"),
            entity("АТ «Київські комунальні»", "Counterparty"),
            entity("33445566", "Edrpou"),
        ],
        "relations": [
            relation("concerns", "Сезонний ризик", "Комунальні послуги"),
            relation("inPeriod", "Сезонний ризик", "2026-01"),
            relation("identifiedBy", "АТ «Київські комунальні»", "33445566"),
        ],
    },
    {
        "id": "d21",
        "split": "test",
        "title": "Ризик залежності доходу",
        "source": "Реєстр ризиків ЛР9, Risk_IncomeDependency, і Cp_Employer",
        "source_kind": "risk_register",
        "date": "2026-04-01",
        "text": (
            "Ризик залежності доходу стосується категорії Заробітна плата.\n"
            "Контрагент ТОВ «Роботодавець» (ЄДРПОУ 87654321) є єдиним джерелом цього доходу, період 2026-04.\n"
        ),
        "entities": [
            entity("Ризик залежності доходу", "Risk"),
            entity("Заробітна плата", "Category"),
            entity("ТОВ «Роботодавець»", "Counterparty"),
            entity("87654321", "Edrpou"),
            entity("2026-04", "Period"),
        ],
        "relations": [
            relation("concerns", "Ризик залежності доходу", "Заробітна плата"),
            relation("identifiedBy", "ТОВ «Роботодавець»", "87654321"),
        ],
    },
    {
        "id": "d22",
        "split": "test",
        "title": "Чорнова нотатка жовтня",
        "source": "Чорнова нотатка: оренда 15000 як у виписці, комуналка 3900 не збігається з Op_00010 (4200) і лишається чернеткою",
        "source_kind": "note",
        "date": "2026-10-20",
        "text": (
            "Коротка нотатка жовтня.\n"
            "З рахунку UA123456789 сплачено орендодавцю 15000.00 грн, період 2026-10.\n"
            "Комуналка за той самий місяць склала 3900.00 грн.\n"
        ),
        "entities": [
            entity("UA123456789", "Account"),
            entity("орендодавцю", "Counterparty"),
            entity("15000.00", "Amount"),
            entity("грн", "Currency"),
            entity("2026-10", "Period"),
            entity("Комуналка", "Category"),
            entity("3900.00", "Amount"),
            entity("грн", "Currency", 1),
        ],
        "relations": [
            relation("paidTo", "15000.00", "орендодавцю"),
            relation("inPeriod", "15000.00", "2026-10"),
            relation("hasCategory", "3900.00", "Комуналка"),
        ],
    },
    {
        "id": "d23",
        "split": "test",
        "title": "Чорновий розбір розмовних назв",
        "source": "Чорнова нотатка з розмовними назвами контрагентів; суми 2000, 640 і 250 не прив'язані до окремих Op, крім того що 250 збігається з типовим рахунком зв'язку",
        "source_kind": "note",
        "date": "2026-07-01",
        "text": (
            "Чорнова нотатка розбору.\n"
            "Сплачено 2000.00 грн ФОПу Іваненку, період 2026-07.\n"
            "Сплачено 640.00 грн у сільпо, категорія їжа.\n"
            "Сплачено 250.00 грн за київстар, категорія зв'язок.\n"
        ),
        "entities": [
            entity("2000.00", "Amount"),
            entity("грн", "Currency"),
            entity("ФОПу Іваненку", "Counterparty"),
            entity("2026-07", "Period"),
            entity("640.00", "Amount"),
            entity("грн", "Currency", 1),
            entity("сільпо", "Counterparty"),
            entity("їжа", "Category"),
            entity("250.00", "Amount"),
            entity("грн", "Currency", 2),
            entity("київстар", "Counterparty"),
            entity("зв'язок", "Category"),
        ],
        "relations": [
            relation("paidTo", "2000.00", "ФОПу Іваненку"),
            relation("inPeriod", "2000.00", "2026-07"),
            relation("paidTo", "640.00", "сільпо"),
            relation("hasCategory", "640.00", "їжа"),
            relation("paidTo", "250.00", "київстар"),
            relation("hasCategory", "250.00", "зв'язок"),
        ],
    },
]


def build_rows(doc):
    text = doc["text"]
    entities = []
    for spec in doc["entities"]:
        start, end = locate(text, spec["surface"], spec["occ"])
        if text[start:end] != spec["surface"]:
            raise SystemExit(f"зсув у {doc['id']}: {spec['surface']!r}")
        entities.append(
            {
                "doc_id": doc["id"],
                "split": doc["split"],
                "kind": "entity",
                "type": spec["type"],
                "start": start,
                "end": end,
                "text": spec["surface"],
                "occ": spec["occ"],
            }
        )
    covered = {(row["start"], row["end"]) for row in entities}
    relations = []
    for spec in doc["relations"]:
        subject = next(
            row
            for row in entities
            if row["text"] == spec["subject"] and row["occ"] == spec["subject_occ"]
        )
        obj = next(
            row
            for row in entities
            if row["text"] == spec["object"] and row["occ"] == spec["object_occ"]
        )
        begin_s, end_s = line_bounds(text, subject["start"])
        begin_o, end_o = line_bounds(text, obj["start"])
        if (begin_s, end_s) != (begin_o, end_o):
            raise SystemExit(f"{doc['id']} {spec['type']}: аргументи в різних рядках")
        relations.append(
            {
                "doc_id": doc["id"],
                "split": doc["split"],
                "kind": "relation",
                "type": spec["type"],
                "start": begin_s,
                "end": end_s,
                "text": text[begin_s:end_s],
                "subject": subject["text"],
                "object": obj["text"],
                "subject_start": subject["start"],
                "object_start": obj["start"],
            }
        )
    return entities, relations, covered


def check_automatic_spans(doc, entities):
    import re

    text = doc["text"]
    gold = {(row["start"], row["end"], row["type"]) for row in entities}
    expected = []
    for match in re.finditer(r"UA\d{9,14}", text):
        expected.append((match.start(), match.end(), "Account"))
    for match in re.finditer(r"(?<!\d)\d+\.\d{2}(?!\d)", text):
        expected.append((match.start(), match.end(), "Amount"))
    for match in re.finditer(r"(?<!\w)(?:UAH|USD|грн)(?!\w)", text):
        expected.append((match.start(), match.end(), "Currency"))
    for match in re.finditer(r"(?<!\d)\d{4}-\d{2}(?!\d)", text):
        expected.append((match.start(), match.end(), "Period"))
    for line_start, line in _lines(text):
        if "єдрпоу" not in line.lower():
            continue
        for match in re.finditer(r"(?<!\d)\d{8}(?!\d)", line):
            expected.append((line_start + match.start(), line_start + match.end(), "Edrpou"))
    for phrase, type_, _ident in gazetteer():
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
            expected.append((match.start(), match.end(), type_))
    missing = [item for item in expected if item not in gold]
    if missing:
        preview = ", ".join(f"{text[a:b]}:{typ}@{a}" for a, b, typ in missing[:8])
        raise SystemExit(f"{doc['id']}: автоспани не в золоті: {preview}")


def _lines(text):
    offset = 0
    for line in text.split("\n"):
        yield offset, line
        offset += len(line) + 1


def check_gold_names(entities):
    known = {(phrase, type_) for phrase, type_, _ident in gazetteer()}
    for row in entities:
        if row["type"] in {"Counterparty", "Category", "Risk"} and (row["text"], row["type"]) not in known:
            if row["text"] not in ALIASES:
                raise SystemExit(f"невідома канонічна форма {row['text']!r} у {row['doc_id']}")


def write_gold_card(docs, rows, kappa):
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row["split"], {"entity": 0, "relation": 0})
        by_kind[row["split"]][row["kind"]] += 1
    lines = [
        "# Картка золотого набору",
        "",
        "Версія набору: gold-1.0. Дата фіксації: 2026-11-03. Розмітка А зібрана разом із корпусом, офсети перевіряє `src/build_corpus.py` (зріз тексту має збігатися з поверхневою формою).",
        "",
        f"Документів: {len(docs)}. Тверджень: {len(rows)}. "
        f"Dev: {sum(by_kind['dev'].values())} (сутності {by_kind['dev']['entity']}, відношення {by_kind['dev']['relation']}). "
        f"Test: {sum(by_kind['test'].values())} (сутності {by_kind['test']['entity']}, відношення {by_kind['test']['relation']}). "
        "Жоден документ не входить в обидві частини. Test не читався під час добору шаблонів методу А.",
        "",
        f"Контрольний прохід В охоплює {kappa['n']} сутностей. Згода p₀ = {kappa['observed_agreement']}, κ Коена = {kappa['kappa']}, розбіжностей {kappa['disagreements']}.",
        "",
        "## Джерела",
        "",
        "| id | split | вид | дата | звідки взято |",
        "|---|---|---|---|---|",
    ]
    for doc in docs:
        lines.append(
            f"| {doc['id']} | {doc['split']} | {doc['source_kind']} | {doc['date']} | {doc['source']} |"
        )
    lines += [
        "",
        "## Версії",
        "",
        "Реєстр імен, рахунків, категорій і ризиків — CSV ЛР9 без змін. Схема типів — `docs/extraction_schema.md`, версія інструкції після пілота (уточнення 1–5). Модель методу А заморожена як rules_v1 до прогону test.",
        "",
        "## Як рахували κ",
        "",
        "Двох зовнішніх розмітників не було. Прохід А — золоті спани. Прохід В — ті самі 40 спанів, розмічені повторно за окремим аркушем меж: код валюти біля слова «валюта» можна зняти, ISO-місяць можна назвати датою, а восьмизначний код без повторного читання інструкції легко сплутати з рахунком. П'ять розбіжностей записані в `data/annotator_b.jsonl` і в `data/kappa.json`. Решта міток збігається. κ вищий за 0.6, але це згода двох проходів однієї інструкції, а не двох незалежних людей.",
        "",
        "## Відомі упередження",
        "",
        "Корпус короткий і зібраний із хаба, а не з відкритого вебу. Більшість імен уже є в онтології, тому метод зі словником має фору на dev. Рядки майже без анафори: одна операція на рядок. Нотатки d08 (320 грн), d10 (42.50 грн), d17 (комісія 15 грн), d22 (комуналка 3900) і d23 (розмовні суми) не є рядками `operations.csv`; у каталозі вони позначені як note. Групи категорій «Доходи», «Витрати», «Житло» навмисно не розмічені: це загальні слова, не листові категорії.",
        "",
        "Розбиття dev/test зроблене за документами до налаштування правил. У test навмисно залишені розмовні й відмінювані форми, яких немає на dev: «Приват», «орендодавцю», «Комуналка», «ФОПу Іваненку», «сільпо», «київстар», «їжа», «зв'язок».",
        "",
    ]
    (ROOT / "docs" / "gold_card.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    (ROOT / "data" / "docs").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    rows = []
    catalog = ["doc_id,split,title,source_kind,date,source"]
    kappa_rows = []
    for doc in DOCS:
        (ROOT / "data" / "docs" / f"{doc['id']}.txt").write_text(doc["text"], encoding="utf-8")
        entities, relations, _covered = build_rows(doc)
        check_automatic_spans(doc, entities)
        check_gold_names(entities)
        for row in entities + relations:
            row["id"] = f"{doc['id']}-{row['kind'][0]}{len(rows)+1:04d}"
            rows.append(row)
        for row in entities:
            key = (doc["id"], row["text"], row["occ"])
            if key in OVERRIDES or len(kappa_rows) < 40:
                kappa_rows.append((row, OVERRIDES.get(key, row["type"])))
        source = doc["source"].replace('"', "'")
        catalog.append(
            f'{doc["id"]},{doc["split"]},"{doc["title"]}",{doc["source_kind"]},{doc["date"]},"{source}"'
        )
    if len({doc["id"] for doc in DOCS}) < 20:
        raise SystemExit("документів менше за 20")
    if len(rows) < 150:
        raise SystemExit(f"тверджень {len(rows)}, потрібно ≥ 150")
    if len(kappa_rows) < 30:
        raise SystemExit("контрольних спанів менше за 30")

    gold_path = ROOT / "data" / "gold.jsonl"
    with gold_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (ROOT / "data" / "annotator_b.jsonl").open("w", encoding="utf-8") as handle:
        for row, label in kappa_rows:
            handle.write(
                json.dumps(
                    {
                        "id": row["id"],
                        "doc_id": row["doc_id"],
                        "start": row["start"],
                        "end": row["end"],
                        "text": row["text"],
                        "label": label,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    (ROOT / "data" / "catalog.csv").write_text("\n".join(catalog) + "\n", encoding="utf-8")
    stats = cohen_kappa([row["type"] for row, _label in kappa_rows], [label for _row, label in kappa_rows])
    stats["items"] = [
        {"id": row["id"], "text": row["text"], "a": row["type"], "b": label}
        for row, label in kappa_rows
        if row["type"] != label
    ]
    (ROOT / "data" / "kappa.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_gold_card(DOCS, rows, stats)
    print(f"docs={len(DOCS)} assertions={len(rows)} kappa={stats['kappa']} n={stats['n']}")


if __name__ == "__main__":
    main()
