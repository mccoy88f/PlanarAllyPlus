import { l2g } from "../../core/conversions";
import { getPointDistance, toLP } from "../../core/geometry";
import type { LocalPoint } from "../../core/geometry";
import { positionSystem } from "../systems/position";
import { positionState } from "../systems/position/state";
import { playerSettingsState } from "../systems/settings/players/state";

const PINCH_SENSITIVITY = 0.4;

let pinchStartDistance = 0;
let pinchStartZoomDisplay = 0;
let pinchCenter: LocalPoint | null = null;

export function handlePinchStart(event: TouchEvent): void {
    if (event.touches.length !== 2) return;
    pinchStartDistance = getPointDistance(
        { x: event.touches[0].pageX, y: event.touches[0].pageY },
        { x: event.touches[1].pageX, y: event.touches[1].pageY },
    );
    pinchStartZoomDisplay = positionState.raw.zoomDisplay;
    pinchCenter = toLP(
        (event.touches[0].pageX + event.touches[1].pageX) / 2,
        (event.touches[0].pageY + event.touches[1].pageY) / 2,
    );
}

export function handlePinchMove(event: TouchEvent): void {
    if (event.touches.length !== 2 || pinchCenter === null) return;
    if (playerSettingsState.raw.disableScrollToZoom.value) return;

    const currentDistance = getPointDistance(
        { x: event.touches[0].pageX, y: event.touches[0].pageY },
        { x: event.touches[1].pageX, y: event.touches[1].pageY },
    );
    if (pinchStartDistance <= 0) return;

    const scale = currentDistance / pinchStartDistance;
    const deltaZoomDisplay = -(scale - 1) * PINCH_SENSITIVITY;
    const newZoomDisplay = Math.max(0, Math.min(1, pinchStartZoomDisplay + deltaZoomDisplay));
    const zoomLocation = l2g(pinchCenter);
    positionSystem.updateZoom(newZoomDisplay, zoomLocation);
    pinchStartDistance = currentDistance;
    pinchStartZoomDisplay = newZoomDisplay;
}

export function handlePinchEnd(): void {
    pinchCenter = null;
    pinchStartDistance = 0;
}
