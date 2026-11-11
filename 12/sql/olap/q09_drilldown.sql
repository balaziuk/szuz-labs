-- question: Drill-down таксономії витрат 2026: група (Житло, Повсякденні, Послуги), потім стаття.
SELECT parent_name,
       CASE WHEN GROUPING(category_name) = 1 THEN '(усі статті групи)' ELSE category_name END AS category_name,
       GROUPING(category_name) AS is_group_total,
       round(sum(amount), 2) AS expense_uah
FROM v_operation
WHERE kind = 'Expense' AND year = 2026 AND parent_name <> ''
GROUP BY GROUPING SETS ((parent_name), (parent_name, category_name))
ORDER BY parent_name, is_group_total DESC, expense_uah DESC;
