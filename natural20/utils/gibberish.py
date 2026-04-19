"""
Utility function to transform English text into fantasy language gibberish.
This is used when a character speaks in a language that the listener doesn't understand.

Each D&D language uses distinct phonotactics, syllable shapes, and vocabulary
fragments inspired by official lore and real-world linguistic models:

  - Elvish: Tolkien Sindarin/Quenya inspired — flowing vowels, liquid consonants
  - Dwarvish (Dethek): Norse/Khuzdul inspired — heavy consonant clusters, runic feel
  - Draconic: Harsh sibilants + plosives, regal and ancient
  - Infernal: Precise Latin-inspired, legalistic and cold
  - Abyssal: Guttural, chaotic, glottal stops and dark vowels
  - Celestial: Angelic, harmonic, Greek/Hebrew inspired
  - Deep Speech: Alien, unpronounceable, Lovecraftian
  - Goblin: Short, harsh, guttural barking
  - Orc: Brutal, heavy, grunting
  - Sylvan: Musical, whimsical, playful fey speech
  - Giant (Jotun): Thunderous, booming, Norse-primitive
  - Gnomish: Quick, clipped, inventive-sounding
  - Halfling (Luiric): Warm, pastoral, rustic
  - Druidic: Celtic/Gaelic nature-speech
  - Primordial: Elemental, ancient, rumbling
  - Undercommon: Dark, whispery, Drow-influenced
"""

import hashlib
import random
import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Lore-accurate phonetic definitions for each D&D 5e language
# ---------------------------------------------------------------------------
# Each language defines:
#   onsets     – consonant(s) that can begin a syllable
#   nuclei    – vowel(s) / diphthongs that form the syllable core
#   codas      – consonant(s) that can end a syllable
#   templates  – weighted syllable shapes (O=onset, N=nucleus, C=coda)
#   particles  – small function words / filler unique to the language
#   roots      – lore-flavored morphemes to sprinkle in
#   min_syl / max_syl – word-length range in syllables

