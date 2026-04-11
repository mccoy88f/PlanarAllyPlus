"""AI Generator extension - OpenRouter, Google AI Studio, and Cerebras Inference API."""

import base64
import hashlib
import json
import re
import uuid
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.user_options import UserOptions
from ....db.models.asset import Asset
from ....db.models.asset_entry import AssetEntry
from ....utils import ASSETS_DIR, STATIC_DIR
from ....utils import get_asset_hash_subpath

OPENROUTER_API = "https://openrouter.ai/api/v1"
CEREBRAS_API = "https://api.cerebras.ai/v1"
GOOGLE_AI_API = "https://generativelanguage.googleapis.com/v1beta"
CEREBRAS_MODEL_PREFIX = "cerebras:"
DEFAULT_FREE_MODEL = "openrouter/free"

# Elenco modelli dipende dalle API key dell’utente: non cacheare sul client.
_JSON_NO_STORE = {"Cache-Control": "no-store"}
DEFAULT_GOOGLE_MODEL = "gemini-2.0-flash"
# Models that support image-to-image (input image + output image)
DEFAULT_IMAGE_MODEL = "sourceful/riverflow-v2-fast"
DEFAULT_GOOGLE_IMAGE_MODEL = "gemini-2.5-flash-image"

# Google image models (generateContent API, image input + output)
GOOGLE_IMAGE_MODELS = [
    {"id": "gemini-2.5-flash-image", "name": "Gemini 2.5 Flash Image (Nano Banana)"},
    {"id": "gemini-3-pro-image-preview", "name": "Gemini 3 Pro Image (Nano Banana Pro)"},
]
GOOGLE_IMAGE_MODEL_IDS = {m["id"] for m in GOOGLE_IMAGE_MODELS}

# PlanarAlly UI locale codes (same as client/src/locales/*.json)
PA_UI_LOCALE_CODES = frozenset({"en", "it", "zh", "tw", "ru", "fr", "es", "dk", "de"})


def _normalize_compendium_translate_source(raw: object) -> str:
    v = (str(raw) if raw is not None else "auto").strip().lower()
    if v == "auto":
        return "auto"
    if v in PA_UI_LOCALE_CODES:
        return v
    return "auto"


def _normalize_compendium_translate_target(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    v = str(raw).strip().lower()
    if v in PA_UI_LOCALE_CODES:
        return v
    return None


def _resolve_image_model(opts) -> str:
    """Return the image model to use based on saved settings."""
    saved = (opts.openrouter_image_model or "").strip()
    if not saved:
        return DEFAULT_IMAGE_MODEL
    return saved


def _get_modalities(m: dict) -> tuple[list[str], list[str]]:
    arch = m.get("architecture") or {}
    inp = arch.get("input_modalities") or []
    out = arch.get("output_modalities") or []
    return (inp if isinstance(inp, list) else [], out if isinstance(out, list) else [])


async def _get_google_models(api_key: str) -> list[dict]:
    """Fetch models from Google AI Studio API."""
    url = f"{GOOGLE_AI_API}/models?key={api_key}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []
    result = []
    for m in (data.get("models") or []):
        mid = m.get("name", "").replace("models/", "")
        if not mid or "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        result.append({
            "id": mid,
            "name": m.get("displayName", mid),
            "context_length": None,
            "is_free": "flash" in mid.lower() or "1.5-flash" in mid,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        })
    return result


async def _fetch_openrouter_models() -> list[dict]:
    """Elenco modelli da OpenRouter (endpoint pubblico /models)."""
    openrouter_models: list[dict] = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OPENROUTER_API}/models") as resp:
                if resp.status != 200:
                    return openrouter_models
                data = await resp.json()
                raw = data.get("data", [])
                for m in raw:
                    model_id = m.get("id", "")
                    pricing = m.get("pricing", {}) or {}
                    prompt_cost = float(pricing.get("prompt", 1) or 1)
                    completion_cost = float(pricing.get("completion", 1) or 1)
                    is_free = prompt_cost == 0 and completion_cost == 0
                    inp_mod, out_mod = _get_modalities(m)
                    openrouter_models.append({
                        "id": model_id,
                        "name": m.get("name", model_id),
                        "context_length": m.get("context_length"),
                        "is_free": is_free,
                        "input_modalities": inp_mod,
                        "output_modalities": out_mod,
                    })
    except Exception:
        pass
    return openrouter_models


def _is_cerebras_model(model: str) -> bool:
    return (model or "").strip().startswith(CEREBRAS_MODEL_PREFIX)


def _cerebras_upstream_model_id(model: str) -> str:
    m = (model or "").strip()
    if m.startswith(CEREBRAS_MODEL_PREFIX):
        return m[len(CEREBRAS_MODEL_PREFIX) :].lstrip()
    return m


