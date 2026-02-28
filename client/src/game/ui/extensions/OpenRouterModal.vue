<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import VueMarkdown from "vue-markdown-render";
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
import LoadingBar from "../../../core/components/LoadingBar.vue";
import { closeOpenRouterModal, focusExtension, openExtensionModal } from "../../systems/extensions/ui";
import { addDungeonToMap, type WallData, type DoorData } from "../../dungeongen";
import { toGP } from "../../../core/geometry";
import type { AssetId } from "../../../assets/models";

export interface TaskDef {
    id: string;
    label: string;
    systemPrompt: string;
    userPrompt: string;
    /** Special task type: "import_character" shows file upload for character sheets,
     *  "import_map" shows file upload for map images,
     *  "multimodal" shows file upload for custom vision tasks. Defaults to normal chat if omitted. */
    type?: "import_character" | "import_map" | "multimodal";
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
        id: "import_character_sheet",
        label: "Importa scheda personaggio",
        type: "import_character" as const,
        systemPrompt: `Sei un esperto di giochi di ruolo D&D 5e. Analizza il contenuto allegato (scheda personaggio, stat block NPC, PDF o documento) ed estrai tutte le informazioni del personaggio.

Il documento potrebbe essere:
- Una scheda personaggio tradizionale D&D 5e (anche su più pagine)
- Uno stat block NPC (formato D&D Beyond o simile) con sezioni Traits, Actions, CR, ecc.
Se sono presenti più immagini/pagine, appartengono tutte allo stesso personaggio: consolida i dati in un unico JSON.

Regole per stat block NPC:
- CR (Challenge Rating) → usa il valore XP come currentXp (es. CR 1/4 = 50 XP, CR 1/2 = 100, CR 1 = 200)
- Tratti e abilità passivi → campo featuresTraits
- Azioni di attacco → array attacks (nome, bonus, danno)
- Incantesimi "at will" → cantrips
- Incantesimi "X/day each" → incantesimi di livello appropriato (lvl1Spells, lvl2Spells, ecc.)
- Tipo creatura (es. "Small Humanoid") → race.fullName
- Sensi (Darkvision, ecc.) → campo otherProficiencies o featuresTraits

Compila il seguente template JSON con TUTTI i dati trovati. Rispondi SOLO con il JSON completo, senza testo aggiuntivo, senza blocchi markdown.

Template (rispetta questa struttura esatta):
${CHARACTER_SHEET_TEMPLATE}

alignmentId: 0="", 1="Lawful Good", 2="Neutral Good", 3="Chaotic Good", 4="Lawful Neutral", 5="Neutral", 6="Chaotic Neutral", 7="Lawful Evil", 8="Neutral Evil", 9="Chaotic Evil"`,
        userPrompt: "Estrai i dati del personaggio da questa scheda e compila il JSON. Rispondi SOLO con il JSON completo.",
    },
    {
        id: "import_map",
        label: "Importa mappa da immagine",
        type: "import_map" as const,
        systemPrompt: "",
        userPrompt: "",
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
        id: "import_character_sheet",
        label: "Import character sheet",
        type: "import_character" as const,
        systemPrompt: `You are an expert in D&D 5e tabletop RPGs. Analyze the attached content (character sheet, NPC stat block, PDF or document) and extract all character information.

The document may be:
- A traditional D&D 5e character sheet (possibly spanning multiple pages)
- An NPC stat block (D&D Beyond format or similar) with Traits, Actions, CR sections, etc.
If multiple images/pages are provided, they all belong to the same character: consolidate data into a single JSON.

Rules for NPC stat blocks:
- CR (Challenge Rating) → use XP value as currentXp (e.g. CR 1/4 = 50 XP, CR 1/2 = 100, CR 1 = 200)
- Passive traits and abilities → featuresTraits field
- Attack actions → attacks array (name, bonus, damage)
- "At will" spells → cantrips
- "X/day each" spells → appropriate spell level (lvl1Spells, lvl2Spells, etc.)
- Creature type (e.g. "Small Humanoid") → race.fullName
- Senses (Darkvision, etc.) → otherProficiencies or featuresTraits field

Fill in the following JSON template with ALL data found. Reply ONLY with the complete JSON, without any additional text or markdown blocks.

Template (follow this exact structure):
${CHARACTER_SHEET_TEMPLATE}

alignmentId: 0="", 1="Lawful Good", 2="Neutral Good", 3="Chaotic Good", 4="Lawful Neutral", 5="Neutral", 6="Chaotic Neutral", 7="Lawful Evil", 8="Neutral Evil", 9="Chaotic Evil"`,
        userPrompt: "Extract character data from this sheet and fill in the JSON. Reply ONLY with the complete JSON.",
    },
    {
        id: "import_map",
        label: "Import map from image",
        type: "import_map" as const,
        systemPrompt: "",
        userPrompt: "",
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
const selectedVisionModel = ref("gemini-2.0-flash");
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
const addTaskPickerVisible = ref(false);
const taskSearch = ref("");
const editingTaskOriginal = ref<TaskDef | null>(null);
const editMode = ref(false);

const visible = computed(() => props.visible);

const imageModelsList = ref<
    { id: string; name: string; is_free: boolean; output_modalities?: string[] }[]
>([]);
const freeModels = computed(() => models.value.filter((m) => m.is_free && !m.id.startsWith("gemini")));
const paidModels = computed(() => models.value.filter((m) => !m.is_free && !m.id.startsWith("gemini")));

const openRouterImageModels = computed(() => models.value.filter((m) => (m.output_modalities ?? []).includes("image") && !m.id.startsWith("gemini")));
const googleImageModels = computed(() => imageModelsList.value.filter((m) => (m.output_modalities ?? []).includes("image")));

const textTasks = computed(() => {
    const q = taskSearch.value.trim().toLowerCase();
    return tasks.value.filter((t) => !t.type && (!q || getTaskLabel(t).toLowerCase().includes(q)));
});
const multimodalTasks = computed(() => {
    const q = taskSearch.value.trim().toLowerCase();
    return tasks.value.filter((t) => !!t.type && (!q || getTaskLabel(t).toLowerCase().includes(q)));
});

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
                visionModel?: string;
                basePrompt?: string;
                tasks?: TaskDef[];
                imageModel?: string;
                defaultLanguage?: string;
                maxTokens?: number;
            };
            apiKey.value = data.hasApiKey ? "********" : "";
            googleApiKey.value = data.hasGoogleKey ? "********" : "";
            selectedModel.value = data.model || "gemini-2.0-flash";
            selectedVisionModel.value = data.visionModel || data.model || "gemini-2.0-flash";
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
                          ...(t.type ? { type: t.type } : {}),
                      }))
                    : getDefaultTasks(lang);
            const defaultTasks = getDefaultTasks(lang);
            const jsonTask = defaultTasks.find((d) => d.id === "generate_character_json");
            const hasJsonTask = loadedTasks.some((t) => t.id === "generate_character_json");
            let finalTasks: TaskDef[];
            if (jsonTask && !hasJsonTask) {
                finalTasks = [loadedTasks[0], jsonTask, ...loadedTasks.slice(1)].filter(
                    (x): x is TaskDef => x != null,
                );
            } else {
                finalTasks = loadedTasks;
            }
            // Backward compat: add new special tasks if missing, or fix type if lost
            for (const specialId of ["import_character_sheet", "import_map"]) {
                const existing = finalTasks.find((t) => t.id === specialId);
                if (!existing) {
                    const t = defaultTasks.find((d) => d.id === specialId);
                    if (t) finalTasks.push(t);
                } else if (!existing.type) {
                    const def = defaultTasks.find((d) => d.id === specialId);
                    if (def?.type) existing.type = def.type;
                }
            }
            tasks.value = finalTasks;
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
            visionModel: string;
            basePrompt: string;
            tasks: TaskDef[];
            imageModel: string;
            defaultLanguage: string;
            maxTokens: number;
        } = {
            model: selectedModel.value,
            visionModel: selectedVisionModel.value,
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
            // Add reloading models on save
            await loadModels();
            activeTab.value = "tasks";
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
    if (editMode.value && task.id !== "custom") {
        startEditTask(task as TaskDef);
        return;
    }
    currentTask.value = task;
    editingTask.value = null;
    taskInput.value = "";
    result.value = "";
    selectedFile.value = null;
    selectedFiles.value = [];
    importMapData.value = null;
    if (fileInputRef.value) fileInputRef.value.value = "";
}

