from typing import Iterator

import httpx

import config


def _provider() -> str:
    return config.LLM_PROVIDER.lower().strip()


def _model() -> str:
    return config.LLM_MODEL


def generate_text(prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """Generate text using the configured LLM provider."""
    provider = _provider()
    if provider == "simulated":
        return ""
    if provider == "openai":
        return _openai_generate(prompt, temperature, max_tokens)
    if provider == "anthropic":
        return _anthropic_generate(prompt, temperature, max_tokens)
    if provider in ("ollama", "ollama_openai"):
        return _ollama_generate(prompt, temperature, max_tokens)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _openai_generate(prompt: str, temperature: float, max_tokens: int) -> str:
    api_key = config.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _model(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _anthropic_generate(prompt: str, temperature: float, max_tokens: int) -> str:
    api_key = config.ANTHROPIC_API_KEY
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": _model(),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def _ollama_generate(prompt: str, temperature: float, max_tokens: int) -> str:
    base_url = config.OLLAMA_BASE_URL.rstrip("/")
    api_key = config.OLLAMA_API_KEY
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Try OpenAI-compatible endpoint first (most hosted Ollama providers)
    chat_url = f"{base_url}/v1/chat/completions"
    try:
        resp = httpx.post(
            chat_url,
            headers=headers,
            json={
                "model": _model(),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError):
        pass

    # Fall back to native Ollama /api/generate endpoint
    resp = httpx.post(
        f"{base_url}/api/generate",
        headers=headers,
        json={
            "model": _model(),
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "").strip()


def wrap_content(content: str) -> str:
    """Wrap user-provided content in a delimiter to prevent prompt injection.
    
    The model is instructed to treat anything between the delimiters as data,
    not as instructions. This is defense-in-depth on top of input sanitization.
    """
    return f"<ARTICLE_CONTENT>\n{content}\n</ARTICLE_CONTENT>"


def is_real_llm_enabled() -> bool:
    return _provider() not in ("simulated", "")
