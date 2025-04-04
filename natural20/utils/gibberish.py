"""
Utility function to transform English text into fantasy language gibberish.
This is used when a character speaks in a language that the listener doesn't understand.
"""

import random
import re

# Phoneme patterns for different fantasy languages
LANGUAGE_PATTERNS = {
    'abyssal': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstvxz',
        'syllables': ['th', 'sh', 'ch', 'kh', 'zh', 'gh'],
        'word_endings': ['oth', 'ath', 'eth', 'ith', 'uth'],
        'prefixes': ['za', 'ka', 'ma', 'na', 'ra'],
        'suffixes': ['oth', 'ath', 'eth', 'ith', 'uth'],
    },
    'celestial': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['iel', 'ael', 'eel', 'iel', 'uel'],
        'prefixes': ['ae', 'ce', 'de', 'fe', 'ge'],
        'suffixes': ['iel', 'ael', 'eel', 'iel', 'uel'],
    },
    'common': {
        'vowels': 'aeiou',
        'consonants': 'bcdfghjklmnpqrstvwxyz',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['ing', 'ed', 'ly', 'ful', 'ous'],
        'prefixes': ['un', 're', 'in', 'dis', 'mis'],
        'suffixes': ['ing', 'ed', 'ly', 'ful', 'ous'],
    },
    'deep': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['oth', 'ath', 'eth', 'ith', 'uth'],
        'prefixes': ['za', 'ka', 'ma', 'na', 'ra'],
        'suffixes': ['oth', 'ath', 'eth', 'ith', 'uth'],
    },
    'draconic': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstvxz',
        'syllables': ['th', 'sh', 'ch', 'kh', 'zh', 'gh'],
        'word_endings': ['ax', 'ix', 'ox', 'ux', 'yx'],
        'prefixes': ['drak', 'krax', 'max', 'nax', 'rax'],
        'suffixes': ['ax', 'ix', 'ox', 'ux', 'yx'],
    },
    'druidic': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['orn', 'arn', 'ern', 'irn', 'urn'],
        'prefixes': ['ae', 'ce', 'de', 'fe', 'ge'],
        'suffixes': ['orn', 'arn', 'ern', 'irn', 'urn'],
    },
    'dwarvish': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['or', 'ar', 'er', 'ir', 'ur'],
        'prefixes': ['dor', 'gar', 'mor', 'nor', 'tor'],
        'suffixes': ['or', 'ar', 'er', 'ir', 'ur'],
    },
    'elvish': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['iel', 'ael', 'eel', 'iel', 'uel'],
        'prefixes': ['ae', 'ce', 'de', 'fe', 'ge'],
        'suffixes': ['iel', 'ael', 'eel', 'iel', 'uel'],
    },
    'giant': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['or', 'ar', 'er', 'ir', 'ur'],
        'prefixes': ['dor', 'gar', 'mor', 'nor', 'tor'],
        'suffixes': ['or', 'ar', 'er', 'ir', 'ur'],
    },
    'gnomish': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['in', 'an', 'en', 'in', 'un'],
        'prefixes': ['din', 'gin', 'min', 'nin', 'tin'],
        'suffixes': ['in', 'an', 'en', 'in', 'un'],
    },
    'goblin': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['uk', 'ak', 'ek', 'ik', 'uk'],
        'prefixes': ['duk', 'gak', 'muk', 'nak', 'ruk'],
        'suffixes': ['uk', 'ak', 'ek', 'ik', 'uk'],
    },
    'halfling': {
        'vowels': 'aeiou',
        'consonants': 'bcdfghjklmnpqrstvwxyz',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['ing', 'ed', 'ly', 'ful', 'ous'],
        'prefixes': ['un', 're', 'in', 'dis', 'mis'],
        'suffixes': ['ing', 'ed', 'ly', 'ful', 'ous'],
    },
    'infernal': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstvxz',
        'syllables': ['th', 'sh', 'ch', 'kh', 'zh', 'gh'],
        'word_endings': ['oth', 'ath', 'eth', 'ith', 'uth'],
        'prefixes': ['za', 'ka', 'ma', 'na', 'ra'],
        'suffixes': ['oth', 'ath', 'eth', 'ith', 'uth'],
    },
    'orc': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['uk', 'ak', 'ek', 'ik', 'uk'],
        'prefixes': ['duk', 'gak', 'muk', 'nak', 'ruk'],
        'suffixes': ['uk', 'ak', 'ek', 'ik', 'uk'],
    },
    'primordial': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['or', 'ar', 'er', 'ir', 'ur'],
        'prefixes': ['dor', 'gar', 'mor', 'nor', 'tor'],
        'suffixes': ['or', 'ar', 'er', 'ir', 'ur'],
    },
    'sylvan': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['orn', 'arn', 'ern', 'irn', 'urn'],
        'prefixes': ['ae', 'ce', 'de', 'fe', 'ge'],
        'suffixes': ['orn', 'arn', 'ern', 'irn', 'urn'],
    },
    'undercommon': {
        'vowels': 'aeiou',
        'consonants': 'bdghjklmnprstv',
        'syllables': ['th', 'sh', 'ch', 'ph', 'wh'],
        'word_endings': ['oth', 'ath', 'eth', 'ith', 'uth'],
        'prefixes': ['za', 'ka', 'ma', 'na', 'ra'],
        'suffixes': ['oth', 'ath', 'eth', 'ith', 'uth'],
    },
}

def generate_syllable(language: str) -> str:
    """Generate a random syllable for the given language."""
    patterns = LANGUAGE_PATTERNS.get(language, LANGUAGE_PATTERNS['common'])
    
    # 30% chance to use a special syllable
    if random.random() < 0.3 and patterns['syllables']:
        return random.choice(patterns['syllables'])
    
    # Otherwise generate a consonant-vowel-consonant pattern
    c1 = random.choice(patterns['consonants'])
    v = random.choice(patterns['vowels'])
    c2 = random.choice(patterns['consonants'])
    return f"{c1}{v}{c2}"

def generate_word(language: str, min_syllables: int = 1, max_syllables: int = 3) -> str:
    """Generate a random word for the given language."""
    patterns = LANGUAGE_PATTERNS.get(language, LANGUAGE_PATTERNS['common'])
    
    # Determine number of syllables
    num_syllables = random.randint(min_syllables, max_syllables)
    
    # 20% chance to add a prefix
    prefix = random.choice(patterns['prefixes']) if random.random() < 0.2 else ""
    
    # Generate the main part of the word
    word = prefix
    for _ in range(num_syllables):
        word += generate_syllable(language)
    
    # 20% chance to add a suffix
    suffix = random.choice(patterns['suffixes']) if random.random() < 0.2 else ""
    word += suffix
    
    return word

def gibberish(text: str, language: str = 'common') -> str:
    """
    Transform English text into fantasy language gibberish.
    
    Args:
        text: The English text to transform
        language: The fantasy language to transform into
        
    Returns:
        The transformed text in the fantasy language
    """
    # Split the text into words while preserving punctuation and spacing
    words = re.findall(r'\b\w+\b|[^\w\s]|\s+', text)
    
    # Transform each word
    transformed_words = []
    for word in words:
        if re.match(r'\b\w+\b', word):  # If it's a word
            # Preserve capitalization
            if word.isupper():
                transformed_words.append(generate_word(language.lower(), 2, 4).upper())
            elif word[0].isupper():
                transformed_words.append(generate_word(language.lower(), 2, 4).capitalize())
            else:
                transformed_words.append(generate_word(language.lower(), 1, 3))
        else:  # If it's punctuation or whitespace
            transformed_words.append(word)
    
    return ''.join(transformed_words) 