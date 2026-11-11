-- question: Ковзне середнє витрат на харчування за 3 місяці у 2026.
SELECT month_key,
       round(sum(amount), 2) AS food_uah,
       round(avg(sum(amount)) OVER (ORDER BY month_key ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS ma3
FROM v_operation
WHERE kind = 'Expense' AND year = 2026 AND category_id = 'Cat_Food'
GROUP BY month_key
ORDER BY month_key;
