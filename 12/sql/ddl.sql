CREATE TABLE dim_date (
    date_sk INTEGER PRIMARY KEY,
    full_date DATE NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_key VARCHAR NOT NULL,
    day INTEGER NOT NULL
);

CREATE TABLE dim_account (
    account_sk INTEGER PRIMARY KEY,
    account_id VARCHAR NOT NULL UNIQUE,
    account_number VARCHAR NOT NULL,
    account_type VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    snapshot_balance DOUBLE NOT NULL
);

CREATE TABLE dim_category (
    category_sk INTEGER PRIMARY KEY,
    category_id VARCHAR NOT NULL UNIQUE,
    category_name VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    parent_id VARCHAR,
    parent_name VARCHAR,
    class_id VARCHAR NOT NULL,
    class_name VARCHAR NOT NULL,
    iri VARCHAR NOT NULL,
    budget_limit_uah DOUBLE
);

CREATE TABLE dim_counterparty (
    counterparty_sk INTEGER PRIMARY KEY,
    counterparty_id VARCHAR NOT NULL,
    counterparty_name VARCHAR NOT NULL,
    counterparty_type VARCHAR NOT NULL,
    edrpou VARCHAR,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN NOT NULL
);

CREATE TABLE dim_source (
    source_sk INTEGER PRIMARY KEY,
    source_id VARCHAR NOT NULL UNIQUE,
    source_name VARCHAR NOT NULL,
    source_kind VARCHAR NOT NULL
);

CREATE TABLE fact_operation (
    operation_id VARCHAR PRIMARY KEY,
    kind VARCHAR NOT NULL,
    amount DOUBLE NOT NULL,
    description VARCHAR NOT NULL,
    date_sk INTEGER NOT NULL,
    account_sk INTEGER NOT NULL,
    category_sk INTEGER NOT NULL,
    counterparty_sk INTEGER NOT NULL,
    source_sk INTEGER NOT NULL
);
