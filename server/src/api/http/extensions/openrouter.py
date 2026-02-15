"""OpenRouter extension - AI services via OpenRouter API."""

import json

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.user_options import UserOptions

OPENROUTER_API = "https://openrouter.ai/api/v1"
DEFAULT_FREE_MODEL = "openrouter/free"


async def get_models(request: web.Request) -> web.Response:
    """Fetch available models from OpenRouter, filtering free ones."""
    await get_authorized_user(request)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OPENROUTER_API}/models") as resp:
                if resp.status != 200:
                    return web.json_response(
                        {"error": "Failed to fetch models"},
                        status=502,
                    )
                data = await resp.json()
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=502,
        )

    models = data.get("data", [])
    result = []
    for m in models:
        model_id = m.get("id", "")
        pricing = m.get("pricing", {}) or {}
        prompt_cost = float(pricing.get("prompt", 1) or 1)
        completion_cost = float(pricing.get("completion", 1) or 1)
        is_free = prompt_cost == 0 and completion_cost == 0
        result.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "context_length": m.get("context_length"),
            "is_free": is_free,
        })

    return web.json_response({"models": result})


async def chat(request: web.Request) -> web.Response:
    """Proxy chat completion to OpenRouter."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    messages = body.get("messages", [])
    if not messages:
        return web.HTTPBadRequest(text="messages is required")

    model = body.get("model", DEFAULT_FREE_MODEL)
    max_tokens = body.get("max_tokens", 2048)
    temperature = body.get("temperature", 0.7)

    opts = UserOptions.get_by_id(user.default_options)
    api_key = (opts.openrouter_api_key or "").strip()
    if not api_key:
        return web.json_response(
            {"error": "OpenRouter API key not configured. Set it in the OpenRouter extension settings."},
            status=400,
        )

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": request.url.origin or "https://planarally.io",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OPENROUTER_API}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    try:
                        err_data = json.loads(text)
                        err_msg = err_data.get("error", {}).get("message", text)
                    except Exception:
                        err_msg = text
                    return web.json_response(
                        {"error": err_msg},
                        status=resp.status,
                    )
                return web.json_response(json.loads(text))
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=502,
        )


async def get_settings(request: web.Request) -> web.Response:
    """Get OpenRouter settings for the current user (API key masked, model, base prompt, tasks)."""
    user = await get_authorized_user(request)
    opts = UserOptions.get_by_id(user.default_options)

    api_key = opts.openrouter_api_key or ""
    has_key = bool(api_key.strip())

    tasks = []
    if opts.openrouter_tasks:
        try:
            tasks = json.loads(opts.openrouter_tasks)
        except (json.JSONDecodeError, TypeError):
            pass

    return web.json_response({
        "hasApiKey": has_key,
        "model": opts.openrouter_model or DEFAULT_FREE_MODEL,
        "basePrompt": opts.openrouter_base_prompt or "",
        "tasks": tasks,
    })


async def set_settings(request: web.Request) -> web.Response:
    """Update OpenRouter settings for the current user."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    api_key = body.get("apiKey", "")
    model = body.get("model", "").strip()
    base_prompt = body.get("basePrompt", "")
    tasks = body.get("tasks")

    opts = UserOptions.get_by_id(user.default_options)

    if "apiKey" in body:
        opts.openrouter_api_key = api_key.strip() or None
    if model:
        opts.openrouter_model = model
    if "basePrompt" in body:
        opts.openrouter_base_prompt = base_prompt.strip() or None
    if tasks is not None:
        opts.openrouter_tasks = json.dumps(tasks) if tasks else None

    opts.save()

    return web.json_response({"ok": True})