async def _fetch_cerebras_models(api_key: str) -> list[dict]:
    """Elenco modelli da Cerebras Inference API (OpenAI-compat /v1/models)."""
    if not (api_key or "").strip():
        return []
    cerebras_models: list[dict] = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CEREBRAS_API}/models",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            ) as resp:
                if resp.status != 200:
                    return cerebras_models
                data = await resp.json()
                raw = data.get("data", [])
                for m in raw:
                    model_id = m.get("id", "")
                    if not model_id:
                        continue
                    prefixed = f"{CEREBRAS_MODEL_PREFIX}{model_id}"
                    cerebras_models.append({
                        "id": prefixed,
                        "name": m.get("name", model_id),
                        "context_length": m.get("context_length"),
                        "is_free": False,
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                    })
    except Exception:
        pass
    return cerebras_models


async def _google_models_for_user(opts, model_type: str) -> list[dict]:
    """Modelli Google (testo o immagine): solo se è salvata una API key Google."""
    api_key = (opts.google_ai_api_key or "").strip()
    if not api_key:
        return []
    if model_type == "image":
        return list(GOOGLE_IMAGE_MODELS)
    return await _get_google_models(api_key)


async def get_models(request: web.Request) -> web.Response:
    """Modelli disponibili: OpenRouter, Google e/o Cerebras solo se salvata la rispettiva API key.

    Query:
    - ``provider=openrouter``: elenco OpenRouter (richiede chiave OpenRouter salvata).
    - ``provider=google``: elenco Google (testo o ``type=image``; richiede chiave Google salvata).
    - ``provider=cerebras``: elenco Cerebras (richiede chiave Cerebras salvata).
    - senza ``provider``: tutti in un'unica risposta (solo provider con chiave).
    """
    user = await get_authorized_user(request)
    opts = UserOptions.get_by_id(user.default_options)

    model_type = (request.query.get("type") or "").strip().lower()
    provider = (request.query.get("provider") or "").strip().lower()
    or_key = (opts.openrouter_api_key or "").strip()
    cb_key = (opts.cerebras_api_key or "").strip()

    if provider == "openrouter":
        openrouter_models = await _fetch_openrouter_models() if or_key else []
        return web.json_response(
            {
                "google_models": [],
                "openrouter_models": openrouter_models,
                "cerebras_models": [],
            },
            headers=_JSON_NO_STORE,
        )

    if provider == "google":
        google_models = await _google_models_for_user(opts, model_type)
        return web.json_response(
            {
                "google_models": google_models,
                "openrouter_models": [],
                "cerebras_models": [],
            },
            headers=_JSON_NO_STORE,
        )

    if provider == "cerebras":
        cerebras_models = await _fetch_cerebras_models(cb_key) if cb_key else []
        return web.json_response(
            {
                "google_models": [],
                "openrouter_models": [],
                "cerebras_models": cerebras_models,
            },
            headers=_JSON_NO_STORE,
        )

    google_models = await _google_models_for_user(opts, model_type)
    openrouter_models = await _fetch_openrouter_models() if or_key else []
    cerebras_models = await _fetch_cerebras_models(cb_key) if cb_key else []

    return web.json_response(
        {
            "google_models": google_models,
            "openrouter_models": openrouter_models,
            "cerebras_models": cerebras_models,
        },
        headers=_JSON_NO_STORE,
    )


def _messages_to_gemini(messages: list) -> tuple[str | None, list]:
    """Convert OpenRouter-style messages to Gemini format. Returns (system_instruction, contents)."""
    system = None
    contents = []
    for msg in messages:
        role = (msg.get("role") or "").lower()
        content = msg.get("content")
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            text = " ".join(text_parts).strip() if text_parts else ""
        else:
            text = str(content or "").strip()
        if not text:
            continue
        if role == "system":
            system = text if system is None else f"{system}\n\n{text}"
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
    return (system, contents)


