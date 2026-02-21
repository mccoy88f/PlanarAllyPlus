import aiohttp
from aiohttp import web
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from ....auth import get_authorized_user
from ....utils import FILE_DIR

# The interceptor script that will be injected into proxied HTML
INTERCEPTOR_JS = """
(function() {
    console.log("[PlanarAlly Agent] Interceptor active");
    
    const PROXY_BASE = "/api/extensions/proxy?url=";

    function wrapUrl(url) {
        if (!url || typeof url !== 'string') return url;
        if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('mailto:')) return url;
        if (url.startsWith(window.location.origin + PROXY_BASE)) return url;
        
        try {
            const absoluteUrl = new URL(url, window.location.href).href;
            // Only proxy if it's external or relative mapping to external
            return PROXY_BASE + encodeURIComponent(absoluteUrl);
        } catch(e) {
            return url;
        }
    }

    // 1. Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = function(input, init) {
        if (typeof input === 'string') {
            input = wrapUrl(input);
        } else if (input instanceof Request) {
            // Complex to clone and wrap, but let's try a simple version
            const newUrl = wrapUrl(input.url);
            input = new Request(newUrl, input);
        }
        return originalFetch(input, init);
    };

    // 2. Intercept XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {
        return originalOpen.apply(this, [method, wrapUrl(url), ...args]);
    };

    // 3. Intercept Blob creations (for downloads)
    const originalCreateObjectURL = URL.createObjectURL;
    const blobMap = new Map();
    URL.createObjectURL = function(obj) {
        const url = originalCreateObjectURL(obj);
        if (obj instanceof Blob) {
            blobMap.set(url, obj);
        }
        return url;
    };

    // 4. Intercept clicks on links (for downloads)
    document.addEventListener("click", function(e) {
        const target = e.target.closest("a");
        if (!target || !target.download) return;
        const href = target.href;
        const filename = target.download || "download.png";
        if (blobMap.has(href)) {
            e.preventDefault();
            e.stopPropagation();
            const blob = blobMap.get(href);
            const reader = new FileReader();
            reader.onload = function() {
                window.parent.postMessage({
                    type: "planarally-intercepted-download",
                    filename: filename,
                    data: reader.result,
                    contentType: blob.type
                }, "*");
            };
            reader.readAsDataURL(blob);
        }
    }, true);
})();
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

                    # 1. Update/Add <base> tag
                    base_tag = soup.find("base")
                    if base_tag:
                        base_tag["href"] = base_url
                    else:
                        base_tag = soup.new_tag("base", href=base_url)
                        if soup.head:
                            soup.head.insert(0, base_tag)
                        else:
                            head = soup.new_tag("head")
                            head.append(base_tag)
                            soup.insert(0, head)

                    # 2. Rewrite attributes in HTML (aggressive)
                    # We rewrite typical tags so they go through our proxy immediately
                    for tag in soup.find_all(['script', 'link', 'img', 'source', 'iframe']):
                        for attr in ['src', 'href']:
                            if tag.has_attr(attr):
                                val = tag[attr]
                                if not val.startswith(('http', '//', 'data:', 'blob:')):
                                    # Don't rewrite here yet if we use <base>, 
                                    # but some JS doesn't respect <base>
                                    pass

                    # 3. Inject PlanarAlly Agent
                    script_tag = soup.new_tag("script")
                    script_tag.string = INTERCEPTOR_JS
                    if soup.body:
                        soup.body.insert(0, script_tag) # Insert at start for fetch override
                    else:
                        soup.append(script_tag)

                    res_headers = {"Content-Type": "text/html", **cors_headers}
                    return web.Response(text=str(soup), headers=res_headers)
                else:
                    # Pass through other resources with CORS
                    res_headers = {"Content-Type": content_type, **cors_headers}
                    # Small optimization: rewrite CSS imports if they are relative? 
                    # Complex, let's stick to CORS and base tag for now.
                    return web.Response(body=body, headers=res_headers)

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Proxy error: {str(e)}")
