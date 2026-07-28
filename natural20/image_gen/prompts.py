"""Prompt builders for campaign tokens and title backgrounds."""

from __future__ import annotations

import re
from typing import Any

# CLIP text encoders (FLUX / SD) truncate at 77 tokens; keep prompts conservative.
CLIP_MAX_WORDS = 65


TOKEN_NEGATIVE = (
    "text, watermark, logo, UI, frame collage, multiple characters, full body distant, "
    "blurry, low quality, deformed hands, extra limbs, photograph of real person"
)

BACKGROUND_NEGATIVE = (
    "text, title text, watermark, logo, UI overlay, modern city, cars, neon cyberpunk, "
    "bright cheerful daylight, cartoon sticker sheet"
)

WILD_SHEEP_TOKEN_STYLE = (
    "fantasy VTT token bust, close-up head and shoulders, face centered, fills frame, "
    "painterly, warm afternoon light, high-detail face"
)

WILD_SHEEP_PORTRAIT_STYLE = (
    "painterly fantasy portrait, head and shoulders, face centered, close-up, warm natural light, no text"
)


def clip_word_limit(text: str, max_words: int = CLIP_MAX_WORDS) -> str:
    """Trim prompt text to a CLIP-safe word budget (keeps the start)."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]).rstrip(".,;:")


def fit_clip_prompt(*segments: str, max_words: int = CLIP_MAX_WORDS) -> str:
    """Join prompt segments and enforce a CLIP-safe word budget."""
    parts = [re.sub(r"\s+", " ", (segment or "").strip()) for segment in segments if segment and segment.strip()]
    return clip_word_limit(". ".join(parts), max_words=max_words)


def npc_visual_description(npc: dict[str, Any]) -> str:
    """Physical look for diffusion prompts; prefers outward_appearance over role description."""
    outward = (npc.get("outward_appearance") or "").strip()
    if outward:
        return outward
    return (npc.get("description") or "").strip()


def campaign_theme_blurb(campaign_meta: dict[str, Any]) -> str:
    title = campaign_meta.get("title") or campaign_meta.get("name") or "fantasy campaign"
    if isinstance(title, list):
        title = " ".join(str(part) for part in title)
    description = (campaign_meta.get("description") or "").strip()
    asset_theme = (campaign_meta.get("asset_theme") or "").strip()
    parts = [str(title), description, asset_theme]
    return ". ".join(part for part in parts if part).strip()


def campaign_asset_mood(campaign_meta: dict[str, Any]) -> str:
    """Short mood string for image prompts — avoids story-length campaign descriptions."""
    asset_theme = (campaign_meta.get("asset_theme") or "").strip()
    if asset_theme:
        return clip_word_limit(asset_theme, 12)
    title = campaign_meta.get("title") or campaign_meta.get("name") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    return clip_word_limit(str(title).strip(), 8)


def _token_style_for_theme(theme: str) -> str:
    lowered = theme.lower()
    if "sheep" in lowered or "prancing flagon" in lowered or "market town" in lowered:
        return WILD_SHEEP_TOKEN_STYLE
    return (
        "fantasy VTT token bust, close-up head and shoulders, face centered, fills frame, "
        "painterly, dramatic lighting, high-detail face"
    )


def _scene_backdrop(scene: str) -> str:
    normalized = (scene or "town").strip().lower()
    if normalized == "tavern":
        return "medieval tavern, hearth glow, blurred patrons"
    if normalized == "market":
        return "market stall, canvas awning, timber buildings"
    if normalized == "street":
        return "cobblestone street, timber shops, afternoon sun"
    if normalized == "bedroom":
        return "treehouse wizard bedroom, warm lamplight, rumpled sheets"
    if normalized == "laboratory":
        return "wizard treehouse lab, enchanted lamps, branch walls"
    return "medieval fantasy town, warm afternoon light"


def npc_scene_portrait_prompt(
    *,
    name: str,
    kind: str,
    description: str,
    race: str | None = None,
    scene: str = "tavern",
    theme: str = "",
) -> str:
    race_bit = f"{race} " if race else ""
    subject = f"Portrait of {name}, a {race_bit}{kind.replace('_', ' ')}"
    desc = clip_word_limit((description or "").replace("\n", " "), 28)
    scene_bit = _scene_backdrop(scene)
    mood_bit = clip_word_limit(theme, 10) if theme else ""
    return fit_clip_prompt(
        subject,
        desc,
        scene_bit,
        WILD_SHEEP_PORTRAIT_STYLE,
        f"Mood: {mood_bit}" if mood_bit else "",
        max_words=CLIP_MAX_WORDS,
    )


def npc_token_prompt(
    *,
    name: str,
    kind: str,
    description: str,
    race: str | None = None,
    alignment: str | None = None,
    theme: str = "",
) -> str:
    race_bit = f"{race} " if race else ""
    align_bit = f", {alignment}" if alignment else ""
    subject = f"VTT bust of {name}, a {race_bit}{kind.replace('_', ' ')}{align_bit}"
    desc = clip_word_limit((description or "").replace("\n", " "), 30)
    style = _token_style_for_theme(theme)
    mood_bit = clip_word_limit(theme, 10) if theme else ""
    return fit_clip_prompt(
        subject,
        desc,
        style,
        f"Mood: {mood_bit}" if mood_bit else "",
        max_words=CLIP_MAX_WORDS,
    )


def _login_scene_for_theme(theme: str) -> str:
    lowered = theme.lower()
    if "sheep" in lowered or "prancing flagon" in lowered:
        return (
            "bustling medieval market square, Prancing Flagon tavern sign, timber stalls, "
            "curious white sheep with scroll in mouth, warm golden afternoon sun"
        )
    return "medieval fantasy town, cobblestone, timber buildings, warm afternoon light"


def _character_select_scene_for_theme(theme: str) -> str:
    lowered = theme.lower()
    if "sheep" in lowered or "prancing flagon" in lowered:
        return (
            "diverse level-five adventuring party: human fighter in plate, half-elf wizard "
            "with staff, dwarf cleric in holy vestments, halfling rogue with daggers, "
            "gathered outside Prancing Flagon tavern, white sheep nearby"
        )
    return "party of fantasy adventurers, dramatic group portrait, warm torchlight"


def login_background_prompt(*, title: str, description: str, theme_keywords: str = "") -> str:
    theme = theme_keywords or "medieval fantasy, warm afternoon light"
    desc = clip_word_limit((description or "").replace("\n", " "), 40)
    scene = _login_scene_for_theme(theme)
    return fit_clip_prompt(
        f"Cinematic wide establishing shot for D&D campaign '{title}'",
        desc,
        scene,
        f"Atmosphere: {clip_word_limit(theme, 12)}",
        "No readable text, no UI, painterly 16:9, warm volumetric lighting",
        max_words=75,
    )


def character_selection_background_prompt(
    *,
    title: str,
    description: str,
    theme_keywords: str = "",
) -> str:
    theme = theme_keywords or "medieval fantasy, warm afternoon light"
    desc = clip_word_limit((description or "").replace("\n", " "), 35)
    scene = _character_select_scene_for_theme(theme)
    return fit_clip_prompt(
        f"Character selection splash art for D&D campaign '{title}'",
        desc,
        scene,
        f"Atmosphere: {clip_word_limit(theme, 12)}",
        "No readable text, no UI, painterly 16:9, warm heroic lighting",
        max_words=75,
    )


def character_portrait_prompt(
    *,
    name: str,
    description: str,
    race: str | None = None,
    character_class: str | None = None,
    theme: str = "",
) -> str:
    race_bit = f"{race.replace('_', ' ')} " if race else ""
    class_bit = f"{character_class.replace('_', ' ')} " if character_class else ""
    subject = f"Character select portrait of {name}, {race_bit}{class_bit}fantasy adventurer".replace("  ", " ")
    desc = clip_word_limit((description or "").replace("\n", " "), 35)
    mood_bit = clip_word_limit(theme, 10) if theme else ""
    style = WILD_SHEEP_PORTRAIT_STYLE if "sheep" in theme.lower() or "prancing flagon" in theme.lower() else (
        "Vertical composition, dramatic lighting, painterly, no text"
    )
    return fit_clip_prompt(
        subject,
        desc,
        style,
        f"Mood: {mood_bit}" if mood_bit else "",
        max_words=CLIP_MAX_WORDS,
    )


ICON_NEGATIVE = (
    "text, letters, watermark, logo, UI frame, multiple items, busy background, "
    "photorealistic, 3d render, painterly illustration, cinematic scene, landscape, "
    "forest, dungeon interior, character, creature, demon, devil, imp, face, "
    "portrait, person, hands, full body, dark moody atmosphere, vignette, blurry, "
    "modern gun, rifle, pistol, firearm, sniper scope, long barrel, low quality"
)

DEFAULT_ICON_STYLE = (
    "flat vector fantasy game icon, bold dark outline, simple gradient fills, "
    "centered symbol, plain light gray background"
)

SPELL_ICON_COMPOSITION = (
    "single symbolic spell effect only, flat vector art, bold dark outline, "
    "bright saturated colors, no characters, no scenery"
)


ITEM_ICON_COMPOSITION = (
    "single inventory object only, flat vector art, bold dark outline, "
    "bright saturated colors, clear recognizable silhouette, no characters, no scenery"
)

ACTION_ICON_COMPOSITION = (
    "single abstract combat maneuver symbol only, flat vector game icon, "
    "bold dark outline, bright saturated colors, no characters, no faces, "
    "no creatures, no scenery, plain background"
)

_ACTION_VISUAL_HINTS: dict[str, str] = {
    "disarming_attack": (
        "medieval sword knocked from grasp, parry and disarm symbol, "
        "crossed blade and gauntlet, weapon falling away"
    ),
    "riposte": (
        "counterattack riposte symbol, crossed rapiers with spark, "
        "defensive parry into thrust"
    ),
    "pickpocket": (
        "stealthy hand lifting coin purse, thief maneuver symbol, "
        "single gloved hand and small pouch"
    ),
    "find_familiar": (
        "arcane summoning circle with small owl or cat silhouette, "
        "wizard familiar spell symbol"
    ),
    "dismiss_familiar": (
        "arcane circle fading with small bird silhouette dissolving"
    ),
    "mage_hand_command": (
        "glowing spectral hand symbol, arcane magic hand gesture icon"
    ),
    "channel_divinity_turn_undead": (
        "holy radiant sunburst with skeletal skull warding symbol, "
        "cleric turn undead ability, divine light repelling bones"
    ),
    "interact_store": (
        "open wooden chest with downward arrow, deposit items symbol"
    ),
    "interact_loot": (
        "open treasure chest with upward arrow, take items symbol"
    ),
    "grapple": (
        "two hands gripping wrists, wrestling grapple symbol"
    ),
    "push": (
        "open palm shove symbol, forceful push maneuver"
    ),
}

_ARMOR_TORSO = (
    "front view wearable body armor torso with shoulder pauldrons, "
    "inventory icon"
)

_ARMOR_ITEM_SLUGS = frozenset({
    "chain_mail", "chain_shirt", "ring_mail", "splint", "plate", "breastplate",
    "half_plate", "scale_mail", "leather_armor", "padded", "studded_leather",
})

_ARMOR_NEGATIVE = (
    "shield, buckler, heater shield, round shield, tower shield, "
    "treasure chest, wooden chest, box, crate, container, barrel"
)

_ITEM_VISUAL_HINTS: dict[str, str] = {
    "sling": (
        "primitive leather sling in Y-shape with stone pouch and two cords, "
        "ancient ranged weapon, not a gun"
    ),
    "light_crossbow": (
        "small medieval crossbow side view, horizontal bow limbs with bowstring, "
        "short wooden stock, no scope, no rifle barrel"
    ),
    "heavy_crossbow": (
        "large medieval crossbow side view, thick bow limbs, wooden stock with "
        "windlass crank, no scope, no rifle barrel"
    ),
    "hand_crossbow": (
        "compact one-handed medieval crossbow, short horizontal bow limbs, "
        "small pistol-grip stock, no scope, no rifle barrel"
    ),
    "longbow": "tall curved wooden longbow with bowstring",
    "shortbow": "short curved wooden bow with bowstring",
    "greatclub": "large thick knobbly wooden log club, no axe blades",
    "morningstar": "spiked metal ball on short wooden handle flail mace, not an axe",
    "warhammer": "metal war hammer with long handle",
    "mace": "metal flanged mace head on handle",
    "trident": "three-pronged spear trident weapon",
    "javelin": "light throwing spear javelin",
    "spear": "wooden spear with metal tip",
    "quarterstaff": "wooden staff weapon",
    "battleaxe": "single-bladed battle axe",
    "greataxe": "large two-handed battle axe",
    "handaxe": "small one-handed axe",
    "dagger": "short dagger knife blade",
    "longsword": "straight longsword blade with crossguard",
    "shortsword": "short curved scimitar blade",
    "rapier": "thin rapier fencing sword",
    "scimitar": "curved scimitar sword",
    "warhammer": "heavy war hammer",
    "bolts": "bundle of short crossbow bolts with metal tips",
    "arrows": "quiver of arrows with fletching",
    "chain_mail": (
        f"{_ARMOR_TORSO}, chain mail hauberk with interlocking metal rings, not a shield"
    ),
    "ring_mail": (
        f"{_ARMOR_TORSO}, ring mail armor with metal rings sewn onto leather, not a shield"
    ),
    "plate": (
        f"{_ARMOR_TORSO}, full plate knight armor with metal plates on chest, not a shield"
    ),
    "splint": (
        f"{_ARMOR_TORSO}, splint armor with vertical metal strips on leather, "
        "not a treasure chest or box"
    ),
    "breastplate": f"{_ARMOR_TORSO}, metal breastplate cuirass covering chest only, not a shield",
    "half_plate": (
        f"{_ARMOR_TORSO}, half plate armor combining plate and chain mail, not a shield"
    ),
    "chain_shirt": (
        f"{_ARMOR_TORSO}, short chain mail shirt with interlocking metal rings, not a shield"
    ),
    "scale_mail": (
        f"{_ARMOR_TORSO}, scale mail armor with overlapping metal scales, not a shield"
    ),
    "leather_armor": f"{_ARMOR_TORSO}, brown leather armor vest with shoulder pads",
    "padded": f"{_ARMOR_TORSO}, quilted padded cloth gambeson armor",
    "studded_leather": (
        f"{_ARMOR_TORSO}, leather armor vest with metal studs and rivets"
    ),
    "shield": "round wooden shield",
    "holy_symbol": "gold holy symbol amulet pendant",
    "arcane_focus": "crystal orb arcane focus",
    "healing_potion": "glass potion bottle with red healing liquid",
    "thieves_tools": "set of lockpicks and small tools",
    "torch": "wooden torch with flame",
    "candle": "lit wax candle",
    "spellbook": "closed leather spellbook",
    "holy_water": "glass flask of holy water",
}


def _weapon_visual_hint(label: str, name: str, item_type: str) -> str:
    text = f"{label} {name}".lower().replace("_", " ")
    if "crossbow" in text:
        if "hand" in text:
            return _ITEM_VISUAL_HINTS["hand_crossbow"]
        if "heavy" in text:
            return _ITEM_VISUAL_HINTS["heavy_crossbow"]
        if "light" in text:
            return _ITEM_VISUAL_HINTS["light_crossbow"]
        return "wooden crossbow weapon"
    if "longbow" in text:
        return _ITEM_VISUAL_HINTS["longbow"]
    if "shortbow" in text or text.endswith(" bow"):
        return _ITEM_VISUAL_HINTS["shortbow"]
    if "sword" in text or "rapier" in text or "scimitar" in text:
        return f"fantasy {text.strip()} blade with hilt"
    if "axe" in text:
        return f"fantasy {text.strip()} weapon"
    if item_type in {"ranged_attack", "ranged"}:
        return f"fantasy ranged weapon {text.strip()}"
    if item_type in {"melee_attack", "melee"}:
        return f"fantasy melee weapon {text.strip()}"
    return ""


def item_visual_hint(
    *,
    name: str,
    label: str,
    item_type: str = "",
    subtype: str = "",
) -> str:
    slug = (name or "").lower().replace(" ", "_")
    if slug in _ITEM_VISUAL_HINTS:
        return _ITEM_VISUAL_HINTS[slug]

    item_type_l = item_type.replace("_", " ").lower()
    subtype_l = subtype.replace("_", " ").lower()
    label_l = (label or name).strip()

    if item_type_l == "armor":
        if slug in _ITEM_VISUAL_HINTS:
            return _ITEM_VISUAL_HINTS[slug]
        armor_kind = subtype_l or "armor"
        return (
            f"{_ARMOR_TORSO}, fantasy {armor_kind} {label_l}, not a shield or chest"
        )
    if item_type_l == "potion":
        return f"glass potion bottle, {label_l}"
    if item_type_l == "ammunition":
        if "bolt" in slug or "bolt" in label_l.lower():
            return _ITEM_VISUAL_HINTS["bolts"]
        if "arrow" in slug or "arrow" in label_l.lower():
            return _ITEM_VISUAL_HINTS["arrows"]
        return f"bundle of {label_l}"
    if item_type_l in {"holy symbol", "holy_symbol"}:
        return _ITEM_VISUAL_HINTS["holy_symbol"]
    if item_type_l in {"arcane focus", "arcane_focus"}:
        return _ITEM_VISUAL_HINTS["arcane_focus"]
    if item_type_l == "tool":
        return f"fantasy adventuring tool kit, {label_l}"
    if item_type_l in {"scroll", "spell_scroll"}:
        return "rolled parchment spell scroll"

    weapon_hint = _weapon_visual_hint(label_l, name, item_type_l)
    if weapon_hint:
        return weapon_hint

    if item_type_l and item_type_l not in label_l.lower():
        return f"{label_l}, {item_type_l}"
    return label_l


_ITEM_NEGATIVE_HINTS: dict[str, str] = {
    "sling": "rifle, gun, pistol, firearm, barrel, scope, stock",
    "light_crossbow": "rifle, sniper, scope, long barrel, firearm, pistol",
    "heavy_crossbow": "rifle, sniper, scope, long barrel, firearm, pistol",
    "hand_crossbow": "rifle, sniper, scope, long barrel, firearm, pistol",
    "morningstar": "axe, double axe, battleaxe, scepter, polearm",
    "greatclub": "axe, battleaxe, blade, sword",
    "plate": _ARMOR_NEGATIVE,
    "splint": _ARMOR_NEGATIVE,
    "ring_mail": _ARMOR_NEGATIVE,
    "chain_mail": _ARMOR_NEGATIVE,
    "chain_shirt": _ARMOR_NEGATIVE,
    "breastplate": _ARMOR_NEGATIVE,
    "half_plate": _ARMOR_NEGATIVE,
    "scale_mail": _ARMOR_NEGATIVE,
    "leather_armor": _ARMOR_NEGATIVE,
    "padded": _ARMOR_NEGATIVE,
    "studded_leather": _ARMOR_NEGATIVE,
}


def item_icon_negative(*, name: str, label: str = "", item_type: str = "") -> str:
    slug = (name or "").lower().replace(" ", "_")
    extra = _ITEM_NEGATIVE_HINTS.get(slug, "")
    text = f"{label} {name}".lower().replace("_", " ")
    item_type_l = item_type.replace("_", " ").lower()
    if not extra and "crossbow" in text:
        extra = "rifle, sniper, scope, long barrel, firearm, pistol"
    if not extra and slug == "sling":
        extra = "rifle, gun, pistol, firearm, barrel"
    if not extra and (item_type_l == "armor" or slug in _ARMOR_ITEM_SLUGS):
        extra = _ARMOR_NEGATIVE
    if not extra:
        return ""
    return f"{ICON_NEGATIVE}, {extra}"


def item_icon_prompt(
    *,
    name: str,
    label: str,
    item_type: str = "",
    subtype: str = "",
    description: str = "",
    icon_style: str = DEFAULT_ICON_STYLE,
    theme: str = "",
) -> str:
    del description, theme
    visual = item_visual_hint(name=name, label=label, item_type=item_type, subtype=subtype)
    subject = f"Inventory icon of {visual}"
    style = clip_word_limit(icon_style or DEFAULT_ICON_STYLE, 20)
    return fit_clip_prompt(
        subject,
        style,
        ITEM_ICON_COMPOSITION,
        "square composition, no text, no border frame",
        max_words=CLIP_MAX_WORDS,
    )


def spell_icon_prompt(
    *,
    name: str,
    label: str,
    school: str = "",
    description: str = "",
    icon_style: str = DEFAULT_ICON_STYLE,
    theme: str = "",
) -> str:
    del description, theme  # bundled spell icons use label/school only
    school_bit = school.replace("_", " ").strip()
    subject = f"RPG spell icon: {label or name}"
    if school_bit:
        subject = f"{subject}, {school_bit} school"
    style = clip_word_limit(icon_style or DEFAULT_ICON_STYLE, 20)
    return fit_clip_prompt(
        subject,
        style,
        SPELL_ICON_COMPOSITION,
        "square composition, no text, no border frame",
        max_words=CLIP_MAX_WORDS,
    )


def effect_icon_prompt(
    *,
    name: str,
    label: str,
    school: str = "",
    description: str = "",
    icon_style: str = DEFAULT_ICON_STYLE,
    theme: str = "",
) -> str:
    del description, theme
    school_bit = school.replace("_", " ").strip()
    subject = f"Status effect buff icon: {label or name}"
    if school_bit:
        subject = f"{subject}, {school_bit} school"
    style = clip_word_limit(icon_style or DEFAULT_ICON_STYLE, 20)
    return fit_clip_prompt(
        subject,
        style,
        SPELL_ICON_COMPOSITION,
        "square composition, no text, no border frame",
        max_words=CLIP_MAX_WORDS,
    )


def action_visual_hint(slug: str, label: str = "") -> str:
    key = (slug or "").strip().lower()
    if key in _ACTION_VISUAL_HINTS:
        return _ACTION_VISUAL_HINTS[key]
    return clip_word_limit(
        f"abstract RPG ability symbol for {label or key.replace('_', ' ')}",
        18,
    )


def action_icon_negative(*, slug: str = "") -> str:
    del slug
    return (
        f"{ICON_NEGATIVE}, goblin, orc, elf, dwarf, humanoid, monster, "
        "full body, cape, armor suit, musketeer, blunderbuss, rifle, pistol"
    )


def action_icon_prompt(
    *,
    slug: str,
    label: str,
    description: str = "",
    icon_style: str = DEFAULT_ICON_STYLE,
    theme: str = "",
) -> str:
    del description, theme  # bundled action icons are global UI assets
    visual = action_visual_hint(slug, label)
    subject = f"Combat action icon: {visual}"
    style = clip_word_limit(icon_style or DEFAULT_ICON_STYLE, 14)
    return fit_clip_prompt(
        subject,
        style,
        ACTION_ICON_COMPOSITION,
        "ability button icon, square composition, no text",
        max_words=CLIP_MAX_WORDS,
    )