async def _chat_google(api_key: str, model: str, messages: list, max_tokens: int, temperature: float) -> dict:
    """Call Google Gemini generateContent API."""
    system, contents = _messages_to_gemini(messages)
    if not contents and not system:
        return {"error": "No valid messages"}

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    url = f"{GOOGLE_AI_API}/models/{model}:generateContent?key={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            text = await resp.text()
            if resp.status != 200:
                try:
                    err_data = json.loads(text)
                    err_raw = err_data.get("error")
                    if isinstance(err_raw, str):
                        return {"error": err_raw, "_status": resp.status}
                    err_obj = err_raw if isinstance(err_raw, dict) else {}
                    err_msg = err_obj.get("message", text) if err_obj else text
                    out: dict = {"error": err_msg, "_status": resp.status}
                    st = err_obj.get("status")
                    if isinstance(st, str) and st:
                        out["upstreamStatus"] = st
                    code = err_obj.get("code")
                    if isinstance(code, int):
                        out["upstreamCode"] = code
                    return out
                except Exception:
                    return {"error": text if text else str(resp.status), "_status": resp.status}
            data = json.loads(text)
    cands = (data.get("candidates") or [])
    if not cands:
        return {"error": "No response from model", "_status": 502}
    parts = (cands[0].get("content") or {}).get("parts") or []
    out_text = " ".join((p.get("text", "") for p in parts)).strip()
    return {"choices": [{"message": {"content": out_text, "role": "assistant"}}]}


async def chat(request: web.Request) -> web.Response:
    """Proxy chat completion to OpenRouter or Google AI Studio based on selected model."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    messages = body.get("messages", [])
    if not messages:
        return web.HTTPBadRequest(text="messages is required")

    opts = UserOptions.get_by_id(user.default_options)
    
    # Infer provider from model name rather than global toggle
    model = body.get("model", DEFAULT_FREE_MODEL)
    is_google = model.startswith("gemini")
    is_cerebras = _is_cerebras_model(model)

    if is_google:
        api_key = (opts.google_ai_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Google AI API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
        max_tokens = body.get("max_tokens") if "max_tokens" in body else (opts.openrouter_max_tokens or 8192)
        temperature = float(body.get("temperature", 0.7))
        result = await _chat_google(api_key, model, messages, max_tokens, temperature)
        if "error" in result:
            payload: dict = {"error": result["error"]}
            if result.get("upstreamStatus"):
                payload["upstreamStatus"] = result["upstreamStatus"]
            if result.get("upstreamCode") is not None:
                payload["upstreamCode"] = result["upstreamCode"]
            return web.json_response(payload, status=int(result.get("_status", 502)))
        return web.json_response(result)

    max_tokens = body.get("max_tokens") if "max_tokens" in body else (opts.openrouter_max_tokens or 8192)
    temperature = body.get("temperature", 0.7)
    referer = str(request.url.origin()) if request.url.absolute else "https://planarally.io"

    if is_cerebras:
        api_key = (opts.cerebras_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Cerebras API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
        upstream_model = _cerebras_upstream_model_id(model)
        payload = {
            "model": upstream_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{CEREBRAS_API}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        try:
                            err_data = json.loads(text)
                            err = err_data.get("error")
                            err_msg = text
                            upstream_code = None
                            upstream_status = None
                            if isinstance(err, dict):
                                err_msg = err.get("message") or text
                                c = err.get("code")
                                if isinstance(c, int):
                                    upstream_code = c
                                t = err.get("type") or err.get("status")
                                if isinstance(t, str) and t:
                                    upstream_status = t
                            elif isinstance(err, str):
                                err_msg = err
                            body_err: dict = {"error": err_msg}
                            if upstream_code is not None:
                                body_err["upstreamCode"] = upstream_code
                            if upstream_status:
                                body_err["upstreamStatus"] = upstream_status
                            return web.json_response(body_err, status=resp.status)
                        except Exception:
                            return web.json_response(
                                {"error": (text[:2000] if text else "Unknown error")},
                                status=resp.status,
                            )
                    return web.json_response(json.loads(text))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    # OpenRouter
    api_key = (opts.openrouter_api_key or "").strip()
    if not api_key:
        return web.json_response(
            {"error": "OpenRouter API key not configured. Set it in the AI Generator settings."},
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
        "HTTP-Referer": referer,
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
                        err = err_data.get("error")
                        err_msg = text
                        upstream_code = None
                        upstream_status = None
                        if isinstance(err, dict):
                            err_msg = err.get("message") or text
                            c = err.get("code")
                            if isinstance(c, int):
                                upstream_code = c
                            t = err.get("type") or err.get("status")
                            if isinstance(t, str) and t:
                                upstream_status = t
                        elif isinstance(err, str):
                            err_msg = err
                        body: dict = {"error": err_msg}
                        if upstream_code is not None:
                            body["upstreamCode"] = upstream_code
                        if upstream_status:
                            body["upstreamStatus"] = upstream_status
                        return web.json_response(body, status=resp.status)
                    except Exception:
                        return web.json_response(
                            {"error": (text[:2000] if text else "Unknown error")},
                            status=resp.status,
                        )
                return web.json_response(json.loads(text))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


async def get_settings(request: web.Request) -> web.Response:
    """Get AI Generator settings (provider API keys masked, mapped models, etc)."""
    user = await get_authorized_user(request)
    opts = UserOptions.get_by_id(user.default_options)

    has_openrouter = bool((opts.openrouter_api_key or "").strip())
    has_google = bool((opts.google_ai_api_key or "").strip())
    has_cerebras = bool((opts.cerebras_api_key or "").strip())

    tasks = []
    if opts.openrouter_tasks:
        try:
            tasks = json.loads(opts.openrouter_tasks)
        except (json.JSONDecodeError, TypeError):
            pass

    model = opts.openrouter_model or DEFAULT_FREE_MODEL
    if model == "gemini-1.5-flash":
        model = "gemini-2.0-flash"
        opts.openrouter_model = model
        opts.save()

    vision_model = opts.openrouter_vision_model or model

    return web.json_response({
        "hasApiKey": has_openrouter,
        "hasGoogleKey": has_google,
        "hasCerebrasKey": has_cerebras,
        "model": model,
        "visionModel": vision_model,
        "basePrompt": opts.openrouter_base_prompt or "",
        "tasks": tasks,
        "imageModel": _resolve_image_model(opts),
        "defaultLanguage": opts.openrouter_default_language or "it",
        "maxTokens": opts.openrouter_max_tokens if opts.openrouter_max_tokens is not None else 8192,
        "compendiumTranslateSource": opts.openrouter_compendium_translate_source or "auto",
        "compendiumTranslateTarget": opts.openrouter_compendium_translate_target,
    })


async def set_settings(request: web.Request) -> web.Response:
    """Update AI Generator settings."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    opts = UserOptions.get_by_id(user.default_options)

    if "apiKey" in body:
        key = (body.get("apiKey") or "").strip()
        opts.openrouter_api_key = key or None

    if "googleApiKey" in body:
        gkey = (body.get("googleApiKey") or "").strip()
        opts.google_ai_api_key = gkey or None

    if "cerebrasApiKey" in body:
        ckey = (body.get("cerebrasApiKey") or "").strip()
        opts.cerebras_api_key = ckey or None

    if "model" in body:
        opts.openrouter_model = (body.get("model") or "").strip() or None
    if "basePrompt" in body:
        opts.openrouter_base_prompt = (body.get("basePrompt") or "").strip() or None
    if "tasks" in body:
        opts.openrouter_tasks = json.dumps(body["tasks"]) if body.get("tasks") else None
    if "imageModel" in body:
        opts.openrouter_image_model = (body.get("imageModel") or "").strip() or None
    if "visionModel" in body:
        opts.openrouter_vision_model = (body.get("visionModel") or "").strip() or None
    if "defaultLanguage" in body:
        lang = (body.get("defaultLanguage") or "it").strip().lower()
        opts.openrouter_default_language = lang if lang in ("it", "en") else "it"
    if "maxTokens" in body:
        val = body.get("maxTokens")
        if val is not None:
            try:
                n = int(val)
                if n > 0:
                    opts.openrouter_max_tokens = n
            except (TypeError, ValueError):
                pass

    if "compendiumTranslateSource" in body:
        opts.openrouter_compendium_translate_source = _normalize_compendium_translate_source(
            body.get("compendiumTranslateSource")
        )
    if "compendiumTranslateTarget" in body:
        opts.openrouter_compendium_translate_target = _normalize_compendium_translate_target(
            body.get("compendiumTranslateTarget")
        )

    opts.save()

    return web.json_response({"ok": True})


