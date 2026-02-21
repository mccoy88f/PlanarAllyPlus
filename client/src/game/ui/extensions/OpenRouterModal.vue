<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import type { ApiNote, ApiNoteRoom } from "../../../apiTypes";
import Modal from "../../../core/components/modals/Modal.vue";
import { uuidv4 } from "../../../core/utils";
import { http } from "../../../core/http";
import { coreStore } from "../../../store/core";
import { gameState } from "../../systems/game/state";
import { noteSystem } from "../../systems/notes";
import { noteState } from "../../systems/notes/state";
import type { NoteId } from "../../systems/notes/types";
import { extensionsState } from "../../systems/extensions/state";
import { closeOpenRouterModal, focusExtension, openExtensionModal } from "../../systems/extensions/ui";

export interface TaskDef {
    id: string;
    label: string;
    systemPrompt: string;
    userPrompt: string;
}

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

const DEFAULT_BASE_PROMPT_IT =
    "Rispondi sempre in formato markdown. Non includere messaggi di apertura (es. \"ok, ti preparo il contenuto\") né di chiusura (es. \"buon divertimento\", \"spero ti sia utile\"). Restituisci solo il contenuto richiesto, senza prefazioni né conclusioni.";

const DEFAULT_BASE_PROMPT_EN =
    "Always respond in markdown format. Do not include opening messages (e.g. \"ok, I'll prepare the content\") or closing messages (e.g. \"enjoy\", \"hope this helps\"). Return only the requested content, without preambles or conclusions.";

/** Template completo per scheda personaggio D&D 5e - Character Sheet extension (da character-template.json) */
const CHARACTER_SHEET_TEMPLATE = `{"name":"","classes":[{"definition":{"name":""},"subclassDefinition":null,"level":1}],"race":{"baseName":"","fullName":"","weightSpeeds":{"normal":{"walk":30}}},"background":{"definition":{"name":""}},"alignmentId":null,"currentXp":0,"inspiration":false,"baseHitPoints":0,"currentHitPoints":0,"temporaryHitPoints":0,"stats":[{"value":10},{"value":10},{"value":10},{"value":10},{"value":10},{"value":10}],"traits":{"personalityTraits":"","ideals":"","bonds":"","flaws":""},"currencies":{"cp":0,"sp":0,"ep":0,"gp":0,"pp":0},"inventory":[],"dndsheets":{"name":"","classLevel":"","background":"","playerName":"","faction":"","race":"","alignment":"","xp":"0","str":"10","dex":"10","con":"10","int":"10","wis":"10","cha":"10","strMod":"","dexMod":"","conMod":"","intMod":"","wisMod":"","chaMod":"","passivePerception":"","ac":"10","init":"0","speed":"30","maxHp":"0","hp":"0","tempHp":"0","hitDiceMax":"","hitDice":"","deathsaveSuccesses":0,"deathsaveFailures":0,"proficiencyBonus":"","attacks":[{"name":"","bonus":"","damage":""},{"name":"","bonus":"","damage":""},{"name":"","bonus":"","damage":""}],"equipment":"","equipment2":"","personalityTraits":"","ideals":"","bonds":"","flaws":"","featuresTraits":"","otherProficiencies":"","age":"","height":"","weight":"","eyes":"","skin":"","hair":"","appearance":"","backstory":"","allies":"","additionalFeatures":"","cantrips":[],"lvl1Spells":[],"lvl2Spells":[],"lvl3Spells":[],"lvl4Spells":[],"lvl5Spells":[],"lvl6Spells":[],"lvl7Spells":[],"lvl8Spells":[],"lvl9Spells":[]},"planarally":{"armorClass":10,"initiative":0,"hitDiceTotal":"","hitDiceRemaining":"","deathSaveSuccesses":0,"deathSaveFailures":0,"savingThrows":{"str":{"mod":0,"proficient":false},"dex":{"mod":0,"proficient":false},"con":{"mod":0,"proficient":false},"int":{"mod":0,"proficient":false},"wis":{"mod":0,"proficient":false},"cha":{"mod":0,"proficient":false}},"skills":{"acrobatics":{"mod":0,"proficient":false},"animalHandling":{"mod":0,"proficient":false},"arcana":{"mod":0,"proficient":false},"athletics":{"mod":0,"proficient":false},"deception":{"mod":0,"proficient":false},"history":{"mod":0,"proficient":false},"insight":{"mod":0,"proficient":false},"intimidation":{"mod":0,"proficient":false},"investigation":{"mod":0,"proficient":false},"medicine":{"mod":0,"proficient":false},"nature":{"mod":0,"proficient":false},"perception":{"mod":0,"proficient":false},"performance":{"mod":0,"proficient":false},"persuasion":{"mod":0,"proficient":false},"religion":{"mod":0,"proficient":false},"sleightOfHand":{"mod":0,"proficient":false},"stealth":{"mod":0,"proficient":false},"survival":{"mod":0,"proficient":false}},"attacks":[],"features":"","proficiencies":""}}`;

