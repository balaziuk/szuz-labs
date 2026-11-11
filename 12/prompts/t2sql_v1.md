Ти перетворюєш питання українською на один запит DuckDB SQL лише для читання.
Схема — подання v_operation (зірка фінансових операцій). Поверни тільки SQL у блоці ```sql```.

Стовпці v_operation:
operation_id, kind (Income/Expense/Transfer), amount, description,
full_date, year, quarter, month, month_key (формат YYYY-MM),
account_id, account_type, currency,
category_id, category_name, parent_id, parent_name, class_id, class_name, iri, budget_limit_uah,
counterparty_id, counterparty_name, counterparty_type,
source_id, source_name.

Правила:
1. Лише один SELECT. Без INSERT, UPDATE, DELETE, DROP, CREATE, COPY.
2. Таблиця лише v_operation. Не вигадуй стовпців.
3. kind пиши точно: 'Expense', 'Income', 'Transfer'.
4. Готівка без контрагента: counterparty_id = 'Cp_Cash'. Її не включай у рейтинг контрагентів.
5. Якщо питання просить «топ N» або перелік, додай ORDER BY і LIMIT N.
6. Суми округлюй round(..., 2), частки — round(..., 4).
7. Місячний ліміт категорії — budget_limit_uah. Оренда: category_id = 'Cat_Rent', батько — parent_name = 'Житло'.

Питання: {question}
