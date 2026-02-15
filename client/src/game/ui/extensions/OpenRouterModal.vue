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
import { closeOpenRouterModal } from "../../systems/extensions/ui";

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

const DEFAULT_BASE_PROMPT =
    "Rispondi sempre in formato markdown. Non includere messaggi di apertura (es. \"ok, ti preparo il contenuto\") né di chiusura (es. \"buon divertimento\", \"spero ti sia utile\"). Restituisci solo il contenuto richiesto, senza prefazioni né conclusioni.";

const DEFAULT_TASKS: TaskDef[] = [
    {
        id: "generate_character",
        label: "Generate character",
        systemPrompt:
            "Sei un esperto di giochi di ruolo. Genera una scheda personaggio completa per un NPC o PG: nome, razza/classe, background breve, tratti caratteriali, statistiche base (FOR, DEX, ecc.), equipaggiamento iniziale. Formato: markdown leggibile.",
        userPrompt: "Genera un personaggio per una campagna fantasy.",
    },
    {
        id: "generate_story",
        label: "Generate story",
        systemPrompt:
            "Sei uno scrittore esperto di narrativa per giochi di ruolo. Scrivi una storia/avventura breve e coinvolgente che un DM possa usare come hook o scenario. Includi: ambientazione, conflitto, possibili sviluppi, NPC rilevanti.",
        userPrompt: "Scrivi una breve avventura per una sessione one-shot.",
    },
    {
        id: "improve_map",
        label: "Improve map (realistic)",
        systemPrompt:
            "Sei un esperto di descrizioni per mappe da tavolo e giochi di ruolo. Dato una descrizione di una mappa, migliorala rendendola più realistica e immersiva. Aggiungi dettagli ambientali, atmosfera, suggerimenti per il DM su come descriverla ai giocatori.",
        userPrompt: "Migliora questa descrizione di mappa rendendola più realistica:",
    },
];

const activeTab = ref<"settings" | "tasks">("tasks");
const apiKey = ref("");
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

const currentTask = ref<TaskDef | { id: "custom"; label: string; systemPrompt: string; userPrompt: string } | null>(null);
const taskInput = ref("");
const editingTask = ref<TaskDef | null>(null);

const visible = computed(() => props.visible);

const freeModels = computed(() => models.value.filter((m) => m.is_free));
const paidModels = computed(() => models.value.filter((m) => !m.is_free));
const imageModels = computed(() =>
    models.value.filter((m) => (m.output_modalities ?? []).includes("image")),
);

async function loadModels(): Promise<void> {
    loadingModels.value = true;
    try {
        const resp = await http.get("/api/extensions/openrouter/models");
        if (resp.ok) {
            const data = (await resp.json()) as {
                models: { id: string; name: string; is_free: boolean; output_modalities?: string[] }[];
            };
            models.value = data.models ?? [];
            if (models.value.length > 0 && !selectedModel.value) {
                selectedModel.value = models.value[0]!.id;
            }
        }
    } catch {
        models.value = [];
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
                model: string;
                basePrompt?: string;
                tasks?: TaskDef[];
                imageModel?: string;
            };
            apiKey.value = data.hasApiKey ? "********" : "";
            selectedModel.value = data.model || "openrouter/free";
            selectedImageModel.value = data.imageModel || "sourceful/riverflow-v2-fast";
            basePrompt.value = (data.basePrompt?.trim() || DEFAULT_BASE_PROMPT);
            tasks.value =
                data.tasks && data.tasks.length > 0
                    ? data.tasks.map((t) => ({
                          id: t.id,
                          label: t.label,
                          systemPrompt: t.systemPrompt,
                          userPrompt: t.userPrompt,
                      }))
                    : [...DEFAULT_TASKS];
        }
    } catch {
        tasks.value = [...DEFAULT_TASKS];
    }
}