const DEFAULT_TASKS_IT: TaskDef[] = [
    {
        id: "generate_character",
        label: "Genera personaggio",
        systemPrompt:
            "Sei un esperto di giochi di ruolo. Genera una scheda personaggio completa per un NPC o PG: nome, razza/classe, background breve, tratti caratteriali, statistiche base (FOR, DEX, ecc.), equipaggiamento iniziale. Formato: markdown leggibile.",
        userPrompt: "Genera un personaggio per una campagna fantasy.",
    },
    {
        id: "generate_character_json",
        label: "Crea personaggio JSON",
        systemPrompt: `Sei un esperto di giochi di ruolo. Genera una scheda personaggio D&D 5e completa in formato JSON, compatibile con PlanarAlly Character Sheet.

IMPORTANTE: Tutti i contenuti testuali (nome, tratti, ideali, legami, difetti, background, descrizioni, incantesimi, equipaggiamento, ecc.) devono essere in italiano.

Usa questo template come struttura. COMPILA TUTTI i campi con i valori del personaggio generato (nome, classe, razza, statistiche, tratti, background, equipaggiamento, CA, PF, tiri salvezza, abilità, ecc.). Non lasciare campi vuoti dove ha senso inserire un valore.

Template (rispetta questa struttura esatta):
${CHARACTER_SHEET_TEMPLATE}

alignmentId: 0="", 1="Lawful Good", 2="Neutral Good", 3="Chaotic Good", 4="Lawful Neutral", 5="Neutral", 6="Chaotic Neutral", 7="Lawful Evil", 8="Neutral Evil", 9="Chaotic Evil"

Rispondi SOLO con il JSON completo, senza markdown (\`\`\`json) né testo prima o dopo.`,
        userPrompt: "Crea un personaggio D&D 5e completo in JSON per una campagna fantasy.",
    },
    {
        id: "generate_story",
        label: "Genera storia",
        systemPrompt:
            "Sei uno scrittore esperto di narrativa per giochi di ruolo. Scrivi una storia/avventura breve e coinvolgente che un DM possa usare come hook o scenario. Includi: ambientazione, conflitto, possibili sviluppi, NPC rilevanti.",
        userPrompt: "Scrivi una breve avventura per una sessione one-shot.",
    },
    {
        id: "improve_map",
        label: "Migliora mappa (realistica)",
        systemPrompt:
            "Sei un esperto di descrizioni per mappe da tavolo e giochi di ruolo. Dato una descrizione di una mappa, migliorala rendendola più realistica e immersiva. Aggiungi dettagli ambientali, atmosfera, suggerimenti per il DM su come descriverla ai giocatori. Non inserire mai segnalini o personaggi.",
        userPrompt: "Migliora questa descrizione di mappa rendendola più realistica:",
    },
];

const DEFAULT_TASKS_EN: TaskDef[] = [
    {
        id: "generate_character",
        label: "Generate character",
        systemPrompt:
            "You are an expert in tabletop RPGs. Generate a complete character sheet for an NPC or PC: name, race/class, brief background, personality traits, base stats (STR, DEX, etc.), starting equipment. Format: readable markdown.",
        userPrompt: "Generate a character for a fantasy campaign.",
    },
    {
        id: "generate_character_json",
        label: "Create character JSON",
        systemPrompt: `You are an expert in tabletop RPGs. Generate a complete D&D 5e character sheet as valid JSON, compatible with PlanarAlly Character Sheet.

IMPORTANT: All text content (name, traits, ideals, bonds, flaws, background, descriptions, spells, equipment, etc.) must be in English.

Use this template as the structure. FILL IN ALL fields with the generated character's values (name, class, race, stats, traits, background, equipment, AC, HP, saving throws, skills, etc.). Do not leave fields empty where a value makes sense.

Template (follow this exact structure):
${CHARACTER_SHEET_TEMPLATE}

alignmentId: 0="", 1="Lawful Good", 2="Neutral Good", 3="Chaotic Good", 4="Lawful Neutral", 5="Neutral", 6="Chaotic Neutral", 7="Lawful Evil", 8="Neutral Evil", 9="Chaotic Evil"

Reply ONLY with the complete JSON, no markdown (\`\`\`json) or text before or after.`,
        userPrompt: "Create a complete D&D 5e character in JSON for a fantasy campaign.",
    },
    {
        id: "generate_story",
        label: "Generate story",
        systemPrompt:
            "You are an expert writer of tabletop RPG narrative. Write a short, engaging story/adventure that a DM can use as a hook or scenario. Include: setting, conflict, possible developments, relevant NPCs.",
        userPrompt: "Write a short adventure for a one-shot session.",
    },
    {
        id: "improve_map",
        label: "Improve map (realistic)",
        systemPrompt:
            "You are an expert in descriptions for tabletop maps and RPGs. Given a map description, improve it to make it more realistic and immersive. Add environmental details, atmosphere, suggestions for the DM on how to describe it to players. Never include markers or characters.",
        userPrompt: "Improve this map description to make it more realistic:",
    },
];

function getDefaultBasePrompt(lang: "it" | "en"): string {
    return lang === "it" ? DEFAULT_BASE_PROMPT_IT : DEFAULT_BASE_PROMPT_EN;
}

function getDefaultTasks(lang: "it" | "en"): TaskDef[] {
    return lang === "it" ? [...DEFAULT_TASKS_IT] : [...DEFAULT_TASKS_EN];
}

const activeTab = ref<"settings" | "tasks">("tasks");
const apiKey = ref("");
const googleApiKey = ref("");
const selectedModel = ref("openrouter/free");
const selectedImageModel = ref("sourceful/riverflow-v2-fast");
const models = ref<{ id: string; name: string; is_free: boolean; output_modalities?: string[] }[]>([]);
const loadingModels = ref(false);
const savingSettings = ref(false);
const runningTask = ref(false);
const result = ref("");
const resultRef = ref<HTMLDivElement | null>(null);
const customPrompt = ref("");
const basePrompt = ref("");
const tasks = ref<TaskDef[]>([]);
const defaultLanguage = ref<"it" | "en">("it");
const maxTokens = ref(8192);

