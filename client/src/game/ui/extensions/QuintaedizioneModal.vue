<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";
import VueMarkdown from "vue-markdown-render";

import { uuidv4 } from "../../../core/utils";
import Modal from "../../../core/components/modals/Modal.vue";
import { http } from "../../../core/http";
import { chatSystem } from "../../systems/chat";
import { extensionsState } from "../../systems/extensions/state";
import { playerSystem } from "../../systems/players";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

interface DbItem {
    slug: string;
    name: string;
    markdown: string;
}

interface DbCollection {
    slug: string;
    name: string;
    count: number;
    items: DbItem[];
}

interface DbData {
    collections: DbCollection[];
}

const loading = ref(true);
const dbData = ref<DbData | null>(null);
const searchQuery = ref("");
const debouncedSearchQuery = ref("");
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
const expandedCollections = ref<Set<string>>(new Set());
const selectedItem = ref<{ collection: DbCollection; item: DbItem } | null>(null);
const modalRef = ref<{ container: HTMLDivElement } | null>(null);

const collections = computed(() => dbData.value?.collections ?? []);

const searchResults = computed(() => {
    const q = debouncedSearchQuery.value.trim().toLowerCase();
    if (!q || !dbData.value) return [];

    const results: { collection: DbCollection; item: DbItem }[] = [];
    for (const coll of dbData.value.collections) {
        for (const item of coll.items) {
            const searchable = `${item.name} ${item.markdown}`.toLowerCase();
            if (searchable.includes(q)) {
                results.push({ collection: coll, item });
            }
        }
    }
    return results;
});

const breadcrumb = computed(() => {
    if (!selectedItem.value) return [];
    const { collection, item } = selectedItem.value;
    return [
        { label: collection.name, slug: collection.slug },
        { label: item.name, slug: item.slug },
    ];
});

const selectedMarkdown = computed(() => selectedItem.value?.item.markdown ?? "");

const isSearchDebouncing = computed(
    () =>
        searchQuery.value.trim().length > 0 &&
        debouncedSearchQuery.value !== searchQuery.value.trim(),
);

function toggleCollection(slug: string): void {
    const next = new Set(expandedCollections.value);
    if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    expandedCollections.value = next;
}

function selectItem(collection: DbCollection, item: DbItem): void {
    selectedItem.value = { collection, item };
}

function selectFromSearch(result: { collection: DbCollection; item: DbItem }): void {
    expandedCollections.value = new Set([...expandedCollections.value, result.collection.slug]);
    selectedItem.value = result;
    searchQuery.value = "";
    debouncedSearchQuery.value = "";
}

function formatCollectionName(name: string): string {
    return name.charAt(0).toUpperCase() + name.slice(1);
}


async function loadDb(): Promise<void> {
    loading.value = true;
    try {
        const response = await http.get("/api/extensions/quintaedizione.online/db");
        if (response.ok) {
            const data = (await response.json()) as DbData;
            dbData.value = data;
            const openItem = extensionsState.raw.quintaedizioneOpenItem;
            if (openItem) {
                const coll = data.collections.find((c) => c.slug === openItem.collectionSlug);
                const item = coll?.items.find((i) => i.slug === openItem.itemSlug);
                if (coll && item) {
                    expandedCollections.value = new Set([coll.slug]);
                    selectedItem.value = { collection: coll, item };
                }
                extensionsState.mutableReactive.quintaedizioneOpenItem = undefined;
            } else if (data.collections.length > 0) {
                expandedCollections.value = new Set([data.collections[0]!.slug]);
            }
        } else {
            dbData.value = { collections: [] };
        }
    } catch {
        dbData.value = { collections: [] };
    } finally {
        loading.value = false;
    }
}

function shareToChat(): void {
    if (!selectedItem.value) return;
    const { collection, item } = selectedItem.value;
    const label = `${item.name} (${formatCollectionName(collection.name)})`;
    const link = `[📖 ${label}](qe:${collection.slug}/${item.slug})`;
    chatSystem.addMessage(
        uuidv4(),
        playerSystem.getCurrentPlayer()?.name ?? "?",
        [link],
        true,
    );
    toast.success(t("game.ui.extensions.QuintaedizioneModal.share_success"));
}

watch(
    () => props.visible,
    (visible) => {
        if (visible) loadDb();
    },
);

