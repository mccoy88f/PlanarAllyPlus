<template>
    <div class="grouped-autocomplete-container">
        <!-- Label -->
        <label v-if="label" class="ga-label">{{ label }}</label>

        <!-- Main Input Container -->
        <div ref="containerRef" class="ga-control-wrapper">
            <div
                class="ga-control"
                :class="{ 'is-open': isOpen }"
                @click="handleOpen"
            >
                <!-- Selected Chips -->
                <div class="ga-chips">
                    <span
                        v-for="item in selectedItems"
                        :key="item.id"
                        class="ga-chip"
                    >
                        <span class="ga-chip-badge">{{ (props.groupBy?.(item) || " ")[0].toUpperCase() }}</span>

                        <span class="ga-chip-text">{{ item.title }}</span>
                        <button class="ga-chip-remove" @click="removeTag(item, $event)">
                            <font-awesome-icon icon="circle-xmark" size="xs" />
                        </button>
                    </span>

                    <!-- Search Input inside layout row -->
                    <input
                        ref="inputRef"
                        v-model="query"
                        type="text"
                        class="ga-input"
                        :placeholder="modelValue.length === 0 ? placeholder : ''"
                        @focus="isOpen = true"
                        @keydown="handleKeyDown"
                    />
                </div>
            </div>

            <!-- Side Icons / Clear buttons -->
            <div class="ga-icons">
                <button
                    v-if="modelValue.length > 0"
                    class="ga-icon-btn ga-clear"
                    title="Deseleziona tutto"
                    @click="clearAll"
                >
                    <font-awesome-icon icon="circle-xmark" />
                </button>
                <span class="ga-icon-btn ga-chevron" :class="{ 'is-open': isOpen }" @click="isOpen = !isOpen">
                    <font-awesome-icon icon="chevron-down" />
                </span>
            </div>

            <!-- Floating Dropdown menu -->
            <div v-show="isOpen" ref="listRef" class="ga-dropdown">
                <div v-if="groupedOptions.length === 0" class="ga-empty">
                    Nessun risultato per "{{ query }}"
                </div>
                <div v-else>
                    <!-- Group loops -->
                    <div v-for="[groupName, items] in groupedOptions" :key="groupName" class="ga-group">
                        <div class="ga-group-header">
                            {{ groupName }}
                            <span class="ga-group-count">{{ items.length }}</span>
                        </div>

                        <!-- Item row loop -->
                        <div
                            v-for="item in items"
                            :key="item.id"
                            class="ga-item"
                            :class="{ 'is-active': flatFilteredOptions.indexOf(item) === activeIndex, 'is-selected': isSelected(item) }"
                            :data-idx="flatFilteredOptions.indexOf(item)"
                            @mousedown.prevent="toggle(item)"
                            @mouseenter="activeIndex = flatFilteredOptions.indexOf(item)"
                        >

                            <!-- Checkbox design -->
                            <div class="ga-item-checkbox" :class="{ 'is-checked': isSelected(item) }">
                                <font-awesome-icon v-if="isSelected(item)" icon="check" size="xs" />
                            </div>
                            <span class="ga-item-title">{{ item.title }}</span>
                        </div>
                    </div>
                </div>

                <!-- Footer summarizing selection count -->
                <div v-if="modelValue.length > 0" class="ga-footer">
                    <span class="ga-footer-count">{{ modelValue.length }} selezionat{{ modelValue.length === 1 ? 'o' : 'i' }}</span>
                    <button class="ga-footer-clear" @mousedown.prevent="clearAll">Deseleziona tutto</button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";

export interface AutocompleteOption {
    id: string | number;
    title: string;
    [key: string]: any; // Allow custom grouping keys
}

const props = withDefaults(
    defineProps<{
        options: AutocompleteOption[];
        modelValue: (string | number)[];
        label?: string;
        placeholder?: string;
        groupBy: (item: AutocompleteOption) => string;
    }>(),

    {
        label: "",
        placeholder: "Cerca...",
        groupBy: (item: AutocompleteOption) => item.category || "Altro",
    }
);

const emit = defineEmits(["update:modelValue"]);

const query = ref("");
const isOpen = ref(false);
const activeIndex = ref(-1);

const containerRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);
const listRef = ref<HTMLElement | null>(null);

const filteredOptions = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return props.options;
    return props.options.filter(o => 
        o.title.toLowerCase().includes(q)
    );
});