const currentTask = ref<TaskDef | { id: "custom"; label: string; systemPrompt: string; userPrompt: string } | null>(null);
const taskInput = ref("");
const editingTask = ref<TaskDef | null>(null);
const editingTaskOriginal = ref<TaskDef | null>(null);

const visible = computed(() => props.visible);

const imageModelsList = ref<
    { id: string; name: string; is_free: boolean; output_modalities?: string[] }[]
>([]);
const freeModels = computed(() => models.value.filter((m) => m.is_free && !m.id.startsWith("gemini")));
const paidModels = computed(() => models.value.filter((m) => !m.is_free && !m.id.startsWith("gemini")));

const openRouterImageModels = computed(() => models.value.filter((m) => (m.output_modalities ?? []).includes("image") && !m.id.startsWith("gemini")));
const googleImageModels = computed(() => imageModelsList.value.filter((m) => (m.output_modalities ?? []).includes("image")));

async function loadModels(): Promise<void> {
    loadingModels.value = true;
    try {
        const resp = await http.get("/api/extensions/openrouter/models");
        if (resp.ok) {
            const data = (await resp.json()) as {
                openrouter_models: { id: string; name: string; is_free: boolean; output_modalities?: string[] }[];
                google_models: { id: string; name: string; is_free: boolean; output_modalities?: string[] }[];
            };
            
            
            // Merge OpenRouter and Google models into one flat list internally
            models.value = [...(data.openrouter_models ?? []), ...(data.google_models ?? [])];
            
            if (models.value.length > 0) {
                const currentInBoth = models.value.some((m) => m.id === selectedModel.value);
                if (!currentInBoth) {
                    selectedModel.value = data.google_models?.length ? data.google_models[0]!.id : models.value[0]!.id;
                }
            }
        }
        
        // Fetch google image models
        const imgResp = await http.get("/api/extensions/openrouter/models?type=image");
        if (imgResp.ok) {
            const imgData = (await imgResp.json()) as {
                google_models: { id: string; name: string }[];
            };
            const list = (imgData.google_models ?? []).map((m) => ({
                ...m,
                is_free: false,
                output_modalities: ["image"],
            }));
            imageModelsList.value = list;
            
            const currentImgInBoth = openRouterImageModels.value.some((m) => m.id === selectedImageModel.value) || list.some((m) => m.id === selectedImageModel.value);
            if (!currentImgInBoth) {
                selectedImageModel.value = list.length > 0 ? list[0]!.id : (openRouterImageModels.value.length > 0 ? openRouterImageModels.value[0]!.id : "");
            }
        } else {
            imageModelsList.value = [];
        }
    } catch {
        models.value = [];
        imageModelsList.value = [];
    } finally {
        loadingModels.value = false;
    }
}

async function loadSettings(): Promise<void> {
    try {
        const resp = await http.get("/api/extensions/openrouter/settings");
        if (resp.ok) {
            const data = (await resp.json()) as {
                hasApiKey: boolean;
                hasGoogleKey: boolean;
                model: string;
                basePrompt?: string;
                tasks?: TaskDef[];
                imageModel?: string;
                defaultLanguage?: string;
                maxTokens?: number;
            };
            apiKey.value = data.hasApiKey ? "********" : "";
            googleApiKey.value = data.hasGoogleKey ? "********" : "";
            selectedModel.value = data.model || "gemini-2.0-flash";
            selectedImageModel.value = data.imageModel || "gemini-2.5-flash-image";
            defaultLanguage.value =
                data.defaultLanguage === "en" ? "en" : "it";
            maxTokens.value = data.maxTokens ?? 8192;
            const lang = defaultLanguage.value;
            basePrompt.value = (data.basePrompt?.trim() || getDefaultBasePrompt(lang));
            const loadedTasks =
                data.tasks && data.tasks.length > 0
                    ? data.tasks.map((t) => ({
                          id: t.id,
                          label: t.label,
                          systemPrompt: t.systemPrompt,
                          userPrompt: t.userPrompt,
                      }))
                    : getDefaultTasks(lang);
            const defaultTasks = getDefaultTasks(lang);
            const jsonTask = defaultTasks.find((d) => d.id === "generate_character_json");
            const hasJsonTask = loadedTasks.some((t) => t.id === "generate_character_json");
            if (jsonTask && !hasJsonTask) {
                tasks.value = [loadedTasks[0], jsonTask, ...loadedTasks.slice(1)].filter(
                    (x): x is TaskDef => x != null,
                );
            } else {
                tasks.value = loadedTasks;
            }
        }
    } catch {
        defaultLanguage.value = "it";
        tasks.value = getDefaultTasks("it");
    }
}