async function saveSettings(): Promise<void> {
    savingSettings.value = true;
    try {
        const body: {
            apiKey?: string;
            model: string;
            basePrompt: string;
            tasks: TaskDef[];
            imageModel: string;
        } = {
            model: selectedModel.value,
            basePrompt: basePrompt.value.trim(),
            tasks: tasks.value,
            imageModel: selectedImageModel.value,
        };
        if (apiKey.value && apiKey.value !== "********") {
            body.apiKey = apiKey.value;
        }
        const resp = await http.postJson("/api/extensions/openrouter/settings", body);
        if (resp.ok) {
            toast.success(t("game.ui.extensions.OpenRouterModal.settings_saved"));
            if (apiKey.value && apiKey.value !== "********") {
                apiKey.value = "********";
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
    const systemParts: string[] = [];
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
            max_tokens: 2048,
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
        const messages: { role: string; content: string }[] = [];
        if (basePrompt.value.trim()) {
            messages.push({ role: "system", content: basePrompt.value.trim() });
        }
        messages.push({ role: "user", content: prompt });

        const resp = await http.postJson("/api/extensions/openrouter/chat", {
            model: selectedModel.value,
            messages,
            max_tokens: 2048,
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
        label: t("game.ui.extensions.OpenRouterModal.task_custom"),
        systemPrompt: "",
        userPrompt: "",
    };
    tasks.value = [...tasks.value, newTask];
    currentTask.value = newTask;
    editingTask.value = newTask;
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
    editingTask.value = task;
}

function cancelEditTask(): void {
    editingTask.value = null;
}

function extractFirstH1(markdown: string): string {
    const m = markdown.match(/^#\s+(.+)$/m);
    return m ? m[1]!.trim() : "Nota AI";
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
        title: title || "Nota AI",
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

watch(visible, (v) => {
    if (v) {
        loadModels();
        loadSettings();
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
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="openrouter-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="openrouter-title">{{ t("game.ui.extensions.OpenRouterModal.title") }}</h2>
                <div class="openrouter-header-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="openrouter-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="openrouter-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="openrouter-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div class="openrouter-body">
            <div class="openrouter-tabs">
                <button
                    :class="{ active: activeTab === 'settings' }"
                    @click="activeTab = 'settings'"
                >
                    {{ t("game.ui.extensions.OpenRouterModal.settings") }}
                </button>
                <button
                    :class="{ active: activeTab === 'tasks' }"
                    @click="activeTab = 'tasks'"
                >
                    {{ t("game.ui.extensions.OpenRouterModal.tasks") }}
                </button>
            </div>

            <div v-show="activeTab === 'settings'" class="openrouter-settings">
                <p class="openrouter-hint">{{ t("game.ui.extensions.OpenRouterModal.api_key_hint") }}</p>
                <div class="openrouter-field">
                    <label>{{ t("game.ui.extensions.OpenRouterModal.api_key") }}</label>
                    <input
                        v-model="apiKey"
                        type="password"
                        :placeholder="t('game.ui.extensions.OpenRouterModal.api_key_placeholder')"
                        autocomplete="off"
                    />
                </div>
                <div class="openrouter-field">
                    <label>{{ t("game.ui.extensions.OpenRouterModal.model") }}</label>
                    <select v-model="selectedModel" :disabled="loadingModels">
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
                        <option v-if="models.length === 0 && !loadingModels" value="openrouter/free">
                            openrouter/free (default)
                        </option>
                    </select>
                </div>
                <div class="openrouter-field">
                    <label>{{ t("game.ui.extensions.OpenRouterModal.image_model") }}</label>
                    <select v-model="selectedImageModel" :disabled="loadingModels">
                        <optgroup
                            v-if="imageModels.length > 0"
                            :label="t('game.ui.extensions.OpenRouterModal.image_model_label')"
                        >
                            <option
                                v-for="m in imageModels"
                                :key="m.id"
                                :value="m.id"
                            >
                                {{ m.name }}
                            </option>
                        </optgroup>
                        <option v-if="imageModels.length === 0 && !loadingModels" value="sourceful/riverflow-v2-fast">
                            sourceful/riverflow-v2-fast (default)
                        </option>
                    </select>
                    <p class="openrouter-hint">{{ t("game.ui.extensions.OpenRouterModal.image_model_hint") }}</p>
                </div>
                <div class="openrouter-field">
                    <label>{{ t("game.ui.extensions.OpenRouterModal.base_prompt") }}</label>
                    <textarea
                        v-model="basePrompt"
                        :placeholder="t('game.ui.extensions.OpenRouterModal.base_prompt_placeholder')"
                        rows="4"
                    />
                    <button
                        type="button"
                        class="openrouter-restore-default"
                        @click="basePrompt = DEFAULT_BASE_PROMPT"
                    >
                        {{ t("game.ui.extensions.OpenRouterModal.restore_default") }}
                    </button>
                </div>
                <button
                    class="openrouter-save-btn"
                    :disabled="savingSettings"
                    @click="saveSettings"
                >
                    {{ savingSettings ? "..." : t("common.save") }}
                </button>
            </div>

            <div v-show="activeTab === 'tasks'" class="openrouter-tasks">
                <section class="openrouter-params-section">
                    <div class="openrouter-tasks-header">
                        <span class="openrouter-tasks-title">{{ t("game.ui.extensions.OpenRouterModal.tasks") }}</span>
                        <button
                            class="openrouter-save-btn-small"
                            :disabled="savingSettings"
                            @click="saveSettings"
                        >
                            {{ savingSettings ? "..." : t("common.save") }}
                        </button>
                    </div>
                    <div class="openrouter-task-list">
                    <button
                        v-for="task in tasks"
                        :key="task.id"
                        :class="{ active: currentTask?.id === task.id }"
                        @click="selectTask(task)"
                    >
                        {{ task.label }}
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

                <div v-if="editingTask" class="openrouter-edit-task">
                    <h4>{{ t("game.ui.extensions.OpenRouterModal.task_label") }}</h4>
                    <input v-model="editingTask.label" type="text" />
                    <h4>{{ t("game.ui.extensions.OpenRouterModal.task_system_prompt") }}</h4>
                    <textarea v-model="editingTask.systemPrompt" rows="4" />
                    <h4>{{ t("game.ui.extensions.OpenRouterModal.task_user_prompt") }}</h4>
                    <textarea v-model="editingTask.userPrompt" rows="2" />
                    <div class="openrouter-edit-actions">
                        <button
                            v-if="editingTask.id.startsWith('custom_')"
                            class="openrouter-delete-btn"
                            @click="deleteTask(editingTask); cancelEditTask()"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.task_delete") }}
                        </button>
                        <button
                            class="openrouter-cancel-btn"
                            @click="cancelEditTask"
                        >
                            {{ t("common.cancel") }}
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
                        <label>{{ t("game.ui.extensions.OpenRouterModal.input_optional") }}</label>
                        <textarea
                            v-model="taskInput"
                            :placeholder="t('game.ui.extensions.OpenRouterModal.input_placeholder')"
                            rows="3"
                        />
                        <button
                            class="openrouter-run-btn"
                            :disabled="runningTask"
                            @click="runTask(currentTask, taskInput)"
                        >
                            {{ runningTask ? "..." : t("game.ui.extensions.OpenRouterModal.run") }}
                        </button>
                    </template>
                    <template v-else>
                        <label>{{ t("game.ui.extensions.OpenRouterModal.custom_prompt") }}</label>
                        <textarea
                            v-model="customPrompt"
                            :placeholder="t('game.ui.extensions.OpenRouterModal.custom_placeholder')"
                            rows="4"
                        />
                        <button
                            class="openrouter-run-btn"
                            :disabled="runningTask || !customPrompt.trim()"
                            @click="runCustomTask"
                        >
                            {{ runningTask ? "..." : t("game.ui.extensions.OpenRouterModal.run") }}
                        </button>
                    </template>
                </div>
                </section>

                <section class="openrouter-result-section">
                    <h3>{{ t("game.ui.extensions.OpenRouterModal.result") }}</h3>
                    <div v-if="!result" class="openrouter-result-placeholder">
                        {{ t("game.ui.extensions.OpenRouterModal.click_run") }}
                    </div>
                    <div v-else ref="resultRef" class="openrouter-result-container">
                        <div class="openrouter-result-content">{{ result }}</div>
                        <button
                            class="openrouter-create-note-btn"
                            @click="createNoteFromResult"
                        >
                            {{ t("game.ui.extensions.OpenRouterModal.create_note") }}
                        </button>
                    </div>
                </section>
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
.openrouter-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .openrouter-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
    }

    .openrouter-header-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .openrouter-btn,
    .openrouter-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.openrouter-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 1rem;
}

.openrouter-tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;

    button {
        padding: 0.5rem 1rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        background: #fff;
        cursor: pointer;

        &.active {
            background: #82c8a0;
            border-color: #82c8a0;
            color: #333;
        }
    }
}

.openrouter-settings {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.openrouter-hint {
    font-size: 0.9em;
    color: #666;
    margin: 0;
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

.openrouter-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;

    label {
        font-weight: 500;
    }

    input,
    select,
    textarea {
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
    }

    textarea {
        resize: vertical;
    }
}

.openrouter-save-btn {
    align-self: flex-start;
    padding: 0.5rem 1.5rem;
    background: #82c8a0;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;

    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
}

.openrouter-tasks {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: row;
    gap: 1.5rem;
    overflow: hidden;
}

.openrouter-params-section {
    flex: 1;
    min-width: 220px;
    max-width: 320px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
}

.openrouter-result-section {
    flex: 1;
    min-width: 200px;
    display: flex;
    flex-direction: column;
    overflow: hidden;

    h3 {
        margin: 0 0 0.75rem;
        font-weight: 600;
        font-size: 1.1em;
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
    color: #888;
    font-style: italic;
}

.openrouter-result-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-height: 0;
    overflow: hidden;
}

.openrouter-create-note-btn {
    align-self: flex-start;
    padding: 0.5rem 1rem;
    background: #82c8a0;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;
    flex-shrink: 0;

    &:hover {
        opacity: 0.9;
    }
}

.openrouter-tasks-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;

    .openrouter-tasks-title {
        font-weight: 500;
    }
}

.openrouter-save-btn-small {
    padding: 0.35rem 0.75rem;
    font-size: 0.9em;
    background: #82c8a0;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;

    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
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

    h4 {
        margin: 0.5rem 0 0;
        font-size: 0.9em;
    }

    input,
    textarea {
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
    }

    .openrouter-edit-actions {
        display: flex;
        gap: 0.5rem;
        margin-top: 0.5rem;
    }

    .openrouter-delete-btn {
        background: #e57373;
        color: white;
        border: none;
        padding: 0.4rem 0.8rem;
        border-radius: 0.25rem;
        cursor: pointer;
    }

    .openrouter-cancel-btn {
        background: #ccc;
        border: none;
        padding: 0.4rem 0.8rem;
        border-radius: 0.25rem;
        cursor: pointer;
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

.openrouter-run-btn {
    align-self: flex-start;
    padding: 0.5rem 1.5rem;
    background: #ff7052;
    color: white;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;

    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
}

.openrouter-result-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.75rem;
    border: 1px solid #eee;
    border-radius: 0.25rem;
    background: #fafafa;
    white-space: pre-wrap;
    font-size: 0.95em;
}
</style>
