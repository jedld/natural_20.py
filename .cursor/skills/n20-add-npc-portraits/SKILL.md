---
name: n20-add-npc-portraits
description: >-
  Add or extend JRPG-style character portrait references for NPC conversational dialogue
  in Natural20. Use when an NPC needs multiple portrait images for dynamic JRPG dialog,
  when setting up portrait-based conversation for a campaign NPC, or when the user asks
  how to add character portraits to NPC YAML for conversation context.
---

# Natural20 — add NPC portraits for JRPG dialog

## Overview

Add `image_gallery` entries to an NPC YAML file so the LLM conversation system can
dynamically switch portraits during JRPG dialog. Each gallery entry is a reference image
with contextual metadata describing when the LLM should use it.

## Prerequisites

- Identify the NPC YAML file (e.g. `user_levels/<campaign>/npcs/<npc>.yml`).
- Gather reference images (photos, AI generations, artwork) showing the character in
  various poses/moods/outfits suitable for dialog context.
- Confirm the character's `portrait_scene` value (used as fallback for scene generation).

## Step-by-step

### 1. Copy reference images to campaign portraits directory

```bash
# Target directory: user_levels/<campaign>/assets/portraits/
cp references/<source_image>.png user_levels/<campaign>/assets/portraits/<npc>_<context>.jpg
```

**Naming convention:** `<npc>_<context>.jpg` where `<context>` describes the pose or mood:
- `standing` — full-body standing pose, greetings
- `sitting_chair` — formal seated pose
- `sitting_crossed_legs` — relaxed, casual
- `sitting_formal` — professional, serious
- `sitting_smiling` — enthusiastic, welcoming
- `crouching` — playful, inspecting
- `leaning` — casual, off-guard
- `walking` — in motion
- `flirtatious` — letting guard down, intimate
- Adjust context names to match the actual image content

**Image format:** JPG preferred (smaller file size). Ensure images are reasonable resolution
(under 2MB ideal, up to 5MB acceptable).

### 2. Add `image_gallery` entries to NPC YAML

Insert the `image_gallery` block after the `profile_image` field in the NPC YAML:

```yaml
profile_image: portraits/<npc>.jpg
image_gallery:
- id: standing
  label: Standing
  image: portraits/<npc>_standing.jpg
  description: Full-body shot of [Name] [pose description], [outfit details], [mood]. Use for [context 1], [context 2], and [context 3].
- id: sitting_chair
  label: Sitting in Chair
  image: portraits/<npc>_sitting_chair.jpg
  description: [Name] sitting upright in a wooden office chair, [pose], [expression]. Use for meeting discussions, one-on-one conversations, and office strategy sessions.
# ... more entries
size: medium
```

**Field descriptions:**
- `id`: Unique identifier used in `[PORTRAIT: <id>]` tokens during conversation. Must be unique within the gallery.
- `label`: Human-readable display name for the character sheet UI.
- `image`: Path relative to campaign root (e.g. `portraits/<npc>_standing.jpg`).
- `description`: Contextual description that the LLM reads to decide when to use this portrait. Include:
  - Physical description (pose, outfit)
  - Mood/expression
  - 3 specific use cases (e.g., "introductions, office greetings, hallway encounters")

### 3. Gallery entry count

Aim for **6-12 portrait entries** per NPC for good variety:
- **1-2** standing/full-body poses for greetings
- **2-3** sitting poses for conversations
- **1-2** mood-specific poses (formal, playful, flirtatious)
- **1** candid/off-guard pose for surprise moments
- **1-2** situation-specific poses (inspecting, reacting)

## Example: Pip the Barmaid (wild_sheep_chase)

Reference: [`user_levels/wild_sheep_chase/npcs/pip_barmaid.yml`](user_levels/wild_sheep_chase/npcs/pip_barmaid.yml)

```yaml
image_gallery:
- id: portrait
  label: Portrait
  image: portraits/portrait_pip.jpg
  description: Close-up head-and-shoulders portrait for normal banter, greetings, and everyday tavern conversation.
- id: full_body
  label: Full Body
  image: portraits/full_body_pip.jpg
  description: Full-body tavern view in her green dress and apron. Use when leaning in flirtatiously, showing off her outfit, serving drinks, or playful body language.
- id: bedroom_doorway
  label: Bedroom Doorway
  image: portraits/pip_bedroom_doorway.jpg
  gallery_scene: tavern_bedroom
  description: Pip in her barmaid dress at a tavern guest-room doorway. Use when inviting someone upstairs, teasing about a private room, or lingering at a bedroom door.
  gallery_prompt: Short halfling barmaid Pip four feet tall at tavern bedroom doorway, green dress low neckline mid-thigh skirt white apron, chestnut curls freckles flirtatious smile on doorframe, timber guest room lamplight, painterly fantasy halfling
```

Note: Some entries include `gallery_scene` (maps to a scene context for AI generation) and
`gallery_prompt` (override prompt for AI image regeneration). These are optional and only
needed when generating new images via the asset pipeline.

## How the LLM uses portraits

The [`entity_rag_handler.npc_image_gallery_guidance_for_conversation()`](n20-webapp/webapp/entity_rag_handler.py:2522)
method reads `image_gallery` entries and injects portrait selection guidance into the NPC's
conversation prompt when the gallery has more than one entry:

```
- You may set your JRPG dialog portrait with [PORTRAIT: <id>] before your spoken line.
  Pick the id that best matches mood, pose, outfit, and the current situation.
  Available portraits:
  - standing: Full-body shot of [Name]...
  - sitting_chair: [Name] sitting upright...
  ...
- Omit [PORTRAIT: ...] to keep the default portrait. Only use ids from this list.
```

The LLM then emits `[PORTRAIT: sitting_chair]` tokens in its responses, which the webapp
resolves to the appropriate image path via [`Entity.resolve_gallery_image()`](natural20/entity.py:210).

## Verification

```python
import yaml
with open('user_levels/<campaign>/npcs/<npc>.yml') as f:
    data = yaml.safe_load(f)
gallery = data.get('image_gallery', [])
print(f'Gallery entries: {len(gallery)}')
for entry in gallery:
    print(f'  - {entry.get("id")}: {entry.get("description")[:60]}...')
```

Also verify images exist:
```bash
ls user_levels/<campaign>/assets/portraits/<npc>_*
```

## When to skip

- NPC has only one portrait (use `profile_image` alone — gallery guidance is skipped for single-entry galleries).
- NPC is not used in conversation/dialog (no `dialog: true` or `passive: true` in YAML).
- Campaign is purely battle-focused with no conversational elements.

## Related

- [`natural20/entity.py`](natural20/entity.py:141) — `image_gallery()` and `resolve_gallery_image()` methods
- [`n20-webapp/webapp/entity_rag_handler.py`](n20-webapp/webapp/entity_rag_handler.py:2522) — `npc_image_gallery_guidance_for_conversation()`
- [`n20-webapp/webapp/conversation_service.py`](n20-webapp/webapp/conversation_service.py:2808) — Gallery guidance injected into NPC conversation prompts
- [`scripts/generate_npc_gallery_images.py`](scripts/generate_npc_gallery_images.py) — AI image generation script for NPC portraits
- [`natural20/image_gen/campaign_assets.py`](natural20/image_gen/campaign_assets.py:307) — `npc_gallery_entries()` and `ensure_npc_image_gallery_entry()`