// Grouped structure: Array of [groupName, items[]]
const groupedOptions = computed(() => {
    const groups: Record<string, AutocompleteOption[]> = {};
    for (const item of filteredOptions.value) {
        const groupKey = props.groupBy(item);
        if (!groups[groupKey]) groups[groupKey] = [];

        groups[groupKey].push(item);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
});

// Flat list for keyboard navigation index mapping
const flatFilteredOptions = computed(() => {
    return groupedOptions.value.flatMap(([, items]) => items);
});

function isSelected(item: AutocompleteOption): boolean {
    return props.modelValue.includes(item.id);
}

function toggle(item: AutocompleteOption): void {
    const selected = [...props.modelValue];
    const idx = selected.indexOf(item.id);
    if (idx >= 0) {
        selected.splice(idx, 1);
    } else {
        selected.push(item.id);
    }
    emit("update:modelValue", selected);
}

function removeTag(item: AutocompleteOption, e: Event): void {
    e.stopPropagation();
    const selected = props.modelValue.filter(id => id !== item.id);
    emit("update:modelValue", selected);
}

function clearAll(e: Event): void {
    e.stopPropagation();
    emit("update:modelValue", []);
}

function handleOpen(): void {
    isOpen.value = true;
    inputRef.value?.focus();
}

function handleKeyDown(e: KeyboardEvent): void {
    if (!isOpen.value) {
        if (e.key === "ArrowDown" || e.key === "Enter") isOpen.value = true;
        return;
    }
    if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex.value = Math.min(activeIndex.value + 1, flatFilteredOptions.value.length - 1);
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex.value = Math.max(activeIndex.value - 1, 0);
    } else if (e.key === "Enter" && activeIndex.value >= 0) {
        toggle(flatFilteredOptions.value[activeIndex.value]);
    } else if (e.key === "Escape") {
        isOpen.value = false;
        query.value = "";
    } else if (e.key === "Backspace" && query.value === "" && props.modelValue.length > 0) {
        const lastId = props.modelValue[props.modelValue.length - 1];
        const lastItem = props.options.find(o => o.id === lastId);
        if (lastItem) toggle(lastItem);
    }

}

function handleClickOutside(e: MouseEvent): void {
    if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
        isOpen.value = false;
        query.value = "";
        activeIndex.value = -1;
    }
}

onMounted(() => {
    document.addEventListener("mousedown", handleClickOutside);
});
onUnmounted(() => {
    document.removeEventListener("mousedown", handleClickOutside);
});

watch(activeIndex, (newIdx) => {
    if (newIdx >= 0 && listRef.value) {
        const el = listRef.value.querySelector(`[data-idx="${newIdx}"]`);
        el?.scrollIntoView({ block: "nearest" });
    }
});

const selectedItems = computed(() => {
    // preserve selection order
    return props.modelValue.map(id => props.options.find(o => o.id === id)).filter(Boolean) as AutocompleteOption[];
});
</script>

<style scoped lang="scss">
.grouped-autocomplete-container {
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
    padding: 4px 44px 4px 10px;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: text;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    transition: border-color 0.15s, box-shadow 0.15s;

    &.is-open {
        border-color: #999;
        box-shadow: 0 0 0 3px rgba(0,0,0,0.04);
    }
}


.ga-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    flex: 1;
}

.ga-chip {
    display: inline-flex;
    align-items: center;
    background: #f1f1f1;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    font-size: 13px;
    overflow: hidden;
    max-width: 220px;
    white-space: nowrap;

    .ga-chip-badge {
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 22px;
        height: 24px;
        background: #444;
        color: #fff;
        font-size: 10px;
        font-weight: 600;
        padding: 0 6px;
        flex-shrink: 0;
    }

    .ga-chip-text {
        padding: 0 5px 0 7px;
        color: #333;
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 12px;
    }

    .ga-chip-remove {
        display: flex;
        align-items: center;
        justify-content: center;
        background: none;
        border: none;
        padding: 0 6px 0 1px;
        cursor: pointer;
        color: #888;
        height: 24px;

        &:hover { color: #555; }
    }
}

.ga-input {
    flex: 1;
    min-width: 80px;
    border: none !important;
    outline: none !important;
    background: transparent !important;
    font-size: 14px;
    color: #333;
    padding: 4px 0;
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

    &:hover { color: #555; }

    &.ga-chevron {
        transition: transform 0.2s ease;
        &.is-open { transform: rotate(180deg); }
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
    box-shadow: 0 8px 24px rgba(0,0,0,0.12);
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

    &:hover, &.is-active {
        background: #f5f5f5;
    }

    &.is-selected {
        .ga-item-title {
            font-weight: 600;
            color: #2e7d32;
        }
    }

    .ga-item-checkbox {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
        border-radius: 4px;
        border: 1.5px solid #ccc;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.15s;
        color: #fff;

        &.is-checked {
            background: #4caf50;
            border-color: #4caf50;
        }
    }

    .ga-item-title {
        flex: 1;
        font-size: 13.5px;
        color: #333;
    }
}

.ga-footer {
    position: sticky;
    bottom: 0;
    z-index: 2;
    border-top: 1px solid #eee;
    padding: 9px 14px;
    background: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .ga-footer-count {
        font-size: 12px;
        font-weight: 500;
        color: #555;
    }

    .ga-footer-clear {
        font-size: 12px;
        font-weight: 500;
        color: #444;
        background: #f5f5f5;
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 4px 12px;
        cursor: pointer;

        &:hover { background: #eeeeee; }
    }
}
</style>
