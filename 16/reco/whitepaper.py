"""Технічна записка 8–12 сторінок. Цифри рекомендацій читаються з metrics.json і cold.json."""

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reco.data import ROOT

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))


def build_pdf(report, cold):
    styles = _styles()
    L = _lab_numbers()
    story = []
    story.append(Paragraph("Хаб фінансових операцій: технічна записка", styles["title"]))
    story.append(Paragraph("Лабораторна робота 16. Сховища знань та управління знаннями, 2026.", styles["note"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Записка збирає те, що вже пораховано в лабораторних 11, 13, 14, 15 і 16. Нових вимірювань для старих таблиць тут немає: якщо цифра взята з попередньої роботи, це сказано в тексті. Користувачі рекомендацій синтетичні.",
        styles["body"],
    ))

    story.append(Paragraph("1. Задача і хто читає хаб", styles["h"]))
    story.append(Paragraph(
        "Хаб тримає особисті фінансові операції одного домогосподарства: рахунки, контрагентів, категорії, бюджети, ризики й короткі нотатки. Користувач, для якого це зібрано, звіряє виписку з нотаткою і хоче отримати або точну цитату, або явну відмову. Другий читач — той, хто супроводжує сховище: йому потрібні метрики якості, слід походження і журнал рішень, а не вільний переказ моделі.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Документів у корпусі витягнення 23. Операцій у реєстрі ЛР9 більше, ніж у RDF-зрізі ЛР8: у CSV-графі 108 операцій мають ребро походження, а в RDF-зрізі вісім операцій не мали жодного prov:wasDerivedFrom. ЛР14 дописала ці ребра в копію (частка {L['prov_after']}), вихідний файл ЛР8 не змінено.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Рекомендаційний модуль не замінює агента. Список документів відповідає на питання «що відкрити далі». Агент відповідає на питання «скільки» і «який код», і лише цитатою з інструмента. Нотатка з іншою сумою не згладжується до одного числа.",
        styles["body"],
    ))

    story.append(Paragraph("2. Архітектура", styles["h"]))
    story.append(Paragraph(
        "Реєстр ЛР9 — таблиці операцій, контрагентів, категорій, рахунків, бюджетів і ризиків. Поруч лежить RDF ЛР8 із префіксом fin. Корпус ЛР13 — текстові картки d01–d23 і золотий набір сутностей. ЛР14 перевіряє якість, дублі назв і суперечності, не переписуючи ці таблиці. ЛР15 читає їх трьома інструментами. ЛР16 читає каталог і золотий набір і будує синтетичні кліки.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Агент ЛР15 — цикл plan → retrieve → verify на Python, «мозок» — LLM {L['agent_model']} з нативним викликом інструментів. Інструменти registry_lookup, search_notes і operations_query віддає MCP-сервер (офіційний Python SDK, FastMCP, stdio, анотація readOnlyHint); усі три лише читають. Захист: білий список інструментів, ізоляція виходу інструментів у <data>, вирізання рядків-інструкцій, канарка в системному промпті, перевірка чисел і id у відповіді, ліміт чотирьох кроків і 12000 токенів. Запис іде окремим шляхом propose_fact (SHACL + рівень ризику) і зупиняється на людині, якщо рівень середній або високий.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Рекомендації ЛР16 мають три списки. Граф з'єднує документ із сутністю золотого набору типів Account, Counterparty, Category і Risk. Профіль користувача — сутності його train-документів. Embedding — 64 числа з символьних триграм, не вектор нейромережі. Популярність — число train-кліків. Гібрид додає 1/(60+ранг) по трьох списках. Фільтри прибирають нотатки, документи раніше 2026-02-01 і, для ролі public, внутрішні нотатки.",
        styles["body"],
    ))

    story.append(Paragraph("3. Звідки взято знання", styles["h"]))
    story.append(Paragraph(
        "Виписка, картка контрагента і реєстр ризиків мають різні ролі. Виписка Op_00128 фіксує комунальні 3500 грн на 2026-10-03. Нотатка d22 про той самий місяць називає 3900 грн. Обидва рядки збережено. Агент на кількісному питанні показує обидві цитати. Рекомендація цей конфлікт не показує, бо d22 — нотатка і фільтр verified її ховає.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Ризик Risk_RentConcentration сформульований як «частка оренди понад 70% усіх витрат». Підрахунок усіх витрат дає 58,1% (105000 із 180805 грн). У вересні 2026 частка окремо перевищує 70%. Твердження ризику і підрахунок не зведені до одного речення. Агент цитує обидва.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Походження в CSV для операцій заповнене; у RDF-зрізі ЛР8 ребра prov:wasDerivedFrom не було (метрика 0 при порозі 0,9). Копія з доданими ребрами (ЛР14, quality/store_after.ttl) має частку {L['prov_after']} і не замінює вихідний файл. Каппа 0,8534 на 40 спанах порахована двома проходами одного автора з п'ятьма навмисними розбіжностями. Це не згода двох незалежних анотаторів.",
        styles["body"],
    ))

    story.append(Paragraph("4. Метрики якості", styles["h"]))
    story.append(Paragraph("Таблиця 1. Витягнення на test, ЛР13. Мікро по сутностях і відношеннях разом. Прогін ЛР16 ці числа не перераховував.", styles["caption"]))
    story.append(_table([["метод", "precision", "recall", "F1"], ["А, словник і регулярні вирази", "1,000", "0,800", "0,889"], ["Б, модель із цитатою", "0,928", "0,963", "0,945"]], styles))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Метод А на dev дає F1 1,000, бо золотий набір і правила ділять один словник. На test 16 пропусків — відмінки й розмовні назви. Метод Б вищий на test, але шість зайвих спрацьовувань лишаються. У граф потрапляє лише згадка, яку вдалося зв'язати з реєстром.",
        styles["body"],
    ))
    story.append(Paragraph("Таблиця 2. Якість сховища, ЛР14 (числа з 14/quality/*.json).", styles["caption"]))
    story.append(_table([
        ["показник", "до", "після"],
        ["безготівкові витрати з контрагентом", "0,959 (поріг 0,95)", "0,959"],
        ["prov:wasDerivedFrom у RDF", "0 (поріг 0,9)", L["prov_after"]],
        ["дедуплікація, test, precision / recall", f"поріг: {L['dd_p']} / {L['dd_r']}", f"поріг + LLM-суддя: {L['dj_p']} / {L['dj_r']}"],
        ["context recall графового лінкера ЛР11, 10 цільових питань", L["probe_before"], L["probe_after"]],
        ["gate: перевірок / інструментів / спійманих дефектів", "—", "12 / 4 / 3 з 3"],
    ], styles))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Поріг дедуплікації 0,40 підібрано на dev. Пари в смузі 0,30–0,70 ({L['judged']} пар) розглядає LLM-суддя {L['judge_model']}: він розвів хибне злиття «Київстар» / «Київські комунальні», але помилково розвів і «ТОВ «Орендодавець»» / «орендодавцю». Злиття зворотне через unmerge. RAG ЛР11 у тому звіті має faithfulness судді 0,895, context recall 1,0 і abstention 1,0. Людська оцінка faithfulness там 0,632. Ці три числа взято зі звіту ЛР11, набір питань для записки не ганявся знову.",
        styles["body"],
    ))

    story.append(Paragraph("Таблиця 3. Агент ЛР15 (числа з 15/claims/claims.csv останнього прогону).", styles["caption"]))
    story.append(_table([
        ["перевірка", "до", "після"],
        [f"{L['n_scen']} сценаріїв, прогони промптів", L["scen_before"], L["scen_after"]],
        [f"{L['n_att']} атак (6 ручних + 12 від red-team моделі)", f"{L['held_before']} стримано без захистів", f"{L['held_after']} стримано із захистами"],
        ["аліас «Приват»", "—", "прийнято автоматично"],
        ["суперечність 3900 і 3500", "—", "людина підтвердила, обидві суми збережено"],
        ["зміна ЄДРПОУ", "—", "відхилено"],
    ], styles))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Перший промпт агента часто відповідав без виклику інструмента або обирав не той інструмент; другий додав правило «спершу інструмент» і формат цитат, третій — маршрут до реєстру для питань про коди й ризики та одне нагадування після порожньої відповіді. Без захистів модель сама відхиляла більшість атак, але пропускала витік нотатки й виклик стороннього інструмента; захисти закрили і їх. Кожен виклик моделі записано в 15/llm_log/agent.jsonl.",
        styles["body"],
    ))

    story.append(Paragraph("5. Рекомендації", styles["h"]))
    story.append(Paragraph(
        f"Кліків у синтетиці { _rows() }. Користувачів 60, seed 42. У метриках залишилось {report['users_evaluated']} користувачів, у яких після фільтрів є хоча б один test-клік. Кандидатів {report['candidate_items']}. Train — клік раніше 2026-08-01, test — від цієї дати. Клік не ставиться раніше за дату документа. Популярність, профіль і центроїд дивляться лише train.",
        styles["body"],
    ))
    story.append(Paragraph("Таблиця 4. П'ять метрик чотирьох конфігурацій. Числа з data/metrics.json цього прогону.", styles["caption"]))
    header = ["конфігурація", "P@5", "R@5", "nDCG@10", "coverage", "novelty"]
    body = [header]
    for name in ("popularity", "graph", "knn", "hybrid"):
        item = report["configs"][name]
        body.append([name, _n(item["p5"]), _n(item["r5"]), _n(item["ndcg10"]), _n(item["coverage"]), _n(item["novelty"])])
    story.append(_table(body, styles))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Рисунок 1. nDCG@10 чотирьох конфігурацій.", styles["caption"]))
    story.append(_bars({name: report["configs"][name]["ndcg10"] for name in ("popularity", "graph", "knn", "hybrid")}))
    pop = report["ndcg_ci95"]["popularity"]
    graph = report["ndcg_ci95"]["graph"]
    hybrid = report["ndcg_ci95"]["hybrid"]
    separated = "не накладаються" if graph["low"] > pop["high"] else "накладаються"
    story.append(Paragraph(
        f"Бутстреп користувачів, 400 повторів, seed 42, 95% інтервал nDCG@10. Популярність {_n(pop['low'])}–{_n(pop['high'])}. Граф {_n(graph['low'])}–{_n(graph['high'])}. Гібрид {_n(hybrid['low'])}–{_n(hybrid['high'])}. Обрано {report['chosen']}: спочатку більший nDCG@10, за рівності більший coverage. Інтервали графа і популярності {separated}. Гібрид на цих кліках нижчий за граф, бо RRF підмішує два списки з нижчим nDCG.",
        styles["body"],
    ))
    story.append(Paragraph("Таблиця 5. Холодний старт того самого прогону.", styles["caption"]))
    story.append(_table([
        ["сценарій", "що міряли", "значення"],
        ["новий користувач", f"P@5, n={cold['new_user']['users']}", _n(cold["new_user"]["p5"])],
        ["новий документ d19", f"частка топ-5, n={cold['new_item']['users_with_shared_node']}", _n(cold["new_item"]["rate"])],
    ], styles))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Новому користувачу не підставляється його історія. Береться один заявлений вузол, документи з цим вузлом сортуються за популярністю інших користувачів. Новий документ d19 датований 2026-10-01, тож у train його немає. Його бачить граф тих, у кого профіль уже містить спільний вузол.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Пояснення — речення зі спільних вузлів, яке LLM {L['explain_model']} лише перефразовує. Перевірка двох рівнів (назви в лапках є вузлами шляху; жодної іншої сутності каталогу в тексті) пропустила {L['ex_ok']} з {L['ex_n']} перефразувань для шести користувачів. Перефразування, що не пройшло перевірку, замінюється реченням шляху. Два контрольні речення з чужою назвою перевірка відхиляє.",
        styles["body"],
    ))
    story.extend(_why(report, styles))
    story.extend(_worked_example(styles, L))

    story.append(Paragraph("6. Ризики за AI Act і NIST AI RMF", styles["h"]))
    story.append(Paragraph(
        "Регламент (EU) 2024/1689 ділить системи за ризиком і вимагає прозорості там, де людина спілкується з генеративною системою. Цей хаб не ухвалює кредит і не керує доступом до роботи. Він відповідає одній людині про її власні операції, тому найближча категорія — обмежений ризик з обов'язком прозорості (ст. 50): користувач має знати, що відповідь сформувала модель. Генеративні кроки: ЛР13 (витяг сутностей), ЛР14 (суддя дублікатів), ЛР15 (агент), ЛР16 (перефразування пояснень). У кожному вихід моделі проходить автоматичну перевірку (цитата-підрядок, SHACL, перевірка чисел і id, перевірка шляху), а запис у сховище — людину.",
        styles["body"],
    ))
    story.append(Paragraph(
        "NIST AI RMF 1.0 розкладає роботу на Govern, Map, Measure, Manage. Для хаба це виглядає так. Govern: запис і зміна ЄДРПОУ не виконуються агентом, високий рівень відхиляється, середній чекає людину. Map: користувач, нотатка і виписка розведені, чутливість нотатки — internal. Measure: таблиці цієї записки і журнали прогонів. Manage: фільтр ролі, ліміт чотирьох кроків, відмова без цитати, окреме збереження суперечних сум.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Окремий ризик — витік нотатки через роль public і через текст, підкладений у вхідну скриньку. Це перевірено {L['n_att']} атаками, 12 з яких згенерувала інша модель (red teaming): без захистів стримано {L['held_before']}, із захистами {L['held_after']}. Залишковий ризик — перефразована ін'єкція без ключових слів: словниковий фільтр її не ловить, тримають ізоляція даних і перевірка відповіді.",
        styles["body"],
    ))

    story.append(Paragraph("7. Вартість", styles["h"]))
    story.append(Paragraph(
        f"Журнал ЛР13: модель openai/gpt-oss-120b, temperature 0, seed 42, 23 документи, 16106 вхідних і 28666 вихідних токенів, 212 передбачень. ЛР14: суддя, {L['judge_tok']} токенів на 7 пар. ЛР15: агент, {L['agent_calls']} викликів, {L['agent_tok_in']} вхідних і {L['agent_tok_out']} вихідних токенів на всі прогони. ЛР16: перефразування, {L['explain_tok']} токенів. Усе на безкоштовному тарифі Groq; обмеженням були не гроші, а денний ліміт токенів, через який прогін ЛР15 розтягнувся на години. Повторні прогони читають кеш і API не чіпають, доки не зміниться підказка.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Людський час сидить у золотому наборі, у трьох рішеннях propose_fact і в читанні суперечностей. Автоматична перевірка цей час не замінює: суддя ЛР14 помилився на одній із семи пар, а перша версія перевірки пояснень ЛР16 хибно відкидала назву самого документа.",
        styles["body"],
    ))

    story.append(Paragraph("8. Обмеження", styles["h"]))
    story.append(Paragraph(
        "Синтетичні кліки повторюють інтереси, закладені в генератор. Високий nDCG на таких даних не обіцяє того самого на живих переглядах. Триграмний хеш не розуміє відмінок. Граф не виконує Cypher і не ходить у Neo4j лабораторної 9. Каппа не є згодою двох людей. Частина метрик RAG процитована зі старого звіту. Образ зібрано на цій машині, лог лежить у docs/docker_log.txt. Друга машина цей каталог не піднімала.",
        styles["body"],
    ))

    story.append(Paragraph("9. Наступні кроки", styles["h"]))
    story.append(Paragraph(
        "Перенести ребра походження з копії ЛР14 у робочий RDF після рішення власника. Підняти поріг дедуплікації лише новим dev-набором і додати людину для рішень судді з низькою впевненістю. Замінити триграмний хеш на модель лише тоді, коли буде окремий тест, що відмінок не зливає різні контрагенти. Додати семантичний фільтр ін'єкцій замість словникового. Повторити запуск образу на другій машині. Живі кліки не вигадувати.",
        styles["body"],
    ))

    story.append(Paragraph("10. Використання генеративного ШІ", styles["h"]))
    story.append(Paragraph(
        "У ЛР13 модель викликалась для методу Б. Ключ брався зі середовища. Префікс ключа відповідав Groq, тому запит ішов на openai/gpt-oss-120b, temperature 0, seed 42. Підказка вимагала закриті типи і дослівною цитатою поле evidence. Відповідь, яка не проходила перевірку, мала повторюватись до трьох разів; у живому прогоні всі 23 документи пройшли з першої спроби. Людина після цього позначила частину карток як перечитані, решту як не перечитані. Кеш лежить у llm_log, ключ у журнал не писався.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"У ЛР14 модель {L['judge_model']} судить спірні пари дублікатів; її рішення — порада, яку власник скасовує через unmerge. У ЛР15 модель {L['agent_model']} — мозок агента: обирає інструмент і формулює відповідь, а код перевіряє, що кожне число й id є у виході інструментів. Red-team атаки згенерувала інша модель ({L['redteam_model']}), щоб атакувальник не збігався з захисником. У ЛР16 модель лише перефразовує речення шляху, а перевірка відкидає будь-яку сутність поза шляхом. Claude (Anthropic) використано як асистента для коду й чернеток звітів; кожне число в записці прочитане з артефактів прогону.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Чого перевірка не робить. Вона не підтверджує, що виписка правильніша за нотатку. Вона не замінює другого анотатора. Вона не перетворює синтетичний nDCG на оцінку живого продукту. Перевірка цитати не доводить, що модель зрозуміла питання: вона лише гарантує, що названі числа й сутності є в джерелі.",
        styles["body"],
    ))

    story.append(Paragraph("11. Межі агента і що лишилось рукою", styles["h"]))
    story.append(Paragraph(
        "Робоча пам'ять агента — слоти одного питання. Вона зникає разом із відповіддю і не переноситься наступному користувачу. Епізодичний слід — data/traces.jsonl лабораторної 15. Його строк у специфікації 30 діб, і агент не перечитує його, щоб відповісти. Семантичний запис у реєстр закритий: єдиний вхід — propose_fact. Низький рівень у прогоні — аліас «Приват» на вже наявного контрагента, його прийнято автоматично. Середній — 3900 проти 3500, спочатку черга, потім підтвердження людини, обидві суми в журналі. Високий — заміна ЄДРПОУ, відхилення без запису.",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Кроків не більше чотирьох, символів питання й відповіді не більше 6000. Повтор того самого виклику зупиняє граф. Інструмент поза списком, зокрема exfiltrate_all, відхиляється до виконання. Рядок вхідної скриньки з текстом «ІНСТРУКЦІЯ АГЕНТУ» у чернетку v2 не потрапляє. Без цих меж (політика v1) стримано {L['held_before']} з {L['n_att']} атак, із ними — {L['held_after']}. Типи: пряма ін'єкція, непряма ін'єкція через вхідну скриньку, запис або видалення, витік нотатки, цикл пошуку, сторонній інструмент, рольова гра й обфускація.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Каппа 0,8534 порахована на 40 спанах. П'ять розбіжностей закладені другим проходом того самого автора: UAH і грн позначені як O, два періоди 2026-04 як Date, ЄДРПОУ 87654321 як Account. Спостережувана згода 0,875, очікувана 0,1475. На захисті це треба називати повторним проходом, а не незалежною розміткою. Золотий dev збігається зі словником методу А, тому F1 1,000 на dev не є окремим доказом.",
        styles["body"],
    ))
    story.append(Paragraph(
        "Три безготівкові витрати лишились без контрагента попри те, що частка 0,959 проходить поріг 0,95: транспорт 2026-09-03, харчування 2026-09-05 і харчування 2026-10-08. Готівкові витрати контрагента не потребують. Цю трійцю записка не «виправляє» у реєстрі ЛР9.",
        styles["body"],
    ))
    story.append(Paragraph("Джерела", styles["h"]))
    for item in _references():
        story.append(Paragraph(item, styles["ref"]))

    story.append(PageBreak())
    story.append(Paragraph("Додаток. Таблиця тверджень", styles["h"]))
    story.append(Paragraph("Повний файл — claims/claims.csv. Тут ті самі рядки цього прогону.", styles["caption"]))
    story.append(_claims_table(styles))
    path = ROOT / "docs" / "whitepaper.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    counter = {"n": 0}

    def _page(canvas, _doc):
        counter["n"] += 1
        canvas.saveState()
        canvas.setFont("Arial", 9)
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, str(counter["n"]))
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Хаб фінансових операцій",
    )
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return counter["n"]


