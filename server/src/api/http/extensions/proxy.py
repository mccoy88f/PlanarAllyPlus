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

    // Intercept Blob creations
    const originalCreateObjectURL = URL.createObjectURL;
    const blobMap = new Map();

    URL.createObjectURL = function(obj) {
        const url = originalCreateObjectURL(obj);
        if (obj instanceof Blob) {
            blobMap.set(url, obj);
        }
        return url;
    };

    // Intercept clicks on links (for downloads)
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
                console.log("[PlanarAlly Agent] Intercepted download:", filename);
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url) as response:
                content_type = response.headers.get("Content-Type", "")
                body = await response.read()

                if "text/html" in content_type:
                    # Rewrite HTML to inject interceptor and fix relative links
                    soup = BeautifulSoup(body, "html.parser")
                    base_url = target_url

                    # Add <base> tag to help with relative assets
                    if not soup.find("base"):
                        base_tag = soup.new_tag("base", href=base_url)
                        if soup.head:
                            soup.head.insert(0, base_tag)
                        else:
                            head = soup.new_tag("head")
                            head.append(base_tag)
                            soup.insert(0, head)

                    # Inject interceptor
                    script_tag = soup.new_tag("script")
                    script_tag.string = INTERCEPTOR_JS
                    if soup.body:
                        soup.body.append(script_tag)
                    else:
                        soup.append(script_tag)

                    return web.Response(text=str(soup), content_type="text/html")
                else:
                    # Generic secondary resource proxying (CSS, JS, images, etc.)
                    return web.Response(body=body, content_type=content_type)

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Proxy error: {str(e)}")
