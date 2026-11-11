-- question: Кубик (dice): витрати на житло у 3 кварталі 2026 за підкласами таксономії.
SELECT category_name, iri, round(sum(amount), 2) AS expense_uah
FROM v_operation
WHERE kind = 'Expense' AND year = 2026 AND quarter = 3 AND parent_name = 'Житло'
GROUP BY category_name, iri
ORDER BY expense_uah DESC;
