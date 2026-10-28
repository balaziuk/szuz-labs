MATCH (o:Operation)-[:FROM_ACCOUNT]->(:Account {id: 'Acc_UA123456789'})
WITH substring(toString(o.date), 0, 7) AS month,
     sum(CASE WHEN o.kind = 'Income' THEN o.amount ELSE 0 END) AS income,
     sum(CASE WHEN o.kind = 'Expense' THEN o.amount ELSE 0 END) AS expenses,
     sum(CASE WHEN o.kind = 'Transfer' THEN o.amount ELSE 0 END) AS toSavings
RETURN month, income, expenses, toSavings, income - expenses - toSavings AS net
ORDER BY month;
