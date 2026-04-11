<template>
    <div class="grouped-single-select">
        <label v-if="label" class="ga-label">{{ label }}</label>
        <div ref="containerRef" class="ga-control-wrapper">
            <div
                class="ga-control"
                :class="{ 'is-open': isOpen, 'is-disabled': disabled }"
                @click="!disabled && handleControlClick()"
            >
                <template v-if="!isOpen && hasDisplayTitle">
                    <span class="ga-single-value" :title="String(displayTitle)">{{ displayTitle }}</span>
                </template>
                <input
                    v-show="isOpen || !hasDisplayTitle"
                    ref="inputRef"
                    v-model="query"
                    type="text"
                    class="ga-input"
                    :disabled="disabled"
                    :placeholder="inputPlaceholder"
                    @focus="onInputFocus"
                    @keydown="handleKeyDown"
                />
            </div>
            <div class="ga-icons">
                <button
                    v-if="clearable && modelValue != null && modelValue !== '' && !disabled"
                    type="button"
                    class="ga-icon-btn ga-clear"
                    :title="clearTitle"
                    @click.stop="clearSelection"
                >
                    <font-awesome-icon icon="circle-xmark" />
                </button>
                <span class="ga-icon-btn ga-chevron" :class="{ 'is-open': isOpen, 'is-disabled': disabled }" @click.stop="toggleOpen">
                    <font-awesome-icon icon="chevron-down" />
                </span>
            </div>

            <div v-show="isOpen && !disabled" ref="listRef" class="ga-dropdown">
                <div v-if="groupedOptions.length === 0" class="ga-empty">
                    {{ noResultsText }}
                </div>
                <div v-else>
                    <div v-for="[groupName, items] in groupedOptions" :key="groupName" class="ga-group">
                        <div class="ga-group-header">
                            {{ groupName }}
                            <span class="ga-group-count">{{ items.length }}</span>
                        </div>
                        <div
                            v-for="item in items"
                            :key="item.id"
                            class="ga-item"
                            :class="{
                                'is-active': flatFilteredOptions.indexOf(item) === activeIndex,
                                'is-selected': isChosen(item),
                            }"
                            :data-idx="flatFilteredOptions.indexOf(item)"
                            @mousedown.prevent="choose(item)"
                            @mouseenter="activeIndex = flatFilteredOptions.indexOf(item)"
                        >
                            <div class="ga-item-radio" :class="{ 'is-on': isChosen(item) }" />
                            <span class="ga-item-title">{{ item.title }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";

export interface SingleSelectOption {
    id: string | number;
    title: string;
    category: string;
}

const props = withDefaults(
    defineProps<{
        options: SingleSelectOption[];
        modelValue: string | number | null;
        label?: string;
        /** Testo quando non c’è selezione e il controllo è attivo */
        placeholder?: string;
        /** Testo quando disabilitato o lista vuota (es. “Caricamento…”) */
        emptyLabel?: string;
        noResultsText?: string;
        clearTitle?: string;
        disabled?: boolean;
        clearable?: boolean;
        groupBy?: (item: SingleSelectOption) => string;
    }>(),
    {
        label: "",
        placeholder: "Cerca…",
        emptyLabel: "",
        noResultsText: "Nessun risultato",
        clearTitle: "Deseleziona",
        disabled: false,
        clearable: true,
        groupBy: (item: SingleSelectOption) => item.category,
    },
);

const emit = defineEmits<{ "update:modelValue": [value: string | number | null] }>();

const query = ref("");
const isOpen = ref(false);
const activeIndex = ref(-1);
const containerRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);
const listRef = ref<HTMLElement | null>(null);

const selectedOption = computed(() =>
    props.options.find((o) => String(o.id) === String(props.modelValue)),
);

const displayTitle = computed(() => selectedOption.value?.title ?? "");

const hasDisplayTitle = computed(
    () =>
        !props.disabled &&
        props.modelValue != null &&
        props.modelValue !== "" &&
        displayTitle.value !== "",
);

const inputPlaceholder = computed(() => {
    if (props.disabled || props.options.length === 0) return props.emptyLabel || props.placeholder;
    if (hasDisplayTitle.value && !isOpen.value) return "";
    return props.placeholder;
});

const filteredOptions = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return props.options;
    return props.options.filter((o) => o.title.toLowerCase().includes(q));
});