async function saveSettings(): Promise<void> {
    savingSettings.value = true;
    try {
        const body: {
            apiKey?: string;
            googleApiKey?: string;
            model: string;
            basePrompt: string;
            tasks: TaskDef[];
            imageModel: string;
            defaultLanguage: string;
            maxTokens: number;
        } = {
            model: selectedModel.value,
            basePrompt: basePrompt.value.trim(),
            tasks: tasks.value,
            imageModel: selectedImageModel.value,
            defaultLanguage: defaultLanguage.value,
            maxTokens: maxTokens.value,
        };
        if (apiKey.value && apiKey.value !== "********") {
            body.apiKey = apiKey.value;
        }
        if (googleApiKey.value && googleApiKey.value !== "********") {
            body.googleApiKey = googleApiKey.value;
        }
        const resp = await http.postJson("/api/extensions/openrouter/settings", body);
        if (resp.ok) {
            toast.success(t("game.ui.extensions.OpenRouterModal.settings_saved"));
            if (apiKey.value && apiKey.value !== "********") {
                apiKey.value = "********";
            }
            if (googleApiKey.value && googleApiKey.value !== "********") {
                googleApiKey.value = "********";
            }
        } else {
            const err = await resp.json().catch(() => ({}));
            toast.error((err as { error?: string }).error || t("game.ui.extensions.OpenRouterModal.save_error"));
        }
    } catch {
        toast.error(t("game.ui.extensions.OpenRouterModal.save_error"));
    } finally {
        savingSettings.value = false;
    }
}

function buildMessages(task: TaskDef | { id: string; systemPrompt: string; userPrompt: string }, input: string) {
    const langInstruction =
        defaultLanguage.value === "it"
            ? "Rispondi sempre in italiano."
            : "Always respond in English.";
    const systemParts: string[] = [langInstruction];
    if (basePrompt.value.trim()) systemParts.push(basePrompt.value.trim());
    if (task.systemPrompt?.trim()) systemParts.push(task.systemPrompt.trim());
    const systemContent = systemParts.join("\n\n");
    const userContent = input.trim() ? `${task.userPrompt}\n\n${input}` : task.userPrompt;

    const messages: { role: string; content: string }[] = [];
    if (systemContent) messages.push({ role: "system", content: systemContent });
    messages.push({ role: "user", content: userContent });
    return messages;
}

