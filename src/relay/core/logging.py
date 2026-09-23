import json
import logging
import re
from typing import Any

SENSITIVE_PATTERNS = [
    (re.compile(r'\b(?:\d[ -]*?){13,16}\b'), "[REDACTED_CARD]"),
    (re.compile(r'(?i)(?:password|secret|token|api_key|authorization)\s*[:=]\s*["\']?([^"\'\s]+)["\']?'), r"\1=[REDACTED_SECRET]"),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'), "[REDACTED_EMAIL]"),
]

def redact_sensitive_text(text: str) -> str:
    """Redacts PII, emails, credit cards, and secret values from strings."""
    if not text or not isinstance(text, str):
        return text
    redacted = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted

class RedactedJsonFormatter(logging.Formatter):
    """
    Structured JSON log formatter that automatically redacts sensitive customer data
    and ensures correlation IDs and timestamps are formatted consistently.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
        }

        # Include custom contextual attributes if available
        for key in ["correlation_id", "job_id", "ticket_id", "tenant_id", "worker_id", "fencing_token"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)

def setup_structured_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactedJsonFormatter())
    
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