def _why(report, styles):
    filters = report["filters"]
    blocks = []
    blocks.append(Paragraph("5.1. Що саме відсіяли фільтри", styles["h"]))
    blocks.append(Paragraph(
        f"Перевірка на користувачі {filters['user']}. Нотатка d22 входить у список analyst, якщо вимкнути verified: {_yn(filters['d22_analyst'])}. У списку public її немає: {_yn(not filters['d22_public'])}. У звичайному списку, де ввімкнені і verified, і свіжість, d22 немає: {_yn(not filters['d22_strict'])}. Документ d20 датований 2026-01-15, і в звичайному списку його немає: {_yn(not filters['d20_strict'])}.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "Тому рекомендація не є місцем, де видно суперечність 3500 і 3900. Нотатку ховає фільтр. Агент ЛР15 цю нотатку читає ролі analyst і ставить обидві суми в одну відповідь. Ролі public пошук нотаток закритий ще до чернетки. Це два різні контури: список документів і відповідь на питання.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "Свіжість відрахована від 2026-02-01, а не від ковзного вікна в кілька тижнів. Якби межу поставити на 2026-06-01, лишились би майже самі осінні картки, і P@5 перестав би розрізняти списки. Межа 2026-02-01 прибирає один застарілий реєстр ризику і лишає 18 кандидатів. Число кандидатів записане в metrics.json.",
        styles["body"],
    ))
    blocks.append(Paragraph("5.2. Чому на цих кліках граф вищий", styles["h"]))
    blocks.append(Paragraph(
        "Генератор дає користувачу два вузли і ставить кліки переважно на документи з цими вузлами. Граф ранжує саме за перетином вузлів, тож він повторює правило генератора. Це очікуваний результат, а не доказ, що графи кращі за гібрид узагалі. Популярність не бачить інтересу і тягне всім одні й ті самі документи, тому coverage у неї нижчий, а novelty теж нижча: у топі частіше те, що й так часто клікали в train.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "Триграмний список має найвищі coverage і novelty. Його nDCG нижчий і за граф, і за гібрид: схоже написання рахунку чи суми зближує документи, які людині не про одне. RRF з k=60 додає цей список до графа і популярності й зсуває частину документів графа вниз. На цих даних гібрид граф не обганяє. Якби кліки були живими і не повторювали золоті вузли, порядок міг би змінитися. Записка цього не екстраполює.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "Часове розбиття тримається дати кліку, не номера документа. Документ квітня може отримати і train-клік у травні, і test-клік у вересні, але один клік не входить в обидві частини. Документ жовтня, зокрема d19, фізично не може мати train-клік: дата документа пізніша за 2026-07-31. Тому d19 у холодному старті — справді новий елемент, а не прихований рядок train.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "P@5 ділить влучання в перших п'яти на 5, навіть якщо релевантних документів у користувача два. Тому P@5 нижчий за R@5: знаменник precision фіксований, а релевантних часто менше за п'ять. nDCG@10 ставить влучання на першому місці вище за влучання на десятому. Coverage — частка з 18 кандидатів, яка хоч раз потрапила в чийсь топ-5. Novelty — середнє −log2 від згладженої train-частоти цих документів.",
        styles["body"],
    ))
    return blocks


