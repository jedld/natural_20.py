#!/usr/bin/env python3
"""Insert flavor_text (and SRD descriptions where missing) into item YAML.

Mundane flavor is original. Magic-item descriptions quote or closely follow
SRD 5.1 / 5.2 text (CC BY 4.0). Campaign-only items are skipped here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Original one-line flavor for mundane SRD / common 5e gear (not PHB prose).
WEAPON_FLAVOR = {
    "battleaxe": "A broad, bearded blade meant to bite through shield and helm in a single swing.",
    "dagger": "A short, double-edged blade small enough to hide in a sleeve or boot.",
    "quarterstaff": "A balanced length of hardwood, worn smooth where countless hands have gripped it.",
    "sling": "A simple leather cup and cords — humble, until a stone finds its mark.",
    "dart": "A fletched throwing spike, light enough to carry by the handful.",
    "greatclub": "A massive length of knotted wood, more tree than weapon.",
    "greataxe": "A two-handed axe whose wide crescent blade is built to fell more than timber.",
    "hand_crossbow": "A compact crossbow that cocks against the forearm and hides beneath a cloak.",
    "handaxe": "A one-handed woodsman's axe, equally at home in camp or close combat.",
    "javelin": "A slender throwing spear with a leaf-shaped head and a long, hungry reach.",
    "heavy_crossbow": "A steel-bowed siege piece, slow to span and brutal when it speaks.",
    "light_crossbow": "A sturdy crossbow a recruit can learn in an afternoon.",
    "light_hammer": "A compact hammer with a short haft, easy to throw or to finish a nail.",
    "longbow": "A tall yew bow that wants a strong arm and an open field.",
    "longsword": "A straight, double-edged sword — the familiar companion of soldiers and knights.",
    "rapier": "A slender thrusting blade built for speed, precision, and a duelist's footwork.",
    "scimitar": "A curved slashing sword that sings when it cuts.",
    "shortsword": "A close-work blade, shorter than a longsword and quicker in a press.",
    "shortbow": "A compact bow suited to woods, rooftops, and tight corridors.",
    "spear": "A simple shaft and point — among the oldest, and still among the most honest, weapons.",
    "torch": "A tarred brand that pops and spatters as it burns.",
    "unarmed_attack": "A fist, a knee, an elbow — whatever the body can bring to bear.",
    "vicious_rapier": "This rapier thirsts; when it bites true, the wound seems to tear wider than the steel.",
    "warhammer": "A martial hammer with a crushing face and a pick opposite, made to dent plate.",
    "mace": "A flanged metal head on a short haft, built to ignore the comfort of armor.",
    "morningstar": "A spiked head bristling like a cruel star, made to punch through mail.",
    "trident": "Three barbed tines on a sailor's shaft, equally useful for fish or foe.",
}

ARMOR_FLAVOR = {
    "padded": "Quilted layers of cloth and batting — cheap protection that rustles with every step.",
    "leather_armor": "Boiled and oiled hide, cut for someone who would rather not be heard.",
    "studded_leather": "Tough leather reinforced with close-set rivets.",
    "hide": "Untreated pelts layered clumsily, the armor of hunters and raiders.",
    "chain_shirt": "A shirt of interlocking rings worn under a cloak, quieter than a full hauberk.",
    "scale_mail": "Overlapping metal scales sewn to a leather coat, like the hide of a great fish.",
    "breastplate": "A fitted metal chest-piece that leaves the limbs free to move.",
    "half_plate": "Partial plate over vital areas, a compromise between safety and speed.",
    "ring_mail": "Heavy leather sewn with thick metal rings — crude, loud, and hard to cut.",
    "chain_mail": "A full hauberk of riveted rings that hangs to the knees and rings with every step.",
    "splint": "Vertical metal strips riveted to chain and leather, a poor knight's plate.",
    "plate": "Interlocking steel plates from gorget to greave, the pinnacle of mundane armor.",
    "shield": "A sturdy barrier of wood and iron, bossed at the center.",
}

# SRD 5.1 adventuring-gear sense (original wording, mechanical gist preserved).
GEAR_FLAVOR = {
    "arcane_focus": "A crafted token — crystal, orb, rod, staff, or wand — through which a spellcaster channels power.",
    "arrows": "Goose-fletched shafts with iron heads, bundled for a quiver.",
    "bolts": "Short, heavy quarrels made for a crossbow's groove.",
    "spellbook": "A locked grimoire of thick vellum, its margins crowded with sigils and notes.",
    "scroll_of_magic_missile": "Ink still faintly luminous on a roll of treated parchment.",
    "scroll_of_protection_from_poison": "A tightly wound prayer-scroll sealed with green wax.",
    "scroll_of_bless": "Sacred script spirals across the vellum in a priest's careful hand.",
    "scroll_of_spiritual_weapon": "The diagram of a hovering weapon is inked beside the incantation.",
    "holy_water": "Clear water blessed in a temple font, stoppered in a fragile flask.",
    "holy_symbol": "A consecrated emblem of faith, worn or held when prayers become spells.",
    "ink": "A small bottle of lampblack ink, enough for a long letter or a short spell.",
    "ink_pen": "A trimmed quill or simple metal nib.",
    "component_pouch": "A watertight leather pouch of tiny pockets for spell components.",
    "copper_piece": "A dull coin of copper, the smallest unit of common trade.",
    "crystal": "A faceted crystal that catches torchlight in its heart — an arcane focus.",
    "electronum": "A pale gold-silver coin of electrum.",
    "gold_piece": "A stamped gold coin, the standard of mercenary pay.",
    "healers_kit": "Bandages, salves, and splints packed for the moment someone stops breathing.",
    "rations": "Dried meat, hardtack, and fruit leather — unlovely, but it keeps.",
    "healing_potion": "A red liquid that sparkles when shaken, smelling faintly of honey and iron.",
    "orb": "A smooth crystal sphere, cool to the touch, used to gather a spell's shape.",
    "parchment": "A scraped sheet of animal skin, ready for ink.",
    "platinum": "A rare, bright coin worth a purse of gold.",
    "rod": "A short metal or bone rod, balanced as an arcane focus.",
    "ruby_gem": "A deep-red stone that drinks the light.",
    "silver_piece": "A common silver coin, ten to a gold.",
    "staff": "A length of carved wood shod in metal, serving as both walking stick and focus.",
    "thieves_tools": "Picks, files, a small mirror, and a set of narrow pliers in a roll of leather.",
    "wand": "A slender wand of wood or bone, tapered to a point.",
    "backpack": "A leather pack with straps and buckles, the adventurer's second spine.",
    "bedroll": "A blanket and pad rolled tight, smelling of campfire smoke.",
    "clothes_common": "Plain homespun — shirt, breeches, and a worn cloak.",
    "clothes_traveler": "Sturdy boots, a weather cloak, and clothes meant to take a road.",
    "torch": "A wooden stick wrapped in pitch-soaked cloth.",
    "rope": "Fifty feet of hempen rope, rough on the hands and reliable on a cliff.",
    "pitons": "Iron spikes for hammering into rock or ice.",
    "crowbar": "A bent iron bar that turns stubborn lids and locked doors into problems of leverage.",
    "tinderbox": "Flint, fire steel, and a scrap of char-cloth in a small tin.",
    "waterskin": "A stoppered skin that sloshes with a day's water.",
    "soap": "A cake of harsh lye soap.",
    "hammer": "A carpenter's hammer, honest and heavy.",
    "tongs": "Iron tongs blackened by the forge.",
    "bellows": "Leather lungs for waking a fire to white heat.",
    "anvil": "A squat iron anvil, scarred by a thousand hammer-blows.",
    "whetstone": "A grooved stone dark with oil, for putting an edge back on steel.",
    "incense": "A stick or cone of resinous incense, sweet when lit.",
    "scale": "A small hanging scale for weighing coin or spice.",
    "charcoal": "Sticks of willow charcoal for sketching or the forge.",
    "chisels": "A set of wood and stone chisels in a canvas wrap.",
    "awls": "Sharp awls for punching leather and starting holes.",
    "knives": "A bundle of small working knives.",
    "needles": "Sewing needles of different sizes, wrapped in cloth.",
    "thread": "A spool of strong linen thread.",
    "scissors": "Iron shears with a tight bite.",
    "tweezers": "Fine tweezers for splinters, gems, or clockwork.",
    "paper": "A sheet of rag paper, cheaper than parchment and quicker to ruin.",
    "book": "A bound book of blank or printed pages.",
    "pot": "A blackened cookpot with a bail handle.",
    "pan": "A shallow iron skillet.",
    "knife": "A kitchen knife with a worn wooden handle.",
    "cutting_board": "A scored wooden board that smells of onion and old meals.",
    "salt": "A twist of coarse salt.",
    "pepper": "A pinch of ground pepper in a paper cone.",
    "wig": "A theatrical wig of horsehair and wire.",
    "makeup": "Pots of greasepaint and powder.",
    "costume_pieces": "Odds of costume — a false nose, a cape clasp, a cardboard crown.",
    "props": "Stage props of painted wood and cheap gilt.",
    "herb_pouches": "A small pouch of dried herbs.",
    "herb_pouch": "A small pouch of dried herbs, fragrant even when tied shut.",
    "wooden_bowl": "A turned wooden bowl, darkened by use.",
    "animal_claw": "A cleaned claw, drilled for a cord.",
    "dice": "Carved bone dice, the pips stained dark.",
    "cards": "A worn deck of playing cards, the edges soft from many hands.",
    "playing_cards": "A deck of painted playing cards in a leather sleeve.",
    "board": "A folding game board, squares faded from travel.",
    "pieces": "A pouch of carved game pieces.",
    "blowpipe": "A jeweler's blowpipe for a small flame.",
    "crucible": "A small clay crucible stained by old melts.",
    "loupe": "A jeweler's loupe on a short cord.",
    "vials": "Empty glass vials stoppered with cork.",
    "drying_rack": "A collapsible rack for herbs or washed cloth.",
    "mortar_pestle": "A stone mortar and pestle, dusted with old powders.",
    "scales": "A merchant's balance with a set of nested weights.",
    "compass": "A brass compass whose needle trembles toward north.",
    "sea_charts": "Rolled charts marked with coasts, reefs, and rumored isles.",
    "astrolabe": "A brass astrolabe etched with degrees of the sky.",
    "dividers": "Navigator's dividers for walking distances on a chart.",
    "wheel": "A heavy potter's wheel, kicked into a slow spin.",
    "kiln": "A small kiln of firebrick, still smelling of old firings.",
    "clay": "A damp lump of potter's clay wrapped in cloth.",
    "plumb_bob": "A pointed lead weight on a chalked line.",
    "square": "A carpenter's square, true along both arms.",
    "chisel_set": "A mason's set of chisels, edges carefully oiled.",
    "costume": "A full costume on a hanger, a second identity in cloth.",
    "whetstone_oil": "A vial of thin oil for the whetstone.",
    "whetstone_water": "A cup of water kept for the stone.",
    "torch_mount": "An iron bracket for holding a torch to a wall or post.",
    "lute": "A pear-shaped lute with a belly of thin wood and a voice that carries.",
    "potion_of_healing_greater": "A deeper crimson than a common healing draught, thick as syrup.",
    "potion_of_invisibility": "The vial looks empty until you tilt it and the air inside bends the light.",
    "potion_of_fire_breath": "The liquid glows like banked coals and smells of smoke and spice.",
    "potion_of_vitality": "A golden cordial that warms the chest like a second sunrise.",
    "spell_scroll_2nd_level": "A spell scroll whose ink still hums faintly under the fingertips.",
    "vestments": "Ceremonial robes cut for temple and graveside alike.",
    "little_bag_of_sand": "A pinch of fine sand in a cloth twist — a spell component, or an hourglass in miniature.",
    "small_knife": "A small working knife, useful for quills, food, and cord.",
    "manacles": "Iron cuffs and a short chain, the lock pitted but sound.",
    "climbers_kit": "Pitons, boot-spikes, a harness, and a climber's hammer in one bundle.",
    "diamond": "A clear stone that throws sharp sparks of light.",
    "mess_kit": "A nested tin cup, plate, and utensils, blackened from campfires.",
    "bag_of_devouring": "This sack looks like a bag of holding, but the darkness inside seems to breathe.",
    "ale_mug": "A dented tankard that still smells of hops.",
    "bread_loaf": "A round loaf with a hard crust and a soft, cheap crumb.",
    "cheese_wedge": "A wedge of pale cheese, edged with rind.",
    "tavern_stew": "A wooden bowl of thick stew, still steaming.",
    "candle": "A tallow candle that weeps as it burns.",
    "oil_flask": "A clay flask of lamp oil, stoppered with waxed cloth.",
    "wooden_stake": "A sharpened length of ash, meant for more than a tent line.",
    "steel_mirror": "A polished steel plate that serves as a mirror in a pinch.",
    "bullseye_lantern": "A hooded lantern that throws a long, narrow cone of light.",
    "bulleyes_lantern": "A hooded lantern that throws a long, narrow cone of light.",
}

# Campaign-named entries already living in templates: original, no module lore.
CAMPAIGN_IN_TEMPLATES_FLAVOR = {
    "tavern_room_buzzer": "A brass pull-cord that rings a distant bell when tugged.",
    "letter_from_a_dead_friend": "A folded letter, the seal broken, the ink brown with age.",
    "wooden_door_key": "A simple iron key with a wooden fob.",
    "mawsse": "A curious little trinket, easily palmed and easily forgotten.",
    "tavern_safe_key": "A heavy iron key whose bit is cut for a strongbox.",
    "tavern_skeleton_key": "A master key, worn bright at the wards.",
    "tavern_room_key_1": "A brass room key, numbered by a careful innkeeper.",
    "tavern_room_key_2": "A brass room key, numbered by a careful innkeeper.",
    "tavern_room_key_3": "A brass room key, numbered by a careful innkeeper.",
    "tavern_room_key_4": "A brass room key, numbered by a careful innkeeper.",
    "tavern_suite_key": "An iron key for a better room than most travelers see.",
    "celestial_shield_of_the_hidden_lord": "A burnished shield whose rim is etched with celestial script.",
}

# SRD 5.1 / 5.2 magic item flavor (short) + descriptions (CC BY 4.0 SRD wording, condensed).
PLUS_WEAPON_FLAVOR = {
    1: "Faint runes glimmer along the metal, and the weapon sits lighter in the hand than it should.",
    2: "The weapon hums with stored power; sparks of pale light crawl the edge when it is drawn.",
    3: "This weapon is unmistakably enchanted — the air around it tastes of ozone and old magic.",
}
PLUS_ARMOR_FLAVOR = {
    1: "The armor's joints move more freely than mundane work, as if the metal were willing.",
    2: "Protective glyphs are inlaid along the plates, cool to the touch.",
    3: "This armor sheds a barely visible sheen, turning blows that ought to land.",
}
PLUS_SHIELD_FLAVOR = {
    1: "The shield's boss is inlaid with a warding rune that warms when danger is near.",
    2: "Blows seem to glance aside as if the shield were larger than its rim.",
    3: "This shield rings like a bell when struck, and the note hangs in the air.",
}

NAMED_MAGIC_FLAVOR = {
    "amulet_of_health": "A heavy amulet on a thick chain; wearing it steadies the breath and the blood.",
    "ring_of_protection": "A plain band that seems to turn just before a blow would land.",
    "headband_of_intellect": "A slim circlet that settles on the brow and clears the fog from thought.",
    "cloak_of_protection": "A well-made cloak whose hem never quite catches on thorn or blade.",
    "gloves_of_thievery": "Supple gloves that seem to find the edge of a lock as if they had eyes.",
    "boots_of_striding_and_springing": "These boots ignore the weight of armor and drink bad footing like dry earth drinks rain.",
    "instrument_of_illusions": "Notes from this instrument shimmer in the air like heat above a road.",
    "flame_tongue_longsword": "Command the blade, and fire runs its length like oil catching light.",
    "frost_brand_longsword": "Frost feathers the fuller; the steel drinks heat from the air around it.",
    "sun_blade": "The hilt is real; the blade is a bar of daylight that appears when it is grasped.",
    "dragon_scale_mail": "Armor of overlapping dragon scales, still faintly warm, still faintly proud.",
    "cloak_of_displacement": "The cloak throws your image a step to the side, a shimmering lie that blades chase.",
    "bag_of_holding": "The mouth of the bag is a dark circle. Reach in, and the bottom is never where it should be.",
    "bag_of_beans": "A handful of ordinary-looking beans that are anything but ordinary once they meet earth.",
    "necklace_of_fireballs": "A golden chain hung with beads like trapped embers, each one a bottled fireball.",
    "wand_of_magic_missiles": "A slender wand that kicks in the hand when it looses darts of force.",
    "staff_of_defense": "A plain wooden staff that grows warm when a spell of warding is near.",
}

NAMED_MAGIC_DESCRIPTION = {
    "amulet_of_health": "Your Constitution score is 19 while you wear this amulet. It has no effect on you if your Constitution is already 19 or higher. Requires attunement.",
    "ring_of_protection": "You gain a +1 bonus to AC and saving throws while wearing this ring. Requires attunement.",
    "headband_of_intellect": "Your Intelligence score is 19 while you wear this headband. It has no effect on you if your Intelligence is already 19 or higher. Requires attunement.",
    "cloak_of_protection": "You gain a +1 bonus to AC and saving throws while you wear this cloak. Requires attunement.",
    "gloves_of_thievery": "These gloves are invisible while worn. While wearing them, you gain a bonus to Dexterity (Sleight of Hand) checks and to checks made to pick locks. Requires attunement. (SRD 5.2)",
    "boots_of_striding_and_springing": "While you wear these boots, your walking speed becomes 30 feet, unless your walking speed is higher, and your speed isn't reduced if you are encumbered or wearing heavy armor. With a 10-foot running start, you can long jump up to 30 feet and high jump up to 15 feet. Requires attunement.",
    "flame_tongue_longsword": "You can use a bonus action to speak this magic sword's command word, causing flames to erupt from the blade. These flames shed bright light in a 40-foot radius and dim light for an additional 40 feet. While the sword is ablaze, it deals an extra 2d6 fire damage to any target it hits. Requires attunement.",
    "frost_brand_longsword": "When you hit with an attack using this magic sword, the target takes an extra 1d6 cold damage. In addition, while you hold the sword, you have resistance to fire damage. In freezing temperatures, the blade sheds bright light in a 10-foot radius and dim light for an additional 10 feet. Requires attunement.",
    "sun_blade": "This item appears to be a longsword hilt. While grasping it, you can use a bonus action to cause a blade of pure radiance to spring into existence. The blade emits bright light in a 15-foot radius and dim light for an additional 15 feet. It deals radiant damage and has the finesse property. Requires attunement.",
    "dragon_scale_mail": "Dragon scale mail is made of the scales of one kind of dragon. While wearing it, you gain a +1 bonus to AC, you have advantage on saving throws against the Frightful Presence and breath weapons of dragons, and you have resistance to one damage type determined by the dragon kind. Requires attunement.",
    "cloak_of_displacement": "While you wear this cloak, it projects an illusion that makes you appear to be standing in a place near your actual location, causing attack rolls against you to have disadvantage. If you take damage, the property ceases to function until the start of your next turn. Requires attunement.",
    "bag_of_holding": "This bag has an interior space considerably larger than its outside dimensions — roughly 2 feet in diameter at the mouth and 4 feet deep. The bag can hold up to 500 pounds, not exceeding a volume of 64 cubic feet. The bag weighs 15 pounds, regardless of its contents.",
    "bag_of_beans": "This heavy cloth bag contains 3d4 dry beans. The bag weighs 1/2 pound plus 1/4 pound for each bean it contains. If you dump the bag's contents out on the ground, they explode in 10 feet, and each creature in that area takes fire damage. If you plant a bean, it has an unpredictable magical effect.",
    "necklace_of_fireballs": "This necklace has 1d6 + 3 beads hanging from it. You can use an action to detach a bead and throw it up to 60 feet. When it reaches the end of its trajectory, the bead detonates as a 3rd-level fireball.",
    "wand_of_magic_missiles": "This wand has 7 charges. While holding it, you can use an action to expend 1 or more of its charges to cast magic missile from it. For 1 charge, you cast the 1st-level version; you increase the spell slot by one for each additional charge. The wand regains 1d6 + 1 expended charges daily at dawn.",
    "staff_of_defense": "This staff can be wielded as a magic quarterstaff. While holding it, you can expend charges to cast mage armor (1 charge) or shield (2 charges). Requires attunement.",
    "instrument_of_illusions": "While you play this instrument, you can weave minor visual illusions into the performance. Requires attunement.",
    "vicious_rapier": "When you roll a 20 on your attack roll with this magic weapon, the target takes an extra 2d6 damage of the weapon's type.",
}

GEAR_DESCRIPTION = {
    "healers_kit": "This kit has ten uses. As an action, you can expend one use of the kit to stabilize a creature that has 0 hit points, without needing to make a Wisdom (Medicine) check.",
    "crowbar": "Using a crowbar grants advantage to Strength checks where the crowbar's leverage can be applied.",
    "climbers_kit": "A climber's kit includes special pitons, boot tips, gloves, and a harness. You can use the kit as an action to anchor yourself; when you do, you can't fall more than 25 feet from the point where you anchored yourself, and you can't climb more than 25 feet away from that point without undoing the anchor.",
    "manacles": "These metal restraints can bind a Small or Medium creature. Escaping the manacles requires a successful DC 20 Dexterity check. Breaking them requires a successful DC 20 Strength check.",
    "holy_water": "As an action, you can splash the contents of this flask onto a creature within 5 feet of you or throw it up to 20 feet. A fiend or undead takes 2d6 radiant damage on a hit.",
    "tinderbox": "This small container holds flint, fire steel, and tinder (usually dry cloth soaked in light oil) used to kindle a fire. Using it to light a torch — or anything else with abundant, exposed fuel — takes an action. Lighting any other fire takes 1 minute.",
    "backpack": "A backpack can hold one cubic foot / 30 pounds of gear. You can also strap items, such as a bedroll or a coil of rope, to the outside of a backpack.",
    "candle": "For 1 hour, a candle sheds bright light in a 5-foot radius and dim light for an additional 5 feet.",
    "oil_flask": "Oil usually comes in a clay flask that holds 1 pint. As an action, you can splash the oil onto a creature within 5 feet or throw it up to 20 feet. If lit, the target takes 5 fire damage at the start of its turn for 2 rounds.",
    "bullseye_lantern": "A bullseye lantern casts bright light in a 60-foot cone and dim light for an additional 60 feet. Once lit, it burns for 6 hours on a flask (1 pint) of oil.",
    "bulleyes_lantern": "A bullseye lantern casts bright light in a 60-foot cone and dim light for an additional 60 feet. Once lit, it burns for 6 hours on a flask (1 pint) of oil.",
    "steel_mirror": "A polished steel mirror, useful for looking around corners or flashing a signal.",
    "wooden_stake": "A sharpened wooden stake. Harmless to most creatures; vampire-hunters carry several.",
    "playing_cards": "A set of illustrated playing cards.",
    "thieves_tools": "This set of tools includes a small file, a set of lock picks, a small mirror mounted on a metal handle, a set of narrow-bladed scissors, and a pair of pliers. Proficiency with these tools lets you add your proficiency bonus to any ability checks you make to disarm traps or open locks.",
    "component_pouch": "A component pouch is a small, watertight leather belt pouch that has compartments to hold all the material components and other special items you need to cast your spells, except for those components that have a specific cost.",
    "spellbook": "Essential for wizards, a spellbook is a leather-bound tome with 100 blank vellum pages suitable for recording spells.",
    "healing_potion": "A character who drinks the magical red fluid in this vial regains 2d4 + 2 hit points. Drinking or administering the potion takes an action.",
    "potion_of_healing_greater": "A character who drinks this potion regains 4d4 + 4 hit points. Drinking or administering the potion takes an action.",
    "potion_of_invisibility": "This potion's container looks empty but feels as though it holds liquid. When you drink it, you become invisible for 1 hour. Anything you wear or carry is invisible with you. The effect ends early if you attack or cast a spell.",
    "potion_of_vitality": "When you drink this potion, it removes any exhaustion you are suffering and cures any disease or poison affecting you. For the next 24 hours, you regain the maximum number of hit points for any Hit Die you spend.",
    "mess_kit": "This tin box contains a cup and simple cutlery. The box clamps together, and one side can be used as a cooking pan and the other as a plate or shallow bowl.",
    "rope": "Hempen rope has 2 hit points and can be burst with a DC 17 Strength check.",
    "waterskin": "A waterskin can hold 4 pints of liquid.",
    "torch": "A torch burns for 1 hour, providing bright light in a 20-foot radius and dim light for an additional 20 feet. If you make a melee attack with a burning torch and hit, it deals 1 fire damage.",
}


def yaml_quote(text: str) -> str:
    if any(ch in text for ch in ":#{}[]&*!|>%@`\"'"):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def plus_bonus(key: str) -> int | None:
    if key.endswith("_plus_one"):
        return 1
    if key.endswith("_plus_two"):
        return 2
    if key.endswith("_plus_three"):
        return 3
    return None


def flavor_for(key: str) -> str | None:
    if key in WEAPON_FLAVOR:
        return WEAPON_FLAVOR[key]
    if key in ARMOR_FLAVOR:
        return ARMOR_FLAVOR[key]
    if key in GEAR_FLAVOR:
        return GEAR_FLAVOR[key]
    if key in CAMPAIGN_IN_TEMPLATES_FLAVOR:
        return CAMPAIGN_IN_TEMPLATES_FLAVOR[key]
    if key in NAMED_MAGIC_FLAVOR:
        return NAMED_MAGIC_FLAVOR[key]
    bonus = plus_bonus(key)
    if bonus is None:
        return None
    if key.startswith("shield_"):
        return PLUS_SHIELD_FLAVOR[bonus]
    armor_roots = (
        "studded_leather", "scale_mail", "breastplate", "chain_mail", "plate",
        "half_plate", "chain_shirt", "splint", "padded", "leather", "ring_mail",
    )
    if any(key.startswith(root) for root in armor_roots):
        return PLUS_ARMOR_FLAVOR[bonus]
    return PLUS_WEAPON_FLAVOR[bonus]


def description_for(key: str) -> str | None:
    if key in NAMED_MAGIC_DESCRIPTION:
        return NAMED_MAGIC_DESCRIPTION[key]
    if key in GEAR_DESCRIPTION:
        return GEAR_DESCRIPTION[key]
    bonus = plus_bonus(key)
    if bonus is None:
        return None
    if key.startswith("shield_"):
        return f"You have a +{bonus} bonus to AC while wielding this shield. Requires attunement."
    armor_roots = (
        "studded_leather", "scale_mail", "breastplate", "chain_mail", "plate",
        "half_plate", "chain_shirt", "splint", "padded", "leather", "ring_mail",
    )
    if any(key.startswith(root) for root in armor_roots):
        return f"You have a +{bonus} bonus to AC while wearing this armor. Requires attunement."
    return f"You have a +{bonus} bonus to attack and damage rolls made with this magic weapon."


BLOCK_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]*):\s*$", re.M)


def split_blocks(text: str) -> list[tuple[str | None, str]]:
    """Return (key or None for preamble, block_text) pairs."""
    matches = list(BLOCK_RE.finditer(text))
    if not matches:
        return [(None, text)]
    parts: list[tuple[str | None, str]] = []
    if matches[0].start() > 0:
        parts.append((None, text[: matches[0].start()]))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((match.group("key"), text[match.start() : end]))
    return parts


def inject_block(key: str, block: str) -> str:
    flavor = flavor_for(key)
    description = description_for(key)
    if not flavor and not description:
        return block
    lines = block.splitlines(keepends=True)
    name_idx = None
    has_flavor = False
    has_description = False
    for i, line in enumerate(lines):
        if line.startswith("  flavor_text:"):
            has_flavor = True
        if line.startswith("  description:"):
            has_description = True
        if line.startswith("  name:"):
            name_idx = i
    insert_at = name_idx if name_idx is not None else 0
    additions = []
    if flavor and not has_flavor:
        additions.append(f"  flavor_text: {yaml_quote(flavor)}\n")
    if description and not has_description:
        if "\n" in description or len(description) > 90:
            additions.append("  description: >-\n")
            additions.append(f"    {description}\n")
        else:
            additions.append(f"  description: {yaml_quote(description)}\n")
    if not additions:
        return block
    lines[insert_at + 1 : insert_at + 1] = additions
    return "".join(lines)


def process_file(path: Path) -> tuple[int, int]:
    original = path.read_text()
    blocks = split_blocks(original)
    updated = []
    changed = 0
    considered = 0
    for key, block in blocks:
        if key is None:
            updated.append(block)
            continue
        considered += 1
        new_block = inject_block(key, block)
        if new_block != block:
            changed += 1
        updated.append(new_block)
    new_text = "".join(updated)
    if new_text != original:
        path.write_text(new_text)
    return considered, changed


NEW_COMMON_ITEMS = """
# --- Common SRD / 5e adventuring gear (used by campaigns including Death House) ---
candle:
  cost: 0.01
  name: Candle
  type: light_source
  weight: 0
  light:
    bright: 5
    dim: 5
oil_flask:
  cost: 0.1
  name: Flask of Oil
  type: gear
  weight: 1
wooden_stake:
  cost: 0.05
  name: Wooden Stake
  type: gear
  weight: 1
steel_mirror:
  cost: 5
  name: Steel Mirror
  type: gear
  weight: 0.5
bullseye_lantern:
  cost: 10
  name: Bullseye Lantern
  type: light_source
  weight: 2
  light:
    bright: 60
    dim: 60
playing_cards:
  cost: 0.5
  name: Playing Card Set
  type: game
  weight: 0
"""


def main() -> None:
    equipment = ROOT / "templates/items/equipment.yml"
    text = equipment.read_text()
    if "\ncandle:\n" not in text:
        equipment.write_text(text.rstrip() + "\n" + NEW_COMMON_ITEMS)
        print("appended common SRD gear to equipment.yml")

    for rel in (
        "templates/items/weapons.yml",
        "templates/items/equipment.yml",
        "templates/items/magic_items.yml",
    ):
        path = ROOT / rel
        considered, changed = process_file(path)
        print(f"{rel}: updated {changed}/{considered} entries")


if __name__ == "__main__":
    main()
