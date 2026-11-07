# Product Sales AI Agent Specification

## Overview
A simple, single-file Python AI Agent for selling products, designed to be extensible for upcoming Evaluation (eval), Guardrails, and Observability.

## Workflow
1. **User Request**: User provides product name and requested quantity (e.g., "I want to buy 2 Laptops").
2. **Tool 1 (`check_inventory`)**:
   - Checks `inventory.json` to verify product exists and stock >= requested quantity.
   - If stock is not enough: Informs the customer and offers available quantity.
   - If stock is enough: Tells the agent to request customer details: Name, Phone, and Address.
3. **Customer Details**:
   - Customer provides: Name, Phone, and Delivery Address.
4. **Tool 2 (`place_order`)**:
   - Deducts ordered quantity from `inventory.json`.
   - Records the order in `orders.json` with an Order ID.
   - Generates a confirmation receipt.

## Configuration
- **Model**: `openai/gpt-oss-20b` (Groq API)
- **API Key**: `GROQ_API_KEY` from `.env`
- **Files**:
  - `sales_agent.py` - Core agent logic & tools
  - `inventory.json` - Product catalog and stock quantities
  - `orders.json` - Saved order logs

