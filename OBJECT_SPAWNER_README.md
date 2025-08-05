# Object Spawner Feature

This feature allows DMs to drag and drop objects onto the battle map similar to how NPCs and player characters are handled.

## What was implemented:

### Backend (Python)
1. **New Routes:**
   - `/available_objects` - GET endpoint that returns a list of placeable objects from `objects.yml`
   - `/spawn_object` - POST endpoint that spawns objects at specified coordinates

2. **Object Loading:**
   - Uses existing `game_session.load_yaml_file('items', 'objects')` to load all objects
   - Filters objects by `placeable: true` property (defaults to true if not specified)
   - Returns object metadata including name, description, AC, HP, etc.

### Frontend (JavaScript/HTML)
1. **UI Components:**
   - Object Spawner window with search functionality
   - Menu item to toggle Object Spawner visibility
   - Visual styling consistent with NPC and PC spawners

2. **Drag & Drop:**
   - Objects can be dragged from the spawner onto any map tile
   - Visual feedback during drag operations
   - Unlike NPCs/PCs, objects can be placed on occupied tiles
   - Supports all map tiles (not just empty ones)

3. **Styling:**
   - Orange/amber color scheme for object spawner
   - Consistent with existing UI patterns
   - Proper hover effects and drag feedback

## How to use:

1. **As a DM:**
   - Open the hamburger menu
   - Click "Object Spawner"
   - Search for objects using the search box
   - Drag objects from the list onto the map
   - Objects will be spawned at the drop location

2. **Object Configuration:**
   - Objects are loaded from `templates/items/objects.yml`
   - Set `placeable: true` for objects that should appear in spawner
   - Set `placeable: false` to hide objects from spawner
   - Objects support all standard properties (AC, HP, passable, etc.)

## Files Modified:

### Backend:
- `webapp/app.py` - Added new routes and object handling logic

### Frontend:
- `webapp/templates/index.html` - Added object spawner UI components
- `webapp/static/styles.css` - Added object spawner styling
- `webapp/static/engine.js` - Added drag & drop functionality

### Example objects.yml structure:
```yaml
barrel:
  color: brown
  cover: half
  default_ac: 15
  hp_die: 4d8
  max_hp: 18
  name: Barrel
  placeable: true  # This makes it appear in spawner
  token_image: barrel.png

secret_door:
  name: Secret Door
  placeable: false  # This hides it from spawner
  # ... other properties
```

## Technical Notes:

- Objects use the existing `Object` class from `natural20.item_library.object`
- Object placement uses `battle_map.place_object()` method
- Objects with interactions are automatically added to `interactable_objects`
- Supports all object properties like light sources, traps, containers, etc.
- Token images are loaded from `/assets/objects/` directory
- Falls back to `/assets/token_object.png` if image not found

## Integration:

This feature integrates seamlessly with the existing game system:
- Objects appear in the map renderer
- Objects can be interacted with using existing interaction system
- Objects persist in game state and save files
- Objects work with existing light, cover, and movement systems
