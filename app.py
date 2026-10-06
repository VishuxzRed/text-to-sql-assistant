import pandas as pd
import streamlit as st

import data_loader
import database
import llm
import sql_utils

MAX_RETRIES = 2  # how many times the model may fix its own SQL

SAMPLE_LABEL = "Sample shop database"
UPLOAD_LABEL = "Upload my own files"

SAMPLE_QUESTIONS = [
    "What is the total revenue from customers in Gotham?",
    "Top 5 customers by revenue",
    "Monthly revenue for the last 6 months",
    "Which product category sold the most units?",
    "What is the average order value per city?",
    "How many cancelled orders are there per city?",
]


def answer_question(question, prompt, db_path):
    """Ask the model for SQL, check it, run it, and retry if it fails.

    Returns a dict with the SQL, the result DataFrame (or an error message)
    and the raw model reply.
    """
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question},
    ]
    result = {"question": question, "sql": "", "df": None, "error": None, "raw": "", "retries": 0}

    for attempt in range(MAX_RETRIES + 1):
        reply = llm.ask_model(messages)
        result["raw"] = reply
        result["retries"] = attempt

        if sql_utils.is_no_answer(reply):
            result["sql"] = ""
            result["error"] = "This question can't be answered from the available tables."
            return result

        sql = sql_utils.extract_sql(reply)
        result["sql"] = sql
        try:
            sql_utils.validate_sql(sql)
            result["df"] = database.run_query(db_path, sql)
            result["error"] = None
            return result
        except (ValueError, database.QueryError) as e:
            result["error"] = str(e)
            # show the model what went wrong and ask for a fixed query
            messages.append({"role": "assistant", "content": sql})
            messages.append({
                "role": "user",
                "content": f"That query failed: {e}\nFix it and return only the corrected SQL.",
            })

    return result


def show_chart(df):
    """Bar chart for results with one label column and one numeric column."""
    if df.shape[1] != 2 or not 1 < len(df) <= 50:
        return
    if pd.api.types.is_numeric_dtype(df.iloc[:, 1]):
        st.bar_chart(df.set_index(df.columns[0]))


def show_result(item, show_raw):
    with st.chat_message("user"):
        st.write(item["question"])

    with st.chat_message("assistant"):
        if item["sql"]:
            st.code(sql_utils.format_sql(item["sql"]), language="sql")

        if item["error"]:
            st.error(item["error"])
        elif item["df"].empty:
            st.info("The query ran but returned no rows.")
        else:
            if item["retries"]:
                st.caption(f"The first query failed, this is the result after {item['retries']} retry(ies).")
            st.dataframe(item["df"], use_container_width=True)
            if len(item["df"]) == database.MAX_ROWS:
                st.caption(f"Showing the first {database.MAX_ROWS} rows.")
            show_chart(item["df"])

        if show_raw:
            with st.expander("Raw model reply"):
                st.text(item["raw"])


def main():
    st.set_page_config(page_title="Text-to-SQL Assistant")
    st.title("Text-to-SQL Assistant")
    st.caption("Ask a question about your data in plain English.")

    try:
        llm.check_ollama()
    except llm.LLMError as e:
        st.error(str(e))
        st.stop()

    database.create_sample_db()
    if "history" not in st.session_state:
        st.session_state["history"] = []

    # Sidebar: choose the data
    with st.sidebar:
        source = st.radio("Data", [SAMPLE_LABEL, UPLOAD_LABEL])
        files = []
        if source == UPLOAD_LABEL:
            files = st.file_uploader("CSV or XLSX files", type=["csv", "xlsx"], accept_multiple_files=True)
        show_debug = st.checkbox("Debug mode")

    if source == SAMPLE_LABEL:
        db_path = database.SAMPLE_DB
        rules = llm.SHOP_RULES
    else:
        if not files:
            st.info("Upload one or more CSV or XLSX files in the sidebar.")
            st.stop()
        db_path = database.CUSTOM_DB
        rules = ""

    # Rebuild the database and clear the chat whenever the data changes
    source_id = (source, tuple((f.name, f.size) for f in files))
    if st.session_state.get("source_id") != source_id:
        if source == UPLOAD_LABEL:
            try:
                data_loader.load_files(files, db_path)
            except Exception as e:  # bad file, missing openpyxl, ...
                st.error(f"Could not read the uploaded files: {e}")
                st.stop()
        st.session_state["history"] = []
        st.session_state["source_id"] = source_id

    schema = database.get_schema(db_path)
    prompt = llm.build_prompt(schema, rules)

    if source == SAMPLE_LABEL:
        examples = SAMPLE_QUESTIONS
    else:
        examples = []
        for table in database.list_tables(db_path)[:2]:
            examples += [f"How many rows are in {table}?", f"Show 10 rows from {table}"]

    with st.sidebar:
        st.subheader("Examples")
        for example in examples:
            if st.button(example, use_container_width=True):
                st.session_state["pending_question"] = example
        with st.expander("Tables"):
            st.code(schema, language="sql")
        if show_debug:
            with st.expander("Prompt sent to the model"):
                st.text(prompt)
        if st.button("Clear chat"):
            st.session_state["history"] = []

    question = st.chat_input("Ask a question about your data")
    question = st.session_state.pop("pending_question", None) or question

    if question:
        with st.spinner("Generating SQL..."):
            try:
                result = answer_question(question, prompt, db_path)
                st.session_state["history"].append(result)
            except llm.LLMError as e:
                st.error(str(e))

    for item in st.session_state["history"]:
        show_result(item, show_debug)


if __name__ == "__main__":
    main()
