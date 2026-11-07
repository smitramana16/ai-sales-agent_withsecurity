"""
Observability Framework: Log, Trace, Span
==========================================
Lightweight, pure-Python observability system tracking:
- Traces: End-to-end request lifecycle and aggregated metrics.
- Spans: Fine-grained execution units (functions, LLM calls, tools, guardrails).
- Logs: Structured contextual event logs within each span.
- Metrics: Execution time (ms), token consumption, cost calculation ($USD), and error tracking.
"""

import time
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================================
# 1. CORE DATA STRUCTURES: LOG, SPAN, TRACE
# ============================================================================

class LogLevel(Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class LogRecord:
    timestamp: str
    level: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata,
        }


class Span:
    """Represents a discrete unit of work (e.g. LLM call, Tool execution, Guardrail check)."""

    def __init__(self, name: str, trace_id: str, parent_span_id: Optional[str] = None):
        self.span_id: str = f"spn_{uuid.uuid4().hex[:8]}"
        self.trace_id: str = trace_id
        self.parent_span_id: Optional[str] = parent_span_id
        self.name: str = name
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.status: str = "OK"  # "OK" or "ERROR"
        self.error: Optional[str] = None
        self.attributes: Dict[str, Any] = {}
        self.logs: List[LogRecord] = []

    def log(self, message: str, level: str = "INFO", **kwargs):
        """Appends a structured log event to this span."""
        record = LogRecord(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            level=level.upper(),
            message=message,
            metadata=kwargs,
        )
        self.logs.append(record)

    def set_attribute(self, key: str, value: Any):
        """Sets metadata attribute (e.g., args, tokens, cost)."""
        self.attributes[key] = value

    def record_error(self, error: Any):
        """Marks the span as failed and records the error."""
        self.status = "ERROR"
        self.error = str(error)
        self.log(f"Error encountered: {self.error}", level="ERROR")

    def end(self):
        """Completes the span and calculates duration."""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.record_error(exc_val)
        self.end()
        return False  # Do not suppress exceptions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
            "logs": [l.to_dict() for l in self.logs],
        }


class Trace:
    """Represents an end-to-end user transaction."""

    # Standard commercial reference pricing per 1M tokens ($0.10 prompt, $0.20 completion)
    PROMPT_TOKEN_RATE_PER_1M = 0.10
    COMPLETION_TOKEN_RATE_PER_1M = 0.20

    def __init__(self, name: str, user_query: str):
        self.trace_id: str = f"trc_{uuid.uuid4().hex[:8]}"
        self.name: str = name
        self.user_query: str = user_query
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.status: str = "OK"
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.spans: List[Span] = []

    def start_span(self, name: str, parent_span_id: Optional[str] = None) -> Span:
        span = Span(name=name, trace_id=self.trace_id, parent_span_id=parent_span_id)
        self.spans.append(span)
        return span

    def add_tokens(self, prompt_tokens: int, completion_tokens: int):
        """Accumulates token usage and updates cost calculation."""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        prompt_cost = (prompt_tokens / 1_000_000) * self.PROMPT_TOKEN_RATE_PER_1M
        completion_cost = (completion_tokens / 1_000_000) * self.COMPLETION_TOKEN_RATE_PER_1M
        self.total_cost_usd = round(self.total_cost_usd + prompt_cost + completion_cost, 6)

    def end(self):
        """Concludes the trace and sums up duration."""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
            # If any span errored, mark trace as error
            if any(s.status == "ERROR" for s in self.spans):
                self.status = "ERROR"

    def print_terminal_summary(self):
        """Prints a visual, structured observability summary directly in the terminal."""
        self.end()
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        status_badge = "OK [SUCCESS]" if self.status == "OK" else "ERROR [FAILED]"

        print("\n" + "=" * 70)
        print("                 OBSERVABILITY TRACE REPORT")
        print("=" * 70)
        print(f" Trace ID:     {self.trace_id}")
        print(f" Query:        \"{self.user_query[:50]}{'...' if len(self.user_query) > 50 else ''}\"")
        print(f" Duration:     {self.duration_ms} ms")
        print(f" Status:       {status_badge}")
        print(f" Tokens Used:  {total_tokens} (Prompt: {self.total_prompt_tokens}, Completion: {self.total_completion_tokens})")
        print(f" Est. Cost:    ${self.total_cost_usd:.6f} USD")
        print("-" * 70)
        print(" SPANS & LOGS TIMELINE:")

        for i, span in enumerate(self.spans, start=1):
            span_status = "✓ OK" if span.status == "OK" else "✗ ERR"
            print(f"\n  [{i}] SPAN: {span.name:<25} [{span_status}] ({span.duration_ms} ms)")
            
            # Print key attributes
            if span.attributes:
                for attr_k, attr_v in span.attributes.items():
                    print(f"      • attr:{attr_k} = {attr_v}")

            # Print error if any
            if span.error:
                print(f"      • ERROR: {span.error}")

            # Print structured logs
            for l in span.logs:
                level_tag = f"[{l.level}]"
                print(f"      └─ {l.timestamp} {level_tag:<7} {l.message}")

        print("=" * 70 + "\n")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "query": self.user_query,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "tokens": {
                "prompt": self.total_prompt_tokens,
                "completion": self.total_completion_tokens,
                "total": self.total_prompt_tokens + self.total_completion_tokens,
            },
            "cost_usd": self.total_cost_usd,
            "spans": [s.to_dict() for s in self.spans],
        }


# ============================================================================
# 2. TRACER MANAGER
# ============================================================================

class Tracer:
    """Manages active traces and provides easy span lifecycle handling."""

    def __init__(self, log_to_file: bool = True, log_file: Optional[Path] = None):
        self.current_trace: Optional[Trace] = None
        self.log_to_file: bool = log_to_file
        self.log_file: Path = log_file or (Path(__file__).resolve().parent / "traces.json")

    def start_trace(self, user_query: str, name: str = "agent_request") -> Trace:
        self.current_trace = Trace(name=name, user_query=user_query)
        return self.current_trace

    def start_span(self, name: str) -> Span:
        if not self.current_trace:
            self.start_trace("untracked_query", name="auto_trace")
        return self.current_trace.start_span(name)

    def end_trace(self, print_terminal: bool = True) -> Optional[Trace]:
        if not self.current_trace:
            return None
        self.current_trace.end()
        if print_terminal:
            self.current_trace.print_terminal_summary()

        if self.log_to_file:
            self._save_trace(self.current_trace)

        trace = self.current_trace
        self.current_trace = None
        return trace

    def _save_trace(self, trace: Trace):
        records = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []
        records.append(trace.to_dict())
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception:
            pass


# Global singleton tracer
default_tracer = Tracer()