function addTask(type?: "multimodal"): void {
    addTaskPickerVisible.value = false;
    const newTask: TaskDef = {
        id: `custom_${Date.now()}`,
        label: t("game.ui.extensions.OpenRouterModal.task_new_default"),
        systemPrompt: "",
        userPrompt: "",
        ...(type ? { type } : {}),
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
    editMode.value = false;
}

async function saveEditTask(): Promise<void> {
    await saveSettings();
    editingTask.value = null;
    editingTaskOriginal.value = null;
    editMode.value = false;
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

// File upload state (for import_character and import_map tasks)
const fileInputRef = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const selectedFiles = ref<File[]>([]); // multi-page support for import_character
const importingToMap = ref(false);
const importMapData = ref<{
    url: string;
    assetId: AssetId;
    gridCells: { width: number; height: number };
    walls?: WallData;
    doors?: DoorData[];
    name?: string;
} | null>(null);

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
            await resp.json();
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
                    titleBarColor: (charSheetExt as any).titleBarColor,
                    icon: (charSheetExt as any).icon,
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


const showImportToSheetButton = computed(
    () => currentTask.value?.id === "generate_character_json" || currentTask.value?.id === "import_character_sheet",
);

const showImportMapButton = computed(
    () => currentTask.value?.id === "import_map" && importMapData.value !== null,
);

function onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const task = currentTask.value as TaskDef | null;
    if (task?.type === "import_character") {
        selectedFiles.value = Array.from(input.files || []);
        selectedFile.value = selectedFiles.value[0] ?? null;
    } else {
        selectedFile.value = input.files?.[0] ?? null;
        selectedFiles.value = selectedFile.value ? [selectedFile.value] : [];
    }
    result.value = "";
    importMapData.value = null;
}

async function runImportTask(): Promise<void> {
    const task = currentTask.value as TaskDef | null;
    if (!task) return;

    const filesToUpload = task.type === "import_character" ? selectedFiles.value : (selectedFile.value ? [selectedFile.value] : []);
    if (filesToUpload.length === 0) {
        toast.error(t("game.ui.extensions.OpenRouterModal.file_required"));
        return;
    }

    runningTask.value = true;
    result.value = "";
    importMapData.value = null;

    try {
        const formData = new FormData();
        for (const f of filesToUpload) {
            formData.append("file", f);
        }

        if (task.type === "import_character" || task.type === "multimodal") {
            formData.append("systemPrompt", task.systemPrompt || "");
            formData.append("userPrompt", task.userPrompt || "");

            const resp = await fetch("/api/extensions/openrouter/import-character", {
                method: "POST",
                body: formData,
                credentials: "include",
            });
            if (resp.ok) {
                const data = (await resp.json()) as { result?: string };
                result.value = data.result ?? "";
            } else {
                const err = (await resp.json().catch(() => ({}))) as { error?: string };
                toast.error(err.error || t("game.ui.extensions.OpenRouterModal.request_error"));
            }
        } else if (task.type === "import_map") {
            const resp = await fetch("/api/extensions/openrouter/import-map", {
                method: "POST",
                body: formData,
                credentials: "include",
            });
            if (resp.ok) {
                const data = (await resp.json()) as {
                    url: string;
                    assetId: AssetId;
                    gridCells: { width: number; height: number };
                    walls?: WallData;
                    doors?: DoorData[];
                    name?: string;
                };
                importMapData.value = {
                    url: data.url,
                    assetId: data.assetId,
                    gridCells: data.gridCells,
                    walls: data.walls,
                    doors: data.doors,
                    name: data.name,
                };
                const wallCount = data.walls?.lines?.length ?? 0;
                const doorCount = data.doors?.length ?? 0;
                result.value = t("game.ui.extensions.OpenRouterModal.map_analysis_success", {
                    width: data.gridCells.width,
                    height: data.gridCells.height,
                    walls: wallCount,
                    doors: doorCount,
                });
            } else {
                const err = (await resp.json().catch(() => ({}))) as { error?: string };
                toast.error(err.error || t("game.ui.extensions.OpenRouterModal.request_error"));
            }
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.OpenRouterModal.request_error"));
        console.error(e);
    } finally {
        runningTask.value = false;
    }
}

async function importMapToCanvas(): Promise<void> {
    if (!importMapData.value) return;
    importingToMap.value = true;
    try {
        const { url, gridCells, walls, doors, name } = importMapData.value;
        const mapName = name ?? selectedFile.value?.name ?? "imported_map";
        await addDungeonToMap(url, gridCells, toGP(0, 0), {
            seed: mapName,
            name: mapName,
            walls,
            doors,
            wallPadding: 0,
        });
        toast.success(t("game.ui.extensions.OpenRouterModal.import_map_success"));
    } catch (e) {
        toast.error(t("game.ui.extensions.OpenRouterModal.import_error"));
        console.error(e);
    } finally {
        importingToMap.value = false;
    }
}

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
        selectedFile.value = null;
        selectedFiles.value = [];
        importMapData.value = null;
        if (fileInputRef.value) fileInputRef.value.value = "";
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
        <div class="ext-modal-body-wrapper">
            <div v-if="runningTask || savingSettings" class="ext-progress-top-container">
                <LoadingBar :progress="100" indeterminate height="6px" />
            </div>
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
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.model_text") }}</h4>
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
                            :label="t('game.ui.extensions.OpenRouterModal.model_google_free')"
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
                            :label="t('game.ui.extensions.OpenRouterModal.model_google_paid')"
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
                </div>
                <div class="ext-ui-section openrouter-settings-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.model_vision") }}</h4>
                    <p class="ext-ui-hint" style="margin-bottom: 0.5rem;">{{ t("game.ui.extensions.OpenRouterModal.model_vision_hint") }}</p>
                    <div class="ext-ui-field openrouter-field">
                        <select v-model="selectedVisionModel" class="ext-ui-select" :disabled="loadingModels">
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
                            :label="t('game.ui.extensions.OpenRouterModal.model_google_free')"
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
                            :label="t('game.ui.extensions.OpenRouterModal.model_google_paid')"
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
                            value="gemini-2.0-flash"
                        >
                            gemini-2.0-flash (default)
                        </option>
                        </select>
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
                                :label="t('game.ui.extensions.OpenRouterModal.model_google_free')"
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
                                :label="t('game.ui.extensions.OpenRouterModal.model_google_paid')"
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
                            rows="6"
                        />
                    </div>
                    <div class="openrouter-restore-default-row">
                        <button
                            type="button"
                            class="openrouter-restore-default"
                            @click="basePrompt = getDefaultBasePrompt(defaultLanguage)"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.restore_default") }}
                        </button>
                    </div>
                </div>
                <div class="ext-ui-section openrouter-settings-section">
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.max_tokens") }}</h4>
                    <div class="ext-ui-field openrouter-field openrouter-field-inline">
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
                    <h4 class="ext-ui-section-title">{{ t("game.ui.extensions.OpenRouterModal.tasks") }}</h4>
                    <p class="ext-ui-hint" style="margin-bottom: 0.5rem;">{{ t("game.ui.extensions.OpenRouterModal.save_tasks_hint") }}</p>
                    <button
                        type="button"
                        class="ext-ui-btn"
                        @click="restoreDefaultTasks"
                    >
                        {{ t("game.ui.extensions.OpenRouterModal.restore_default_tasks") }}
                    </button>
                </div>
            </div>

            <div v-show="activeTab === 'tasks'" class="ext-toolbar-bar openrouter-task-toolbar">
                <div class="ext-search-bar">
                    <font-awesome-icon icon="search" class="ext-search-icon" />
                    <input
                        v-model="taskSearch"
                        type="text"
                        class="ext-search-input"
                        :placeholder="t('game.ui.extensions.OpenRouterModal.task_search_placeholder')"
                    />
                    <button
                        type="button"
                        class="ext-search-add-btn"
                        :title="t('game.ui.extensions.OpenRouterModal.task_add')"
                        @click="addTaskPickerVisible = !addTaskPickerVisible; editMode = false"
                    >
                        <font-awesome-icon icon="plus" />
                    </button>
                </div>
                <button
                    type="button"
                    class="ext-toolbar-btn"
                    :class="{ 'openrouter-edit-active': editMode }"
                    :title="t('game.ui.extensions.OpenRouterModal.task_edit_mode_toggle')"
                    @click="editMode = !editMode; addTaskPickerVisible = false"
                >
                    <font-awesome-icon :icon="editMode ? 'lock-open' : 'lock'" :style="{ color: editMode ? '#f44336' : '#4caf50' }" />
                </button>
                <button
                    type="button"
                    class="ext-toolbar-btn"
                    :title="t('game.ui.extensions.OpenRouterModal.settings')"
                    @click="activeTab = 'settings'; addTaskPickerVisible = false; editMode = false"
                >
                    <font-awesome-icon icon="gear" />
                </button>
            </div>

            <div v-show="activeTab === 'tasks'" class="ext-body ext-two-col">
                <section class="ext-ui-section ext-two-col-main openrouter-result-section">
                    <h3>{{ t("game.ui.extensions.OpenRouterModal.result") }}</h3>
                    <!-- Map import preview with wall/door overlay -->
                    <template v-if="importMapData">
                        <p class="openrouter-map-preview-summary">{{ result }}</p>
                        <div class="openrouter-map-preview">
                            <img :src="importMapData.url" class="openrouter-preview-image" :alt="importMapData.name ?? 'map'" />
                            <svg
                                class="openrouter-preview-overlay"
                                :viewBox="`0 0 ${importMapData.gridCells.width} ${importMapData.gridCells.height}`"
                                preserveAspectRatio="none"
                            >
                                <!-- Walls -->
                                <line
                                    v-for="(line, i) in importMapData.walls?.lines ?? []"
                                    :key="'w' + i"
                                    :x1="line[0][0]" :y1="line[0][1]"
                                    :x2="line[1][0]" :y2="line[1][1]"
                                    stroke="#00e676" stroke-width="0.08" stroke-linecap="round"
                                />
                                <!-- Doors -->
                                <rect
                                    v-for="(door, i) in importMapData.doors ?? []"
                                    :key="'d' + i"
                                    :x="door.x + 0.15" :y="door.y + 0.15"
                                    width="0.7" height="0.7"
                                    fill="none" stroke="#ffaa00" stroke-width="0.08"
                                />
                            </svg>
                            <div class="openrouter-preview-legend">
                                <span class="openrouter-legend-wall">{{ t("game.ui.extensions.OpenRouterModal.preview_legend_wall") }}</span>
                                <span v-if="(importMapData.doors ?? []).length > 0" class="openrouter-legend-door">{{ t("game.ui.extensions.OpenRouterModal.preview_legend_door") }}</span>
                            </div>
                        </div>
                    </template>
                    <template v-else>
                        <div v-if="!result" class="ext-ui-empty openrouter-result-placeholder">
                            {{ t("game.ui.extensions.OpenRouterModal.click_run") }}
                        </div>
                        <div v-else ref="resultRef" class="openrouter-result-container">
                            <VueMarkdown class="openrouter-result-content openrouter-markdown" :source="result" />
                        </div>
                    </template>
                </section>

                <section class="ext-ui-section ext-two-col-side openrouter-params-section">
                    <div v-if="editMode && !editingTask && !addTaskPickerVisible" class="openrouter-edit-mode-indicator">
                        <font-awesome-icon icon="lock-open" />
                        <span>{{ t("game.ui.extensions.OpenRouterModal.edit_mode_active") }}</span>
                    </div>

                    <div v-if="addTaskPickerVisible" class="openrouter-add-task-picker">
                        <span class="openrouter-add-task-picker-label">{{ t("game.ui.extensions.OpenRouterModal.task_add_type_label") }}</span>
                        <button class="openrouter-add-task-type-btn" @click="addTask()">
                            {{ t("game.ui.extensions.OpenRouterModal.task_add_type_text") }}
                        </button>
                        <button class="openrouter-add-task-type-btn openrouter-add-task-type-btn--multimodal" @click="addTask('multimodal')">
                            {{ t("game.ui.extensions.OpenRouterModal.task_add_type_multimodal") }}
                        </button>
                    </div>
                    
                    <div v-if="!editingTask && !addTaskPickerVisible" class="openrouter-task-list">
                        <span class="openrouter-task-group-label">{{ t("game.ui.extensions.OpenRouterModal.task_group_text") }}</span>
                        <button
                            v-for="task in textTasks"
                            :key="task.id"
                            :class="{ active: currentTask?.id === task.id }"
                            @click="selectTask(task)"
                        >
                            {{ getTaskLabel(task) }}
                        </button>
                        <span class="openrouter-task-group-label openrouter-task-group-label--multimodal">{{ t("game.ui.extensions.OpenRouterModal.task_group_multimodal") }}</span>
                        <button
                            v-for="task in multimodalTasks"
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
                    </div>
                    <div v-else-if="currentTask" class="openrouter-task-panel">
                    <!-- Hidden file input for import tasks -->
                    <input
                        ref="fileInputRef"
                        type="file"
                        style="display:none"
                        :accept="(currentTask as TaskDef).type === 'import_character' || (currentTask as TaskDef).type === 'multimodal'
                            ? '.png,.jpg,.jpeg,.pdf,.doc,.docx'
                            : '.png,.jpg,.jpeg'"
                        :multiple="(currentTask as TaskDef).type === 'import_character'"
                        @change="onFileSelected"
                    />

                    <template v-if="currentTask.id !== 'custom'">

                        <!-- Multimodal hint -->
                        <div v-if="(currentTask as TaskDef).type" class="openrouter-multimodal-hint">
                            {{ t("game.ui.extensions.OpenRouterModal.task_multimodal_hint") }}
                        </div>

                        <!-- File upload for import tasks -->
                        <template v-if="(currentTask as TaskDef).type === 'import_character' || (currentTask as TaskDef).type === 'import_map' || (currentTask as TaskDef).type === 'multimodal'">
                            <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.file_upload_label") }}</label>
                            <div class="ext-ui-field openrouter-file-upload">
                                <button
                                    type="button"
                                    class="ext-ui-btn"
                                    @click="fileInputRef?.click()"
                                >
                                    {{ t("game.ui.extensions.OpenRouterModal.file_select") }}
                                </button>
                                <span v-if="(currentTask as TaskDef).type === 'import_character' && selectedFiles.length > 1" class="openrouter-file-name">{{ t("game.ui.extensions.OpenRouterModal.files_selected", { count: selectedFiles.length }) }}</span>
                                <span v-else-if="selectedFile" class="openrouter-file-name">{{ selectedFile.name }}</span>
                                <span v-else class="openrouter-file-hint">
                                    {{ (currentTask as TaskDef).type === 'import_character' || (currentTask as TaskDef).type === 'multimodal'
                                        ? t("game.ui.extensions.OpenRouterModal.file_hint_character")
                                        : t("game.ui.extensions.OpenRouterModal.file_hint_map") }}
                                </span>
                            </div>
                        </template>

                        <!-- Standard textarea for regular tasks -->
                        <template v-else>
                            <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.input_optional") }}</label>
                            <div class="ext-ui-field">
                                <textarea
                                    v-model="taskInput"
                                    class="ext-ui-textarea"
                                    :placeholder="t('game.ui.extensions.OpenRouterModal.input_placeholder')"
                                    rows="6"
                                />
                            </div>
                        </template>
                    </template>
                    <template v-else>
                        <label class="ext-ui-label">{{ t("game.ui.extensions.OpenRouterModal.custom_prompt") }}</label>
                        <div class="ext-ui-field">
                            <textarea
                                v-model="customPrompt"
                                class="ext-ui-textarea"
                                :placeholder="t('game.ui.extensions.OpenRouterModal.custom_placeholder')"
                                rows="7"
                            />
                        </div>
                    </template>
                </div>
                </section>
            </div>
            <div class="ext-bottom-bar openrouter-bottom-bar">
                <!-- Far left actions -->
                <div class="openrouter-bottom-left-actions">
                    <button
                        v-if="editMode"
                        type="button"
                        class="ext-ui-btn"
                        @click="restoreDefaultTasks"
                    >
                        {{ t("game.ui.extensions.OpenRouterModal.restore_default_tasks") }}
                    </button>
                </div>

                <div class="openrouter-bottom-actions">
                    <template v-if="activeTab === 'settings'">
                        <button
                            type="button"
                            class="ext-ui-btn"
                            @click="activeTab = 'tasks'"
                        >
                            {{ t("common.cancel") }}
                        </button>
                        <button
                            type="button"
                            class="ext-ui-btn ext-ui-btn-success"
                            :disabled="savingSettings"
                            @click="saveSettings"
                        >
                            {{ savingSettings ? "..." : t("common.save") }}
                        </button>
                    </template>
                    <template v-else-if="editingTask">
                        <button
                            v-if="editingTask.id.startsWith('custom_')"
                            class="ext-ui-btn ext-ui-btn-danger"
                            @click="deleteTask(editingTask); cancelEditTask()"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.task_delete") }}
                        </button>
                        <button
                            class="ext-ui-btn"
                            @click="cancelEditTask"
                        >
                            {{ t("common.cancel") }}
                        </button>
                        <button
                            class="ext-ui-btn ext-ui-btn-success"
                            :disabled="savingSettings"
                            @click="saveEditTask"
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
                            v-if="showImportMapButton"
                            type="button"
                            class="ext-ui-btn ext-ui-btn-primary"
                            :disabled="importingToMap"
                            @click="importMapToCanvas"
                        >
                            {{ importingToMap ? "..." : t("game.ui.extensions.OpenRouterModal.import_to_map") }}
                        </button>
                        <button
                            v-if="result.trim() && currentTask?.id !== 'import_map'"
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
                            :disabled="runningTask
                                || (currentTask.id === 'custom' && !customPrompt.trim())
                                || ((currentTask as TaskDef).type === 'import_character' && selectedFiles.length === 0)
                                || (((currentTask as TaskDef).type === 'import_map' || (currentTask as TaskDef).type === 'multimodal') && !selectedFile)"
                            @click="currentTask.id === 'custom'
                                ? runCustomTask()
                                : ((currentTask as TaskDef).type === 'import_character' || (currentTask as TaskDef).type === 'import_map' || (currentTask as TaskDef).type === 'multimodal')
                                    ? runImportTask()
                                    : runTask(currentTask, taskInput)"
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

    .ext-modal-header {
        width: 100%;
        flex-shrink: 0;
        background: #fafafa;
        padding: 0.5rem 1.5rem;
        border-bottom: 1px solid #eee;
    }
}
</style>

