"""
Sales AI Agent
==============
Simple, single-file Python AI Agent for product ordering.
- Powered by Groq API (`openai/gpt-oss-20b`)
- Tool 1: check_inventory -> Checks stock from inventory.json
- Tool 2: place_order -> Deducts quantity and saves order with Name, Phone, Address
- Architecture designed for easy addition of Guardrails, Observability, and Eval.
"""

import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

# Import modular guardrail framework
try:
    from guardrails import GuardrailPipeline, GuardrailAction, GuardrailResult
except ImportError:
    from .guardrails import GuardrailPipeline, GuardrailAction, GuardrailResult

# Import observability framework (Log, Trace, Span)
try:
    from observability import Tracer, default_tracer
except ImportError:
    from .observability import Tracer, default_tracer

# Ensure UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================================
# 1. ENVIRONMENT & CONFIGURATION
# ============================================================================

def load_environment() -> str:
    """Find and load .env file to retrieve GROQ_API_KEY."""
    try:
        from dotenv import load_dotenv, find_dotenv
        env_file = find_dotenv(usecwd=True)
        if env_file:
            load_dotenv(env_file, override=True)
    except ImportError:
        pass

    # Fallback parent search
    curr = Path(__file__).resolve().parent
    for _ in range(5):
        potential = curr / ".env"
        if potential.is_file():
            try:
                with open(potential, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            except Exception:
                pass
            break
        curr = curr.parent

    key = os.environ.get("GROQ_API_KEY")
    if not key or key == "your_groq_api_key_here":
        print("[Warning] GROQ_API_KEY is not set in .env.")
    return key or ""


GROQ_API_KEY = load_environment()
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

BASE_DIR = Path(__file__).resolve().parent
INVENTORY_FILE = BASE_DIR / "inventory.json"
ORDERS_FILE = BASE_DIR / "orders.json"


# ============================================================================
# 2. INVENTORY & ORDER MANAGEMENT
# ============================================================================

def get_inventory() -> Dict[str, Dict[str, Any]]:
    """Loads inventory data from inventory.json."""
    if not INVENTORY_FILE.exists():
        default_inventory = {
            "laptop": {"name": "Laptop", "stock": 10, "price": 800},
            "phone": {"name": "Smartphone", "stock": 15, "price": 500},
            "headphones": {"name": "Headphones", "stock": 25, "price": 50},
            "smartwatch": {"name": "Smartwatch", "stock": 3, "price": 150},
        }
        with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(default_inventory, f, indent=2)
        return default_inventory

    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error reading inventory.json]: {e}")
        return {}


def save_inventory(inventory_data: Dict[str, Dict[str, Any]]):
    """Saves updated inventory data back to inventory.json."""
    with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(inventory_data, f, indent=2)


def record_order(order_data: Dict[str, Any]):
    """Appends completed order record to orders.json."""
    orders = []
    if ORDERS_FILE.exists():
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                orders = json.load(f)
        except Exception:
            orders = []

    orders.append(order_data)
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)


# ============================================================================
# 3. TOOLS
# ============================================================================

def check_inventory(product_name: str, quantity: int) -> str:
    """
    Tool 1: Checks if product exists and whether stock is sufficient.
    If enough: Returns AVAILABLE and instructs to collect Name, Phone, and Address.
    If not enough: Returns INSUFFICIENT_STOCK with remaining count.
    """
    if quantity <= 0:
        return f"INVALID_QUANTITY: Quantity must be a positive number greater than 0. Received: {quantity}."

    inv = get_inventory()
    norm_query = product_name.strip().lower()

    # Find matching product key (exact or substring)
    matched_key = None
    for key, data in inv.items():
        if norm_query in key or norm_query in data.get("name", "").lower():
            matched_key = key
            break

    if not matched_key:
        available_names = [d["name"] for d in inv.values()]
        return (
            f"NOT_FOUND: Product '{product_name}' is not in our catalog.\n"
            f"Available products in store: {', '.join(available_names)}."
        )

    product = inv[matched_key]
    current_stock = product.get("stock", 0)
    display_name = product.get("name", matched_key.title())
    price = product.get("price", 0)

    if current_stock >= quantity:
        total_estimate = price * quantity
        return (
            f"AVAILABLE: Yes, we have {current_stock} units of {display_name} in stock! "
            f"Requested: {quantity} unit(s). Unit Price: ${price} (Estimated Total: ${total_estimate}). "
            f"Please ask the customer to provide their Name, Phone number, and Delivery Address to place this order."
        )
    else:
        return (
            f"INSUFFICIENT_STOCK: Sorry, we only have {current_stock} unit(s) of {display_name} in stock, "
            f"which is less than the requested {quantity} unit(s). Please inform the customer."
        )


