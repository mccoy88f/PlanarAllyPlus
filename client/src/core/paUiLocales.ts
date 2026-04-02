/** Locale codes with a PlanarAlly `client/src/locales/*.json` file. */
export const PA_UI_LOCALE_CODES = ["en", "it", "zh", "tw", "ru", "fr", "es", "dk", "de"] as const;
export type PaUiLocaleCode = (typeof PA_UI_LOCALE_CODES)[number];

const PA_SET = new Set<string>(PA_UI_LOCALE_CODES);

export function isPaUiLocale(code: string): code is PaUiLocaleCode {
    return PA_SET.has(code);
}

/** English names for LLM translation prompts. */
export function localeToEnglishPromptName(code: string): string {
    const m: Record<string, string> = {
        en: "English",
        it: "Italian",
        zh: "Chinese (Simplified)",
        tw: "Chinese (Traditional)",
        ru: "Russian",
        fr: "French",
        es: "Spanish",
        dk: "Danish",
        de: "German",
    };
    return m[code] ?? code;
}

/** Map vue-i18n locale string to a PA UI code when possible. */
export function normalizeToPaLocale(locale: string): PaUiLocaleCode {
    const l = locale.toLowerCase();
    if (l === "tw" || l.startsWith("zh-tw") || l === "zh_hant") return "tw";
    if (l.startsWith("zh")) return "zh";
    if (l.startsWith("it")) return "it";
    const head = l.split("-")[0] ?? l;
    if (isPaUiLocale(head)) return head;
    if (isPaUiLocale(l)) return l;
    return "en";
}
