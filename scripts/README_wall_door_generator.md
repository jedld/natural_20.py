# Wall and Door Tile Generator

This utility script generates PNG images for D&D-style walls and doors that can be used in tabletop gaming applications.

## Features

- Generate square PNG tiles with customizable dimensions
- Add walls on any combination of sides (top, bottom, left, right)
- Add wooden doors on any wall side
- Configurable wall thickness and door width
- D&D-style stone walls and wooden doors with 3D effects
- Stone floor texture background
- **Auto-generate from objects.yml files** - automatically create tiles for `DoorObjectWall` and `StoneWallDirectional` objects

## Requirements

```bash
pip install Pillow
```

## Usage

### Command Line Interface

```bash
python scripts/generate_wall_door_tile.py [options]
```

#### Options:

- `--size SIZE`: Size of the square image in pixels (default: 64)
- `--walls WALLS [WALLS ...]`: Locations of walls (choices: top, bottom, left, right)
- `--door DOOR`: Location of door (choices: top, bottom, left, right) - must be on a wall
- `--door-width WIDTH`: Width of the door opening in pixels (default: 32)
- `--wall-thickness THICKNESS`: Thickness of walls in pixels (default: 10)
- `--output OUTPUT`: Output filename (default: tile.png)
- `--yaml YAML_FILE`: Path to objects.yml file to auto-generate tiles from
- `--output-dir OUTPUT_DIR`: Output directory for auto-generated tiles (default: generated_tiles)

#### Examples:

```bash
# Generate a corner room with walls on top and left
python scripts/generate_wall_door_tile.py --walls top left --output corner.png

# Generate a room with walls on all sides and a door on the bottom
python scripts/generate_wall_door_tile.py --walls top bottom left right --door bottom --output room_with_door.png

# Generate a larger tile (128x128) with a wider door
python scripts/generate_wall_door_tile.py --size 128 --walls top bottom left right --door right --door-width 40 --output large_room.png

# Generate a horizontal corridor
python scripts/generate_wall_door_tile.py --walls top bottom --output corridor.png

# Generate just a single wall
python scripts/generate_wall_door_tile.py --walls top --output wall.png

# Auto-generate tiles from objects.yml file
python scripts/generate_wall_door_tile.py --yaml tests/fixtures/items/objects.yml

# Auto-generate with custom size and output directory
python scripts/generate_wall_door_tile.py --yaml path/to/objects.yml --size 128 --output-dir my_tiles
```

### Auto-Generation from YAML Files

The script can automatically generate tiles for `DoorObjectWall` and `StoneWallDirectional` objects defined in YAML files:

```bash
python scripts/generate_wall_door_tile.py --yaml path/to/objects.yml
```

The script will:
- Parse the YAML file for objects with `item_class: DoorObjectWall` or `item_class: StoneWallDirectional`
- Read the `border` array `[top, right, bottom, left]` to determine wall placement
- Read the `door_pos` value (0=top, 1=right, 2=bottom, 3=left) for door placement
- Generate appropriately named PNG files with suffixes like `_door_top`, `_wall_left_right`, etc.

#### YAML Object Properties

The script looks for these properties in your objects.yml:

```yaml
my_door:
  item_class: DoorObjectWall
  border: [1, 1, 0, 1]  # walls on top, right, and left
  door_pos: 2           # door on bottom
  name: "My Custom Door"

my_wall:
  item_class: StoneWallDirectional  
  border: [1, 0, 1, 0]  # walls on top and bottom
  name: "Horizontal Wall"
```

### Python API

You can also use the function directly in your Python code:

```python
from scripts.generate_wall_door_tile import create_wall_door_tile

# Generate a tile programmatically
create_wall_door_tile(
    size=64,
    walls=['top', 'left'],
    door_location='top',
    door_width=20,
    wall_thickness=10,
    output_path='my_tile.png'
)
```

### Generate Examples

Run the example generator to see various tile configurations:

```bash
python scripts/generate_examples.py
```

This will create an `example_tiles` directory with several sample tiles showing different wall and door combinations.

### Test YAML Generation

Test the YAML functionality with the provided test fixtures:

```bash
python scripts/test_yaml_generation.py
```

## Tile Specifications

- **Wall Thickness**: Default 10px (configurable)
- **Door Width**: Default 20px (configurable)
- **Colors**:
  - Stone floor: #8B7355 (sandy brown)
  - Walls: #4A4A4A (dark gray) with 3D highlights/shadows
  - Doors: #8B4513 (saddle brown) with wooden texture
  - Door handles: #FFD700 (gold)

## Use Cases

- D&D map tiles
- Dungeon generators
- Board game assets
- RPG map creation tools
- Tabletop gaming applications

## Output

The script generates PNG images with:
- Stone textured floor background
- 3D-effect stone walls on specified sides
- Wooden doors with panels and handles
- Proper transparency for integration with mapping tools
