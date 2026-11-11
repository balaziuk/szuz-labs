-- question: Який обсяг доходів, витрат і переказів за кварталами 2025–2026, включно з маргіналами CUBE?
SELECT year, quarter, kind, round(sum(amount), 2) AS amount_uah, count(*) AS operations
FROM v_operation
WHERE year IN (2025, 2026)
GROUP BY CUBE (year, quarter, kind)
ORDER BY year NULLS LAST, quarter NULLS LAST, kind NULLS LAST;