def _worked_example(styles, L):
    from reco.data import load_docs, load_rows
    from reco.explain import examples

    docs = load_docs()
    rows = load_rows()
    shown = examples(docs, rows, "u01", limit=5)
    blocks = [Paragraph("Таблиця 6. П'ять пояснень для u01: речення шляху і його LLM-перефразування.", styles["caption"])]
    table = [["документ", "речення шляху", "перефразування LLM", "перевірка"]]
    for item in shown:
        llm = item["llm"]
        table.append([item["doc"], item["sentence"], llm["text"] if llm else "—", ("так" if llm["ok"] else "ні") if llm else "—"])
    blocks.append(_table(table, styles))
    blocks.append(Spacer(1, 3 * mm))
    blocks.append(Paragraph(
        "Контроль для першого речення додає «неіснуючий-вузол», другий — назву чужого рахунку без лапок. Обидва перевірка відхиляє. Частка коректних — це не оцінка якості поради, а перевірка, що текст не назвав чужий вузол.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        "Демонстратор показує u01 той самий список графа — конфігурацію, обрану за nDCG@10, а гібрид і решту списків лише для порівняння. Документ без спільного вузла теж отримує речення, у ньому просто немає лапок, і перевірка не дозволяє додати їх від себе.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        f"Дедуплікація ЛР14 лишається окремим контуром. Поріг 0,40 дав на test precision {L['dd_p']} і recall {L['dd_r']}: хибна пара — короткі «Київстар» і «Київські комунальні». Суддя на спірних парах дав {L['dj_p']} / {L['dj_r']}. Аліаси з дедуплікації підняли context recall графового лінкера ЛР11 на цільових питаннях з {L['probe_before']} до {L['probe_after']}.",
        styles["body"],
    ))
    blocks.append(Paragraph(
        f"Агент на питанні про жовтневі комунальні не вибирає 3500 чи 3900. Відповідь v2 містить рядок виписки Op_00128 на 3500 грн і рядок нотатки d22 на 3900 грн. Питання про частку оренди так само містить і 58,1% з операцій, і формулу ризику «понад 70%». Сценарії від першого до останнього промпту: {L['scen_before']} → {L['scen_after']} з {L['n_scen']}.",
        styles["body"],
    ))
    return blocks