LANGUAGE_PHONETICS = {
    # --- ELVISH (Espruar) ---------------------------------------------------
    # Inspired by Tolkien's Sindarin/Quenya: liquid consonants, long vowels,
    # diphthongs, gentle sibilants. Words flow musically.
    'elvish': {
        'onsets': [
            'l', 'r', 'n', 'm', 'th', 's', 'f', 'v', 'qu',
            'gl', 'el', 'al', 'il', 'ar', 'an', 'w', 'y',
            'gal', 'tel', 'mel', 'sil', 'fin', 'lor', 'cel',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ae', 'ai', 'ei', 'ia',
            'ea', 'ie', 'ue', 'io', 'au', 'oa',
        ],
        'codas': [
            'l', 'r', 'n', 'th', 's', 'nd', 'ss', 'nn', 'll',
            'rn', 'ld', 'lm', 'ril', 'wen', 'dh',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('N', 1)],
        'particles': [
            'na', 'le', 'en', 'a', 'o', 'il', 'an', 'mae', 'ni',
        ],
        'roots': [
            'quess', 'elen', 'myth', 'thal', 'shar', 'amar', 'gala',
            'riel', 'lam', 'mire', 'fael', 'anor', 'silv', 'essa',
            'thil', 'erin', 'loth', 'quel', 'draen', 'tinu',
        ],
        'min_syl': 2,
        'max_syl': 4,
    },

    # --- DWARVISH (Dethek) --------------------------------------------------
    # Norse/Germanic/Khuzdul inspired. Heavy consonant clusters, short harsh
    # vowels, guttural feel. Think Tolkien Dwarvish + Old Norse.
    'dwarvish': {
        'onsets': [
            'kh', 'th', 'gr', 'dr', 'br', 'kr', 'st', 'sk',
            'g', 'd', 'b', 'k', 't', 'n', 'm', 'r', 'z',
            'str', 'ghr', 'thr', 'dw', 'mund',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ai', 'ei', 'ur', 'or', 'ar',
        ],
        'codas': [
            'k', 'd', 'n', 'r', 'g', 'th', 'rn', 'nd', 'lk',
            'rd', 'rg', 'nk', 'rm', 'ld', 'zd', 'gd', 'rl',
        ],
        'templates': [('ONC', 5), ('ON', 2), ('NC', 2), ('ONCC', 1)],
        'particles': ['az', 'ok', 'ur', 'ek', 'ga', 'da', 'na'],
        'roots': [
            'khaz', 'baraz', 'felak', 'mazn', 'thark', 'durin',
            'gabil', 'mund', 'rune', 'storn', 'grund', 'mith',
            'dalg', 'bolg', 'gimr', 'narg', 'drak', 'borg',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- DRACONIC -----------------------------------------------------------
    # Language of dragons. Harsh sibilants (s, z, sh), plosives (k, t),
    # regal and ancient. Short punchy words with occasional grandeur.
    'draconic': {
        'onsets': [
            'sz', 'th', 'kr', 'dr', 'sk', 'sv', 'vr', 'zk',
            'k', 'r', 's', 'z', 't', 'v', 'x', 'ix',
            'thra', 'sza', 'ixen', 'ossav',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'aa', 'ii', 'ei', 'oi', 'au',
        ],
        'codas': [
            'x', 'ss', 'th', 'rk', 'sk', 'zz', 'ks', 'rx',
            'r', 'k', 's', 'z', 'n', 'xis',
        ],
        'templates': [('ONC', 4), ('ON', 3), ('NC', 2), ('ON', 1)],
        'particles': ['vi', 'xe', 'ir', 'ka', 'zi', 'ith'],
        'roots': [
            'thacz', 'ixen', 'ossav', 'vyth', 'aryx', 'klauth',
            'szen', 'kriv', 'drak', 'szar', 'taxr', 'verax',
            'rasz', 'thurk', 'gorax', 'zekk', 'svith', 'kothar',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- INFERNAL -----------------------------------------------------------
    # Language of devils. Precise, legalistic, Latin-inspired but sinister.
    # Measured cadence, long vowels, sharp endings.
    'infernal': {
        'onsets': [
            'v', 'z', 'ph', 'th', 'm', 'n', 'r', 's', 'l',
            'cr', 'pr', 'tr', 'str', 'mal', 'mor', 'dis', 'ex',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ae', 'ei', 'ou', 'ia', 'uo',
        ],
        'codas': [
            'x', 'z', 'th', 'us', 'is', 'os', 'as', 'es',
            'nus', 'ris', 'tis', 'lus', 'mus', 'rex', 'lex',
        ],
        'templates': [('ONC', 4), ('ON', 3), ('NC', 2), ('ONC', 1)],
        'particles': ['et', 'ex', 'de', 'in', 'na', 'vo', 'ur'],
        'roots': [
            'asmod', 'mephist', 'dispat', 'zariel', 'baalz',
            'cania', 'nessus', 'phleg', 'stygr', 'avernus',
            'malbol', 'timat', 'regis', 'nexus', 'pactum',
        ],
        'min_syl': 2,
        'max_syl': 4,
    },

    # --- ABYSSAL ------------------------------------------------------------
    # Language of demons. Guttural, chaotic, glottal stops, dark vowels.
    # Unpredictable rhythm, harsh and unsettling.
    'abyssal': {
        'onsets': [
            'gh', 'kr', 'zr', 'gr', 'dr', "k'", "z'", "g'",
            'k', 'g', 'z', 'r', 'v', 'b', 'th', 'khr',
            'graz', 'zug', 'bak', 'vrk',
        ],
        'nuclei': [
            'a', 'u', 'o', 'aa', 'uu', 'ae', 'ua', 'uo', 'i',
        ],
        'codas': [
            'zt', 'rk', 'gz', 'kh', 'th', 'zz', "k'",
            'g', 'k', 'z', 'r', 'rg', 'zk', 'ghr',
        ],
        'templates': [('ONC', 4), ('NC', 3), ('ON', 2), ('ONCC', 1)],
        'particles': ["z'", 'uk', 'ga', 'rr', 'ak', 'ugh'],
        'roots': [
            "graz'zt", 'demog', 'orcus', 'zuggt', 'bapho',
            'yeenog', 'kossuth', 'thanat', 'vrak', 'ghaal',
            "k'thar", 'bazug', 'skraa', 'ghuul', 'drekk',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- CELESTIAL ----------------------------------------------------------
    # Language of angels/celestials. Melodic, harmonic, Greek/Hebrew inspired.
    # Long flowing syllables, soft consonants, diphthongs.
    'celestial': {
        'onsets': [
            's', 'l', 'r', 'n', 'm', 'th', 'ph', 'ch',
            'el', 'al', 'ar', 'sol', 'lum', 'ser', 'hal',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ae', 'ei', 'ia', 'oi',
            'ea', 'io', 'ue', 'au',
        ],
        'codas': [
            'l', 'n', 'r', 'th', 's', 'el', 'iel', 'ael',
            'im', 'on', 'an', 'em', 'is', 'en',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('N', 1)],
        'particles': [
            'al', 'el', 'na', 'sha', 'va', 'om', 'lu', 'ae',
        ],
        'roots': [
            'seraph', 'solan', 'lumin', 'halael', 'empyr',
            'archon', 'astral', 'celest', 'divin', 'etern',
            'gloris', 'sancth', 'thaum', 'verit', 'zaphk',
        ],
        'min_syl': 2,
        'max_syl': 4,
    },

    # --- DEEP SPEECH --------------------------------------------------------
    # Language of aberrations (mind flayers, beholders). Alien, unsettling,
    # impossible consonant clusters. Lovecraftian.
    'deep speech': {
        'onsets': [
            'cth', 'zth', 'ph', 'xr', 'zl', 'ng', "rl'",
            'fh', 'yg', 'nth', 'sht', "gl'", 'vl', 'zn',
        ],
        'nuclei': [
            'u', 'a', 'o', 'uu', 'aa', 'oe', 'ua', 'ia', 'uo',
        ],
        'codas': [
            'th', 'gn', 'lth', 'rn', 'gg', 'ph', "l'",
            'ngth', 'thk', 'ghul', 'zn', 'rgl',
        ],
        'templates': [('ONC', 4), ('NC', 3), ('ONCC', 2), ('ON', 1)],
        'particles': ["ph'", 'ng', 'ul', "r'", 'zz', "aa'"],
        'roots': [
            'cthul', 'nyarl', 'yog', 'shogg', 'dagon',
            'tsath', 'illith', 'xaris', 'gholam', 'voidr',
            "zul'k", 'eldrn', 'aberra', 'ulaam',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- GOBLIN -------------------------------------------------------------
    # Short, harsh, guttural barking. Crude and functional.
    'goblin': {
        'onsets': [
            'g', 'k', 'b', 'r', 'z', 'n', 'kr', 'gr', 'sk',
            'sn', 'sp', 'gn', 'br', 'tr', 'dr',
        ],
        'nuclei': ['a', 'u', 'i', 'o', 'e', 'ik', 'ak', 'uk'],
        'codas': [
            'k', 'g', 'b', 'z', 'rk', 'nk', 'gk', 'gg',
            'zz', 'bb', 'nt', 'tz', 'kt', 'sh',
        ],
        'templates': [('ONC', 5), ('ON', 3), ('NC', 2)],
        'particles': ['ik', 'uk', 'ga', 'na', 'za', 'ko'],
        'roots': [
            'grubb', 'snag', 'krik', 'zark', 'mug',
            'nib', 'skrit', 'grik', 'bozz', 'klak',
            'skritz', 'nakk', 'gruk', 'zib', 'tok',
        ],
        'min_syl': 1,
        'max_syl': 2,
    },

    # --- ORC ----------------------------------------------------------------
    # Brutal, heavy, grunting. Short aggressive syllables.
    'orc': {
        'onsets': [
            'gr', 'kr', 'dr', 'br', 'th', 'sk', 'g', 'k', 'b',
            'r', 'd', 'z', 'gh', 'ghr', 'shr', 'vr',
        ],
        'nuclei': ['a', 'u', 'o', 'aa', 'uu', 'agh', 'ugh', 'og'],
        'codas': [
            'k', 'g', 'th', 'rk', 'gh', 'rg', 'gk', 'zg',
            'rd', 'ng', 'nk', 'rm', 'gd', 'rkh',
        ],
        'templates': [('ONC', 5), ('ON', 2), ('NC', 2), ('ONC', 1)],
        'particles': ['ug', 'ok', 'ga', 'ra', 'zug', 'agh'],
        'roots': [
            'gruum', 'luth', 'ilnev', 'bahgt', 'yurtu',
            'skullk', 'thokk', 'vrag', 'grash', 'mogur',
            'krug', 'brug', 'zarak', 'durgat', 'gharl',
        ],
        'min_syl': 1,
        'max_syl': 2,
    },

    # --- SYLVAN -------------------------------------------------------------
    # Language of the fey. Musical, whimsical, trills and light sounds.
    # Similar to Elvish but more playful and unpredictable.
    'sylvan': {
        'onsets': [
            'f', 'l', 'r', 'w', 'y', 'n', 'fl', 'fr', 'wh',
            'tl', 'tr', 'pr', 'sp', 'tw', 'br', 'gl', 'bl',
        ],
        'nuclei': [
            'i', 'e', 'a', 'o', 'ie', 'ea', 'ai', 'oo', 'ee',
            'ia', 'io', 'ui',
        ],
        'codas': [
            'l', 'n', 'r', 'll', 'nn', 'th', 'ss', 'ff',
            'rn', 'lk', 'nd', 'rl', 'wn',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('N', 2), ('NC', 1)],
        'particles': [
            'ti', 'la', 'ri', 'fi', 'lo', 'na', 'wi', 'ye',
        ],
        'roots': [
            'twisp', 'flitt', 'briar', 'whims', 'glimm',
            'prill', 'froli', 'spinn', 'bloom', 'trill',
            'wilder', 'faerl', 'nymph', 'pixie', 'gleam',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- GIANT (Jotun) ------------------------------------------------------
    # Thunderous, booming, Norse-primitive. Simple but massive-sounding.
    'giant': {
        'onsets': [
            'th', 'hr', 'sk', 'st', 'gr', 'kr', 'br', 'dr',
            'g', 'k', 'r', 'j', 'h', 'v', 'str', 'skr',
        ],
        'nuclei': [
            'o', 'u', 'a', 'au', 'ou', 'oi', 'uu', 'aa', 'ei',
        ],
        'codas': [
            'r', 'n', 'g', 'rn', 'rm', 'ng', 'rd', 'rk',
            'nd', 'nn', 'rg', 'ndr', 'mm', 'ldr',
        ],
        'templates': [('ONC', 5), ('ON', 2), ('NC', 2), ('ONCC', 1)],
        'particles': ['ok', 'ja', 'ha', 'oi', 'ug', 'vor'],
        'roots': [
            'thund', 'jotunn', 'storm', 'hring', 'skald',
            'geirr', 'hrung', 'brann', 'grond', 'valdi',
            'bergr', 'fjall', 'helgr', 'mjoln', 'surtr',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- GNOMISH ------------------------------------------------------------
    # Quick, clipped, inventive. Lots of stops and fricatives, bright vowels.
    'gnomish': {
        'onsets': [
            'g', 'n', 'f', 'b', 'w', 't', 'p', 'z', 'kl',
            'fl', 'tw', 'sp', 'sn', 'qu', 'gl', 'pr', 'cr',
        ],
        'nuclei': [
            'i', 'e', 'a', 'o', 'u', 'ee', 'ii', 'ea', 'io', 'ie',
        ],
        'codas': [
            'k', 'p', 't', 'n', 'x', 'nk', 'ck', 'pp', 'tt',
            'ff', 'zz', 'mp', 'nt', 'nd', 'rk',
        ],
        'templates': [('ONC', 4), ('ON', 3), ('NC', 2), ('ON', 1)],
        'particles': [
            'ni', 'fi', 'bi', 'ge', 'po', 'ka', 'ze', 'wi',
        ],
        'roots': [
            'fizzl', 'tinkr', 'gizmo', 'sprck', 'whirr',
            'clickt', 'blink', 'gnurl', 'sparkl', 'widgt',
            'bopp', 'zapp', 'crink', 'flobb', 'prink',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- HALFLING (Luiric) --------------------------------------------------
    # Warm, pastoral, rustic. Old English countryside feel. Comfortable sounds.
    'halfling': {
        'onsets': [
            'b', 'd', 'f', 'g', 'h', 'l', 'm', 'n', 'p', 'r',
            'w', 'th', 'wh', 'br', 'gr', 'pr', 'tr', 'sw',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ea', 'ou', 'ow', 'ai', 'ee',
        ],
        'codas': [
            'n', 'l', 'r', 'th', 'ff', 'll', 'rn', 'ld',
            'nd', 'ng', 'nt', 'mp', 'rd', 'lm',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('ON', 1)],
        'particles': [
            'an', 'ol', 'em', 'un', 'le', 'er', 'me', 'we',
        ],
        'roots': [
            'burr', 'thorn', 'dell', 'holm', 'brook',
            'mead', 'fenn', 'barle', 'heath', 'shire',
            'bramb', 'roos', 'goodr', 'merri', 'swale',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- DRUIDIC ------------------------------------------------------------
    # Secret nature-language. Celtic/Gaelic feel — soft fricatives, 'wh',
    # diphthongs, rolling r's.
    'druidic': {
        'onsets': [
            'c', 'f', 'g', 'l', 'm', 'n', 'r', 's', 'th', 'wh',
            'dh', 'gh', 'br', 'cr', 'dr', 'gl', 'sl', 'sr',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ae', 'ai', 'ea', 'oi',
            'ui', 'ao', 'ia',
        ],
        'codas': [
            'n', 'r', 'l', 'th', 'dh', 'gh', 'nn', 'll',
            'rn', 'rr', 'ch', 'lf', 'rm', 'ng',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('N', 1)],
        'particles': [
            'an', 'na', 'le', 'fi', 'mo', 'ri', 'da', 'si',
        ],
        'roots': [
            'nemeth', 'derwi', 'ogham', 'crann', 'lugh',
            'duir', 'beith', 'nuin', 'saille', 'fern',
            'ailm', 'rowan', 'coll', 'muin', 'gort',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- PRIMORDIAL ---------------------------------------------------------
    # Language of elementals. Ancient, rumbling, elemental forces.
    # Deep vowels, resonant consonants.
    'primordial': {
        'onsets': [
            'r', 'th', 'gr', 'kr', 'v', 'z', 'm', 'n',
            'rum', 'thr', 'ghr', 'str', 'fl', 'br', 'dr',
        ],
        'nuclei': [
            'a', 'o', 'u', 'aa', 'oo', 'uu', 'au', 'ou', 'oa',
        ],
        'codas': [
            'r', 'm', 'n', 'rn', 'rm', 'nd', 'rr', 'mm',
            'ng', 'rd', 'rg', 'rl', 'nn', 'lg',
        ],
        'templates': [('ONC', 5), ('ON', 2), ('NC', 2), ('ONCC', 1)],
        'particles': ['om', 'ur', 'ra', 'ka', 'aa', 'vu'],
        'roots': [
            'rumbl', 'thundr', 'magma', 'geysr', 'tempe',
            'zephr', 'torrn', 'quakr', 'flamm', 'stonn',
            'vorte', 'tidal', 'cryst', 'surgi', 'erosi',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- UNDERCOMMON --------------------------------------------------------
    # Trade language of the Underdark. Dark, whispery, Drow-influenced.
    # Mix of Elvish elegance with sinister undertones.
    'undercommon': {
        'onsets': [
            'v', 'z', 'ss', 'sh', 'zh', 'dr', 'kr', 'n',
            'l', 'r', 'th', 'ph', 'qu', 'sl', 'gl',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ae', 'ei', 'ia', 'uu', 'ii',
        ],
        'codas': [
            'ss', 'zz', 'th', 'n', 'r', 'l', 'sh', 'zh',
            'rn', 'nd', 'rd', 'lth', 'nz', 'rl',
        ],
        'templates': [('ONC', 4), ('ON', 3), ('NC', 2), ('ON', 1)],
        'particles': [
            'zhi', 'va', 'ne', 'il', 'sha', 'dro', 'qu', 'ss',
        ],
        'roots': [
            'drizz', 'velsh', 'pharr', 'menzu', 'lloth',
            'shaalr', 'queth', 'vhael', 'sszen', 'daerl',
            'narbr', 'zilch', 'ertu', 'krenl', 'szith',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- COMMON -------------------------------------------------------------
    # Generic trade tongue. Bland mix of everything, simple and functional.
    'common': {
        'onsets': [
            'b', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p',
            'r', 's', 't', 'v', 'w', 'th', 'sh', 'ch', 'br', 'tr',
        ],
        'nuclei': [
            'a', 'e', 'i', 'o', 'u', 'ai', 'ou', 'ea', 'oo',
        ],
        'codas': [
            'n', 'r', 'l', 'k', 't', 'th', 'nd', 'rn', 'nt',
            'rd', 'lk', 'mp', 'ng', 'st',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('ON', 1)],
        'particles': ['an', 'de', 'lo', 'en', 'va', 'or', 'ke'],
        'roots': [
            'mark', 'hold', 'land', 'stead', 'ford',
            'glen', 'field', 'bridge', 'haven', 'stone',
            'brook', 'wall', 'gate', 'tower', 'crown',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },

    # --- KENDERSPEAK --------------------------------------------------------
    # Kender language (Dragonlance). Excitable, fast, sing-song.
    'kenderspeak': {
        'onsets': [
            'k', 't', 'p', 'b', 'f', 'w', 'n', 'l', 'r',
            'fl', 'tr', 'pr', 'tw', 'sk', 'sp', 'kl',
        ],
        'nuclei': [
            'i', 'e', 'a', 'ee', 'oo', 'ie', 'ai', 'ea', 'io',
        ],
        'codas': [
            'k', 'p', 'n', 'l', 'r', 'nk', 'ck', 'll',
            'pp', 'ff', 'ss', 'nt', 'nd',
        ],
        'templates': [('ON', 4), ('ONC', 3), ('NC', 2), ('ON', 1)],
        'particles': [
            'ee', 'oo', 'la', 'ti', 'ka', 'wi', 'po', 'fi',
        ],
        'roots': [
            'tassle', 'flint', 'kender', 'pouch', 'quick',
            'borrow', 'wander', 'trinkt', 'jingle', 'scampr',
        ],
        'min_syl': 1,
        'max_syl': 3,
    },
}

# Aliases so callers can use either name
LANGUAGE_PHONETICS['deep'] = LANGUAGE_PHONETICS['deep speech']


def _word_hash(word: str, language: str) -> int:
    """Deterministic hash for a (lowered word, language) pair."""
    data = f"{word.lower()}:{language}".encode('utf-8')
    return int(hashlib.md5(data).hexdigest(), 16)


def _pick(seq: list, rng: random.Random):
    """Pick a random element from *seq* using the given RNG."""
    return seq[rng.randint(0, len(seq) - 1)]


def _build_syllable(phon: dict, template: str, rng: random.Random) -> str:
    """Build one syllable from a template string (O=onset, N=nucleus, C=coda)."""
    parts = []
    for ch in template:
        if ch == 'O':
            parts.append(_pick(phon['onsets'], rng))
        elif ch == 'N':
            parts.append(_pick(phon['nuclei'], rng))
        elif ch == 'C':
            parts.append(_pick(phon['codas'], rng))
    return ''.join(parts)


def _weighted_choice(weighted: List[Tuple[str, int]], rng: random.Random) -> str:
    """Pick from a list of (value, weight) pairs."""
    total = sum(w for _, w in weighted)
    r = rng.randint(1, total)
    cumulative = 0
    for val, w in weighted:
        cumulative += w
        if r <= cumulative:
            return val
    return weighted[-1][0]


def generate_word(language: str, source_word: str = '', min_syl: int = 0, max_syl: int = 0) -> str:
    """Generate a gibberish word for *language*.

    Uses a deterministic seed based on *(source_word, language)* so the same
    English word always maps to the same gibberish within a language, giving
    the output a more consistent, real-language feel.
    """
    lang = language.lower()
    phon = LANGUAGE_PHONETICS.get(lang, LANGUAGE_PHONETICS['common'])

    # Seed the RNG deterministically from the source word
    seed = _word_hash(source_word, lang) if source_word else random.randint(0, 2**32)
    rng = random.Random(seed)

    lo = min_syl or phon['min_syl']
    hi = max_syl or phon['max_syl']

    # Scale output length loosely by input length
    src_len = len(source_word)
    if src_len <= 3:
        hi = min(hi, lo + 1)
    elif src_len >= 7:
        lo = max(lo, 2)

    num_syl = rng.randint(lo, hi)

    # ~25% chance to start with a lore root fragment
    if rng.random() < 0.25 and phon['roots']:
        root = _pick(phon['roots'], rng)
        # Trim root to a reasonable fragment length
        frag_len = rng.randint(2, min(len(root), 5))
        word = root[:frag_len]
        num_syl = max(0, num_syl - 1)
    else:
        word = ''

    for _ in range(num_syl):
        tmpl = _weighted_choice(phon['templates'], rng)
        word += _build_syllable(phon, tmpl, rng)

    # ~15% chance to append a particle as a suffix
    if rng.random() < 0.15 and phon['particles']:
        word += "'" + _pick(phon['particles'], rng)

    return word


def gibberish(text: str, language: str = 'common') -> str:
    """Transform English text into fantasy language gibberish.

    Preserves punctuation, whitespace, and capitalisation patterns.
    The same source word always produces the same output for a given language
    so the result reads more like an actual foreign language.
    """
    tokens = re.findall(r'\b\w+\b|[^\w\s]|\s+', text)

    transformed: list[str] = []
    for token in tokens:
        if re.match(r'\b\w+\b', token):
            word = generate_word(language, source_word=token)
            # Preserve capitalisation
            if token.isupper():
                word = word.upper()
            elif token[0].isupper():
                word = word.capitalize()
            transformed.append(word)
        else:
            transformed.append(token)

    return ''.join(transformed) 