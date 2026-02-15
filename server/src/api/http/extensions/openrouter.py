"""OpenRouter extension - AI services via OpenRouter API."""

import base64
import json
import uuid
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.user_options import UserOptions
from ....utils import STATIC_DIR

OPENROUTER_API = "https://openrouter.ai/api/v1"
DEFAULT_FREE_MODEL = "openrouter/free"
# Models that support image-to-image (input image + output image)
DEFAULT_IMAGE_MODEL = "sourceful/riverflow-v2-fast"


def _get_modalities(m: dict) -> tuple[list[str], list[str]]:
    arch = m.get("architecture") or {}
    inp = arch.get("input_modalities") or []
    out = arch.get("output_modalities") or []
    return (inp if isinstance(inp, list) else [], out if isinstance(out, list) else [])


async def get_models(request: web.Request) -> web.Response:
    """Fetch available models from OpenRouter, including modality info."""
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
        inp_mod, out_mod = _get_modalities(m)
        result.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "context_length": m.get("context_length"),
            "is_free": is_free,
            "input_modalities": inp_mod,
            "output_modalities": out_mod,
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
        "imageModel": opts.openrouter_image_model or DEFAULT_IMAGE_MODEL,
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
    image_model = body.get("imageModel", "").strip()

    opts = UserOptions.get_by_id(user.default_options)

    if "apiKey" in body:
        opts.openrouter_api_key = api_key.strip() or None
    if model:
        opts.openrouter_model = model
    if "basePrompt" in body:
        opts.openrouter_base_prompt = base_prompt.strip() or None
    if tasks is not None:
        opts.openrouter_tasks = json.dumps(tasks) if tasks else None
    if "imageModel" in body:
        opts.openrouter_image_model = image_model or None

    opts.save()

    return web.json_response({"ok": True})


async def transform_image(request: web.Request) -> web.Response:
    """Transform dungeon image to realistic via OpenRouter image-to-image model."""
    user = await get_authorized_user(request)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    image_url = (body.get("imageUrl") or "").strip()
    archetype = (body.get("archetype") or "classic").strip().lower()
    if not image_url:
        return web.HTTPBadRequest(text="imageUrl is required")

    opts = UserOptions.get_by_id(user.default_options)
    api_key = (opts.openrouter_api_key or "").strip()
    if not api_key:
        return web.json_response(
            {"error": "OpenRouter API key not configured. Set it in the OpenRouter extension settings."},
            status=400,
        )

    image_model = opts.openrouter_image_model or DEFAULT_IMAGE_MODEL

    # Resolve image path: /static/temp/dungeons/xxx.png -> STATIC_DIR/temp/dungeons/xxx.png
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
    data_url = f"data:image/png;base64,{base64_image}"

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
        "Keep the exact same layout, room positions, corridors, and structure. "
        "Make it look like a real tabletop RPG battle map with proper lighting and atmospheric details."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    payload = {
        "model": image_model,
        "messages": messages,
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
                    return web.json_response(
                        {"error": err_msg},
                        status=resp.status,
                    )
                data = json.loads(text)
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=502,
        )

    # Extract generated image from response
    choices = data.get("choices") or []
    if not choices:
        return web.json_response(
            {"error": "No response from image model."},
            status=502,
        )

    message = choices[0].get("message") or {}
    images = message.get("images") or []
    if not images:
        return web.json_response(
            {"error": "Model did not return an image. Ensure the selected model supports image-to-image generation (e.g. Sourceful Riverflow)."},
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

    # Decode base64 and save to static temp so addDungeonToMap can use it
    try:
        header, b64 = result_data_url.split(",", 1)
        image_bytes = base64.b64decode(b64)
    except Exception as e:
        return web.json_response(
            {"error": f"Failed to decode image: {e}"},
            status=502,
        )

    temp_dir = STATIC_DIR / "temp" / "dungeons"
    temp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = temp_dir / filename
    filepath.write_bytes(image_bytes)

    url = f"/static/temp/dungeons/{filename}"
    return web.json_response({"imageUrl": url})