watch(searchQuery, (newVal) => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const trimmed = newVal.trim();
    if (trimmed === "") {
        debouncedSearchQuery.value = "";
        return;
    }
    searchDebounceTimer = setTimeout(() => {
        debouncedSearchQuery.value = trimmed;
        searchDebounceTimer = null;
    }, 1000);
});

onMounted(() => {
    if (props.visible) loadDb();
});
</script>

<template>
    <Modal
        v-if="visible"
        ref="modalRef"
        :visible="visible"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="quintaedizione-modal"
        @close="onClose"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="qe-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="qe-title">{{ t("game.ui.extensions.QuintaedizioneModal.title") }}</h2>
                <div class="qe-header-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="qe-header-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="qe-header-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="qe-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="onClose"
                    />
                </div>
            </div>
        </template>
        <div class="qe-body">
            <div class="qe-search-bar">
                <font-awesome-icon icon="search" class="qe-search-icon" />
                <input
                    v-model="searchQuery"
                    type="text"
                    class="qe-search-input"
                    :placeholder="t('game.ui.extensions.QuintaedizioneModal.search_placeholder')"
                />
            </div>

            <div v-if="loading" class="qe-loading">
                {{ t("game.ui.extensions.QuintaedizioneModal.loading") }}
            </div>

            <div v-else-if="searchQuery.trim()" class="qe-search-results">
                <div
                    v-if="isSearchDebouncing"
                    class="qe-search-empty"
                >
                    {{ t("game.ui.extensions.QuintaedizioneModal.searching") }}
                </div>
                <template v-else>
                    <div
                        v-for="(result, idx) in searchResults"
                        :key="`${result.collection.slug}-${result.item.slug}-${idx}`"
                        class="qe-search-result-item"
                        @click="selectFromSearch(result)"
                    >
                        <span class="qe-search-category">{{ formatCollectionName(result.collection.name) }}</span>
                        <span class="qe-search-name">{{ result.item.name }}</span>
                    </div>
                    <div v-if="searchResults.length === 0" class="qe-search-empty">
                        {{ t("game.ui.extensions.QuintaedizioneModal.no_results") }}
                    </div>
                </template>
            </div>

            <div v-else-if="!loading" class="qe-main">
                <nav class="qe-tree">
                    <div
                        v-for="coll in collections"
                        :key="coll.slug"
                        class="qe-tree-collection"
                    >
                        <button
                            class="qe-tree-toggle"
                            :class="{ expanded: expandedCollections.has(coll.slug) }"
                            @click="toggleCollection(coll.slug)"
                        >
                            <font-awesome-icon :icon="expandedCollections.has(coll.slug) ? 'chevron-down' : 'chevron-right'" />
                            {{ formatCollectionName(coll.name) }}
                            <span class="qe-tree-count">({{ coll.count }})</span>
                        </button>
                        <div
                            v-show="expandedCollections.has(coll.slug)"
                            class="qe-tree-items"
                        >
                            <button
                                v-for="item in coll.items"
                                :key="item.slug"
                                class="qe-tree-item"
                                :class="{ active: selectedItem?.collection.slug === coll.slug && selectedItem?.item.slug === item.slug }"
                                @click="selectItem(coll, item)"
                            >
                                {{ item.name }}
                            </button>
                        </div>
                    </div>
                </nav>
                <div class="qe-content-area">
                    <div v-if="selectedItem" class="qe-breadcrumb">
                        <div class="qe-breadcrumb-path">
                            <template v-for="(crumb, i) in breadcrumb" :key="crumb.slug">
                                <span v-if="i > 0" class="qe-breadcrumb-sep"> › </span>
                                <span class="qe-breadcrumb-item">{{ crumb.label }}</span>
                            </template>
                        </div>
                        <button
                            class="qe-share-btn"
                            :title="t('game.ui.extensions.QuintaedizioneModal.share_to_chat')"
                            @click="shareToChat"
                        >
                            <font-awesome-icon icon="share-alt" />
                            {{ t("game.ui.extensions.QuintaedizioneModal.share") }}
                        </button>
                    </div>
                    <div v-if="selectedItem" class="qe-markdown">
                        <VueMarkdown :source="selectedMarkdown" />
                    </div>
                    <div v-else class="qe-empty">
                        {{ t("game.ui.extensions.QuintaedizioneModal.select_item") }}
                    </div>
                </div>
            </div>
        </div>
    </Modal>
