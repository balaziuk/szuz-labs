CREATE VIEW v_operation AS
SELECT
    f.operation_id, f.kind, f.amount, f.description,
    d.full_date, d.year, d.quarter, d.month, d.month_key,
    a.account_id, a.account_type, a.currency,
    c.category_id, c.category_name, c.parent_id, c.parent_name, c.class_id, c.class_name,
    c.iri, c.budget_limit_uah,
    p.counterparty_id, p.counterparty_name, p.counterparty_type,
    s.source_id, s.source_name
FROM fact_operation f
JOIN dim_date d ON f.date_sk = d.date_sk
JOIN dim_account a ON f.account_sk = a.account_sk
JOIN dim_category c ON f.category_sk = c.category_sk
JOIN dim_counterparty p ON f.counterparty_sk = p.counterparty_sk
JOIN dim_source s ON f.source_sk = s.source_sk;
