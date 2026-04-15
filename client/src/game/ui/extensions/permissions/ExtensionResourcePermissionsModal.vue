<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import Modal from "../../../../core/components/modals/Modal.vue";
import { useModal } from "../../../../core/plugins/modals/plugin";
import { playerState } from "../../../systems/players/state";

import type { ExtensionResourceAcl, ExtensionResourceGrant } from "./extensionResourceAcl";
import { defaultExtensionResourceAcl, normalizeResourceAcl } from "./extensionResourceAcl";

const props = defineProps<{
    visible: boolean;
    /** Utente proprietario della risorsa; ha sempre view+edit (non legato alla campagna). */
    creatorName: string;
    acl: ExtensionResourceAcl;
    readOnly?: boolean;
}>();

const emit = defineEmits<{
    (e: "update:visible", v: boolean): void;
    (e: "update:acl", v: ExtensionResourceAcl): void;
    (e: "apply", v: ExtensionResourceAcl): void;
}>();

const { t } = useI18n();
const modals = useModal();

const draft = ref<ExtensionResourceAcl>(defaultExtensionResourceAcl(""));

watch(
    () => props.visible,
    (v) => {
        if (v) {
            draft.value = normalizeResourceAcl(JSON.parse(JSON.stringify(props.acl)));
        }
    },
);

watch(
    () => props.acl,
    () => {
        if (props.visible) {
            draft.value = normalizeResourceAcl(JSON.parse(JSON.stringify(props.acl)));
        }
    },
    { deep: true },
);

const roomPlayerNames = computed(() => {
    const names = new Set<string>();
    for (const p of playerState.raw.players.values()) {
        if (p.name !== draft.value.creatorName) {
            names.add(p.name);
        }
    }
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
});

const grantRows = computed(() => {
    const map = new Map<string, ExtensionResourceGrant>();
    for (const g of draft.value.grants) {
        map.set(g.userName, g);
    }
    const rows: ExtensionResourceGrant[] = [];
    for (const name of roomPlayerNames.value) {
        rows.push(map.get(name) ?? { userName: name, canView: false, canEdit: false });
    }
    for (const g of draft.value.grants) {
        if (!roomPlayerNames.value.includes(g.userName)) {
            rows.push(g);
        }
    }
    return rows;
});

function setPublicView(v: boolean): void {
    draft.value = { ...draft.value, publicView: v };
}

function setGrant(row: ExtensionResourceGrant, field: "canView" | "canEdit", value: boolean): void {
    const next = { ...row, [field]: value } as ExtensionResourceGrant;
    if (field === "canView" && !value) {
        next.canEdit = false;
    }
    if (next.canEdit) {
        next.canView = true;
    }
    const others = draft.value.grants.filter((g) => g.userName !== row.userName);
    draft.value = {
        ...draft.value,
        grants: [...others, next].filter((g) => g.canView || g.canEdit),
    };
}

async function addUsers(): Promise<void> {
    const taken = new Set(draft.value.grants.map((g) => g.userName));
    taken.add(draft.value.creatorName);
    const choices = roomPlayerNames.value.filter((n) => !taken.has(n));

    const extra = await modals.selectionBox(
        t("game.ui.extensions.resourcePermissions.add_user_title"),
        choices,
        { multiSelect: true },
    );
    if (extra === undefined) return;

    const merged = [...draft.value.grants];
    for (const name of extra) {
        if (!merged.some((g) => g.userName === name)) {
            merged.push({ userName: name, canView: true, canEdit: false });
        }
    }
    draft.value = { ...draft.value, grants: merged };
}

function removeGrant(userName: string): void {
    draft.value = {
        ...draft.value,
        grants: draft.value.grants.filter((g) => g.userName !== userName),
    };
}

function close(): void {
    emit("update:visible", false);
}

function apply(): void {
    const normalized = normalizeResourceAcl(draft.value);
    emit("update:acl", normalized);
    emit("apply", normalized);
    emit("update:visible", false);
}
</script>

