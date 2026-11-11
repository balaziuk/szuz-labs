-- question: Як розподіляються витрати 2026 року за місяцями і групами таксономії (житло, повсякденні, послуги), разом із підсумками?
SELECT month_key, parent_name, round(sum(amount), 2) AS expense_uah
FROM v_operation
WHERE kind = 'Expense' AND year = 2026 AND parent_name <> ''
GROUP BY ROLLUP (month_key, parent_name)
ORDER BY month_key NULLS LAST, parent_name NULLS LAST;
