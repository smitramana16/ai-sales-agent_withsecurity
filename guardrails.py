"""
Modular AI Agent Guardrails Framework
======================================
Enterprise-grade, modular security pipeline implementing:
1. InputGuardrail: Blocks prompt injection, jailbreaks, and persona hijacks.
2. ToolExecutionGuardrail: Validates schemas, enforces quantity limits, and strictly checks 10/12-digit phone numbers and sanitized inputs.
3. OutputGuardrail: Intercepts secret leakage, API keys, and sensitive token disclosures.

Designed following SOLID principles, clean architecture, and type safety.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple


class GuardrailAction(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    SANITIZE = "SANITIZE"


@dataclass
class GuardrailResult:
    action: GuardrailAction
    is_safe: bool
    reason: Optional[str] = None
    violation_type: Optional[str] = None
    sanitized_data: Optional[Any] = None

    @classmethod
    def allow(cls, sanitized_data: Optional[Any] = None) -> "GuardrailResult":
        return cls(action=GuardrailAction.ALLOW, is_safe=True, sanitized_data=sanitized_data)

    @classmethod
    def block(cls, reason: str, violation_type: str) -> "GuardrailResult":
        return cls(action=GuardrailAction.BLOCK, is_safe=False, reason=reason, violation_type=violation_type)

    @classmethod
    def sanitize(cls, sanitized_data: Any, reason: str, violation_type: str) -> "GuardrailResult":
        return cls(action=GuardrailAction.SANITIZE, is_safe=True, reason=reason, violation_type=violation_type, sanitized_data=sanitized_data)


# ============================================================================
# BASE GUARDRAIL INTERFACE
# ============================================================================

class BaseGuardrail(ABC):
    """Abstract base class for all guardrail rules (Interface Segregation / Open-Closed)."""
    
    @abstractmethod
    def validate(self, target: Any) -> GuardrailResult:
        """Validates the target data and returns a GuardrailResult."""
        pass


# ============================================================================
# 1. INPUT GUARDRAILS (Pre-LLM)
# ============================================================================

class InputSecurityGuardrail(BaseGuardrail):
    """
    Scans user prompt for prompt injection, jailbreaks, persona hijacking,
    and dangerous command signatures before passing to the model.
    """

    # Adversarial & injection signatures
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous\s+|prior\s+|above\s+)?instructions",
        r"disregard\s+(all\s+)?(previous\s+|prior\s+|above\s+)?instructions",
        r"you\s+are\s+now\s+(a|an)\s+",
        r"pretend\s+(you\s+are|to\s+be)\s+",
        r"jailbreak",
        r"developer\s+mode",
        r"giveaway\s+bot",
        r"free\s+of\s+charge",
        r"for\s+free\s+(\(\$0\))?",
        r"system\s+prompt",
        r"system\s+instructions",
        r"secret\s+api\s+key",
        r"reveal\s+your\s+(hidden|internal|prompt)",
        r"(write|generate|create)\s+(a\s+)?(keylogger|malware|ransomware|exploit|virus)",
        r"drop\s+table\s+",
        r"<script.*?>.*?</script>",
    ]

    def __init__(self, blocked_patterns: Optional[List[str]] = None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (blocked_patterns or self.INJECTION_PATTERNS)]

    def validate(self, target: str) -> GuardrailResult:
        if not isinstance(target, str):
            return GuardrailResult.block("Input must be a valid text string.", "INVALID_TYPE")

        clean_text = target.strip()
        if not clean_text:
            return GuardrailResult.block("Input cannot be empty.", "EMPTY_INPUT")

        for pattern in self.patterns:
            if pattern.search(clean_text):
                return GuardrailResult.block(
                    "Security Notice: Request blocked by security guardrails due to detected prompt injection or disallowed intent.",
                    "PROMPT_INJECTION_DETECTED"
                )

        return GuardrailResult.allow(clean_text)


# ============================================================================
# 2. TOOL EXECUTION GUARDRAILS (Pre-Tool Execution)
# ============================================================================

class ToolExecutionGuardrail(BaseGuardrail):
    """
    Validates tool parameters before invocation:
    - Enforces valid positive quantity limits (1 <= quantity <= 100).
    - Enforces strict 10 or 12 digit phone number validation.
    - Sanitizes and validates customer names and addresses against XSS/injections.
    """

    MAX_ORDER_QUANTITY = 100
    MIN_ORDER_QUANTITY = 1

    def validate(self, target: Tuple[str, Dict[str, Any]]) -> GuardrailResult:
        """
        Target is a tuple of (tool_name, arguments_dict).
        """
        tool_name, args = target
        if not isinstance(args, dict):
            return GuardrailResult.block("Tool arguments must be a structured dictionary.", "INVALID_TOOL_ARGS")

        if tool_name == "check_inventory":
            return self._validate_check_inventory(args)
        elif tool_name == "place_order":
            return self._validate_place_order(args)
        else:
            return GuardrailResult.allow(args)

    def _validate_check_inventory(self, args: Dict[str, Any]) -> GuardrailResult:
        # Validate quantity
        quantity = args.get("quantity")
        if quantity is None or not isinstance(quantity, (int, float)):
            return GuardrailResult.block("Quantity must be a numeric integer value.", "INVALID_QUANTITY_TYPE")

        qty_int = int(quantity)
        if qty_int < self.MIN_ORDER_QUANTITY:
            return GuardrailResult.block(
                f"Security Policy: Order quantity must be at least {self.MIN_ORDER_QUANTITY}. Received: {qty_int}.",
                "INVALID_QUANTITY_RANGE"
            )
        if qty_int > self.MAX_ORDER_QUANTITY:
            return GuardrailResult.block(
                f"Security Policy: Order quantity exceeds maximum bulk purchase limit of {self.MAX_ORDER_QUANTITY} units.",
                "EXCESSIVE_QUANTITY"
            )

        # Validate product_name
        product = args.get("product_name", "")
        if not isinstance(product, str) or not product.strip():
            return GuardrailResult.block("Product name cannot be empty.", "INVALID_PRODUCT_NAME")

        if len(product) > 50:
            return GuardrailResult.block("Product name length exceeds security boundary (max 50 chars).", "PAYLOAD_TOO_LARGE")

        sanitized_args = dict(args)
        sanitized_args["quantity"] = qty_int
        sanitized_args["product_name"] = product.strip()
        return GuardrailResult.allow(sanitized_args)

    def _validate_place_order(self, args: Dict[str, Any]) -> GuardrailResult:
        # 1. Validate quantity
        inventory_check = self._validate_check_inventory(args)
        if not inventory_check.is_safe:
            return inventory_check

        sanitized_args = dict(args)

        # 2. Strict Phone Number Validation: exactly 10 or 12 digits
        phone = str(args.get("phone", "")).strip()
        digits_only = re.sub(r"\D", "", phone)
        if len(digits_only) not in (10, 12):
            return GuardrailResult.block(
                f"Security Policy: Phone number must contain exactly 10 or 12 digits. Received {len(digits_only)} digits: '{phone}'.",
                "INVALID_PHONE_FORMAT"
            )
        sanitized_args["phone"] = digits_only

        # 3. Customer Name Validation & Sanitization
        name = str(args.get("name", "")).strip()
        if len(name) < 2 or len(name) > 60:
            return GuardrailResult.block("Customer name must be between 2 and 60 characters.", "INVALID_NAME_LENGTH")
        if re.search(r"[<>{}\[\];=]", name):
            return GuardrailResult.block("Customer name contains invalid or unsafe characters.", "XSS_OR_INJECTION_IN_NAME")
        sanitized_args["name"] = name

        # 4. Customer Address Validation & Sanitization
        address = str(args.get("address", "")).strip()
        if len(address) < 5 or len(address) > 150:
            return GuardrailResult.block("Delivery address must be between 5 and 150 characters.", "INVALID_ADDRESS_LENGTH")
        if re.search(r"(<script|javascript:|drop\s+table)", address, re.IGNORECASE):
            return GuardrailResult.block("Delivery address contains disallowed script or command patterns.", "INJECTION_IN_ADDRESS")
        sanitized_args["address"] = address

        return GuardrailResult.allow(sanitized_args)


# ============================================================================
# 3. OUTPUT GUARDRAILS (Post-LLM / Pre-User)
# ============================================================================

class OutputSecurityGuardrail(BaseGuardrail):
    """
    Scans the LLM output before presentation to user:
    - Blocks secret leaks (API keys like gsk_..., tvly-..., sk-...).
    - Prevents system prompt or internal developer instruction disclosure.
    """

    SECRET_PATTERNS = [
        re.compile(r"gsk_[A-Za-z0-9_-]{20,}", re.IGNORECASE),
        re.compile(r"tvly-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
        re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
        re.compile(r"ey[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT tokens
    ]

    LEAKAGE_SIGNATURES = [
        re.compile(r"SYSTEM_PROMPT\s*=", re.IGNORECASE),
        re.compile(r"call_groq\(", re.IGNORECASE),
        re.compile(r"GROQ_API_KEY", re.IGNORECASE),
    ]

    def validate(self, target: str) -> GuardrailResult:
        if not isinstance(target, str):
            return GuardrailResult.allow(target)

        text = target

        # 1. Check for secret key leakage
        for secret_pattern in self.SECRET_PATTERNS:
            if secret_pattern.search(text):
                # Redact secret token
                sanitized_text = secret_pattern.sub("[REDACTED_API_KEY]", text)
                return GuardrailResult.sanitize(
                    sanitized_text,
                    "Security Warning: An API key or secret token was redacted from model output.",
                    "SECRET_DATA_LEAKAGE"
                )

        # 2. Check for system prompt / internal instruction leakage
        for leak_sig in self.LEAKAGE_SIGNATURES:
            if leak_sig.search(text):
                return GuardrailResult.block(
                    "Security Notice: Model response withheld because it contained internal system configuration disclosures.",
                    "INTERNAL_DATA_LEAKAGE"
                )

        return GuardrailResult.allow(text)


# ============================================================================
# 4. ORCHESTRATED GUARDRAILS PIPELINE
# ============================================================================

class GuardrailPipeline:
    """
    Unified manager orchestrating Input, Tool, and Output guardrails.
    Adheres to Single Responsibility Principle.
    """

    def __init__(
        self,
        input_guardrail: Optional[InputSecurityGuardrail] = None,
        tool_guardrail: Optional[ToolExecutionGuardrail] = None,
        output_guardrail: Optional[OutputSecurityGuardrail] = None,
    ):
        self.input_guardrail = input_guardrail or InputSecurityGuardrail()
        self.tool_guardrail = tool_guardrail or ToolExecutionGuardrail()
        self.output_guardrail = output_guardrail or OutputSecurityGuardrail()
        self.violations_log: List[Dict[str, Any]] = []

    def validate_input(self, user_prompt: str) -> GuardrailResult:
        result = self.input_guardrail.validate(user_prompt)
        if not result.is_safe:
            self._log_violation("INPUT", result)
        return result

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> GuardrailResult:
        result = self.tool_guardrail.validate((tool_name, arguments))
        if not result.is_safe:
            self._log_violation("TOOL", result, {"tool": tool_name, "args": arguments})
        return result

    def validate_output(self, model_output: str) -> GuardrailResult:
        result = self.output_guardrail.validate(model_output)
        if not result.is_safe:
            self._log_violation("OUTPUT", result)
        return result

    def _log_violation(self, stage: str, result: GuardrailResult, extra: Optional[Dict[str, Any]] = None):
        log_entry = {
            "stage": stage,
            "action": result.action.value,
            "violation_type": result.violation_type,
            "reason": result.reason,
            "extra": extra or {},
        }
        self.violations_log.append(log_entry)