def place_order(
    product_name: str,
    quantity: int,
    name: str,
    phone: str,
    address: str
) -> str:
    """
    Tool 2: Deducts ordered items from inventory and creates the order.
    Requires customer details: Name, Phone, Address.
    """
    if quantity <= 0:
        return f"ORDER_FAILED: Quantity must be greater than 0. Received: {quantity}."

    inv = get_inventory()
    norm_query = product_name.strip().lower()

    matched_key = None
    for key, data in inv.items():
        if norm_query in key or norm_query in data.get("name", "").lower():
            matched_key = key
            break

    if not matched_key:
        return f"ERROR: Product '{product_name}' could not be located in inventory."

    product = inv[matched_key]
    current_stock = product.get("stock", 0)
    display_name = product.get("name", matched_key.title())
    price = product.get("price", 0)

    # Final stock sanity check
    if current_stock < quantity:
        return f"ORDER_FAILED: Insufficient stock. Only {current_stock} unit(s) remaining."

    # Deduct stock and update inventory
    product["stock"] = current_stock - quantity
    save_inventory(inv)

    order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    total_price = price * quantity

    # Save order record
    order_record = {
        "order_id": order_id,
        "product_key": matched_key,
        "product_name": display_name,
        "quantity": quantity,
        "unit_price": price,
        "total_price": total_price,
        "customer_name": name,
        "customer_phone": phone,
        "customer_address": address,
        "timestamp": datetime.now().isoformat(),
        "status": "CONFIRMED",
    }
    record_order(order_record)

    return (
        f"SUCCESS: Order #{order_id} placed successfully!\n"
        f"- Product: {display_name}\n"
        f"- Quantity: {quantity}\n"
        f"- Total Amount: ${total_price}\n"
        f"- Customer: {name}\n"
        f"- Phone: {phone}\n"
        f"- Delivery Address: {address}\n"
        f"- Remaining Stock in Store: {product['stock']}"
    )


TOOLS_REGISTRY = {
    "check_inventory": check_inventory,
    "place_order": place_order,
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Checks if the requested product exists in the catalog and has enough stock available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Name of the product (e.g. 'Laptop', 'Smartphone', 'Headphones', 'Smartwatch')."
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "The quantity the user wants to buy."
                    }
                },
                "required": ["product_name", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_order",
            "description": "Places an order after stock is verified. Deducts items from total inventory and logs customer details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The product being purchased."
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to order."
                    },
                    "name": {
                        "type": "string",
                        "description": "Full name of the customer."
                    },
                    "phone": {
                        "type": "string",
                        "description": "Customer contact phone number."
                    },
                    "address": {
                        "type": "string",
                        "description": "Customer delivery/shipping address."
                    }
                },
                "required": ["product_name", "quantity", "name", "phone", "address"],
            },
        },
    },
]


# ============================================================================
# 4. LLM CALLER (STANDARD LIBRARY - ZERO EXTERNAL LLM PACKAGES)
# ============================================================================

def call_groq(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sends chat completions request to Groq API using built-in urllib."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing in your .env file.")

    payload: Dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
    }

    req = urllib.request.Request(BASE_URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls"),
            "usage": usage,
        }


# ============================================================================
# 5. SALES AGENT CLASS
# ============================================================================

