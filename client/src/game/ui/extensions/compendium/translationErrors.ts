/** Costruisce il messaggio per i toast partendo dalla risposta HTTP dell'API chat (OpenRouter / Google proxy). */
export async function formatTranslationChatErrorResponse(r: Response): Promise<string> {
    const status = r.status;
    const statusText = (r.statusText || "").trim();
    const httpLine = statusText.length > 0 ? `${status} ${statusText}` : `${status}`;
    let raw = "";
    try {
        raw = await r.text();
    } catch {
        raw = "";
    }
    let apiMessage = "";
    let upstreamStatus = "";
    let upstreamCode: number | undefined;
    if (raw.length > 0) {
        try {
            const j = JSON.parse(raw) as {
                error?: string | { message?: string; code?: number; status?: string };
                upstreamStatus?: string;
                upstreamCode?: number;
            };
            if (typeof j.error === "string") {
                apiMessage = j.error.trim();
            } else if (j.error && typeof j.error === "object") {
                apiMessage = (j.error.message ?? "").trim();
                if (typeof j.error.status === "string" && j.error.status.length > 0) {
                    upstreamStatus = j.error.status;
                }
                if (typeof j.error.code === "number") {
                    upstreamCode = j.error.code;
                }
            }
            if (typeof j.upstreamStatus === "string" && j.upstreamStatus.length > 0) {
                upstreamStatus = j.upstreamStatus;
            }
            if (typeof j.upstreamCode === "number") {
                upstreamCode = j.upstreamCode;
            }
        } catch {
            const t = raw.trim();
            if (t.length > 0 && t.length < 800) {
                apiMessage = t;
            }
        }
    }
    const parts: string[] = [httpLine];
    if (upstreamStatus.length > 0) {
        parts.push(upstreamStatus);
    }
    if (upstreamCode != null && upstreamCode !== status) {
        parts.push(`code ${upstreamCode}`);
    }
    if (apiMessage.length > 0) {
        parts.push(apiMessage);
    }
    return parts.join(" — ");
}

export function formatTranslationCaughtError(e: unknown): string {
    if (e instanceof DOMException && e.name === "AbortError") {
        return "";
    }
    if (e instanceof Error) {
        return `${e.name}: ${e.message}`;
    }
    return String(e);
}

/** Errore HTTP generico (salvataggio / caricamento traduzioni da DB). */
export async function formatTranslationHttpErrorResponse(r: Response): Promise<string> {
    return formatTranslationChatErrorResponse(r);
}
