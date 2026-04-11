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

/** Bandierine regionali (emoji) per le lingue con file `client/src/locales/*.json`. */
const PA_LOCALE_FLAG: Record<PaUiLocaleCode, string> = {
    en: "\u{1F1FA}\u{1F1F8}",
    it: "\u{1F1EE}\u{1F1F9}",
    zh: "\u{1F1E8}\u{1F1F3}",
    tw: "\u{1F1F9}\u{1F1FC}",
    ru: "\u{1F1F7}\u{1F1FA}",
    fr: "\u{1F1EB}\u{1F1F7}",
    es: "\u{1F1EA}\u{1F1F8}",
    dk: "\u{1F1E9}\u{1F1F0}",
    de: "\u{1F1E9}\u{1F1EA}",
};

const PA_LOCALE_ALPHA3: Record<PaUiLocaleCode, string> = {
    en: "ENG",
    it: "ITA",
    zh: "ZHO",
    tw: "ZHT",
    ru: "RUS",
    fr: "FRA",
    es: "SPA",
    dk: "DAN",
    de: "DEU",
};

/**
 * Etichetta compatta per la lingua di traduzione: emoji bandiera se nota, altrimenti codice ISO 639-2/B a 3 lettere.
 */
export function localeToCompendiumTranslationBadge(code: string): string {
    const norm = code.toLowerCase().trim();
    const head = (norm.split(/[-_]/)[0] ?? norm) as string;
    if (isPaUiLocale(head)) {
        const flag = PA_LOCALE_FLAG[head];
        return flag ?? PA_LOCALE_ALPHA3[head];
    }
    const letters = norm.replace(/[^a-z]/gi, "").toUpperCase();
    if (letters.length >= 3) return letters.slice(0, 3);
    if (letters.length > 0) return letters.padEnd(3, "·");
    return "···";
}
