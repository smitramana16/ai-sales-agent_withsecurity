# AI Agent Security & Production Architecture

A simple, practical guide explaining the three core security and reliability pillars implemented in this project: **Guardrails**, **Observability**, and **Evaluation**.

---

## 1. Guardrails (Real-Time Protection)

### What It Does
Guardrails act as a real-time shield surrounding the AI agent. Every message and tool call passes through three defensive layers:

1. **Input Guardrail (Pre-LLM)**: Scans user messages *before* sending them to the AI.
2. **Tool Guardrail (Pre-Tool Execution)**: Validates function arguments *before* any code or database changes happen.
3. **Output Guardrail (Post-LLM)**: Inspects the AI's response *before* the user can see it.

### Problems It Prevents
- **Prompt Injection & Jailbreaks**: Blocks attacks like *"Ignore previous instructions"*, *"You are now a giveaway bot"*, or developer mode tricks.
- **Negative & Zero Quantity Tampering**: Prevents attackers from ordering `-5` or `0` items to corrupt stock.
- **Bulk Stock Depletion**: Blocks orders over 100 units to stop inventory hoarding or denial-of-service.
- **Fake Customer Data**: Strictly enforces **10 or 12 digit phone numbers** and rejects invalid or fake contact numbers.
- **Script & SQL Injection**: Blocks XSS (`<script>`) and database injection (`DROP TABLE`) inside names and addresses.
- **Secret & API Key Leakage**: Automatically detects and redacts private API keys (`gsk_...`, `sk-...`, `tvly-...`) so secrets never leak to users.
- **Off-Topic Distraction**: Strictly restricts the AI to store sales only, refusing general trivia, coding, jokes, or non-sales questions.

---

## 2. Observability (Trace, Span, Log)

### What It Does
Observability provides full visibility into everything the agent does during a request, broken down into three simple concepts:

- **Trace**: The full journey of one user request from start to finish.
- **Span**: A specific step inside the trace (e.g., Input Guardrail, Groq LLM API Call, `check_inventory` Tool).
- **Log**: Detailed, timestamped event records within each span.

### Problems It Prevents
- **Silent Failures**: If a tool fails or an API times out, you see the exact step, error message, and timestamp immediately.
- **Surprise Bills & High Costs**: Calculates tokens used and exact dollar cost ($USD) for every query so you never get unexpected API bills.
- **Slow Performance & Lag**: Tracks duration in milliseconds (`ms`) for every single step, showing you which tool or model call is slowing down the system.
- **Debugging Blindness**: Without observability, an agent is a black box. With it, you have a complete audit trail of inputs, parameters, and outputs.

---

## 3. Evaluation (Automated Testing & Scoring)

### What It Does
Evaluation runs an automated test suite of **10 critical security and workflow scenarios** against the agent, verifies whether the answer is **CORRECT** or **WRONG**, and outputs a final score out of 10 (e.g. `10 / 10 - 100%`).

### Problems It Prevents
- **Hidden Security Vulnerabilities**: Tests the agent against real adversarial attacks before users can exploit them.
- **Regression Bugs**: Ensures that adding new features or changing prompts does not accidentally break existing security rules.
- **False Assumptions**: Verifies with real test results rather than guessing if the model is safe.
- **Model Drift**: Allows you to test different models (e.g., Llama, GPT, Qwen) to verify they all adhere to store rules.

---

## Quick Summary Matrix

| Pillar | What It Is | What Problems It Prevents |
| :--- | :--- | :--- |
| **Guardrails** | Active runtime firewall (Input, Tool, Output) | Prompt injections, fake phone numbers, negative quantities, code injections, API key leaks. |
| **Observability** | Monitoring system (Trace, Span, Log) | Hidden errors, runaway token costs, slow bottlenecks, unmonitored tool executions. |
| **Evaluation** | Automated security test scorecard | Broken rules after updates, security regressions, untested edge cases. |

---

## How to Run Each Component

```powershell
# 1. Run the Sales AI Agent (with Guardrails & Live Observability)
python sales_agent.py

# 2. Run the Security & Functional Evaluation (Score out of 10)
python eval_security.py

# 3. Run Guardrail Unit Tests
python test_guardrails.py

# 4. Run Observability Unit Tests
python test_observability.py
```

