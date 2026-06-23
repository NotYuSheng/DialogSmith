"""Shared OpenAI-compatible LLM client.

One client for every optional LLM feature (quality validation, LLM redaction).
It speaks the OpenAI Chat Completions API, so it works against OpenAI itself
*and* any local/self-hosted server that exposes that API — Ollama, vLLM, LM
Studio, llama.cpp's server, LiteLLM, etc. Running a local endpoint is the
privacy-preserving way to use these features, since your chat text never leaves
your machine.

Environment variables:
  LLM_VALIDATE   true/false. Default: enabled when LLM_API_KEY or
                 LLM_API_BASE_URL is set, disabled otherwise.
  LLM_API_BASE_URL  OpenAI-compatible base URL. Set this for a local model, e.g.
                 http://localhost:11434/v1 (Ollama) or http://localhost:8000/v1
                 (vLLM). Unset → OpenAI's hosted API.
  LLM_MODEL      Model id (default: gpt-4o-mini). For a local server use whatever
                 it serves, e.g. "qwen2.5" or "llama3.1".
  LLM_API_KEY    API key. Local servers usually accept any value; falls back to
                 OPENAI_API_KEY if unset.
"""

import os

VALIDATE_ENV = "LLM_VALIDATE"
MODEL_ENV = "LLM_MODEL"
BASE_URL_ENV = "LLM_API_BASE_URL"
API_KEY_ENV = "LLM_API_KEY"
DEFAULT_MODEL = "gpt-4o-mini"


def base_url() -> str:
    return os.environ.get(BASE_URL_ENV, "").strip()


def model() -> str:
    return os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL


def is_local() -> bool:
    """True when a custom (presumably local/self-hosted) endpoint is configured."""
    return bool(base_url())


def _api_key() -> str:
    return (
        os.environ.get(API_KEY_ENV, "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )


def should_validate() -> bool:
    val = os.environ.get(VALIDATE_ENV, "").strip().lower()
    if val == "false":
        return False
    if val == "true":
        return True
    # Default: enable when there's something to talk to.
    return bool(_api_key() or base_url())


def get_client():
    """Build an OpenAI-compatible client. Raises if unusable (caller handles)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for LLM features. "
            "Install it with: pip install openai"
        )
    url = base_url()
    key = _api_key()
    if not key:
        if url:
            key = "not-needed"  # local servers ignore it, but the SDK requires a value
        else:
            raise EnvironmentError(
                f"{API_KEY_ENV} is not set. Set it, point {BASE_URL_ENV} at a "
                f"local endpoint, or set {VALIDATE_ENV}=false."
            )
    kwargs = {"api_key": key}
    if url:
        kwargs["base_url"] = url
    return OpenAI(**kwargs)


def endpoint_label() -> str:
    return base_url() or "OpenAI API"


def chat(client, model_name: str, prompt: str, max_tokens: int = 256) -> str:
    """Single-prompt completion; returns the assistant message text."""
    resp = client.chat.completions.create(
        model=model_name,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()