async function runTask(
    task: TaskDef | { id: string; systemPrompt: string; userPrompt: string },
    input: string,
): Promise<void> {
    runningTask.value = true;
    result.value = "";
    try {
        const messages = buildMessages(task, input);
        const resp = await http.postJson("/api/extensions/openrouter/chat", {
            model: selectedModel.value,
            messages,
            max_tokens: Math.max(256, Math.min(65536, maxTokens.value || 8192)),
            temperature: 0.7,
        });
        if (resp.ok) {
            const data = (await resp.json()) as { choices?: { message?: { content?: string } }[] };
            const content = data.choices?.[0]?.message?.content ?? "";
            result.value = content || t("game.ui.extensions.OpenRouterModal.no_response");
            await nextTick();
            resultRef.value?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } else {
            const err = (await resp.json().catch(() => ({}))) as { error?: string };
            toast.error(err.error || t("game.ui.extensions.OpenRouterModal.request_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.OpenRouterModal.request_error"));
        console.error(e);
    } finally {
        runningTask.value = false;
    }
}

async function runCustomTask(): Promise<void> {
    const prompt = customPrompt.value.trim();
    if (!prompt) {
        toast.error(t("game.ui.extensions.OpenRouterModal.enter_prompt"));
        return;
    }
    runningTask.value = true;
    result.value = "";
    try {
    const langInstruction =
        defaultLanguage.value === "it"
            ? "Rispondi sempre in italiano."
            : "Always respond in English.";
    const systemParts: string[] = [langInstruction];
    if (basePrompt.value.trim()) systemParts.push(basePrompt.value.trim());
    const systemContent = systemParts.join("\n\n");
    const messages: { role: string; content: string }[] = [];
    if (systemContent) messages.push({ role: "system", content: systemContent });
    messages.push({ role: "user", content: prompt });

        const resp = await http.postJson("/api/extensions/openrouter/chat", {
            model: selectedModel.value,
            messages,
            max_tokens: Math.max(256, Math.min(65536, maxTokens.value || 8192)),
            temperature: 0.7,
        });
        if (resp.ok) {
            const data = (await resp.json()) as { choices?: { message?: { content?: string } }[] };
            const content = data.choices?.[0]?.message?.content ?? "";
            result.value = content || t("game.ui.extensions.OpenRouterModal.no_response");
            await nextTick();
            resultRef.value?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } else {
            const err = (await resp.json().catch(() => ({}))) as { error?: string };
            toast.error(err.error || t("game.ui.extensions.OpenRouterModal.request_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.OpenRouterModal.request_error"));
        console.error(e);
    } finally {
        runningTask.value = false;
    }
}

function selectTask(task: TaskDef | { id: "custom"; label: string; systemPrompt: string; userPrompt: string }): void {
    currentTask.value = task;
    editingTask.value = null;
    taskInput.value = "";
    result.value = "";
}

function addTask(): void {
    const newTask: TaskDef = {
        id: `custom_${Date.now()}`,
        label: t("game.ui.extensions.OpenRouterModal.task_new_default"),
        systemPrompt: "",
        userPrompt: "",
    };
    tasks.value = [...tasks.value, newTask];
    currentTask.value = newTask;
    editingTask.value = newTask;
    editingTaskOriginal.value = null;
    taskInput.value = "";
    result.value = "";
}

function deleteTask(task: TaskDef): void {
    tasks.value = tasks.value.filter((t) => t.id !== task.id);
    if (currentTask.value?.id === task.id) {
        currentTask.value = null;
        editingTask.value = null;
        result.value = "";
    }
}

function startEditTask(task: TaskDef): void {
    editingTaskOriginal.value = { ...task, label: task.label, systemPrompt: task.systemPrompt, userPrompt: task.userPrompt };
    editingTask.value = task;
}

function cancelEditTask(): void {
    if (editingTask.value) {
        if (editingTaskOriginal.value && editingTask.value.id === editingTaskOriginal.value.id) {
            editingTask.value.label = editingTaskOriginal.value.label;
            editingTask.value.systemPrompt = editingTaskOriginal.value.systemPrompt;
            editingTask.value.userPrompt = editingTaskOriginal.value.userPrompt;
        } else if (!editingTaskOriginal.value && editingTask.value.id.startsWith("custom_")) {
            deleteTask(editingTask.value);
        }
    }
    editingTask.value = null;
    editingTaskOriginal.value = null;
}

async function saveEditTask(): Promise<void> {
    await saveSettings();
    editingTask.value = null;
    editingTaskOriginal.value = null;
}

function getTaskLabel(task: TaskDef): string {
    const key = `game.ui.extensions.OpenRouterModal.task_${task.id}`;
    const translated = t(key);
    return translated !== key ? translated : task.label;
}

function restoreDefaultTasks(): void {
    tasks.value = getDefaultTasks(defaultLanguage.value);
    currentTask.value = null;
    editingTask.value = null;
    taskInput.value = "";
    result.value = "";
    toast.success(t("game.ui.extensions.OpenRouterModal.tasks_restored"));
}

function extractFirstH1(markdown: string): string {
    const m = markdown.match(/^#\s+(.+)$/m);
    const fallback = defaultLanguage.value === "it" ? "Nota AI" : "AI Note";
    return m ? m[1]!.trim() : fallback;
}

function extractJsonFromResult(text: string): unknown | null {
    const trimmed = text.trim();
    const codeBlockMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
    const toParse = codeBlockMatch ? codeBlockMatch[1]!.trim() : trimmed;
    try {
        return JSON.parse(toParse) as unknown;
    } catch {
        return null;
    }
}

const importingToSheet = ref(false);

async function importCharacterToSheet(): Promise<void> {
    if (!result.value.trim()) return;
    const parsed = extractJsonFromResult(result.value);
    if (!parsed || typeof parsed !== "object") {
        toast.error(
            t("game.ui.extensions.OpenRouterModal.import_json_invalid", {
                task: t("game.ui.extensions.OpenRouterModal.task_generate_character_json"),
            }),
        );
        return;
    }
    const [roomCreator, ...roomNameParts] = gameState.fullRoomName.value.split("/") as [string, ...string[]];
    const roomName = roomNameParts.join("/");
    if (!roomCreator || !roomName) {
        toast.error(t("game.ui.extensions.OpenRouterModal.import_no_room"));
        return;
    }
    importingToSheet.value = true;
    try {
        const resp = await http.postJson("/api/extensions/character-sheet/sheet", {
            roomCreator,
            roomName,
            sheet: parsed,
        });
        if (resp.ok) {
            const data = (await resp.json()) as { sheetId?: string };
            toast.success(t("game.ui.extensions.OpenRouterModal.import_success"));
            const charSheetExt = extensionsState.reactive.extensions.find(
                (e) => e.id === "character-sheet" || e.folder === "character-sheet",
            );
            if (charSheetExt?.uiUrl && charSheetExt?.folder) {
                openExtensionModal({
                    id: charSheetExt.id,
                    name: charSheetExt.name,
                    folder: charSheetExt.folder,
                    uiUrl: charSheetExt.uiUrl,
                    titleBarColor: charSheetExt.titleBarColor,
                    icon: charSheetExt.icon,
                });
            }
        } else {
            const err = (await resp.json().catch(() => ({}))) as { error?: string };
            toast.error(err.error || t("game.ui.extensions.OpenRouterModal.import_error"));
        }
    } catch {
        toast.error(t("game.ui.extensions.OpenRouterModal.import_error"));
    } finally {
        importingToSheet.value = false;
    }
}

const canImportToSheet = computed(
    () =>
        currentTask.value?.id === "generate_character_json" &&
        !!result.value.trim(),
);

const showImportToSheetButton = computed(
    () => currentTask.value?.id === "generate_character_json",
);

async function createNoteFromResult(): Promise<void> {
    if (!result.value.trim()) return;
    const title = extractFirstH1(result.value);
    const [roomCreator, ...roomNameParts] = gameState.fullRoomName.value.split("/") as [string, ...string[]];
    const roomName = roomNameParts.join("/");
    const rooms: ApiNoteRoom[] = [
        { roomCreator, roomName, locationId: null, locationName: null },
    ];
    const note: ApiNote = {
        uuid: uuidv4() as unknown as NoteId,
        creator: coreStore.state.username,
        title: title || (defaultLanguage.value === "it" ? "Nota AI" : "AI Note"),
        text: result.value,
        showOnHover: false,
        showIconOnShape: false,
        rooms,
        tags: [],
        access: [],
        shapes: [],
    };
    await noteSystem.newNote(note, true);
    noteState.mutableReactive.currentNote = note.uuid;
    toast.success(t("game.ui.extensions.OpenRouterModal.note_created"));
}

function close(): void {
    closeOpenRouterModal();
    props.onClose();
}

watch(visible, async (v) => {
    if (v) {
        await loadSettings();
        loadModels();
        activeTab.value = "tasks";
        result.value = "";
        currentTask.value = null;
        customPrompt.value = "";
        editingTask.value = null;
    }
});


onMounted(() => {
    if (visible.value) {
        loadModels();
        loadSettings();
    }
});
</script>

<template>
    <Modal
        v-if="visible"
        :visible="visible"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="openrouter-modal"
        @close="close"
        @focus="focusExtension('openrouter')"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">
                    {{ t("game.ui.extensions.OpenRouterModal.title") }}
                </h2>
                <div class="ext-modal-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="ext-modal-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="ext-modal-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="ext-modal-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div class="ext-modal-body-wrapper openrouter-body">
            <div v-show="activeTab === 'settings'" class="ext-body openrouter-settings">
                <div class="ext-ui-section openrouter-settings-section">

                    <h4 class="ext-ui-section-title">OpenRouter API Key</h4>
                    <div class="ext-ui-field openrouter-field">
                        <input
                            v-model="apiKey"
                            type="password"
                            class="ext-ui-input"
                            :placeholder="t('game.ui.extensions.OpenRouterModal.api_key_placeholder')"
                            autocomplete="off"
                        />
                    </div>
                    
                    <h4 class="ext-ui-section-title" style="margin-top: 15px;">Google AI Studio API Key</h4>
                    <div class="ext-ui-field openrouter-field">
                        <input
                            v-model="googleApiKey"
                            type="password"
                            class="ext-ui-input"
                            :placeholder="t('game.ui.extensions.OpenRouterModal.api_key_placeholder')"
                            autocomplete="off"
                        />
                        <p class="ext-ui-hint">{{ t("game.ui.extensions.OpenRouterModal.api_key_hint") }}</p>
                    </div>
                </div>
                <div class="ext-ui-section openrouter-settings-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.model") }}</h4>
                    <div class="ext-ui-field openrouter-field">
                        <select v-model="selectedModel" class="ext-ui-select" :disabled="loadingModels">
                        <optgroup
                            v-if="freeModels.length > 0"
                            :label="t('game.ui.extensions.OpenRouterModal.model_free')"
                        >
                            <option
                                v-for="m in freeModels"
                                :key="m.id"
                                :value="m.id"
                            >
                                {{ m.name }}
                            </option>
                        </optgroup>
                        <optgroup
                            v-if="paidModels.length > 0"
                            :label="t('game.ui.extensions.OpenRouterModal.model_paid')"
                        >
                            <option
                                v-for="m in paidModels"
                                :key="m.id"
                                :value="m.id"
                            >
                                {{ m.name }}
                            </option>
                        </optgroup>
                        <optgroup
                            v-if="models.filter(x => x.id.startsWith('gemini') && x.is_free).length > 0"
                            label="Google AI Studio (Gratuito)"
                        >
                            <option
                                v-for="m in models.filter(x => x.id.startsWith('gemini') && x.is_free)"
                                :key="m.id"
                                :value="m.id"
                            >
                                {{ m.name }}
                            </option>
                        </optgroup>
                        <optgroup
                            v-if="models.filter(x => x.id.startsWith('gemini') && !x.is_free).length > 0"
                            label="Google AI Studio (A pagamento)"
                        >
                            <option
                                v-for="m in models.filter(x => x.id.startsWith('gemini') && !x.is_free)"
                                :key="m.id"
                                :value="m.id"
                            >
                                {{ m.name }}
                            </option>
                        </optgroup>
                        <option
                            v-if="models.length === 0 && !loadingModels"
                            value="openrouter/free"
                        >
                            openrouter/free (default)
                        </option>
                        </select>
                    </div>
                    <div class="ext-ui-field openrouter-field openrouter-field-inline">
                        <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.default_language") }}</label>
                        <select v-model="defaultLanguage" class="ext-ui-select">
                        <option value="it">{{ t("game.ui.extensions.OpenRouterModal.language_it") }}</option>
                        <option value="en">{{ t("game.ui.extensions.OpenRouterModal.language_en") }}</option>
                        </select>
                        <p class="ext-ui-hint">{{ t("game.ui.extensions.OpenRouterModal.default_language_hint") }}</p>
                    </div>
                    <div class="ext-ui-field openrouter-field openrouter-field-inline">
                        <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.max_tokens") }}</label>
                        <input
                            v-model.number="maxTokens"
                            type="number"
                            class="ext-ui-input"
                            min="256"
                            max="65536"
                            step="256"
                        />
                        <p class="ext-ui-hint">{{ t("game.ui.extensions.OpenRouterModal.max_tokens_hint") }}</p>
                    </div>
                </div>
                <div class="ext-ui-section openrouter-settings-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.image_model") }}</h4>
                    <div class="ext-ui-field openrouter-field">
                        <select v-model="selectedImageModel" class="ext-ui-select" :disabled="loadingModels">
                            <optgroup
                                v-if="openRouterImageModels.length > 0"
                                label="OpenRouter"
                            >
                                <option
                                    v-for="m in openRouterImageModels"
                                    :key="m.id"
                                    :value="m.id"
                                >
                                    {{ m.name }}
                                </option>
                            </optgroup>
                            <optgroup
                                v-if="googleImageModels.filter(m => m.is_free).length > 0"
                                label="Google AI Studio (Gratuito)"
                            >
                                <option
                                    v-for="m in googleImageModels.filter(m => m.is_free)"
                                    :key="m.id"
                                    :value="m.id"
                                >
                                    {{ m.name }}
                                </option>
                            </optgroup>
                            <optgroup
                                v-if="googleImageModels.filter(m => !m.is_free).length > 0"
                                label="Google AI Studio (A pagamento)"
                            >
                                <option
                                    v-for="m in googleImageModels.filter(m => !m.is_free)"
                                    :key="m.id"
                                    :value="m.id"
                                >
                                    {{ m.name }}
                                </option>
                            </optgroup>
                            <option
                                v-if="googleImageModels.length === 0 && openRouterImageModels.length === 0 && !loadingModels"
                                value="sourceful/riverflow-v2-fast"
                            >
                                sourceful/riverflow-v2-fast (default)
                            </option>
                        </select>
                        <p class="ext-ui-hint">{{ t("game.ui.extensions.OpenRouterModal.image_model_hint") }}</p>
                    </div>
                </div>
                <div class="ext-ui-section openrouter-settings-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.base_prompt") }}</h4>
                    <div class="ext-ui-field openrouter-field">
                    <textarea
                        v-model="basePrompt"
                        class="ext-ui-textarea"
                        :placeholder="t('game.ui.extensions.OpenRouterModal.base_prompt_placeholder')"
                        rows="3"
                    />
                        <button
                            type="button"
                            class="openrouter-restore-default"
                            @click="basePrompt = getDefaultBasePrompt(defaultLanguage)"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.restore_default") }}
                        </button>
                    </div>
                </div>
            </div>

            <div v-show="activeTab === 'tasks'" class="ext-body ext-two-col">
                <section class="ext-ui-section ext-two-col-main openrouter-result-section">
                    <h3>{{ t("game.ui.extensions.OpenRouterModal.result") }}</h3>
                    <div v-if="!result" class="ext-ui-empty openrouter-result-placeholder">
                        {{ t("game.ui.extensions.OpenRouterModal.click_run") }}
                    </div>
                    <div v-else ref="resultRef" class="openrouter-result-container">
                        <div class="openrouter-result-content">{{ result }}</div>
                    </div>
                </section>

                <section class="ext-ui-section ext-two-col-side openrouter-params-section">
                    <div class="openrouter-tasks-header">
                        <span class="openrouter-tasks-title">{{ t("game.ui.extensions.OpenRouterModal.tasks") }}</span>
                        <button
                            type="button"
                            class="openrouter-restore-tasks"
                            @click="restoreDefaultTasks"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.restore_default_tasks") }}
                        </button>
                    </div>
                    <div class="openrouter-task-list">
                        <button
                            v-for="task in tasks"
                            :key="task.id"
                            :class="{ active: currentTask?.id === task.id }"
                            @click="selectTask(task)"
                        >
                            {{ getTaskLabel(task) }}
                        </button>
                        <button
                            :class="{ active: currentTask?.id === 'custom' }"
                            @click="
                                currentTask = {
                                    id: 'custom',
                                    label: '',
                                    systemPrompt: '',
                                    userPrompt: '',
                                };
                                taskInput = '';
                                result = '';
                                editingTask = null;
                            "
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.task_custom") }}
                        </button>
                        <button
                            class="openrouter-add-task"
                            @click="addTask"
                        >
                            + {{ t("game.ui.extensions.OpenRouterModal.task_add") }}
                        </button>
                    </div>

                    <div v-if="editingTask" class="openrouter-edit-task ext-ui-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.task_label") }}</h4>
                    <div class="ext-ui-field">
                        <input v-model="editingTask.label" type="text" class="ext-ui-input" />
                    </div>
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.task_system_prompt") }}</h4>
                    <div class="ext-ui-field">
                        <textarea v-model="editingTask.systemPrompt" class="ext-ui-textarea" rows="4" />
                    </div>
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.task_user_prompt") }}</h4>
                    <div class="ext-ui-field">
                        <textarea v-model="editingTask.userPrompt" class="ext-ui-textarea" rows="2" />
                    </div>
                    <div class="openrouter-edit-actions">
                        <button
                            v-if="editingTask.id.startsWith('custom_')"
                            class="ext-ui-btn ext-ui-btn-danger openrouter-delete-btn"
                            @click="deleteTask(editingTask); cancelEditTask()"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.task_delete") }}
                        </button>
                        <button
                            class="ext-ui-btn openrouter-cancel-btn"
                            @click="cancelEditTask"
                        >
                            {{ t("common.cancel") }}
                        </button>
                        <button
                            class="ext-ui-btn ext-ui-btn-success openrouter-save-btn-inline"
                            :disabled="savingSettings"
                            @click="saveEditTask"
                        >
                            {{ savingSettings ? "..." : t("common.save") }}
                        </button>
                    </div>
                </div>

                <div v-else-if="currentTask" class="openrouter-task-panel">
                    <template v-if="currentTask.id !== 'custom'">
                        <button
                            class="openrouter-edit-inline"
                            @click="startEditTask(currentTask as TaskDef)"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.task_edit") }}
                        </button>
                        <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.input_optional") }}</label>
                        <div class="ext-ui-field">
                            <textarea
                                v-model="taskInput"
                                class="ext-ui-textarea"
                                :placeholder="t('game.ui.extensions.OpenRouterModal.input_placeholder')"
                                rows="3"
                            />
                        </div>
                    </template>
                    <template v-else>
                        <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.custom_prompt") }}</label>
                        <div class="ext-ui-field">
                            <textarea
                                v-model="customPrompt"
                                class="ext-ui-textarea"
                                :placeholder="t('game.ui.extensions.OpenRouterModal.custom_placeholder')"
                                rows="4"
                            />
                        </div>
                    </template>
                </div>
                </section>
            </div>
            <div class="ext-bottom-bar openrouter-bottom-bar">
                <div class="openrouter-bottom-tabs">
                    <button
                        type="button"
                        class="ext-ui-btn"
                        :class="{ 'ext-ui-btn-success': activeTab === 'tasks' }"
                        @click="activeTab = 'tasks'"
                    >
                        {{ t("game.ui.extensions.OpenRouterModal.tasks") }}
                    </button>
                    <button
                        type="button"
                        class="ext-ui-btn"
                        :class="{ 'ext-ui-btn-success': activeTab === 'settings' }"
                        @click="activeTab = 'settings'"
                    >
                        {{ t("game.ui.extensions.OpenRouterModal.settings") }}
                    </button>
                </div>
                <div class="openrouter-bottom-actions">
                    <template v-if="activeTab === 'settings'">
                        <button
                            type="button"
                            class="ext-ui-btn ext-ui-btn-success"
                            :disabled="savingSettings"
                            @click="saveSettings"
                        >
                            {{ savingSettings ? "..." : t("common.save") }}
                        </button>
                    </template>
                    <template v-else>
                        <button
                            v-if="showImportToSheetButton && result.trim()"
                            type="button"
                            class="ext-ui-btn ext-ui-btn-primary"
                            :disabled="importingToSheet"
                            @click="importCharacterToSheet"
                        >
                            {{ importingToSheet ? "..." : t("game.ui.extensions.OpenRouterModal.import_to_sheet") }}
                        </button>
                        <button
                            v-if="result.trim()"
                            type="button"
                            class="ext-ui-btn ext-ui-btn-success"
                            @click="createNoteFromResult"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.create_note") }}
                        </button>
                        <button
                            v-if="currentTask"
                            type="button"
                            class="ext-ui-btn ext-ui-btn-success"
                            :disabled="runningTask || (currentTask.id === 'custom' && !customPrompt.trim())"
                            @click="currentTask.id === 'custom' ? runCustomTask() : runTask(currentTask, taskInput)"
                        >
                            {{ runningTask ? "..." : t("game.ui.extensions.OpenRouterModal.run") }}
                        </button>
                    </template>
                </div>
            </div>
        </div>
    </Modal>