def _decode_data_url(b64_data: str) -> bytes:
    """Decode a base64 data URL (or raw base64) string to bytes."""
    try:
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        return base64.b64decode(b64_data)
    except Exception as e:
        raise ValueError(f"Failed to decode image: {e}") from e


def _save_generated_image(b64_data: str) -> str:
    """Decode base64 image and save to static temp. Returns URL path."""
    image_bytes = _decode_data_url(b64_data)
    temp_dir = STATIC_DIR / "temp" / "dungeons"
    temp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = temp_dir / filename
    filepath.write_bytes(image_bytes)
    return f"/static/temp/dungeons/{filename}"


async def _transform_image_google(
    api_key: str, base64_image: str, prompt: str, model: str | None = None
) -> str:
    """Transform image via Google Gemini image model."""
    model = model if model in GOOGLE_IMAGE_MODEL_IDS else DEFAULT_GOOGLE_IMAGE_MODEL
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": base64_image}},
            ]
        }],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    url = f"{GOOGLE_AI_API}/models/{model}:generateContent?key={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            text = await resp.text()
            if resp.status != 200:
                try:
                    err_data = json.loads(text)
                    err_msg = (err_data.get("error") or {}).get("message", text)
                except Exception:
                    err_msg = text
                raise ValueError(err_msg)
            data = json.loads(text)
    cands = data.get("candidates") or []
    if not cands:
        raise ValueError("No response from image model.")
    parts = (cands[0].get("content") or {}).get("parts") or []
    for p in parts:
        inline = p.get("inline_data") or p.get("inlineData")
        if inline:
            b64 = inline.get("data", "")
            if b64:
                return f"data:image/png;base64,{b64}"
    raise ValueError("Model did not return an image.")


