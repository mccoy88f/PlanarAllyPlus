import { registerSystem } from "../../../core/systems";
import type { System, SystemClearReason } from "../../../core/systems/models";

import { sendChatMessage } from "./emits";
import { renderChatMarkdown } from "./md";
import { chatState } from "./state";

const { mutableReactive: $ } = chatState;

class ChatSystem implements System {
    clear(reason: SystemClearReason): void {
        if (reason === "full-loading") $.messages = [];
    }

    addMessage(id: string, author: string, data: string[], sync: boolean): void {
        const message = {
            id,
            author,
            content: renderChatMarkdown(data.join("")),
        };

        if (sync) sendChatMessage({ id, author, data });

        $.messages.push(message);
    }

    updateImage(id: string, content: string): void {
        const message = $.messages.findLast((m) => m.id === id);
        if (message) {
            message.content = renderChatMarkdown(content);
        }
    }
}

export const chatSystem = new ChatSystem();
registerSystem("chat", chatSystem, false, chatState);
