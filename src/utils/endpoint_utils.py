from __future__ import annotations
import os


def normalize_openrouter_base_url(url: str | None) -> str:
    """Normalize OpenRouter base URL to the /api/v1 form.

    Examples:
      https://openrouter.ai/api    -> https://openrouter.ai/api/v1
      https://openrouter.ai/api/   -> https://openrouter.ai/api/v1
      https://openrouter.ai/api/v1 -> https://openrouter.ai/api/v1
      http://172.17.0.1:4200       -> http://172.17.0.1:4200/v1
      http://172.17.0.1:4200/v1    -> http://172.17.0.1:4200/v1
    """
    if not url:
        return "https://openrouter.ai/api/v1"

    normalized = url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    if normalized.endswith("/api"):
        return normalized + "/v1"
    # Bare host or arbitrary path that's clearly a non-openrouter LiteLLM
    # endpoint (e.g. http://172.17.0.1:4200): append /v1.
    return normalized + "/v1"


def normalize_openrouter_base_url_for_openclaw(url: str | None) -> str:
    return normalize_openrouter_base_url(url)


def normalize_openrouter_base_url_for_claudecode(url: str | None) -> str:
    """Strip trailing /v1 so the Anthropic SDK appends its own /v1/messages.

    Examples (verified):
      https://openrouter.ai/api/v1  -> https://openrouter.ai/api
      http://172.17.0.1:4200/v1     -> http://172.17.0.1:4200
      http://172.17.0.1:4200        -> http://172.17.0.1:4200
    """
    if not url:
        return "https://openrouter.ai/api"

    normalized = url.strip().rstrip("/")
    # Fix for self-hosted LiteLLM (Wanli-Lee/CUA-Claw-Harness): the upstream
    # rule only stripped /api/v1, leaving non-openrouter /v1 endpoints
    # like http://172.17.0.1:4200/v1 alone — which then makes the Anthropic
    # SDK POST to .../v1/v1/messages. Strip a bare trailing /v1 too.
    if normalized.endswith("/api/v1"):
        return normalized[: -len("/v1")]
    if normalized.endswith("/v1"):
        return normalized[: -len("/v1")]
    return normalized


# ---------------------------------------------------------------------------
# WCB-specific helpers — agent endpoint (4200) vs judge endpoint (4141)
# ---------------------------------------------------------------------------

WCB_DEFAULT_AGENT_BASE_URL = "http://172.17.0.1:4200/v1"
WCB_DEFAULT_AGENT_API_KEY  = "sk-litellm-azure-direct"
WCB_DEFAULT_AGENT_MODEL    = "gpt-5.5"

WCB_DEFAULT_JUDGE_BASE_URL = "http://172.17.0.1:4141/v1"
WCB_DEFAULT_JUDGE_API_KEY  = ""  # cop-api requires no key
WCB_DEFAULT_JUDGE_MODEL    = "gpt-5.5"


def wcb_agent_endpoint() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) for the agent LLM, with env override.

    Env precedence:
      WCB_AGENT_BASE_URL > OPENROUTER_BASE_URL > WCB_DEFAULT_AGENT_BASE_URL
      WCB_AGENT_API_KEY  > OPENROUTER_API_KEY  > WCB_DEFAULT_AGENT_API_KEY
      WCB_AGENT_MODEL    > DEFAULT_MODEL       > WCB_DEFAULT_AGENT_MODEL
    """
    base_url = (
        os.environ.get("WCB_AGENT_BASE_URL")
        or os.environ.get("OPENROUTER_BASE_URL")
        or WCB_DEFAULT_AGENT_BASE_URL
    )
    api_key = (
        os.environ.get("WCB_AGENT_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or WCB_DEFAULT_AGENT_API_KEY
    )
    model = (
        os.environ.get("WCB_AGENT_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or WCB_DEFAULT_AGENT_MODEL
    )
    return base_url, api_key, model


def wcb_judge_endpoint() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) for the LLM judge, with env override."""
    base_url = (
        os.environ.get("WCB_JUDGE_BASE_URL")
        or WCB_DEFAULT_JUDGE_BASE_URL
    )
    api_key = os.environ.get("WCB_JUDGE_API_KEY", WCB_DEFAULT_JUDGE_API_KEY)
    model = (
        os.environ.get("WCB_JUDGE_MODEL")
        or WCB_DEFAULT_JUDGE_MODEL
    )
    return base_url, api_key, model
