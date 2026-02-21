<script setup lang="ts">
const props = defineProps<{
    /** A value between 0 and 100 */
    progress: number;
    /** Optional label displayed next to or above the bar */
    label?: string;
    /** If true, the bar animates even when not progressing, indicating it's processing */
    indeterminate?: boolean;
    /** Allows customization of the bar height (e.g., '12px') */
    height?: string;
}>();
</script>

<template>
    <div class="pa-loading-bar-wrapper">
        <label v-if="label" class="pa-loading-bar-label">{{ label }}</label>
        <div class="pa-loading-bar-track" :style="{ height: height || '8px' }">
            <div
                class="pa-loading-bar-fill"
                :class="{ 'pa-loading-bar-indeterminate': indeterminate }"
                :style="{ width: indeterminate ? '100%' : `${Math.min(100, Math.max(0, progress))}%` }"
            ></div>
        </div>
        <div v-if="!indeterminate" class="pa-loading-bar-text">
            {{ Math.round(progress) }}%
        </div>
    </div>
</template>

<style scoped>
.pa-loading-bar-wrapper {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
}

.pa-loading-bar-label {
    font-size: 0.9em;
    font-weight: 500;
}

.pa-loading-bar-track {
    width: 100%;
    background-color: var(--primary-bg, #2c3e50);
    border-radius: 4px;
    overflow: hidden;
    position: relative;
    border: 1px solid var(--primary-border, #455a64);
}

.pa-loading-bar-fill {
    height: 100%;
    background-color: var(--primary-accent, #42b983);
    border-radius: 4px;
    transition: width 0.3s ease-out;
}

.pa-loading-bar-indeterminate {
    background: linear-gradient(
        90deg,
        var(--primary-accent, #42b983) 25%,
        rgba(255, 255, 255, 0.4) 50%,
        var(--primary-accent, #42b983) 75%
    );
    background-size: 200% 100%;
    animation: loading-bar-stripes 1.5s linear infinite;
}

.pa-loading-bar-text {
    font-size: 0.8em;
    align-self: flex-end;
    color: var(--primary-text, #ffffff);
}

@keyframes loading-bar-stripes {
    0% {
        background-position: 200% 0;
    }
    100% {
        background-position: -200% 0;
    }
}
</style>