</template>

<style lang="scss">
.openrouter-modal {
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    resize: both;
    min-width: 600px;
    min-height: 400px;
    width: min(90vw, 900px);
    height: min(85vh, 600px);
    overflow: hidden;
}
</style>

<style scoped lang="scss">

.openrouter-body {
    padding: 1rem 1.5rem 0;
    overflow: hidden;
}

.openrouter-bottom-bar {
    margin: 1rem -1.5rem 0 -1.5rem;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}

.openrouter-bottom-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.openrouter-bottom-tabs {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.openrouter-settings {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    overflow-y: auto;
    padding-right: 0.25rem;

    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-thumb {
        background: #ccc;
        border-radius: 3px;
    }
    &::-webkit-scrollbar-track {
        background: #f5f5f5;
        border-radius: 3px;
    }
}

.openrouter-settings-section {
    padding: 1rem;
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 0.5rem;
    margin-top: 0;
    padding-top: 1rem;
    border-top: none;

    &.ext-ui-section:first-child {
        margin-top: 0;
    }

    .openrouter-field-inline {
        margin-top: 0.75rem;
    }
}

.openrouter-restore-default {
    align-self: flex-start;
    font-size: 0.85em;
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: 1px dashed #999;
    border-radius: 0.25rem;
    cursor: pointer;
    color: #666;

    &:hover {
        background: #f5f5f5;
    }
}

.openrouter-params-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
}

