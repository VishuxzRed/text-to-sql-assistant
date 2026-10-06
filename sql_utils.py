import re

import sqlglot
from sqlglot import exp

# Only these statement types are allowed
ALLOWED_STATEMENTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)


def extract_sql(reply):
    """Get the SQL out of the model's reply (it sometimes adds a markdown block)."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", reply, re.DOTALL | re.IGNORECASE)
    sql = match.group(1) if match else reply
    return sql.strip().rstrip(";").strip()


def is_no_answer(reply):
    """The prompt tells the model to reply with 'ERROR: ...' if the schema can't answer the question."""
    return reply.strip("\"'` \n").upper().startswith("ERROR:")


def validate_sql(sql):
    """Raise ValueError unless the SQL is a single read-only SELECT query."""
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.SqlglotError as e:
        # keep only the first line, the rest of sqlglot's message is formatting
        raise ValueError(f"Could not parse the SQL: {str(e).splitlines()[0]}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is required.")

    tree = statements[0]
    if not isinstance(tree, ALLOWED_STATEMENTS):
        raise ValueError("Only SELECT queries are allowed.")

    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ValueError("Table functions are not allowed.")
        if table.name.lower().startswith("sqlite_"):
            raise ValueError("SQLite internal tables cannot be queried.")


def format_sql(sql):
    """Format the SQL for display. Falls back to the original text if it can't be parsed."""
    try:
        return sqlglot.transpile(sql, read="sqlite", write="sqlite", pretty=True)[0]
    except sqlglot.errors.SqlglotError:
        return sql
