# Create NPC Skill

Guide for creating new NPCs for Natural20 campaigns with complete asset generation.

## Workflow

### 1. Create NPC YAML File

Location: `user_levels/<campaign>/npcs/<npc_name>.yml`

```yaml
uid: npc_<name_snake_case>
entity_uid: npc_<name_snake_case>   # Stable unique id; NPC Spawner shows Unique and moves instead of duplicating
kind: Commoner
description: <one-line description>
physical_description: |
  Detailed physical appearance matching the portrait image.
  Include hair color/style, eye color, build, skin tone, distinctive features.
outward_appearance: >
  Scene description for narration: what the NPC looks like in context.
passive_perception: 12
ability:
  str: 10
  dex: 12
  con: 10
  int: 10
  wis: 14
  cha: 12
skills:
  - perception
  - insight
race: Human
alignment: Neutral Good
size: Medium
speed: 30
ac: 10
hp: 10
portrait_scene: <portrait generation prompt>
token_image: token_<name>.png        # Path relative to campaign root
profile_image: portraits/<name>.jpg  # Path relative to campaign root
voice:
  prompt: "<voice style description for TTS>"
  reference_audio: assets/voice_<name>.wav
  strategy: clone
  locked: true
backstory: |
  Multi-line backstory here
conversation_buffer:
  - message: "Greeting message."
    target: all
backstory_buffer:
  - message: "Hidden backstory reveal message."
    target: all
conversation_keywords:
  - keyword: topic_name
    update_state:
      - map: map_name
        target: area_name
        state: state_name

# IMPORTANT: Only include equipped items that exist in templates.
# Cosmetic clothing (cardigan, jeans, etc.) must NOT be in equipped
# unless they are defined in templates/items/*.yml
equipped:
  - company_badge   # Only include valid template items
```

#### 1a. Physical Description Guidelines
- **Match the portrait image**: Hair color/style, eye color, clothing, accessories
- **Include clothing details**: What they wear is visible in-game
- **Be specific**: "Strawberry blonde wavy hair with dark headband" not just "blonde"
- **Include height/build**: e.g., "5'4", slim/average build"

### 2. Validate Equipped Items (CRITICAL)

**DO NOT add clothing or cosmetic items to `equipped:` unless they exist in the templates.**

The engine will try to load every item in `equipped:` as a template object. Missing items cause a hard crash:

```
AssertionError: Object cardigan_sweater not found
```

**Safe approach:**
- Only include items known to exist in `templates/items/*.yml` (e.g., `company_badge`, `smartphone`)
- **Exclude**: cardigan_sweater, jeans, canvas_sneakers, hoop_earrings, necklace, wristwatch, etc.
- If an item isn't in templates, describe it in `physical_description` instead
- Comment out unknown items for reference but keep them out of `equipped:`

```yaml
# WRONG - causes crash:
equipped:
  - company_badge
  - cardigan_sweater    # NOT in templates!
  - jeans               # NOT in templates!
  - canvas_sneakers     # NOT in templates!

# CORRECT - only template items:
equipped:
  - company_badge
  # Clothing described in physical_description instead
```

Add entry to `user_levels/<campaign>/index.json` → `npcs` array:
```json
{
  "name": "NPC Display Name",
  "file": "npcs/<npc_name>.yml"
}
```

### 3. Generate Voice Assets

#### 3a. Prepare Reference Audio
- Place reference audio in `user_levels/<campaign>/references/<name>/`
- Convert to WAV (24kHz, mono, 16-bit):
  ```bash
  ffmpeg -i ref.mp3 -ar 24000 -ac 1 voice_sample.wav
  ```

#### 3b. Create Voice Samples Directory
```bash
mkdir -p user_levels/<campaign>/assets/voice_samples/
cp voice_sample.wav user_levels/<campaign>/assets/voice_samples/<name>.wav
echo "<reference text>" > user_levels/<campaign>/assets/voice_samples/<name>.wav.ref.txt
```

#### 3c. Register Voice with vLLM Server
```bash
cd services/vllm-omni-tts
VLLM_OMNI_TTS_URL=http://<server>:8091 python scripts/register_campaign_voices.py \
  ../../user_levels/<campaign> --force
```

#### 3d. Generate Greeting Audio
```bash
curl -X POST "http://<server>:8091/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "input": "<greeting text>",
    "voice": "n20_<name>",
    "language": "English",
    "response_format": "wav"
  }' -o user_levels/<campaign>/assets/voice_<name>.wav
```

### 4. Generate Image Assets

#### 4a. Portrait
- Use reference image or generate via image service
- Save to `user_levels/<campaign>/assets/portraits/<name>.jpg`

#### 4b. Token
Generate circular token from portrait:
```python
from PIL import Image, ImageDraw

img = Image.open('portrait.jpg').resize((96, 96))
mask = Image.new('L', (96, 96), 0)
ImageDraw.Draw(mask).ellipse([0, 0, 96, 96], fill=255)
result = Image.new('RGBA', (96, 96), (0,0,0,0))
result.paste(img.convert('RGBA'), (0, 0), mask)
ImageDraw.Draw(result).ellipse([0,0,96,96], outline=(255,215,0,255), width=3)
result.save('token.png', 'PNG')
```

### 5. Add Legend Entry to Map (CRITICAL)

**This step is required for the NPC to appear on the map.** Without a legend entry, the map entity token will not resolve to an NPC.

Add to map YAML `legend` section:
```yaml
legend:
  NPC_TOKEN:        # Must match the token used in entities below
    name: NPC Display Name
    type: npc
    sub_type: npc_filename      # Matches the YAML filename (e.g. pam_beesly)
    group: c                    # 'c' for civilian/neutral, 'a' for player party, 'b'/'hostile' for enemies
    overrides:
      entity_uid: npc_uid       # Must match the NPC's entity_uid or filename
      token_image: token_name.png
      profile_image: portraits/name.jpg
      label: Display Name
      dialog: true
      passive: true
      voice:
        prompt: "Voice style description"
        style: friendly
        accent: american
        language: en
      backstory: |
        Brief NPC backstory for the game engine.
      conversation_buffer:
      - message: "Greeting message."
        target: all
```

> **Path convention**: Use paths relative to campaign root (e.g., `token_name.png`, NOT `assets/token_name.png`).

### 6. Place Entity on Map

Add to map YAML `entities` array (the `token` must match the legend key):
```yaml
entities:
- token: NPC_TOKEN    # Must match the legend entry key above
  pos:
  - x
  - y
```

### 7. Update Map Narration

Add NPC introduction to `on_enter` narration in map YAML.

## Key Patterns

- **UID format**: `npc_<name_snake_case>`
- **Voice prefix**: `n20_<name>` for vLLM registration
- **Voice sample location**: `assets/voice_samples/<name>.wav`
- **Ref text sidecar**: `assets/voice_samples/<name>.wav.ref.txt`
- **Token size**: 96x96 pixels, circular with gold border
- **Portrait aspect**: Square crop centered on face

## Dependencies

- vLLM-Omni TTS server running (`services/vllm-omni-tts/`)
- `httpx` for voice registration script
- `Pillow` for token generation
- `ffmpeg` for audio conversion
