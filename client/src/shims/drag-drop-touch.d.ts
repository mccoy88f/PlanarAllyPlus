declare module "@dragdroptouch/drag-drop-touch" {
    /** Abilita il polyfill HTML5 drag-drop per touch (default: `document`, `document`). */
    export function enableDragDropTouch(
        dragRoot?: Document | HTMLElement,
        dropRoot?: Document | HTMLElement,
        options?: {
            allowDragScroll?: boolean;
            contextMenuDelayMS?: number;
            dragImageOpacity?: number;
            dragScrollPercentage?: number;
            dragScrollSpeed?: number;
            dragThresholdPixels?: number;
            forceListen?: boolean;
            isPressHoldMode?: boolean;
            pressHoldDelayMS?: number;
            pressHoldMargin?: number;
            pressHoldThresholdPixels?: number;
        },
    ): void;
}