SYSTEM_PROMPT = """You are a helpful and polite Product Sales AI Assistant for an online electronics store.

CRITICAL RULE - STRICT SALES DOMAIN ONLY:
- You are EXCLUSIVELY a product sales assistant for this electronics store.
- You must ONLY answer questions directly related to our products (Laptop, Smartphone, Headphones, Smartwatch), prices, inventory, purchasing, shipping, and order placement.
- If the user asks ANY question unrelated to store products or sales (for example: general knowledge, geography, coding, science, history, weather, jokes, poems, recipes, politics, personal questions, etc.), you MUST decline to answer and reply:
  "I can only assist with store sales, products, and placing orders. How can I help you with our store items today?"
- NEVER answer off-topic questions even if you know the answer.

Follow this exact sales workflow:
1. When a user asks about buying a product and specifies quantity:
   - Call `check_inventory(product_name, quantity)` first.
2. If the product is NOT found or stock is INSUFFICIENT:
   - Politely inform the user about current availability or catalog items.
3. If stock IS AVAILABLE:
   - Tell the user the product is in stock with price, and ask them to provide their 3 details:
     (1) Name, (2) Phone Number, (3) Delivery Address.
4. Once the customer provides their Name, Phone, and Address:
   - Call `place_order(product_name, quantity, name, phone, address)`.
   - Confirm the order with the Order ID, total amount, and delivery address.

Keep your responses friendly, concise, and professional.
"""


