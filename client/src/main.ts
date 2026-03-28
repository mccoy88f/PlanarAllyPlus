import "../style.css";
import { enableDragDropTouch } from "@dragdroptouch/drag-drop-touch";
import { FontAwesomeIcon } from "@fortawesome/vue-fontawesome";
import { createApp } from "vue";
import { watch } from "vue";
import Toast, { POSITION } from "vue-toastification";
import type { PluginOptions } from "vue-toastification";

// eslint-disable-next-line import/default
import App from "./App.vue";
import { PlanarAllyModalsPlugin } from "./core/plugins/modals/plugin";
import { loadFontAwesome } from "./fa";
import { i18n } from "./i18n";
import { router } from "./router";
import { bootstrapRouter } from "./router/bootstrap";

bootstrapRouter();

// Touch: emula HTML5 drag-and-drop (asset → cartelle / mappa). Il canvas di gioco non usa `draggable`, quindi i touch lì restano gestiti da `game/tools/events.ts` (long-press incluso).
enableDragDropTouch();

loadFontAwesome();

// Sincronizza html lang per componenti che lo leggono (es. viewer PDF)
watch(() => i18n.global.locale.value, (locale) => {
    document.documentElement.lang = locale;
}, { immediate: true });

const toastOptions: PluginOptions = {
    position: POSITION.BOTTOM_RIGHT,
    shareAppContext: true,
};

const app = createApp(App);
app.use(router)
    .use(i18n)
    .use(Toast, toastOptions)
    .use(PlanarAllyModalsPlugin)
    .component("font-awesome-icon", FontAwesomeIcon)
    .mount("body");