const groupedOptions = computed(() => {
    const groups: Record<string, SingleSelectOption[]> = {};
    for (const item of filteredOptions.value) {
        const groupKey = props.groupBy!(item);
        if (!groups[groupKey]) groups[groupKey] = [];
        groups[groupKey].push(item);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
});

const flatFilteredOptions = computed(() => groupedOptions.value.flatMap(([, items]) => items));

function isChosen(item: SingleSelectOption): boolean {
    return String(props.modelValue) === String(item.id);
}

function choose(item: SingleSelectOption): void {
    emit("update:modelValue", item.id);
    query.value = "";
    isOpen.value = false;
    activeIndex.value = -1;
}

function clearSelection(): void {
    emit("update:modelValue", null);
    query.value = "";
}

function toggleOpen(): void {
    if (props.disabled) return;
    isOpen.value = !isOpen.value;
    if (isOpen.value) {
        query.value = "";
        activeIndex.value = -1;
        void nextTickFocus();
    }
}

function nextTickFocus(): void {
    requestAnimationFrame(() => inputRef.value?.focus());
}

function handleControlClick(): void {
    if (props.disabled) return;
    if (!isOpen.value) {
        isOpen.value = true;
        query.value = "";
        activeIndex.value = -1;
        nextTickFocus();
    }
}

function onInputFocus(): void {
    if (props.disabled) return;
    isOpen.value = true;
}

function handleKeyDown(e: KeyboardEvent): void {
    if (props.disabled) return;
    if (!isOpen.value) {
        if (e.key === "ArrowDown" || e.key === "Enter") {
            isOpen.value = true;
        }
        return;
    }
    if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex.value = Math.min(activeIndex.value + 1, flatFilteredOptions.value.length - 1);
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex.value = Math.max(activeIndex.value - 1, 0);
    } else if (e.key === "Enter" && activeIndex.value >= 0) {
        const item = flatFilteredOptions.value[activeIndex.value];
        if (item) choose(item);
    } else if (e.key === "Escape") {
        isOpen.value = false;
        query.value = "";
        activeIndex.value = -1;
    }
}

function handleClickOutside(e: MouseEvent): void {
    if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
        isOpen.value = false;
        query.value = "";
        activeIndex.value = -1;
    }
}

onMounted(() => document.addEventListener("mousedown", handleClickOutside));
onUnmounted(() => document.removeEventListener("mousedown", handleClickOutside));

watch(activeIndex, (newIdx) => {
    if (newIdx >= 0 && listRef.value) {
        const el = listRef.value.querySelector(`[data-idx="${newIdx}"]`);
        el?.scrollIntoView({ block: "nearest" });
    }
});

watch(
    () => props.modelValue,
    () => {
        if (!isOpen.value) query.value = "";
    },
);
</script>

<style scoped lang="scss">
.grouped-single-select {
    width: 100%;
}

.ga-label {
    display: block;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 8px;
}

.ga-control-wrapper {
    position: relative;
    width: 100%;
}

.ga-control {
    padding: 6px 44px 6px 10px;
    min-height: 36px;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: text;
    display: flex;
    align-items: center;
    transition: border-color 0.15s, box-shadow 0.15s;

    &.is-open {
        border-color: #999;
        box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.04);
    }

    &.is-disabled {
        background: #f5f5f5;
        cursor: not-allowed;
        opacity: 0.85;
    }
}

.ga-single-value {
    flex: 1;
    font-size: 14px;
    color: #333;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 2px 0;
}

.ga-input {
    flex: 1;
    width: 100%;
    min-width: 0;
    border: none !important;
    outline: none !important;
    background: transparent !important;
    font-size: 14px;
    color: #333;
    padding: 2px 0;
    box-shadow: none !important;
}

.ga-icons {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    gap: 4px;
}

.ga-icon-btn {
    background: none;
    border: none;
    padding: 4px;
    color: #888;
    cursor: pointer;
    border-radius: 4px;
    display: flex;
    align-items: center;

    &:hover:not(.is-disabled) {
        color: #555;
    }

    &.ga-chevron {
        transition: transform 0.2s ease;
        &.is-open {
            transform: rotate(180deg);
        }
        &.is-disabled {
            cursor: not-allowed;
            opacity: 0.5;
        }
    }
}

.ga-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    max-height: 280px;
    overflow-y: auto;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    z-index: 200;

    .ga-empty {
        padding: 20px 16px;
        text-align: center;
        font-size: 13px;
        color: #888;
    }
}

.ga-group-header {
    position: sticky;
    top: 0;
    padding: 7px 14px 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #666;
    background: #fcfcfc;
    border-bottom: 1px solid #f0f0f0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 6px;

    .ga-group-count {
        font-size: 9px;
        background: #eeeeee;
        color: #555;
        border-radius: 10px;
        padding: 1px 6px;
        font-weight: 500;
    }
}

.ga-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    cursor: pointer;
    transition: background 0.1s;

    &:hover,
    &.is-active {
        background: #f5f5f5;
    }

    &.is-selected .ga-item-title {
        font-weight: 600;
        color: #2e7d32;
    }

    .ga-item-radio {
        width: 14px;
        height: 14px;
        flex-shrink: 0;
        border-radius: 50%;
        border: 2px solid #bbb;
        transition: border-color 0.15s, background 0.15s;

        &.is-on {
            border-color: #2e7d32;
            background: radial-gradient(circle at center, #2e7d32 45%, transparent 46%);
        }
    }

    .ga-item-title {
        flex: 1;
        font-size: 13.5px;
        color: #333;
    }
}
</style>