.openrouter-result-section {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;

    h3 {
        margin: 0 0 0.75rem;
        font-weight: 600;
        font-size: 1.1em;
        flex-shrink: 0;
    }
}

.openrouter-result-placeholder {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    border: 1px dashed #ccc;
    border-radius: 0.25rem;
    background: #fafafa;
}

.openrouter-result-container {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    overflow: hidden;
}

.openrouter-result-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    flex-shrink: 0;
}

.openrouter-create-note-btn {
    flex-shrink: 0;
}

.openrouter-tasks-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.5rem;

    .openrouter-tasks-title {
        font-weight: 500;
    }
}

.openrouter-restore-tasks {
    font-size: 0.85em;
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: 1px dashed #999;
    border-radius: 0.25rem;
    cursor: pointer;
    color: #666;

    &:hover {
        background: #f5f5f5;
    }
}

.openrouter-task-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;

    button {
        padding: 0.5rem 1rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        background: #fff;
        cursor: pointer;
        font-size: 0.95em;

        &.active {
            background: #82c8a0;
            border-color: #82c8a0;
        }

        &.openrouter-add-task {
            border-style: dashed;
            color: #666;
        }
    }
}

.openrouter-edit-task {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 0.25rem;
    background: #fafafa;

    &.ext-ui-section {
        margin-top: 0;
        padding-top: 0.75rem;
        border-top: none;
    }

    .ext-ui-section-title {
        margin: 0.5rem 0 0.25rem;
    }

    .openrouter-edit-actions {
        display: flex;
        gap: 0.5rem;
        margin-top: 0.5rem;
    }
}

.openrouter-cancel-btn {
    background: #e0e0e0;
    border-color: #ccc;
    color: #444;

    &:hover:not(:disabled) {
        background: #d0d0d0;
        border-color: #bbb;
    }
}

.openrouter-edit-inline {
    align-self: flex-start;
    font-size: 0.85em;
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: 1px dashed #999;
    border-radius: 0.25rem;
    cursor: pointer;
    color: #666;
}

.openrouter-task-panel {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;

    label {
        font-weight: 500;
    }

    textarea {
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        resize: vertical;
    }
}

.openrouter-action-buttons {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.openrouter-result-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.75rem;
    border: 1px solid #eee;
    border-radius: 0.25rem;
    background: #fafafa;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 0.95em;
}
</style>
