"""
Adattatore D&D Beyond <-> PlanarAlly character sheet.

Struttura D&D Beyond (da dndbeyond.com/characters/ID/json):
  { "character": { "name", "classes", "race", "background", "stats", "traits", "notes", ... } }

Compatibile con BeyondImporter per Roll20:
  https://github.com/RobinKuiper/Roll20APIScripts/blob/master/BeyondImporter_5eOGL/BeyondImporter.js
"""

from __future__ import annotations

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_BEYOND_ABILITY_IDS = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}
_ALIGNMENTS = [
    "", "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
]


def _get_total_ability(character: dict, ability_id: int) -> int:
    """Calcola il valore totale di una caratteristica (come BeyondImporter)."""
    stats = character.get("stats") or [{}] * 6
    bonus = character.get("bonusStats") or [{}] * 6
    override = character.get("overrideStats") or [{}] * 6
    idx = ability_id - 1
    base = stats[idx].get("value") if idx < len(stats) else 10
    bonus_val = bonus[idx].get("value") if idx < len(bonus) else 0
    override_val = override[idx].get("value") if idx < len(override) else 0
    if base is None:
        base = 10
    if bonus_val is None:
        bonus_val = 0
    total = base + bonus_val
    if override_val and override_val > 0:
        total = override_val
    return total


def _ability_modifier(value: int) -> int:
    return (value - 10) // 2


