-- question: Накопичений чистий потік (доходи мінус витрати) по місяцях 2026.
SELECT month_key,
       round(sum(CASE WHEN kind = 'Income' THEN amount WHEN kind = 'Expense' THEN -amount ELSE 0 END), 2) AS net_uah,
       round(sum(sum(CASE WHEN kind = 'Income' THEN amount WHEN kind = 'Expense' THEN -amount ELSE 0 END))
             OVER (ORDER BY month_key), 2) AS running_net_uah
FROM v_operation
WHERE year = 2026
GROUP BY month_key
ORDER BY month_key;
