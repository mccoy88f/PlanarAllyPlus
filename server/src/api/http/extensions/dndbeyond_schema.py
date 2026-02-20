"""
Schema D&D Beyond per character sheet.
Riferimento: https://github.com/RobinKuiper/Roll20APIScripts (BeyondImporter)
Export D&D Beyond: dndbeyond.com/characters/ID/json
"""


def empty_character() -> dict:
    """Struttura vuota compatibile D&D Beyond."""
    return {
        "name": "",
        "classes": [
            {
                "definition": {"name": "", "spellCastingAbilityId": None},
                "subclassDefinition": None,
                "level": 1,
            }
        ],
        "race": {
            "baseName": "",
            "fullName": "",
            "subRaceShortName": "",
            "weightSpeeds": {
                "normal": {"walk": 30, "fly": 0, "burrow": 0, "swim": 0, "climb": 0}
            },
        },
        "background": {
            "definition": {"name": ""},
            "customBackground": {"name": ""},
        },
        "alignmentId": None,
        "currentXp": 0,
        "inspiration": False,
        "temporaryHitPoints": 0,
        "baseHitPoints": 0,
        "currentHitPoints": 0,
        "planarally": {
            "armorClass": 10,
            "initiative": 0,
            "hitDiceTotal": "",
            "hitDiceRemaining": "",
            "deathSaveSuccesses": 0,
            "deathSaveFailures": 0,
            "savingThrows": {ab: {"proficient": False, "mod": 0} for ab in ("str", "dex", "con", "int", "wis", "cha")},
            "skills": {k: {"proficient": False, "mod": 0} for k in (
                "acrobatics", "animalHandling", "arcana", "athletics", "deception", "history",
                "insight", "intimidation", "investigation", "medicine", "nature", "perception",
                "performance", "persuasion", "religion", "sleightOfHand", "stealth", "survival"
            )},
            "spellcasting": {"ability": "", "dc": 0, "attackBonus": 0},
            "features": "",
            "proficiencies": "",
        },
        "stats": [{"value": 10} for _ in range(6)],
        "bonusStats": [{"value": 0} for _ in range(6)],
        "overrideStats": [{"value": 0} for _ in range(6)],
        "traits": {
            "personalityTraits": "",
            "ideals": "",
            "bonds": "",
            "flaws": "",
            "appearance": "",
        },
        "notes": {
            "backstory": "",
            "allies": "",
            "organizations": "",
            "enemies": "",
            "personalPossessions": "",
            "otherHoldings": "",
            "otherNotes": "",
        },
        "currencies": {"cp": 0, "sp": 0, "gp": 0, "ep": 0, "pp": 0},
        "inventory": [],
        "modifiers": [],
        "feats": [],
        "spells": {"race": [], "class": []},
        "classSpells": {},
        "spellSlots": [],  # [{ "level": 1, "used": 0, "max": 2 }, ...]
        "age": "",
        "size": "",
        "height": "",
        "weight": "",
        "eyes": "",
        "hair": "",
        "skin": "",
        "faith": "",
        "lifestyle": {},
    }


_ALIGNMENTS = [
    "", "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
]


def get_character_name(data: dict) -> str:
    """Estrae il nome per la lista schede. Supporta formato D&D Beyond, dndsheets e vecchio formato."""
    if not data:
        return "Unnamed"
    name = data.get("name") or ""
    if not name and "basics" in data:
        basics = data.get("basics") or {}
        name = basics.get("name") or ""
    if not name:
        dnd = data.get("dndsheets") or {}
        name = dnd.get("name") or ""
    return (name or "").strip() or "Unnamed"
