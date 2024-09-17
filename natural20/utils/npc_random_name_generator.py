import random

# Syllable pools for goblinoid names
goblin_prefixes = ['Gor', 'Nar', 'Thak', 'Krul', 'Hruk', 'Rok', 'Brak', 'Vrog', 'Zug', 'Darg']
goblin_middles = ['rag', 'bog', 'tur', 'gan', 'gar', 'bak', 'mok', 'duk', 'zar', 'vak']
goblin_suffixes = ['nak', 'zuk', 'rak', 'gor', 'zug', 'tuk', 'mak', 'rog', 'dash', 'bar']

# Syllable pools for ogre names (simpler, brutish sounds)
ogre_prefixes = ['Ugg', 'Grum', 'Thog', 'Bro', 'Mug', 'Drog', 'Hog', 'Tor', 'Ruk', 'Brog']
ogre_suffixes = ['thak', 'mok', 'zug', 'gak', 'grok', 'rag', 'tar', 'mog', 'buk', 'tak']

# Function to generate random goblinoid names
def generate_goblinoid_name():
    include_middle = random.choice([True, False])
    if include_middle:
        name = random.choice(goblin_prefixes) + random.choice(goblin_middles) + random.choice(goblin_suffixes)
    else:
        name = random.choice(goblin_prefixes) + random.choice(goblin_suffixes)
    return name

# Function to generate random ogre names
def generate_ogre_name():
    # Ogres generally have shorter, brutish names with only a prefix and suffix
    name = random.choice(ogre_prefixes) + random.choice(ogre_suffixes)
    return name

# Generate multiple goblinoid names
def generate_goblinoid_names(count=10):
    return [generate_goblinoid_name() for _ in range(count)]

# Generate multiple ogre names
def generate_ogre_names(count=10):
    return [generate_ogre_name() for _ in range(count)]

# Example usage
goblin_names = generate_goblinoid_names(10)
ogre_names = generate_ogre_names(10)

print("Goblinoid Names:")
for name in goblin_names:
    print(name)

print("\nOgre Names:")
for name in ogre_names:
    print(name)