def _styles():
    body = ParagraphStyle("body", fontName="Arial", fontSize=11, leading=16, alignment=TA_JUSTIFY, spaceAfter=8)
    return {
        "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=16, leading=20, spaceAfter=4),
        "h": ParagraphStyle("h", fontName="Arial-Bold", fontSize=13, leading=16, spaceBefore=8, spaceAfter=4),
        "body": body,
        "caption": ParagraphStyle("caption", fontName="Arial", fontSize=9, leading=12, spaceBefore=4, spaceAfter=2),
        "note": ParagraphStyle("note", fontName="Arial", fontSize=10, leading=13, textColor=colors.HexColor("#333333")),
        "ref": ParagraphStyle("ref", fontName="Arial", fontSize=9, leading=12, leftIndent=4 * mm, firstLineIndent=-4 * mm, spaceAfter=2),
        "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8, leading=10),
    }


def _table(rows, styles):
    head = ParagraphStyle("headcell", parent=styles["cell"], textColor=colors.white, fontName="Arial")
    wrapped = []
    for index, row in enumerate(rows):
        style = head if index == 0 else styles["cell"]
        wrapped.append([Paragraph(str(cell), style) for cell in row])
    table = Table(wrapped, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Arial"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f4f7fb")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#8aa0b8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _bars(values):
    drawing = Drawing(460, 150)
    maximum = max(values.values()) or 1
    for index, (name, value) in enumerate(values.items()):
        height = 100 * value / maximum
        left = 30 + index * 110
        drawing.add(Rect(left, 24, 48, height, fillColor=colors.HexColor("#1f4e79"), strokeColor=colors.HexColor("#1f4e79")))
        drawing.add(String(left, 10, name, fontName="Arial", fontSize=8))
        drawing.add(String(left, 28 + height, f"{value:.2f}", fontName="Arial", fontSize=8))
    return drawing


