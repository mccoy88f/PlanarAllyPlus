import aiohttp
from aiohttp import web
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from ....auth import get_authorized_user
from ....utils import FILE_DIR

# The interceptor script that will be injected into proxied HTML
# It will be formatted with the target_url as the base
INTERCEPTOR_JS_TEMPLATE = """
(function() {{
    console.log("[PlanarAlly Agent] Interceptor active");
    
    const PROXY_BASE = "/api/extensions/proxy?url=";
    const ORIGINAL_BASE = "{base_url}";

    function wrapUrl(url) {{
        if (!url || typeof url !== 'string') return url;
        if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('mailto:')) return url;
        if (url.startsWith(window.location.origin + PROXY_BASE)) return url;
        
        try {{
            // Resolve relative to the ORIGINAL base, not the proxy URL
            const absoluteUrl = new URL(url, ORIGINAL_BASE).href;
            return PROXY_BASE + encodeURIComponent(absoluteUrl);
        }} catch(e) {{
            return url;
        }}
    }}

    // 1. Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = function(input, init) {{
        if (typeof input === 'string') {{
            input = wrapUrl(input);
        }} else if (input instanceof Request) {{
            const newUrl = wrapUrl(input.url);
            input = new Request(newUrl, input);
        }}
        return originalFetch(input, init);
    }};

    // 2. Intercept XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {{
        return originalOpen.apply(this, [method, wrapUrl(url), ...args]);
    }};

    // 3. Intercept Blob creations (for downloads)
    const originalCreateObjectURL = URL.createObjectURL;
    const blobMap = new Map();
    URL.createObjectURL = function(obj) {{
        const url = originalCreateObjectURL(obj);
        if (obj instanceof Blob) {{
            blobMap.set(url, obj);
        }}
        return url;
    }};

    // 4. Intercept clicks on links (for downloads)
    document.addEventListener("click", function(e) {{
        const target = e.target.closest("a");
        if (!target || !target.download) return;
        const href = target.href;
        const filename = target.download || "download.png";
        if (blobMap.has(href)) {{
            e.preventDefault();
            e.stopPropagation();
            const blob = blobMap.get(href);
            const reader = new FileReader();
            reader.onload = function() {{
                window.parent.postMessage({{
                    type: "planarally-intercepted-download",
                    filename: filename,
                    data: reader.result,
                    contentType: blob.type
                }}, "*");
            }};
            reader.readAsDataURL(blob);
        }}
    }}, true);
}})();
"""

async def proxy_handler(request: web.Request) -> web.Response:
    target_url = request.query.get("url")
    if not target_url:
        return web.HTTPBadRequest(text="Missing 'url' parameter")

    # Basic security check - could be expanded
    parsed_target = urlparse(target_url)
    if not parsed_target.scheme or not parsed_target.netloc:
        return web.HTTPBadRequest(text="Invalid URL")

    try:
        async with aiohttp.ClientSession() as session:
            # Forward necessary headers but be careful
            headers = {
                "User-Agent": request.headers.get("User-Agent", "PlanarAllyProxy/1.0"),
                "Accept-Language": request.headers.get("Accept-Language", ""),
            }
            
            async with session.get(target_url, headers=headers) as response:
                content_type = response.headers.get("Content-Type", "")
                body = await response.read()

                # Basic CORS headers for all proxied content
                cors_headers = {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }

                if "text/html" in content_type:
                    soup = BeautifulSoup(body, "html.parser")
                    
                    # Ensure we have a base URL for recursion
                    base_url = target_url
                    if not base_url.endswith("/") and "." not in base_url.split("/")[-1]:
                        base_url += "/"

                    # 1. REMOVE any existing <base> tag to avoid interference
                    for b in soup.find_all("base"):
                        b.decompose()

                    # 2. Rewrite attributes in HTML
                    # We rewrite them to be absolute and then proxy them
                    proxy_path = "/api/extensions/proxy?url="
                    for tag in soup.find_all(['script', 'link', 'img', 'source', 'iframe', 'a']):
                        for attr in ['src', 'href']:
                            if tag.has_attr(attr):
                                val = tag[attr]
                                if not val.startswith(('http', '//', 'data:', 'blob:', 'mailto:', '#')):
                                    # Make absolute relative to original target
                                    abs_val = urljoin(base_url, val)
                                    tag[attr] = f"{proxy_path}{abs_val}"
                                elif val.startswith(('http', '//')) and not val.startswith(request.host):
                                    # Also proxy external absolute links if they are assets?
                                    # Careful with external links, but for Watabou they are often on same domain
                                    pass

                    # 3. Inject PlanarAlly Agent
                    script_tag = soup.new_tag("script")
                    script_tag.string = INTERCEPTOR_JS_TEMPLATE.format(base_url=base_url)
                    if soup.body:
                        soup.body.insert(0, script_tag)
                    else:
                        soup.append(script_tag)

                    res_headers = {"Content-Type": "text/html", **cors_headers}
                    return web.Response(text=str(soup), headers=res_headers)
                else:
                    # Pass through other resources with CORS
                    res_headers = {"Content-Type": content_type, **cors_headers}
                    return web.Response(body=body, headers=res_headers)

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Proxy error: {str(e)}")
