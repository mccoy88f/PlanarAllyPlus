<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";

const router = useRouter();
const { t } = useI18n();

const selected = ref(0);
const modes = [
    {
        typeKey: "dashboard.CreateSwitcher.start_scratch",
        descKey: "dashboard.CreateSwitcher.start_scratch_desc",
        target: "create-blank-game",
    },
    {
        typeKey: "dashboard.CreateSwitcher.import_game",
        descKey: "dashboard.CreateSwitcher.import_game_desc",
        target: "import-game",
    },
];

async function create(): Promise<void> {
    const mode = modes[selected.value];
    if (mode === undefined) return;
    await router.push({ name: mode.target });
}
</script>

<template>
    <div id="content">
        <div class="title">{{ t("dashboard.CreateSwitcher.title") }}</div>
        <div id="switch">
            <div
                v-for="[i, mode] of modes.entries()"
                :key="mode.target"
                :class="{ selected: i === selected }"
                @click="selected = i"
            >
                <div class="type">{{ t(mode.typeKey) }}</div>
                <div class="desc">
                    {{ t(mode.descKey) }}
                </div>
            </div>
        </div>
        <div class="action">
            <button class="go" @click="router.push({ name: 'games' })">
                <font-awesome-icon icon="chevron-left" />
                <span>{{ t("dashboard.CreateSwitcher.back") }}</span>
            </button>
            <button class="go" @click="create">
                <span>{{ t("dashboard.CreateSwitcher.continue") }}</span>
                <font-awesome-icon icon="play" />
            </button>
        </div>
    </div>
</template>

<style scoped lang="scss">
#content {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;

    background-color: rgba(77, 59, 64, 0.6);
    border-radius: 20px;
    padding: 3.75rem;
    padding-right: 2rem; // adjust for scroll bar

    .title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 3.125em;
        color: white;
        border-bottom: 5px solid #ffa8bf;
        font-weight: bold;
        margin-bottom: 2rem;

        > span:last-child {
            color: #ffa8bf;

            &:hover {
                cursor: pointer;
            }
        }
    }

    #switch {
        display: flex;
        flex-direction: column;

        > div {
            width: 50vw;
            background-color: rgba(137, 0, 37, 1);

            display: flex;
            // align-items: center;
            flex-direction: column;

            border: 4px solid transparent;
            border-radius: 20px;

            padding: 10px;
            margin-bottom: 3rem;

            font-size: 1.2em;

            &.selected {
                border-color: rgba(255, 255, 255, 0.75);
            }

            &:hover {
                cursor: pointer;
            }

            .type {
                font-weight: bold;
                border-bottom: solid 2px white;
                padding: 5px;
                padding-bottom: 10px;
                margin-bottom: 10px;

                font-size: 1.2em;
            }

            .desc {
                padding: 5px;
            }
        }
    }

    .action {
        display: flex;

        button {
            margin-top: 1.25rem;
            width: 15rem;
            height: 2.5rem;
            color: white;
            font-size: 1.125em;
            background-color: rgba(137, 0, 37, 1);
            border: 1px solid transparent;
            border-radius: 5px;
            box-shadow: 0 0 10px 0 rgba(6, 6, 6, 0.5);

            display: flex;
            align-items: center;
            justify-content: center;

            > span {
                margin-left: 15px;
                margin-right: 15px;
            }

            &:last-child {
                border: 1px solid rgba(255, 255, 255, 0.75);
                margin-left: 1.25rem;
            }

            &:hover {
                cursor: pointer;
                border: 2px solid rgba(255, 255, 255, 0.75);
            }
        }
    }
}
</style>
