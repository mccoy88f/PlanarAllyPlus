"""AI Generator extension - OpenRouter and Google AI Studio."""

import base64
import json
import uuid
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.user_options import UserOptions
from ....db.models.asset import Asset
from ....utils import ASSETS_DIR, STATIC_DIR
from ....utils import get_asset_hash_subpath

OPENROUTER_API = "https://openrouter.ai/api/v1"
GOOGLE_AI_API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_FREE_MODEL = "openrouter/free"
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


def _resolve_image_model(opts) -> str:
    """Return the image model to use based on saved settings."""
    saved = (opts.openrouter_image_model or "").strip()
    if not saved:
        return DEFAULT_IMAGE_MODEL
    return saved


# Well-known Gemini models (used when API key not set for Google)
# gemini-1.5-flash deprecato; usare gemini-2.0-flash o gemini-1.5-flash-8b
GOOGLE_DEFAULT_MODELS = [
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "is_free": True},
    {"id": "gemini-2.0-flash-lite-001", "name": "Gemini 2.0 Flash Lite", "is_free": True},
    {"id": "gemini-1.5-flash-8b", "name": "Gemini 1.5 Flash 8B", "is_free": True},
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "is_free": False},
]


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


async def get_models(request: web.Request) -> web.Response:
    """Fetch available models from OpenRouter and Google AI Studio simultaneously."""
    user = await get_authorized_user(request)
    opts = UserOptions.get_by_id(user.default_options)

    model_type = (request.query.get("type") or "").strip().lower()

    google_models = []
    if model_type == "image":
        google_models = GOOGLE_IMAGE_MODELS
    else:
        api_key = (opts.google_ai_api_key or "").strip()
        if api_key:
            google_models = await _get_google_models(api_key)
        else:
            google_models = [{
                "id": m["id"],
                "name": m["name"],
                "context_length": None,
                "is_free": m["is_free"],
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            } for m in GOOGLE_DEFAULT_MODELS]

    # OpenRouter
    openrouter_models = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OPENROUTER_API}/models") as resp:
                if resp.status == 200:
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
        pass  # Just return what we have (e.g. at least Google models)

    return web.json_response({
        "google_models": google_models,
        "openrouter_models": openrouter_models
    })


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
                    err_msg = (err_data.get("error") or {}).get("message", text)
                except Exception:
                    err_msg = text
                return {"error": err_msg, "_status": resp.status}
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
            return web.json_response(
                {"error": result["error"]},
                status=result.get("_status", 502),
            )
        return web.json_response(result)

    # OpenRouter
    max_tokens = body.get("max_tokens") if "max_tokens" in body else (opts.openrouter_max_tokens or 8192)
    temperature = body.get("temperature", 0.7)
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
                return web.json_response(json.loads(text))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


async def get_settings(request: web.Request) -> web.Response:
    """Get AI Generator settings (provider API keys masked, mapped models, etc)."""
    user = await get_authorized_user(request)
    opts = UserOptions.get_by_id(user.default_options)

    has_openrouter = bool((opts.openrouter_api_key or "").strip())
    has_google = bool((opts.google_ai_api_key or "").strip())

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

    return web.json_response({
        "hasApiKey": has_openrouter,
        "hasGoogleKey": has_google,
        "model": model,
        "basePrompt": opts.openrouter_base_prompt or "",
        "tasks": tasks,
        "imageModel": _resolve_image_model(opts),
        "defaultLanguage": opts.openrouter_default_language or "it",
        "maxTokens": opts.openrouter_max_tokens if opts.openrouter_max_tokens is not None else 8192,
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

    if "model" in body:
        opts.openrouter_model = (body.get("model") or "").strip() or None
    if "basePrompt" in body:
        opts.openrouter_base_prompt = (body.get("basePrompt") or "").strip() or None
    if "tasks" in body:
        opts.openrouter_tasks = json.dumps(body["tasks"]) if body.get("tasks") else None
    if "imageModel" in body:
        opts.openrouter_image_model = (body.get("imageModel") or "").strip() or None
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

    # Decode the image once, then save as a proper PlanarAlly asset so the
    # client gets a valid assetId it can pass to setImage().
    try:
        img_bytes = _decode_data_url(result_data_url)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=502)

    try:
        import hashlib
        h = hashlib.sha1(img_bytes).hexdigest()
        asset_path = ASSETS_DIR / get_asset_hash_subpath(h)
        if not asset_path.exists():
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(img_bytes)
        folder = Asset.get_or_create_extension_folder(user, "dungeongen")
        filename = f"realistic_{uuid.uuid4().hex[:8]}.png"
        asset = Asset.create(name=filename, file_hash=h, owner=user, parent=folder)
        asset_url = f"/static/assets/{get_asset_hash_subpath(h).as_posix()}"
        return web.json_response({"imageUrl": asset_url, "assetId": asset.id})
    except Exception:
        # Asset creation failed — fall back to temp file so the user still
        # sees the result, but replace will not work without assetId.
        url = _save_generated_image(result_data_url)
        return web.json_response({"imageUrl": url})
