import type { CharacterCreate, CharacterLink } from "../../../apiTypes";
import { wrapSocket } from "../../api/socket";

import type { CharacterId } from "./models";

export const sendCreateCharacter = wrapSocket<CharacterCreate>("Character.Create");
export const sendRemoveCharacter = wrapSocket<CharacterId>("Character.Remove");
export const sendLinkCharacter = wrapSocket<CharacterLink>("Character.Link");
