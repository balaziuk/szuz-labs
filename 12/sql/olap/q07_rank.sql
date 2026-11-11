-- question: Ранг контрагентів за сумою витрат у 2026 (без готівки).
SELECT counterparty_name,
       round(sum(amount), 2) AS expense_uah,
       rank() OVER (ORDER BY sum(amount) DESC) AS rnk
FROM v_operation
WHERE kind = 'Expense' AND year = 2026 AND counterparty_id <> 'Cp_Cash'
GROUP BY counterparty_name
ORDER BY rnk, counterparty_name;