<template>
    <teleport to="#teleport-modals">
        <Modal :visible="visible" :mask="true" @close="close">
            <template #header="m">
                <div class="modal-header" draggable="true" @dragstart="m.dragStart" @dragend="m.dragEnd">
                    {{ t("game.ui.extensions.resourcePermissions.title") }}
                    <div class="header-close" :title="t('common.close')" @click.stop="close">
                        <font-awesome-icon :icon="['far', 'window-close']" />
                    </div>
                </div>
            </template>
            <div class="modal-body ext-perm-body">
                <section class="ext-perm-section">
                    <h4>{{ t("game.ui.extensions.resourcePermissions.creator_section") }}</h4>
                    <p class="ext-perm-hint">{{ t("game.ui.extensions.resourcePermissions.creator_hint") }}</p>
                    <div class="ext-perm-creator-row">
                        <font-awesome-icon icon="user" />
                        <strong>{{ creatorName }}</strong>
                        <span class="ext-perm-badges">
                            <span class="ext-perm-badge">{{ t("game.ui.extensions.resourcePermissions.view") }}</span>
                            <span class="ext-perm-badge">{{ t("game.ui.extensions.resourcePermissions.edit") }}</span>
                        </span>
                    </div>
                </section>

                <section class="ext-perm-section">
                    <label class="ext-perm-row">
                        <input
                            type="checkbox"
                            class="styled-checkbox"
                            :checked="draft.publicView"
                            :disabled="readOnly"
                            @change="setPublicView(($event.target as HTMLInputElement).checked)"
                        />
                        <span>{{ t("game.ui.extensions.resourcePermissions.public_view") }}</span>
                    </label>
                    <p class="ext-perm-hint">{{ t("game.ui.extensions.resourcePermissions.public_view_hint") }}</p>
                </section>

                <section class="ext-perm-section">
                    <div class="ext-perm-toolbar">
                        <h4>{{ t("game.ui.extensions.resourcePermissions.users_section") }}</h4>
                        <button
                            v-if="!readOnly"
                            type="button"
                            class="styled-button"
                            @click="addUsers"
                        >
                            {{ t("game.ui.extensions.resourcePermissions.add_user") }}
                        </button>
                    </div>
                    <div class="ext-perm-table">
                        <div class="ext-perm-head">
                            <span>{{ t("game.ui.extensions.resourcePermissions.user") }}</span>
                            <span class="center">{{ t("game.ui.extensions.resourcePermissions.view") }}</span>
                            <span class="center">{{ t("game.ui.extensions.resourcePermissions.edit") }}</span>
                            <span class="center" />
                        </div>
                        <div v-for="row in grantRows" :key="row.userName" class="ext-perm-row">
                            <span>{{ row.userName }}</span>
                            <label class="center">
                                <input
                                    type="checkbox"
                                    class="styled-checkbox"
                                    :checked="row.canView || row.canEdit"
                                    :disabled="readOnly"
                                    @change="
                                        setGrant(row, 'canView', ($event.target as HTMLInputElement).checked)
                                    "
                                />
                            </label>
                            <label class="center">
                                <input
                                    type="checkbox"
                                    class="styled-checkbox"
                                    :checked="row.canEdit"
                                    :disabled="readOnly"
                                    @change="
                                        setGrant(row, 'canEdit', ($event.target as HTMLInputElement).checked)
                                    "
                                />
                            </label>
                            <label class="center">
                                <button
                                    v-if="!readOnly"
                                    type="button"
                                    class="icon-button"
                                    :title="t('game.ui.extensions.resourcePermissions.remove')"
                                    @click="removeGrant(row.userName)"
                                >
                                    <font-awesome-icon icon="times" />
                                </button>
                            </label>
                        </div>
                    </div>
                </section>

                <div v-if="!readOnly" class="ext-perm-actions">
                    <button type="button" class="styled-button" @click="close">
                        {{ t("common.cancel") }}
                    </button>
                    <button type="button" class="styled-button" @click="apply">
                        {{ t("common.save") }}
                    </button>
                </div>
            </div>
        </Modal>
    </teleport>
</template>

<style scoped lang="scss">
.ext-perm-body {
    min-width: 380px;
    max-width: 520px;
    max-height: 70vh;
    overflow: auto;
}

.ext-perm-section {
    margin-bottom: 1.25rem;
}

.ext-perm-section h4 {
    margin: 0 0 0.35rem 0;
    font-size: 0.95rem;
}

.ext-perm-hint {
    margin: 0 0 0.5rem 0;
    font-size: 0.82rem;
    opacity: 0.85;
}

.ext-perm-creator-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.ext-perm-badges {
    display: flex;
    gap: 0.35rem;
    margin-left: auto;
}

.ext-perm-badge {
    font-size: 0.75rem;
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.06);
}

.ext-perm-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.ext-perm-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
}

.ext-perm-table {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.9rem;
}

.ext-perm-head,
.ext-perm-table .ext-perm-row {
    display: grid;
    grid-template-columns: 1fr 4rem 4rem 2.5rem;
    align-items: center;
    gap: 0.35rem;
}

.ext-perm-head {
    font-weight: 600;
    border-bottom: 1px solid rgba(0, 0, 0, 0.12);
    padding-bottom: 0.25rem;
}

.center {
    text-align: center;
    justify-content: center;
}

.ext-perm-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.icon-button {
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 0.2rem;
    opacity: 0.75;
    &:hover {
        opacity: 1;
    }
}
</style>