<style scoped lang="scss">

.openrouter-bottom-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

:deep(.ext-progress-top-container) {
    padding: 0.25rem 1.5rem;
    background: #fafafa;
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

.openrouter-map-preview-summary {
    font-size: 0.85em;
    color: #555;
    margin-bottom: 0.5rem;
    white-space: pre-line;
}

.openrouter-map-preview {
    position: relative;
    width: 100%;
    flex: 1;
    min-height: 0;
    overflow: hidden;
    border-radius: 0.25rem;
    border: 1px solid #ddd;

    .openrouter-preview-image {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: contain;
    }

    .openrouter-preview-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
    }

    .openrouter-preview-legend {
        position: absolute;
        bottom: 0.4rem;
        left: 0.4rem;
        display: flex;
        gap: 0.75rem;
        font-size: 0.75em;
        font-weight: 600;

        span {
            padding: 0.15rem 0.4rem;
            border-radius: 0.2rem;
            background: rgba(0,0,0,0.55);
        }

        .openrouter-legend-wall { color: #00e676; }
        .openrouter-legend-door { color: #ffaa00; }
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

.openrouter-result-content.openrouter-markdown {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 0.75rem;
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 0.25rem;
    font-size: 0.93em;
    line-height: 1.6;
    white-space: normal;
    word-break: break-word;

    :deep(h1), :deep(h2), :deep(h3) {
        margin: 0.75rem 0 0.4rem;
        font-weight: 600;
    }
    :deep(h1) { font-size: 1.2em; }
    :deep(h2) { font-size: 1.1em; }
    :deep(h3) { font-size: 1em; }
    :deep(p) { margin: 0.4rem 0; }
    :deep(ul), :deep(ol) { padding-left: 1.5rem; margin: 0.4rem 0; }
    :deep(li) { margin: 0.15rem 0; }
    :deep(strong) { font-weight: 700; }
    :deep(em) { font-style: italic; }
    :deep(code) {
        background: #f0f0f0;
        border-radius: 0.2rem;
        padding: 0.1em 0.3em;
        font-family: monospace;
        font-size: 0.9em;
    }
    :deep(pre) {
        background: #f0f0f0;
        border-radius: 0.3rem;
        padding: 0.6rem 0.8rem;
        overflow-x: auto;
        margin: 0.5rem 0;

        code {
            background: none;
            padding: 0;
        }
    }
    :deep(blockquote) {
        border-left: 3px solid #ccc;
        margin: 0.5rem 0;
        padding: 0.2rem 0.75rem;
        color: #555;
    }
    :deep(hr) {
        border: none;
        border-top: 1px solid #ddd;
        margin: 0.75rem 0;
    }
    :deep(table) {
        border-collapse: collapse;
        width: 100%;
        margin: 0.5rem 0;
        font-size: 0.9em;

        th, td {
            border: 1px solid #ddd;
            padding: 0.3rem 0.6rem;
        }
        th {
            background: #f0f0f0;
            font-weight: 600;
        }
    }
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

.openrouter-task-toolbar {
    margin-bottom: 0;
    flex-shrink: 0;
    background: #fafafa;
    border: none;
    border-bottom: 1px solid #eee;
    padding: 0.625rem 1.5rem;
    min-height: 2.75rem;
    display: flex;
    gap: 0.5rem;
}

.openrouter-edit-active {
    background-color: #ffebee !important;
    border-color: #ef9a9a !important;
}

.openrouter-edit-mode-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    margin-bottom: 0.5rem;
    background-color: #ffebee;
    color: #c62828;
    border-radius: 4px;
    font-size: 0.85rem;
    font-weight: 500;
}

.openrouter-bottom-bar {
    display: flex;
    justify-content: space-between !important;
    align-items: center;
    padding: 0.75rem 1.5rem;
    background: #fafafa;
    border-top: 1px solid #eee;
}

.openrouter-bottom-left-actions {
    display: flex;
    gap: 0.5rem;
}

.openrouter-bottom-actions {
    display: flex;
    gap: 0.5rem;
    margin-left: auto;
}

.openrouter-task-group-label {
    width: 100%;
    font-size: 0.72em;
    font-weight: 700;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.35rem 0 0.1rem;
    border-bottom: 1px solid #e8e8e8;
    margin-bottom: 0.1rem;

    &--multimodal {
        color: #5a9fd4;
        border-bottom-color: #c8dff0;
    }
}

.openrouter-restore-default-row {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.5rem;
}

.openrouter-add-task-picker {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    padding: 0.5rem 0.75rem;
    background: #f7f7f7;
    border: 1px solid #ddd;
    border-radius: 0.25rem;
    margin-bottom: 0.5rem;

    .openrouter-add-task-picker-label {
        font-size: 0.85em;
        color: #555;
        flex-shrink: 0;
    }
}

.openrouter-add-task-type-btn {
    padding: 0.35rem 0.85rem;
    border: 1px solid #aaa;
    border-radius: 0.25rem;
    background: #fff;
    cursor: pointer;
    font-size: 0.88em;

    &:hover {
        background: #f0f0f0;
    }

    &--multimodal {
        border-color: #5a9fd4;
        color: #5a9fd4;

        &:hover {
            background: #eef5fc;
        }
    }
}

.openrouter-multimodal-hint {
    font-size: 0.82em;
    color: #5a9fd4;
    background: #eef5fc;
    border: 1px solid #c8dff0;
    border-radius: 0.25rem;
    padding: 0.4rem 0.6rem;
    margin-bottom: 0.5rem;
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

.openrouter-file-upload {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.openrouter-file-name {
    font-size: 0.9em;
    color: #333;
    font-weight: 500;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.openrouter-file-hint {
    font-size: 0.85em;
    color: #888;
    font-style: italic;
}
</style>