async def transform_image(request: web.Request) -> web.Response:
    """Transform dungeon image to realistic via OpenRouter or Google (Gemini 2.5 Flash Image)."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    image_url = (body.get("imageUrl") or "").strip()
    archetype = (body.get("archetype") or "classic").strip().lower()
    extra_prompt = (body.get("extraPrompt") or "").strip()
    if not image_url:
        return web.HTTPBadRequest(text="imageUrl is required")

    opts = UserOptions.get_by_id(user.default_options)

    # Infer provider from image model name
    image_model = _resolve_image_model(opts)
    is_google = image_model in GOOGLE_IMAGE_MODEL_IDS

    # Resolve image path
    if image_url.startswith("/static/"):
        rel_path = unquote(image_url[len("/static/"):].lstrip("/"))
        filepath = STATIC_DIR / rel_path
    else:
        return web.json_response(
            {"error": "Only /static/ URLs are supported for dungeon images."},
            status=400,
        )

    if not filepath.exists() or not filepath.is_file():
        return web.json_response(
            {"error": "Image file not found."},
            status=404,
        )

    try:
        image_bytes = filepath.read_bytes()
    except OSError as e:
        return web.json_response(
            {"error": f"Failed to read image: {e}"},
            status=500,
        )

    base64_image = base64.b64encode(image_bytes).decode("ascii")

    archetype_descriptions = {
        "classic": "classic dungeon with stone walls, corridors, and medieval architecture",
        "warren": "underground warren or maze-like network of tunnels, burrow-like",
        "temple": "temple or sacred place with grand halls, columns, and religious architecture",
        "crypt": "crypt or tomb with dark burial chambers, sarcophagi, and funerary atmosphere",
        "cavern": "natural cavern with rocky formations, stalactites, and organic shapes",
        "fortress": "military fortress with defensive structures, battlements, and strategic layout",
        "lair": "creature lair or nest with organic, cave-like dwelling",
    }
    archetype_desc = archetype_descriptions.get(archetype, archetype_descriptions["classic"])
    prompt = (
        f"Transform this schematic dungeon map into a photorealistic, detailed isometric or top-down dungeon map. "
        f"The style should be: {archetype_desc}. "
        "Keep the exact same layout, room positions, corridors, walls, doors and structure. "
        "Make it look like a real tabletop RPG battle map with proper lighting and atmospheric details."
    )
    if extra_prompt:
        prompt += f"\n\nAdditional instructions from user: {extra_prompt}"

    result_data_url = None

    if is_google:
        api_key = (opts.google_ai_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Google AI API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
        try:
            result_data_url = await _transform_image_google(
                api_key, base64_image, prompt, model=image_model
            )
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=502)
    else:
        # OpenRouter
        api_key = (opts.openrouter_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "OpenRouter API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
        data_url = f"data:image/png;base64,{base64_image}"
        payload = {
            "model": image_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            "modalities": ["image", "text"],
            "max_tokens": 4096,
        }
        referer = str(request.url.origin()) if request.url.absolute else "https://planarally.io"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer,
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
                        return web.json_response({"error": err_msg}, status=resp.status)
                    data = json.loads(text)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

        choices = data.get("choices") or []
        if not choices:
            return web.json_response({"error": "No response from image model."}, status=502)
        message = choices[0].get("message") or {}
        images = message.get("images") or []
        if not images:
            return web.json_response(
                {"error": "Model did not return an image. Ensure the selected model supports image-to-image."},
                status=502,
            )
        img_data = images[0]
        img_url = img_data.get("image_url") or img_data.get("imageUrl") or {}
        result_data_url = img_url.get("url")

    if not result_data_url or not result_data_url.startswith("data:image"):
        return web.json_response(
            {"error": "Invalid image response format."},
            status=502,
        )

    # Validate payload; image is written only to temp (MapsGen commit adds to library on "add to map").
    try:
        _decode_data_url(result_data_url)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=502)

    # Same as MapsGen generate: temp file only; library entry on "add to map" (dungeongen/commit).
    url = _save_generated_image(result_data_url)
    return web.json_response({"imageUrl": url})


# ── Vision helpers ─────────────────────────────────────────────────────────────

async def _vision_call(
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    base64_data: str,
    mime_type: str,
    max_tokens: int,
    vision_backend: str,
    referer: str = "https://planarally.io",
) -> dict:
    """Call a vision-capable AI model with an image/document attachment.

    vision_backend: ``google`` | ``openrouter`` | ``cerebras``
    """
    if vision_backend == "google":
        payload: dict = {
            "contents": [{
                "parts": [
                    {"text": user_text},
                    {"inline_data": {"mime_type": mime_type, "data": base64_data}},
                ],
            }],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        url = f"{GOOGLE_AI_API}/models/{model}:generateContent?key={api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    try:
                        err_data = json.loads(text)
                        err_msg = (err_data.get("error") or {}).get("message", text)
                    except Exception:
                        err_msg = text
                    return {"error": err_msg}
                data = json.loads(text)
        cands = data.get("candidates") or []
        if not cands:
            return {"error": "No response from vision model"}
        parts = (cands[0].get("content") or {}).get("parts") or []
        out_text = " ".join(p.get("text", "") for p in parts).strip()
        return {"text": out_text}
    else:
        # OpenRouter or Cerebras (OpenAI-compatible chat completions + vision)
        upstream_model = _cerebras_upstream_model_id(model) if vision_backend == "cerebras" else model
        base_url = CEREBRAS_API if vision_backend == "cerebras" else OPENROUTER_API
        data_url = f"data:{mime_type};base64,{base64_data}"
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": user_text},
            ],
        })
        payload = {"model": upstream_model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if vision_backend == "openrouter":
            headers["HTTP-Referer"] = referer
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    try:
                        err_data = json.loads(text)
                        err_raw = err_data.get("error")
                        if isinstance(err_raw, dict):
                            err_msg = err_raw.get("message", text)
                        else:
                            err_msg = err_raw if isinstance(err_raw, str) else text
                    except Exception:
                        err_msg = text
                    return {"error": err_msg}
                data = json.loads(text)
        choices = data.get("choices") or []
        if not choices:
            return {"error": "No response from vision model"}
        content = (choices[0].get("message") or {}).get("content", "")
        return {"text": content}


async def _vision_call_multi(
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    images: list[tuple[str, str]],  # list of (base64_data, mime_type)
    max_tokens: int,
    vision_backend: str,
    referer: str = "https://planarally.io",
) -> dict:
    """Call a vision-capable AI model with one or more image/document attachments."""
    if vision_backend == "google":
        parts: list[dict] = [{"text": user_text}]
        for b64, mime in images:
            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        payload: dict = {
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        url = f"{GOOGLE_AI_API}/models/{model}:generateContent?key={api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    try:
                        err_data = json.loads(text)
                        err_msg = (err_data.get("error") or {}).get("message", text)
                    except Exception:
                        err_msg = text
                    return {"error": err_msg}
                data = json.loads(text)
        cands = data.get("candidates") or []
        if not cands:
            return {"error": "No response from vision model"}
        out_parts = (cands[0].get("content") or {}).get("parts") or []
        out_text = " ".join(p.get("text", "") for p in out_parts).strip()
        return {"text": out_text}
    else:
        upstream_model = _cerebras_upstream_model_id(model) if vision_backend == "cerebras" else model
        base_url = CEREBRAS_API if vision_backend == "cerebras" else OPENROUTER_API
        content: list[dict] = []
        for b64, mime in images:
            data_url = f"data:{mime};base64,{b64}"
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        content.append({"type": "text", "text": user_text})
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        payload = {"model": upstream_model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if vision_backend == "openrouter":
            headers["HTTP-Referer"] = referer
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    try:
                        err_data = json.loads(text)
                        err_raw = err_data.get("error")
                        if isinstance(err_raw, dict):
                            err_msg = err_raw.get("message", text)
                        else:
                            err_msg = err_raw if isinstance(err_raw, str) else text
                    except Exception:
                        err_msg = text
                    return {"error": err_msg}
                data = json.loads(text)
        choices = data.get("choices") or []
        if not choices:
            return {"error": "No response from vision model"}
        out_content = (choices[0].get("message") or {}).get("content", "")
        return {"text": out_content}


def _parse_json_response(text: str) -> dict | None:
    """Extract and parse JSON from an AI response (strips markdown code blocks)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using available libraries."""
    try:
        import pdfminer.high_level
        import io
        return pdfminer.high_level.extract_text(io.BytesIO(file_bytes))
    except ImportError:
        pass
    try:
        import fitz  # type: ignore[import]  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        pass
    raise ImportError("No PDF text extraction library found. Install pdfminer.six or PyMuPDF, or use Google AI with a PDF.")


def _extract_docx_text(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    import io
    import docx  # type: ignore[import]  # python-docx
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


# ── Import Character Sheet ─────────────────────────────────────────────────────

async def import_character(request: web.Request) -> web.Response:
    """Import a character sheet from one or more uploaded files (images/PDFs/DOCX) using AI vision."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    files: list[tuple[str, bytes]] = []  # (filename, bytes)
    system_prompt = ""
    user_prompt = ""

    async for part in reader:
        if part.name == "file":
            filename = part.filename or ""
            file_bytes = await part.read()
            files.append((filename, file_bytes))
        elif part.name == "systemPrompt":
            system_prompt = await part.text()
        elif part.name == "userPrompt":
            user_prompt = await part.text()

    if not files:
        return web.HTTPBadRequest(text="No file provided")

    opts = UserOptions.get_by_id(user.default_options)
    model = (opts.openrouter_vision_model or opts.openrouter_model or DEFAULT_FREE_MODEL).strip()
    if model.startswith("gemini"):
        vision_backend = "google"
    elif _is_cerebras_model(model):
        vision_backend = "cerebras"
    else:
        vision_backend = "openrouter"
    max_tokens = opts.openrouter_max_tokens or 8192

    if vision_backend == "google":
        api_key = (opts.google_ai_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Google AI API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
    elif vision_backend == "cerebras":
        api_key = (opts.cerebras_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Cerebras API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
    else:
        api_key = (opts.openrouter_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "OpenRouter API key not configured. Set it in the AI Generator settings."},
                status=400,
            )

    referer = str(request.url.origin()) if request.url.absolute else "https://planarally.io"

    # Parse each uploaded file into image parts or text parts
    image_parts: list[tuple[str, str]] = []  # (base64_data, mime_type)
    text_parts: list[str] = []

    for fname, fbytes in files:
        ext = Path(fname).suffix.lower()
        if ext in {".png", ".jpg", ".jpeg"}:
            mime_type = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
            b64 = base64.b64encode(fbytes).decode("ascii")
            image_parts.append((b64, mime_type))
        elif ext == ".pdf":
            if vision_backend == "google":
                b64 = base64.b64encode(fbytes).decode("ascii")
                image_parts.append((b64, "application/pdf"))
            else:
                try:
                    text_parts.append(_extract_pdf_text(fbytes))
                except ImportError as e:
                    return web.json_response(
                        {"error": f"Impossibile elaborare il PDF: {e}. Usa Google AI (supporta PDF nativamente) oppure carica un'immagine."},
                        status=400,
                    )
        elif ext in {".docx", ".doc"}:
            try:
                text_parts.append(_extract_docx_text(fbytes))
            except (ImportError, Exception) as e:
                return web.json_response(
                    {"error": f"Impossibile elaborare il file DOC/DOCX: {e}. Installa python-docx oppure carica un'immagine o PDF."},
                    status=400,
                )
        else:
            return web.json_response(
                {"error": f"Tipo di file non supportato: {ext}. Usa PNG, JPG, PDF o DOCX."},
                status=400,
            )

    default_prompt = user_prompt or "Estrai i dati del personaggio da questa scheda e compila il JSON."

    if image_parts:
        # Vision call: send all images in a single request
        full_prompt = default_prompt
        if text_parts:
            full_prompt += "\n\nContenuto testuale aggiuntivo:\n" + "\n---\n".join(text_parts)
        result = await _vision_call_multi(
            api_key, model, system_prompt, full_prompt, image_parts, max_tokens, vision_backend, referer
        )
    elif text_parts:
        # Text-only: use chat completion
        full_content = default_prompt + "\n\nContenuto scheda:\n" + "\n---\n".join(text_parts)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_content},
        ]
        if vision_backend == "google":
            result_raw = await _chat_google(api_key, model, messages, max_tokens, 0.3)
            content = (result_raw.get("choices") or [{}])[0].get("message", {}).get("content", "")
            result = {"text": content}
        else:
            upstream_model = _cerebras_upstream_model_id(model) if vision_backend == "cerebras" else model
            base_url = CEREBRAS_API if vision_backend == "cerebras" else OPENROUTER_API
            payload = {"model": upstream_model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
            headers: dict[str, str] = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if vision_backend == "openrouter":
                headers["HTTP-Referer"] = referer
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                    text_r = await resp.text()
                    if resp.status != 200:
                        try:
                            err_data = json.loads(text_r)
                            err_raw = err_data.get("error")
                            if isinstance(err_raw, dict):
                                err_msg = err_raw.get("message", text_r)
                            else:
                                err_msg = err_raw if isinstance(err_raw, str) else text_r
                        except Exception:
                            err_msg = text_r
                        return web.json_response({"error": err_msg}, status=resp.status)
                    data = json.loads(text_r)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            result = {"text": content}
    else:
        return web.json_response({"error": "Nessun contenuto da elaborare."}, status=400)

    if "error" in result:
        return web.json_response({"error": result["error"]}, status=502)

    return web.json_response({"result": result.get("text", "")})


# ── Import Map from Image ──────────────────────────────────────────────────────

_MAP_ANALYSIS_PROMPT = (
    "You are an expert tabletop RPG map analyzer. Analyze this map image carefully.\n\n"
    "Your task:\n"
    "1. Count the grid cells: how many columns (width) and rows (height) does the map have?\n"
    "2. Identify walls and room dividers as line segments in grid coordinates.\n"
    "   Each wall segment is [[x1,y1],[x2,y2]] where coordinates are GRID CELL CORNERS.\n"
    "   Origin (0,0) is the TOP-LEFT corner of the map.\n"
    "3. Identify doors: the cell they occupy (x,y) counted from top-left (0-indexed), "
    "and the wall face direction (north/south/east/west).\n\n"
    "Return ONLY a valid JSON object with EXACTLY this structure (no markdown, no extra text):\n"
    '{"gridCells":{"width":N,"height":N},"walls":{"lines":[[[x1,y1],[x2,y2]],...]}'
    ',"doors":[{"x":N,"y":N,"direction":"north","type":"normal"},...]}\n\n'
    "Be precise with wall positions. Walls define room boundaries and corridors. "
    "If the map has no visible doors, return an empty doors array."
)


async def import_map(request: web.Request) -> web.Response:
    """Import a map from an uploaded image using AI vision to detect grid, walls and doors."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    file_bytes: bytes | None = None
    filename = ""

    async for part in reader:
        if part.name == "file":
            filename = part.filename or "map.png"
            file_bytes = await part.read()

    if not file_bytes:
        return web.HTTPBadRequest(text="No file provided")

    ext = Path(filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        return web.json_response(
            {"error": "Solo immagini PNG/JPG sono supportate per l'analisi mappa."},
            status=400,
        )

    opts = UserOptions.get_by_id(user.default_options)
    model = (opts.openrouter_vision_model or opts.openrouter_model or DEFAULT_FREE_MODEL).strip()
    if model.startswith("gemini"):
        vision_backend = "google"
    elif _is_cerebras_model(model):
        vision_backend = "cerebras"
    else:
        vision_backend = "openrouter"

    if vision_backend == "google":
        api_key = (opts.google_ai_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Google AI API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
    elif vision_backend == "cerebras":
        api_key = (opts.cerebras_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "Cerebras API key not configured. Set it in the AI Generator settings."},
                status=400,
            )
    else:
        api_key = (opts.openrouter_api_key or "").strip()
        if not api_key:
            return web.json_response(
                {"error": "OpenRouter API key not configured. Set it in the AI Generator settings."},
                status=400,
            )

    mime_type = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
    b64 = base64.b64encode(file_bytes).decode("ascii")
    referer = str(request.url.origin()) if request.url.absolute else "https://planarally.io"

    result = await _vision_call(
        api_key, model, "", _MAP_ANALYSIS_PROMPT, b64, mime_type, 4096, vision_backend, referer
    )

    if "error" in result:
        return web.json_response({"error": result["error"]}, status=502)

    map_data = _parse_json_response(result.get("text", ""))
    if not map_data or "gridCells" not in map_data:
        return web.json_response(
            {"error": "L'AI non ha restituito dati mappa validi. Riprova con un modello con visione (es. Gemini, multimodale OpenRouter o Cerebras con supporto immagini)."},
            status=502,
        )

    # Save image as PlanarAlly asset
    h = hashlib.sha1(file_bytes).hexdigest()
    asset_path = ASSETS_DIR / get_asset_hash_subpath(h)
    if not asset_path.exists():
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(file_bytes)

    folder = AssetEntry.get_or_create_extension_folder(user, "AI generator")
    stem = Path(filename).stem
    asset_name = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
    asset, _ = Asset.get_or_create(
        file_hash=h,
        defaults={"kind": "regular", "extension": ext.lstrip("."), "file_size": len(file_bytes)},
    )
    entry = AssetEntry.create(name=asset_name, asset=asset, owner=user, parent=folder)

    from ....thumbnail import generate_thumbnail_for_asset
    asyncio.create_task(generate_thumbnail_for_asset(h))

    asset_url = f"/static/assets/{get_asset_hash_subpath(h).as_posix()}"

    return web.json_response({
        "url": asset_url,
        "assetId": asset.id,
        "entryId": entry.id,
        "name": stem,
        "gridCells": map_data.get("gridCells", {"width": 20, "height": 15}),
        "walls": map_data.get("walls"),
        "doors": map_data.get("doors", []),
    })
