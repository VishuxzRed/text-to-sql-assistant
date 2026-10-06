import re

import requests

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen3.5:9b-64k"  # must match a name shown by `ollama list`
REQUEST_TIMEOUT = 300          # seconds, local models can be slow

# app.py checks for replies that start with "ERROR:", so keep that wording
BASE_PROMPT = """Convert the user's question into a SQLite SELECT query.

- Use only the tables and columns in the schema below. Do not invent any.
- Return only the SQL. No explanation and no markdown.
- Use table aliases and explicit JOIN ... ON.
- Keep the query simple. Use a JOIN with GROUP BY instead of nested subqueries when possible.
- For rankings use ORDER BY ... DESC, and LIMIT for "top N".
- Dates are stored as text. Use strftime() or date() for date logic.
- Text values may use different casing, so compare with LOWER() when unsure.
- If the schema can't answer the question, reply exactly:
  ERROR: Insufficient schema metadata to construct query.
"""

# Business rules for the sample shop database only
SHOP_RULES = """Business rules for this database:
- Order status is 'delivered', 'shipped' or 'cancelled'.
- Revenue (or sales) = SUM(order_items.quantity * products.price) for delivered orders only.
  Include shipped orders only if the user asks for shipped or gross sales.
- Units sold = SUM(order_items.quantity) for orders that are not cancelled.
- Average order value = revenue / COUNT(DISTINCT orders.id), delivered orders only.
- Cancelled orders never count toward revenue, sales or units sold.
- Customer cities: 'Metropolis', 'Gotham', 'Star City'.
- Product categories: 'Electronics', 'Apparel', 'Home Decor', 'Fitness'.

Example:
Question: What is the total revenue from customers in Gotham?
SQL: SELECT SUM(oi.quantity * p.price) AS total_revenue
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN customers c ON c.id = o.customer_id
JOIN products p ON p.id = oi.product_id
WHERE c.city = 'Gotham' AND o.status = 'delivered'
"""


class LLMError(Exception):
    """Ollama isn't running, the model is missing, or the request failed."""


def check_ollama():
    """Raise LLMError with a clear message if Ollama or the model isn't available."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.ConnectionError:
        raise LLMError(f"Can't connect to Ollama at {OLLAMA_URL}. Start it and refresh the page.")
    except requests.RequestException as e:
        raise LLMError(f"Ollama returned an error: {e}")

    installed = [model["name"] for model in response.json().get("models", [])]
    if MODEL_NAME not in installed:
        raise LLMError(
            f"Model '{MODEL_NAME}' is not installed. Installed models: {', '.join(installed) or 'none'}. "
            "Install it with `ollama pull`, or change MODEL_NAME in llm.py."
        )


def build_prompt(schema, rules=""):
    """Combine the instructions, the table definitions and any business rules."""
    prompt = f"{BASE_PROMPT}\nSchema:\n{schema}\n"
    if rules:
        prompt += f"\n{rules}"
    return prompt


def ask_model(messages):
    """Send the chat messages to Ollama and return the model's reply as text."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "think": False,  # skip the "thinking" step, it is slow and not needed for SQL
        "options": {"temperature": 0, "num_predict": 2048},
    }
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code == 400 and "think" in response.text.lower():
            del payload["think"]  # this Ollama version/model doesn't support the option
            response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        raise LLMError(f"Request to Ollama failed: {e}")

    reply = response.json()["message"]["content"]
    # some models still include their reasoning in <think> tags
    return re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
