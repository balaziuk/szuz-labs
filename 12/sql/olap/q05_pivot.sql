-- question: Зведення (pivot) витрат за категоріями у липні–жовтні 2026.
PIVOT (
    SELECT category_name, month_key, amount
    FROM v_operation
    WHERE kind = 'Expense' AND month_key IN ('2026-07', '2026-08', '2026-09', '2026-10')
) ON month_key
USING sum(amount)
GROUP BY category_name
ORDER BY category_name;
