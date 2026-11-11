-- question: Зріз (slice) лише витрат: скільки їх за кожен рік?
SELECT year, round(sum(amount), 2) AS expense_uah, count(*) AS operations
FROM v_operation
WHERE kind = 'Expense'
GROUP BY year
ORDER BY year;