def dndbeyond_to_internal(beyond_json: dict) -> dict:
    """
    Converte JSON D&D Beyond nel formato interno PlanarAlly.
    Accetta sia { "character": {...} } che direttamente { ... } (oggetto character).
    """
    char = beyond_json.get("character", beyond_json)
    if not isinstance(char, dict):
        return {}

    # Basics
    name = char.get("name") or ""
    classes = char.get("classes") or []
    main_class = classes[0] if classes else {}
    class_def = main_class.get("definition") or {}
    subclass_def = main_class.get("subclassDefinition")
    level = main_class.get("level") or 1
    total_level = sum(c.get("level", 0) for c in classes)

    race_data = char.get("race") or {}
    race_name = race_data.get("baseName") or race_data.get("fullName") or ""

    bg_data = char.get("background") or {}
    bg_def = bg_data.get("definition") or {}
    bg_custom = bg_data.get("customBackground") or {}
    background = bg_def.get("name") or bg_custom.get("name") or ""

    align_id = char.get("alignmentId")
    alignment = _ALIGNMENTS[align_id] if isinstance(align_id, int) and 0 <= align_id < len(_ALIGNMENTS) else ""

    xp = char.get("currentXp") or 0

    # Abilities
    abilities = {}
    for bid, key in _BEYOND_ABILITY_IDS.items():
        val = _get_total_ability(char, bid)
        mod = _ability_modifier(val)
        abilities[key] = {"value": val, "mod": mod}

    # Traits / Personality
    traits = char.get("traits") or {}
    personality = {
        "traits": traits.get("personalityTraits") or "",
        "ideals": traits.get("ideals") or "",
        "bonds": traits.get("bonds") or "",
        "flaws": traits.get("flaws") or "",
    }

    # Notes / Background story
    notes_data = char.get("notes") or {}
    backstory = notes_data.get("backstory") or ""
    # Merge background type + backstory for our single "Background" textarea
    if background and backstory:
        background = f"Background: {background}\n\n{backstory}"
    elif backstory:
        background = backstory

    # Speed
    weight_speeds = (race_data.get("weightSpeeds") or {}).get("normal") or {}
    speed = weight_speeds.get("walk") or 30

    # HP
    hp_data = char.get("baseHitPoints") or 0
    hp_current = hp_data if isinstance(hp_data, dict) else hp_data
    hp_max = hp_current if isinstance(hp_current, int) else 0
    if isinstance(hp_data, dict):
        hp_current = hp_data.get("current", hp_data.get("value", 0))
        hp_max = hp_data.get("max", hp_current)
    temp_hp = char.get("temporaryHitPoints") or 0

    # Combat (valori base, AC va calcolato da inventory/modifiers in Beyond)
    modifiers = char.get("modifiers") or []
    ac_bonus = 0
    for m in modifiers:
        if m.get("type") == "bonus" and m.get("subType") == "armor-class":
            ac_bonus += m.get("value", 0)

    # Inventory -> equipment (lista nomi/descrizioni)
    inv = char.get("inventory") or []
    equipment = []
    for item in inv:
        defn = item.get("definition") or {}
        qty = item.get("quantity") or 1
        iname = defn.get("name") or ""
        if iname:
            equipment.append(f"{iname} x{qty}" if qty > 1 else iname)

    # Spellcasting semplificato
    spell_ability = ""
    for c in classes:
        cd = c.get("definition") or {}
        said = cd.get("spellCastingAbilityId")
        if said:
            spell_ability = _BEYOND_ABILITY_IDS.get(said, "")

    return {
        "basics": {
            "name": name,
            "class": class_def.get("name", ""),
            "level": total_level or level,
            "race": race_name,
            "background": background,
            "alignment": alignment,
            "experience": xp,
            "subclass": subclass_def.get("name", "") if subclass_def else "",
            "proficiencyBonus": 2 + (total_level - 1) // 4 if total_level else 2,
            "inspiration": 1 if char.get("inspiration") else 0,
            "passivePerception": 10 + _ability_modifier(_get_total_ability(char, 5)),  # WIS
        },
        "abilities": abilities,
        "savingThrows": {k: {"proficient": False, "mod": abilities[k]["mod"]} for k in _ABILITIES},
        "skills": {
            "acrobatics": {"ability": "dex", "proficient": False, "mod": 0},
            "animalHandling": {"ability": "wis", "proficient": False, "mod": 0},
            "arcana": {"ability": "int", "proficient": False, "mod": 0},
            "athletics": {"ability": "str", "proficient": False, "mod": 0},
            "deception": {"ability": "cha", "proficient": False, "mod": 0},
            "history": {"ability": "int", "proficient": False, "mod": 0},
            "insight": {"ability": "wis", "proficient": False, "mod": 0},
            "intimidation": {"ability": "cha", "proficient": False, "mod": 0},
            "investigation": {"ability": "int", "proficient": False, "mod": 0},
            "medicine": {"ability": "wis", "proficient": False, "mod": 0},
            "nature": {"ability": "int", "proficient": False, "mod": 0},
            "perception": {"ability": "wis", "proficient": False, "mod": 0},
            "performance": {"ability": "cha", "proficient": False, "mod": 0},
            "persuasion": {"ability": "cha", "proficient": False, "mod": 0},
            "religion": {"ability": "int", "proficient": False, "mod": 0},
            "sleightOfHand": {"ability": "dex", "proficient": False, "mod": 0},
            "stealth": {"ability": "dex", "proficient": False, "mod": 0},
            "survival": {"ability": "wis", "proficient": False, "mod": 0},
        },
        "combat": {
            "armorClass": 10 + ac_bonus,
            "initiative": _ability_modifier(_get_total_ability(char, 2)),
            "speed": speed,
            "hp": {"current": hp_current, "max": hp_max, "temp": temp_hp},
            "hitDice": {"total": "", "remaining": ""},
            "deathSaves": {"successes": 0, "failures": 0},
        },
        "attacks": [],
        "spellcasting": {"ability": spell_ability, "dc": 0, "attackBonus": 0, "slots": [], "spells": []},
        "equipment": equipment,
        "features": "",
        "proficiencies": "",
        "personality": personality,
        "notes": backstory,
    }


def migrate_old_to_beyond(sheet: dict) -> dict | None:
    """
    Se sheet è in formato vecchio (basics, abilities, ...), restituisce character in formato D&D Beyond.
    Altrimenti restituisce None (già in formato Beyond).
    """
    if "basics" in sheet and "character" not in sheet:
        result = internal_to_dndbeyond(sheet)
        return result.get("character")
    return None


