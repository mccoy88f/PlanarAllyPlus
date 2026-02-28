<script setup lang="ts" generic="T">
import ToggleGroup from "./ToggleGroup.vue";

defineProps<{
    options: readonly { label: string; value: T }[];
    modelValue: T;
}>();

const emit = defineEmits<{
    "update:modelValue": [T];
}>();
</script>

<template>
    <div class="header-mode-selector">
        <ToggleGroup
            :options="options"
            :model-value="modelValue"
            :multi-select="false"
            active-color="#ff7052"
            color="rgba(0, 0, 0, 0.05)"
            class="mode-toggle-group"
            @update:model-value="emit('update:modelValue', $event)"
        />
    </div>
</template>

<style scoped lang="scss">
.header-mode-selector {
    display: flex;
    justify-content: center;
    padding: 0.75rem 0;
    border-bottom: 1px solid #eee;
    background-color: #fafafa;
}

:deep(.mode-toggle-group) {
    border-radius: 2rem;
    border: none;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.05);

    > div {
        padding: 0.4rem 1.5rem;
        font-weight: 600;
        font-size: 0.9rem;
        transition: all 0.2s ease;
        border-radius: 2rem;
        color: #666;

        &:hover {
            color: white;
        }

        &.selected {
            color: white;
            box-shadow: 0 2px 8px rgba(255, 112, 82, 0.4);
        }
    }
}
</style>
