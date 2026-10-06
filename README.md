# Text-to-SQL Assistant

Ask questions about your data in plain English. A **local LLM** (via [Ollama](https://ollama.com)) writes the SQL, the app validates it, runs it **read-only** on SQLite, and shows the results as a table and chart. Nothing leaves your machine.

## Features

- **Natural language → SQL** using a strict system prompt with a schema and business rules (e.g. revenue counts delivered orders only)
- **Runs 100% locally** with Ollama (default model: `qwen3.5:9b-64k`, configurable)
- **Safe by design:** single `SELECT` only, forbidden keywords blocked, database internals blocked, and a read-only database connection
- **Self-correcting:** if the generated SQL fails, the error is fed back to the model for up to 2 retries
- **Guardrail:** questions the schema can't answer return a clear "insufficient schema" message instead of made-up SQL
- **Bring your own data:** upload CSV or Excel files and the app builds the tables, schema, and prompt automatically
- **Instant results:** data table plus an automatic bar chart when the result fits one

## How it works

```
Question → system prompt + schema → local LLM → SQL
        → validation (SELECT-only, no internals, balanced parentheses)
        → read-only SQLite → results table + chart
        ↳ on error: feed the error back to the LLM and retry
```

## Quick start

**1. Prerequisites:** Python 3.10+ and [Ollama](https://ollama.com) installed and running.

**2. Get a model** (the default is set in `MODEL_NAME` at the top of `text_to_sql_app.py`):

```bash
ollama pull qwen2.5-coder:7b
```

If you use a different model, change `MODEL_NAME` to match the name shown by `ollama list`.

**3. Install and run:**

```bash
git clone https://github.com/YOUR-USERNAME/text-to-sql-assistant.git
cd text-to-sql-assistant
pip install -r requirements.txt
streamlit run text_to_sql_app.py
```

The sample shop database is created automatically on first run.

## Example questions

- What is our total revenue from customers in Gotham?
- Top 5 customers by revenue
- Monthly revenue for the last 6 months
- Which product category sold the most units?
- What is the average order value per city?

## Customizing

- **Model:** change `MODEL_NAME` in `text_to_sql_app.py`
- **Business rules:** edit `SYSTEM_PROMPT` (sample database) or `build_custom_prompt()` (uploaded data)
- **Your own data:** pick *Upload my own data* in the sidebar and drop in CSV/Excel files

## Tech stack

Python · SQLite · Streamlit · pandas · Ollama (local LLMs)

## Roadmap

- [ ] Accuracy benchmark with a set of test questions and expected results
- [ ] Model comparison (e.g. 3B vs 7B vs 9B)

## Author

Built by Vishal