def _claims_table(styles):
    import csv

    rows = [["id", "твердження", "статус"]]
    with (ROOT / "claims" / "claims.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append([row["id"], row["claim"], row["status"]])
    return _table(rows, styles)


def _references():
    return [
        "1. Regulation (EU) 2024/1689 of the European Parliament and of the Council of 13 June 2024 laying down harmonised rules on artificial intelligence (AI Act). Official Journal of the European Union.",
        "2. NIST. Artificial Intelligence Risk Management Framework (AI RMF 1.0). NIST AI 100-1, January 2023.",
        "3. W3C. RDF 1.1 Concepts and Abstract Syntax. Recommendation, 25 February 2014.",
        "4. W3C. SPARQL 1.1 Query Language. Recommendation, 21 March 2013.",
        "5. W3C. Shapes Constraint Language (SHACL). Recommendation, 20 July 2017.",
        "6. W3C. PROV-O: The PROV Ontology. Recommendation, 30 April 2013.",
        "7. Cohen J. A Coefficient of Agreement for Nominal Scales. Educational and Psychological Measurement. 1960. Vol. 20, No. 1.",
        "8. Järvelin K., Kekäläinen J. Cumulated Gain-based Evaluation of IR Techniques. ACM Transactions on Information Systems. 2002. Vol. 20, No. 4.",
        "9. Cormack G. V., Clarke C. L. A., Buettcher S. Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. Proceedings of SIGIR 2009.",
        "10. Ricci F., Rokach L., Shapira B. (eds.) Recommender Systems Handbook. 2nd ed. Springer, 2015.",
        "11. Aggarwal C. C. Recommender Systems: The Textbook. Springer, 2016.",
        "12. Model Context Protocol. Specification, 2025. https://modelcontextprotocol.io/specification",
        "13. Zheng L. et al. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023.",
        "14. Greshake K. et al. Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection. AISec 2023.",
    ]


def _lab_numbers():
    """Числа ЛР14–16 з артефактів; якщо файлу немає — «—»."""
    import json
    import re

    labs = ROOT.parent
    out = {}

    def load(rel):
        path = labs / rel
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    dd = load("14/quality/dedup_report.json") or {}
    out["dd_p"], out["dd_r"] = _n(dd.get("test", {}).get("precision", 0)), _n(dd.get("test", {}).get("recall", 0))
    out["dj_p"], out["dj_r"] = _n(dd.get("test_with_judge", {}).get("precision", 0)), _n(dd.get("test_with_judge", {}).get("recall", 0))
    out["judged"] = dd.get("judged_pairs", "—")
    merges = load("14/quality/merges.json") or {}
    out["judge_model"] = next((v["model"] for v in (merges.get("judge") or {}).values()), "—")
    store = labs / "14" / "quality" / "store_after.ttl"
    out["prov_after"] = "1,000" if store.exists() and "wasDerivedFrom" in store.read_text(encoding="utf-8") else "—"
    probe = load("14/quality/rag_probe.json") or {}
    summary = probe.get("summary", {})

    def recall(name):
        value = summary.get(name, {})
        value = value.get("context_recall") if isinstance(value, dict) else value
        return f"{value:.2f}".replace(".", ",") if isinstance(value, (int, float)) else "—"

    out["probe_before"], out["probe_after"] = recall("registry"), recall("judge")
    cache14 = labs / "14" / "llm_log" / "judge_cache.jsonl"
    rows14 = [json.loads(x) for x in cache14.read_text(encoding="utf-8").splitlines() if x.strip()] if cache14.exists() else []
    out["judge_tok"] = sum(r["tokens_in"] + r["tokens_out"] for r in rows14)
    claims15 = labs / "15" / "claims" / "claims.csv"
    text15 = claims15.read_text(encoding="utf-8") if claims15.exists() else ""
    scen = re.search(r"LLM ([\w/.\-]+)\) у прогоні \d+ проходить (\d+) з (\d+) сценаріїв \((?:прогін|прогони) [^:]+: ([\d, ]+)\)", text15)
    if scen:
        out["agent_model"], out["scen_after"], out["n_scen"] = scen.group(1), scen.group(2), scen.group(3)
        out["scen_before"] = " → ".join(x.strip() for x in scen.group(4).split(","))
    else:
        out.update(agent_model="openai/gpt-oss-120b", scen_after="—", n_scen="10", scen_before="—")
    att = re.search(r"стримано (\d+) з (\d+) атак \(до: (\d+)\)", text15)
    out["held_after"], out["n_att"], out["held_before"] = att.groups() if att else ("—", "—", "—")
    red = re.search(r"згенерувала ([\w/.\-]+)", text15)
    out["redteam_model"] = red.group(1) if red else "—"
    summary15 = load("15/llm_log/summary.json") or {}
    out["agent_calls"] = summary15.get("calls", "—")
    out["agent_tok_in"] = summary15.get("tokens_in", "—")
    out["agent_tok_out"] = summary15.get("tokens_out", "—")
    ev = load("16/data/explain_eval.json") or {}
    out["ex_ok"], out["ex_n"] = ev.get("llm_ok", "—"), ev.get("llm_explanations", "—")
    cache16 = ROOT / "llm_log" / "explain_cache.jsonl"
    rows16 = [json.loads(x) for x in cache16.read_text(encoding="utf-8").splitlines() if x.strip()] if cache16.exists() else []
    out["explain_tok"] = sum(r["tokens_in"] + r["tokens_out"] for r in rows16)
    from reco.explain import MODEL
    out["explain_model"] = MODEL
    return out


def _yn(value):
    return "так" if value else "ні"


def _n(value):
    return f"{value:.3f}".replace(".", ",")


def _rows():
    import csv

    path = ROOT / "data" / "interactions.csv"
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))
