"""Redact secret-looking strings from log text before it is stored or sent.

`EPOCHIX_SCRUB_SECRETS` was documented — "Redact secret-looking strings from
stored lines" — and implemented nowhere, so turning it on changed nothing: a
training log that printed its W&B key, a database URL or an `HF_TOKEN` kept it
verbatim in the raw-line store, and the opt-in LLM fallback sent it to whatever
provider was configured. This is the implementation, and it is on by default:
it only ever touches the stored or transmitted COPY of a line, never what the
parsers read, so it cannot change a metric.

Every quantifier is bounded (AGENTS.md: an unbounded run before a delimiter is
O(n^2) on a long line). A plain number is never redacted, so a metric such as
`tokens_per_sec=1234` still reads as it was printed.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# scheme://user:password@host — keep the user, drop the password.
_URL_CREDENTIALS = re.compile(r"\b([a-z][a-z0-9+.-]{1,20}://[^\s:/@]{1,256}):[^\s@/]{1,256}@", re.I)

# Authorization: Bearer <token>
_BEARER = re.compile(r"\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,1024}", re.I)

# api_key=…, SECRET: …, "password": "…" — the name stays, the value goes. The
# name must END in the secret word: HF_TOKEN and WANDB_API_KEY match,
# tokenizer=… and max_tokens=512 do not.
_NAMED = re.compile(
    r"\b([A-Za-z0-9_.-]{0,40}"
    r"(?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key|private[_-]?key))"
    r"(['\"]?\s{0,4}[:=]\s{0,4})"
    r"(['\"]?)"
    r"(?![-+]?\d{1,40}(?:\.\d{1,40})?(?:[eE][-+]?\d{1,4})?(?:['\"\s,;)}\]]|$))"
    r"([^\s'\",;)}\]]{4,1024})",
    re.I,
)

# Credential formats that are recognisable on their own, named or not.
_SHAPES = re.compile(
    r"\b(?:"
    r"(?:AKIA|ASIA)[0-9A-Z]{16}"  # AWS access key id
    r"|gh[pousr]_[A-Za-z0-9]{36,255}"  # GitHub token
    r"|github_pat_[A-Za-z0-9_]{22,255}"  # GitHub fine-grained token
    r"|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,255}"  # OpenAI / Anthropic key
    r"|hf_[A-Za-z0-9]{30,64}"  # Hugging Face token
    r"|xox[abprs]-[A-Za-z0-9-]{10,255}"  # Slack token
    r"|AIza[0-9A-Za-z_-]{35}"  # Google API key
    r"|eyJ[A-Za-z0-9_-]{8,2048}\.[A-Za-z0-9_-]{8,2048}\.[A-Za-z0-9_-]{8,2048}"  # JWT
    r")\b"
)


def scrub_secrets(text: str) -> str:
    """*text* with anything that looks like a credential replaced by [REDACTED]."""
    if not text:
        return text
    text = _URL_CREDENTIALS.sub(rf"\1:{REDACTED}@", text)
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    text = _NAMED.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}", text)
    return _SHAPES.sub(REDACTED, text)
