import re
import sqlite3
from pathlib import Path

import pandas as pd

# Words that would break queries if used as plain table/column names
RESERVED_WORDS = {
    "select", "from", "where", "group", "order", "by", "table", "index", "key",
    "values", "limit", "check", "default", "join", "union", "case", "when",
}


def clean_name(name, default="col"):
    """Turn a file/column name into a safe SQL name: 'Order Date (UTC)' -> 'order_date_utc'."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower() or default
    if name[0].isdigit():
        name = "n_" + name
    if name in RESERVED_WORDS or name.startswith("sqlite_"):
        name = "t_" + name
    return name


def make_unique(name, used_names):
    """Add _2, _3, ... to the name if it is already used."""
    unique = name
    count = 2
    while unique in used_names:
        unique = f"{name}_{count}"
        count += 1
    return unique


def read_file(uploaded_file):
    """Read one uploaded file. Returns a list of (table_name, DataFrame), one per sheet for Excel."""
    stem = Path(uploaded_file.name).stem

    if uploaded_file.name.lower().endswith(".xlsx"):
        sheets = pd.read_excel(uploaded_file, sheet_name=None)
        if len(sheets) == 1:
            return [(stem, df) for df in sheets.values()]
        return [(f"{stem}_{sheet}", df) for sheet, df in sheets.items()]

    try:
        df = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding="latin-1")
    return [(stem, df)]


def load_files(uploaded_files, db_path):
    """Create a fresh SQLite database with one table per CSV file / Excel sheet.

    Returns the list of table names.
    """
    Path(db_path).unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    table_names = []

    try:
        for uploaded_file in uploaded_files:
            for raw_name, df in read_file(uploaded_file):
                table = make_unique(clean_name(raw_name, "table"), table_names)

                column_names = []
                for column in df.columns:
                    column_names.append(make_unique(clean_name(column), column_names))
                df.columns = column_names

                df.to_sql(table, conn, index=False)
                table_names.append(table)
        conn.commit()
    finally:
        conn.close()

    return table_names
