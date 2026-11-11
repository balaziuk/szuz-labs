import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
API = "https://uk.wikipedia.org/w/api.php"
UA = {"User-Agent": "LNU-KMS-lab10/1.0 (student coursework; educational use)"}

TITLES = [
    "Фінанси", "Бюджет", "Сімейний бюджет", "Бухгалтерський облік", "Грошовий потік",
    "Звіт про рух грошових коштів", "Ліквідність", "Фінансовий ризик", "Валютний ризик",
    "Кредитний ризик", "Інфляція", "Національний банк України", "Банківський рахунок",
    "Банківський депозит", "Кредит", "Відсоткова ставка", "Облікова ставка",
    "Податок на доходи фізичних осіб", "Податок на додану вартість", "Фізична особа — підприємець",
    "Оренда", "Платіжна картка", "Безготівкові розрахунки", "Гривня", "Валютний курс",
    "Фінансовий аналіз", "Диверсифікація", "Заощадження", "Фінансовий менеджмент",
    "Бюджетування", "Комунальні послуги", "Фриланс", "Заробітна плата", "Єдиний соціальний внесок",
]


def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(10 * (attempt + 1))
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
            time.sleep(5)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    saved = []
    for t in TITLES:
        slug = re.sub(r"\W+", "_", t).strip("_")
        if (RAW / f"wiki_{slug}.json").exists():
            continue
        data = api({"action": "query", "prop": "extracts|revisions|info", "titles": t, "redirects": 1,
                    "explaintext": 1, "exsectionformat": "wiki", "rvprop": "timestamp", "inprop": "url"})
        page = data["query"]["pages"][0]
        if page.get("missing") or len(page.get("extract", "")) < 1500:
            print(f"пропущено: {t} ({'немає' if page.get('missing') else len(page.get('extract', ''))})")
            continue
        doc = {
            "title": page["title"],
            "source_url": page["fullurl"],
            "date": page["revisions"][0]["timestamp"][:10],
            "license": "CC BY-SA 4.0",
            "text": page["extract"],
        }
        slug = re.sub(r"\W+", "_", page["title"]).strip("_")
        (RAW / f"wiki_{slug}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        saved.append((page["title"], len(page["extract"])))
        time.sleep(3)
    for t, n in saved:
        print(f"{n:7d}  {t}")
    print("збережено:", len(saved))


if __name__ == "__main__":
    main()