class SalesAgent:
    def __init__(
        self,
        max_turns: int = 5,
        use_guardrails: bool = True,
        guardrails: Optional[GuardrailPipeline] = None,
        use_observability: bool = True,
        tracer: Optional[Tracer] = None,
    ):
        self.max_turns = max_turns
        self.use_guardrails = use_guardrails
        self.guardrails = guardrails or GuardrailPipeline()
        self.use_observability = use_observability
        self.tracer = tracer or default_tracer
        self.conversation_history: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def chat(self, user_message: str, print_observability: bool = True) -> str:
        """Processes user input through the tool-calling agent loop with guardrails and observability."""
        trace = self.tracer.start_trace(user_message) if self.use_observability else None

        # 1. Input Guardrail: Block prompt injection, jailbreaks, or out-of-scope commands
        if self.use_guardrails:
            span = self.tracer.start_span("guardrail.input") if self.use_observability else None
            if span:
                span.log(f"Evaluating user prompt: '{user_message}'")
            input_check = self.guardrails.validate_input(user_message)
            if not input_check.is_safe:
                refusal = input_check.reason or "Security Notice: Request blocked by security guardrails."
                if span:
                    span.record_error(f"Blocked: {input_check.violation_type}")
                    span.end()
                if trace:
                    self.tracer.end_trace(print_terminal=print_observability)
                self.conversation_history.append({"role": "user", "content": user_message})
                self.conversation_history.append({"role": "assistant", "content": refusal})
                return refusal
            if span:
                span.log("Input validated: passed security policies.")
                span.end()

        self.conversation_history.append({"role": "user", "content": user_message})

        turns = 0
        while turns < self.max_turns:
            turns += 1

            # 2. LLM Call Span
            llm_span = self.tracer.start_span("llm.call_groq") if self.use_observability else None
            if llm_span:
                llm_span.log(f"Invoking Groq API model: {MODEL}")
                llm_span.set_attribute("model", MODEL)

            try:
                response = call_groq(messages=self.conversation_history, tools=TOOLS_SCHEMA)
                usage = response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                comp_tokens = usage.get("completion_tokens", 0)
                if trace:
                    trace.add_tokens(prompt_tokens, comp_tokens)
                if llm_span:
                    llm_span.set_attribute("tokens", {"prompt": prompt_tokens, "completion": comp_tokens})
                    llm_span.log(f"Response received. Tokens: {prompt_tokens + comp_tokens}")
                    llm_span.end()
            except Exception as e:
                if llm_span:
                    llm_span.record_error(e)
                    llm_span.end()
                if trace:
                    self.tracer.end_trace(print_terminal=print_observability)
                return f"[Error connecting to AI service]: {e}"

            tool_calls = response.get("tool_calls")
            content = response.get("content")

            # 3. Output Guardrail check on direct content
            if self.use_guardrails and content:
                out_span = self.tracer.start_span("guardrail.output") if self.use_observability else None
                output_check = self.guardrails.validate_output(content)
                if not output_check.is_safe:
                    if out_span:
                        out_span.record_error(f"Violation: {output_check.violation_type}")
                    content = (
                        output_check.sanitized_data
                        if output_check.action == GuardrailAction.SANITIZE
                        else output_check.reason
                    )
                else:
                    if out_span:
                        out_span.log("Output validated: no secret/PII leaks detected.")
                if out_span:
                    out_span.end()

            # If no tool called, agent produced direct text response
            if not tool_calls:
                self.conversation_history.append({"role": "assistant", "content": content or ""})
                if trace:
                    self.tracer.end_trace(print_terminal=print_observability)
                return content or ""

            # Tool execution
            self.conversation_history.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": tool_calls
            })

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})

                print(f"  [*] Executing tool: `{fn_name}` with args: {args}")

                # 4. Tool Execution Span
                tool_span = self.tracer.start_span(f"tool.{fn_name}") if self.use_observability else None
                if tool_span:
                    tool_span.set_attribute("tool_name", fn_name)
                    tool_span.set_attribute("args", args)
                    tool_span.log(f"Calling tool `{fn_name}` with args: {args}")

                # Tool Execution Guardrail: Validate & sanitize parameters before calling
                if self.use_guardrails:
                    tool_check = self.guardrails.validate_tool_call(fn_name, args)
                    if not tool_check.is_safe:
                        tool_result = f"GUARDRAIL_BLOCKED: {tool_check.reason}"
                        print(f"  [!] Tool blocked by guardrail: {tool_check.reason}")
                        if tool_span:
                            tool_span.record_error(f"Guardrail blocked: {tool_check.reason}")
                            tool_span.end()
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", "call_1"),
                            "name": fn_name,
                            "content": str(tool_result),
                        })
                        continue
                    elif tool_check.sanitized_data:
                        args = tool_check.sanitized_data

                if fn_name in TOOLS_REGISTRY:
                    try:
                        tool_result = TOOLS_REGISTRY[fn_name](**args)
                        if tool_span:
                            tool_span.set_attribute("result_preview", str(tool_result)[:100])
                            tool_span.log(f"Tool `{fn_name}` executed successfully.")
                    except Exception as err:
                        tool_result = f"Error executing {fn_name}: {err}"
                        if tool_span:
                            tool_span.record_error(err)
                else:
                    tool_result = f"Error: Tool '{fn_name}' not available."
                    if tool_span:
                        tool_span.record_error(f"Tool {fn_name} not found")

                if tool_span:
                    tool_span.end()

                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_1"),
                    "name": fn_name,
                    "content": str(tool_result),
                })

        if trace:
            self.tracer.end_trace(print_terminal=print_observability)
        return "I could not complete your request within the turn limit. Please try again."


# ============================================================================
# 6. INTERACTIVE CLI RUNNER
# ============================================================================

def main():
    print("=" * 65)
    print("           PRODUCT SALES AI AGENT")
    print(f" Model:     {MODEL} (Groq Free API)")
    print(f" Inventory: {INVENTORY_FILE.name}")
    print("=" * 65)
    print("Type your message below (or 'exit' to quit).\n")

    agent = SalesAgent()

    # Show initial catalog
    inv = get_inventory()
    print("Current Catalog:")
    for k, v in inv.items():
        print(f"  - {v['name']}: ${v['price']} (Stock: {v['stock']})")
    print("-" * 65)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\nYou > {query}")
        reply = agent.chat(query)
        print(f"\nAI  > {reply}\n")
        return

    while True:
        try:
            user_input = input("\nYou > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Thank you for shopping with us! Goodbye.")
                break
            reply = agent.chat(user_input)
            print(f"\nAI  > {reply}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break


if __name__ == "__main__":
    main()