def internal_to_dndbeyond(sheet: dict) -> dict:
    """
    Converte formato interno PlanarAlly in JSON compatibile D&D Beyond.
    Produce { "character": { ... } } che può essere usato da BeyondImporter o re-importato.
    """
    basics = sheet.get("basics") or {}
    abilities = sheet.get("abilities") or {}
    combat = sheet.get("combat") or {}
    personality = sheet.get("personality") or {}
    hp = combat.get("hp") or {}

    def stat_val(ab: str) -> int:
        a = abilities.get(ab, {})
        if isinstance(a, dict):
            return a.get("value", 10)
        return 10

    def stat_mod(ab: str) -> int:
        a = abilities.get(ab, {})
        if isinstance(a, dict):
            return a.get("mod", 0)
        return 0

    stats = [{"value": stat_val(k)} for k in _ABILITIES]
    bonus_stats = [{"value": 0} for _ in _ABILITIES]
    override_stats = [{"value": 0} for _ in _ABILITIES]

    align_id = 0
    al = (basics.get("alignment") or "").strip()
    for i, a in enumerate(_ALIGNMENTS):
        if a == al:
            align_id = i
            break

    level = basics.get("level") or 1
    class_name = basics.get("class") or ""

    return {
        "character": {
            "name": basics.get("name") or "Unnamed",
            "classes": [{
                "definition": {"name": class_name, "spellCastingAbilityId": None},
                "subclassDefinition": {"name": basics.get("subclass", "")} if basics.get("subclass") else None,
                "level": level,
            }],
            "race": {
                "baseName": basics.get("race") or "",
                "fullName": basics.get("race") or "",
                "subRaceShortName": "",
                "weightSpeeds": {
                    "normal": {
                        "walk": combat.get("speed", 30),
                        "fly": 0,
                        "swim": 0,
                        "climb": 0,
                        "burrow": 0,
                    }
                },
            },
            "background": {
                "definition": {"name": basics.get("background") or ""},
                "customBackground": {"name": basics.get("background") or ""},
            },
            "alignmentId": align_id,
            "currentXp": basics.get("experience") or 0,
            "inspiration": bool(basics.get("inspiration")),
            "temporaryHitPoints": hp.get("temp") or 0,
            "baseHitPoints": hp.get("max") or hp.get("current") or 0,
            "stats": stats,
            "bonusStats": bonus_stats,
            "overrideStats": override_stats,
            "traits": {
                "personalityTraits": personality.get("traits") or "",
                "ideals": personality.get("ideals") or "",
                "bonds": personality.get("bonds") or "",
                "flaws": personality.get("flaws") or "",
                "appearance": "",
            },
            "notes": {
                "backstory": sheet.get("notes") or basics.get("background") or "",
                "allies": "",
                "organizations": "",
                "enemies": "",
                "personalPossessions": "",
                "otherHoldings": "",
                "otherNotes": sheet.get("features") or "",
            },
            "currencies": {"cp": 0, "sp": 0, "gp": 0, "ep": 0, "pp": 0},
            "inventory": [
                {"definition": {"name": (e if isinstance(e, str) else str(e.get("name", ""))).split(" x")[0].strip()}, "quantity": 1}
                for e in (sheet.get("equipment") or [])
            ],
            "modifiers": [],
            "feats": [],
            "currentHitPoints": hp.get("current") or hp.get("max") or 0,
            "planarally": {
                "armorClass": combat.get("armorClass", 10),
                "initiative": combat.get("initiative", 0),
                "hitDiceTotal": (combat.get("hitDice") or {}).get("total", ""),
                "hitDiceRemaining": (combat.get("hitDice") or {}).get("remaining", ""),
                "deathSaveSuccesses": (combat.get("deathSaves") or {}).get("successes", 0),
                "deathSaveFailures": (combat.get("deathSaves") or {}).get("failures", 0),
                "savingThrows": sheet.get("savingThrows") or {k: {"proficient": False, "mod": 0} for k in _ABILITIES},
                "skills": sheet.get("skills") or {},
                "spellcasting": sheet.get("spellcasting") or {},
                "features": sheet.get("features") or "",
                "proficiencies": sheet.get("proficiencies") or "",
            },
        }
    }