</template>

<style lang="scss">
.quintaedizione-modal {
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    resize: both;
    width: 800px;
    height: 600px;
    min-width: 500px;
    min-height: 400px;
    max-width: min(100vw, 1200px);
    max-height: min(100vh, 900px);
    overflow: hidden;
}
</style>

<style lang="scss" scoped>
.qe-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .qe-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
    }

    .qe-header-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .qe-header-btn,
    .qe-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.qe-body {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.qe-search-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: #f5f5f5;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;

    .qe-search-icon {
        color: #666;
        flex-shrink: 0;
    }

    .qe-search-input {
        flex: 1;
        padding: 0.4rem 0.6rem;
        border: 1px solid #ddd;
        border-radius: 0.25rem;
        font-size: 0.95rem;

        &:focus {
            outline: none;
            border-color: #888;
        }
    }
}

.qe-loading {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    font-style: italic;
}

.qe-search-results {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem 1rem;

    .qe-search-result-item {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        padding: 0.5rem 0.75rem;
        cursor: pointer;
        border-radius: 0.25rem;
        border: 1px solid transparent;

        &:hover {
            background: #f0f0f0;
            border-color: #ddd;
        }

        .qe-search-category {
            font-size: 0.75rem;
            color: #666;
            text-transform: capitalize;
        }

        .qe-search-name {
            font-weight: 500;
        }
    }

    .qe-search-empty {
        padding: 1rem;
        color: #666;
        font-style: italic;
    }
}

.qe-main {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.qe-tree {
    width: 220px;
    flex-shrink: 0;
    border-right: 1px solid #eee;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    padding: 0.5rem 0;

    .qe-tree-collection {
        margin-bottom: 0.25rem;
    }

    .qe-tree-toggle {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        width: 100%;
        padding: 0.4rem 0.75rem;
        border: none;
        background: transparent;
        cursor: pointer;
        text-align: left;
        font-size: 0.9rem;

        &:hover {
            background: #f0f0f0;
        }

        .qe-tree-count {
            font-size: 0.8rem;
            color: #888;
            margin-left: auto;
        }
    }

    .qe-tree-items {
        padding-left: 1.25rem;
    }

    .qe-tree-item {
        display: block;
        width: 100%;
        padding: 0.35rem 0.75rem;
        border: none;
        background: transparent;
        cursor: pointer;
        text-align: left;
        font-size: 0.85rem;
        border-radius: 0.2rem;

        &:hover {
            background: #f0f0f0;
        }

        &.active {
            background: #e0e8f0;
            font-weight: 500;
        }
    }
}

.qe-content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
}

.qe-breadcrumb {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.5rem 1rem;
    background: #fafafa;
    border-bottom: 1px solid #eee;
    font-size: 0.85rem;
    color: #555;

    .qe-breadcrumb-path {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .qe-breadcrumb-sep {
        color: #999;
    }

    .qe-breadcrumb-item {
        text-transform: capitalize;
    }

    .qe-share-btn {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        flex-shrink: 0;
        padding: 0.35rem 0.6rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        background: #fff;
        cursor: pointer;
        font-size: 0.8rem;

        &:hover {
            background: #f0f0f0;
            border-color: #999;
        }
    }
}

.qe-markdown {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem 1.5rem;
    font-size: 0.9rem;
    line-height: 1.5;

    :deep(h1) {
        font-size: 1.4rem;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }

    :deep(h2) {
        font-size: 1.2rem;
        margin-top: 0.9rem;
        margin-bottom: 0.4rem;
    }

    :deep(h3) {
        font-size: 1.05rem;
        margin-top: 0.7rem;
        margin-bottom: 0.3rem;
    }

    :deep(table) {
        border-collapse: collapse;
        width: 100%;
        margin: 0.5rem 0;

        th,
        td {
            border: 1px solid #ddd;
            padding: 0.35rem 0.6rem;
            text-align: left;
        }

        th {
            background: #f5f5f5;
            font-weight: 600;
        }
    }

    :deep(p) {
        margin: 0.4rem 0;
    }

    :deep(ul),
    :deep(ol) {
        margin: 0.4rem 0;
        padding-left: 1.5rem;
    }
}

.qe-empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #888;
    font-style: italic;
}
</style>
