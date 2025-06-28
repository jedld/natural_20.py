"""
Game Context Functions for LLM RAG System

This module provides functions that can be called by the LLM to retrieve
current game state information for the VTT system.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class GameContextProvider:
    """Provides game context information for the LLM RAG system."""
    
    def __init__(self, game_session, current_game):
        self.game_session = game_session
        self.current_game = current_game
    
    def get_map_info(self) -> Dict[str, Any]:
        """Get current map information including terrain, layout, and basic details."""
        try:
            # Get current map for the session
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return {"error": "No current map available"}
            
            map_info = {
                "name": battle_map.name,
                "size": battle_map.size if hasattr(battle_map, 'size') else None,
                "feet_per_grid": battle_map.feet_per_grid if hasattr(battle_map, 'feet_per_grid') else 5,
                "background_image": getattr(battle_map, 'background_image', None),
                "description": getattr(battle_map, 'description', 'No description available'),
                "properties": getattr(battle_map, 'properties', {})
            }
            
            # Add terrain information if available
            if hasattr(battle_map, 'terrain'):
                map_info["terrain"] = {
                    "difficult_terrain": getattr(battle_map.terrain, 'difficult_terrain', []),
                    "impassable": getattr(battle_map.terrain, 'impassable', [])
                }
            
            return map_info
            
        except Exception as e:
            logger.error(f"Error getting map info: {e}")
            return {"error": str(e)}
    
    def get_entities(self) -> List[Dict[str, Any]]:
        """Get all entities on the current map with their positions and basic information."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return []
            
            entities = []
            for entity in battle_map.entities:
                try:
                    entity_info = {
                        "name": entity.label() if hasattr(entity, 'label') else str(entity),
                        "type": entity.__class__.__name__,
                        "entity_uid": getattr(entity, 'entity_uid', None),
                        "position": battle_map.entity_or_object_pos(entity) if hasattr(battle_map, 'entity_or_object_pos') else None
                    }
                    
                    # Add additional entity properties
                    if hasattr(entity, 'hp'):
                        entity_info["hp"] = entity.hp
                        entity_info["max_hp"] = getattr(entity, 'max_hp', entity.hp)
                    
                    if hasattr(entity, 'ac'):
                        entity_info["ac"] = entity.ac
                    
                    if hasattr(entity, 'level'):
                        entity_info["level"] = entity.level
                    
                    if hasattr(entity, 'dead'):
                        entity_info["dead"] = entity.dead()
                    
                    if hasattr(entity, 'unconscious'):
                        entity_info["unconscious"] = entity.unconscious()
                    
                    if hasattr(entity, 'prone'):
                        entity_info["prone"] = entity.prone()
                    
                    if hasattr(entity, 'hidden'):
                        entity_info["hidden"] = entity.hidden()
                    
                    entities.append(entity_info)
                    
                except Exception as e:
                    logger.error(f"Error processing entity {entity}: {e}")
                    continue
            
            return entities
            
        except Exception as e:
            logger.error(f"Error getting entities: {e}")
            return []
    
    def get_player_characters(self) -> List[Dict[str, Any]]:
        """Get information about player characters on the current map."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return []
            
            player_characters = []
            for entity in battle_map.entities:
                try:
                    # Check if this is a player character
                    if hasattr(entity, 'player_character') and entity.player_character:
                        pc_info = {
                            "name": entity.label() if hasattr(entity, 'label') else str(entity),
                            "entity_uid": getattr(entity, 'entity_uid', None),
                            "position": battle_map.entity_or_object_pos(entity) if hasattr(battle_map, 'entity_or_object_pos') else None,
                            "class": getattr(entity, 'class_name', 'Unknown'),
                            "level": getattr(entity, 'level', 1),
                            "hp": getattr(entity, 'hp', 0),
                            "max_hp": getattr(entity, 'max_hp', 0),
                            "ac": getattr(entity, 'ac', 10)
                        }
                        
                        # Add ability scores if available
                        if hasattr(entity, 'strength'):
                            pc_info["abilities"] = {
                                "strength": entity.strength,
                                "dexterity": getattr(entity, 'dexterity', 10),
                                "constitution": getattr(entity, 'constitution', 10),
                                "intelligence": getattr(entity, 'intelligence', 10),
                                "wisdom": getattr(entity, 'wisdom', 10),
                                "charisma": getattr(entity, 'charisma', 10)
                            }
                        
                        # Add current status effects
                        if hasattr(entity, 'current_effects'):
                            pc_info["effects"] = [str(effect['effect']) for effect in entity.current_effects()]
                        
                        player_characters.append(pc_info)
                        
                except Exception as e:
                    logger.error(f"Error processing player character {entity}: {e}")
                    continue
            
            return player_characters
            
        except Exception as e:
            logger.error(f"Error getting player characters: {e}")
            return []
    
    def get_npcs(self) -> List[Dict[str, Any]]:
        """Get information about NPCs on the current map."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return []
            
            npcs = []
            for entity in battle_map.entities:
                try:
                    # Check if this is an NPC (not a player character)
                    if not (hasattr(entity, 'player_character') and entity.player_character):
                        npc_info = {
                            "name": entity.label() if hasattr(entity, 'label') else str(entity),
                            "entity_uid": getattr(entity, 'entity_uid', None),
                            "position": battle_map.entity_or_object_pos(entity) if hasattr(battle_map, 'entity_or_object_pos') else None,
                            "type": entity.__class__.__name__,
                            "hp": getattr(entity, 'hp', 0),
                            "max_hp": getattr(entity, 'max_hp', 0),
                            "ac": getattr(entity, 'ac', 10)
                        }
                        
                        # Add NPC-specific information
                        if hasattr(entity, 'cr'):
                            npc_info["challenge_rating"] = entity.cr
                        
                        if hasattr(entity, 'alignment'):
                            npc_info["alignment"] = entity.alignment
                        
                        if hasattr(entity, 'size'):
                            npc_info["size"] = entity.size
                        
                        if hasattr(entity, 'dead'):
                            npc_info["dead"] = entity.dead()
                        
                        if hasattr(entity, 'unconscious'):
                            npc_info["unconscious"] = entity.unconscious()
                        
                        if hasattr(entity, 'hostile'):
                            npc_info["hostile"] = getattr(entity, 'hostile', False)
                        
                        npcs.append(npc_info)
                        
                except Exception as e:
                    logger.error(f"Error processing NPC {entity}: {e}")
                    continue
            
            return npcs
            
        except Exception as e:
            logger.error(f"Error getting NPCs: {e}")
            return []
    
    def get_entity_details(self, entity_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific entity by name."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return {"error": "No current map available"}
            
            # Find entity by name (case-insensitive)
            target_entity = None
            for entity in battle_map.entities:
                if hasattr(entity, 'label') and entity.label().lower() == entity_name.lower():
                    target_entity = entity
                    break
                elif hasattr(entity, 'name') and entity.name.lower() == entity_name.lower():
                    target_entity = entity
                    break
            
            if not target_entity:
                return {"error": f"Entity '{entity_name}' not found"}
            
            # Build detailed entity information
            details = {
                "name": target_entity.label() if hasattr(target_entity, 'label') else str(target_entity),
                "entity_uid": getattr(target_entity, 'entity_uid', None),
                "type": target_entity.__class__.__name__,
                "position": battle_map.entity_or_object_pos(target_entity) if hasattr(battle_map, 'entity_or_object_pos') else None
            }
            
            # Add combat stats
            if hasattr(target_entity, 'hp'):
                details["hp"] = target_entity.hp
                details["max_hp"] = getattr(target_entity, 'max_hp', target_entity.hp)
            
            if hasattr(target_entity, 'ac'):
                details["ac"] = target_entity.ac
            
            if hasattr(target_entity, 'initiative'):
                details["initiative"] = target_entity.initiative
            
            # Add ability scores
            if hasattr(target_entity, 'strength'):
                details["abilities"] = {
                    "strength": target_entity.strength,
                    "dexterity": getattr(target_entity, 'dexterity', 10),
                    "constitution": getattr(target_entity, 'constitution', 10),
                    "intelligence": getattr(target_entity, 'intelligence', 10),
                    "wisdom": getattr(target_entity, 'wisdom', 10),
                    "charisma": getattr(target_entity, 'charisma', 10)
                }
            
            # Add status information
            if hasattr(target_entity, 'dead'):
                details["dead"] = target_entity.dead()
            
            if hasattr(target_entity, 'unconscious'):
                details["unconscious"] = target_entity.unconscious()
            
            if hasattr(target_entity, 'prone'):
                details["prone"] = target_entity.prone()
            
            if hasattr(target_entity, 'hidden'):
                details["hidden"] = target_entity.hidden()
            
            if hasattr(target_entity, 'grappled'):
                details["grappled"] = target_entity.grappled()
            
            # Add current effects
            if hasattr(target_entity, 'current_effects'):
                details["effects"] = [str(effect['effect']) for effect in target_entity.current_effects()]
            
            # Add inventory if available
            if hasattr(target_entity, 'inventory_items'):
                try:
                    inventory = target_entity.inventory_items(self.game_session)
                    if inventory:
                        details["inventory"] = [item.get('name', 'Unknown Item') for item in inventory]
                except:
                    pass
            
            # Add equipment if available
            if hasattr(target_entity, 'equipment'):
                try:
                    equipment = target_entity.equipment()
                    if equipment:
                        details["equipment"] = equipment
                except:
                    pass
            
            return details
            
        except Exception as e:
            logger.error(f"Error getting entity details for '{entity_name}': {e}")
            return {"error": str(e)}
    
    def get_battle_status(self) -> Dict[str, Any]:
        """Get current battle information if combat is active."""
        try:
            battle = self.current_game.get_current_battle()
            if not battle:
                return {"active": False, "message": "No active battle"}
            
            battle_info = {
                "active": True,
                "current_turn_index": battle.current_turn_index,
                "total_turns": len(battle.turn_order)
            }
            
            # Get current turn entity
            current_turn = battle.current_turn()
            if current_turn:
                battle_info["current_turn"] = {
                    "entity_name": current_turn.label() if hasattr(current_turn, 'label') else str(current_turn),
                    "entity_uid": getattr(current_turn, 'entity_uid', None)
                }
            
            # Get turn order
            turn_order = []
            for i, entity in enumerate(battle.turn_order):
                turn_info = {
                    "index": i,
                    "entity_name": entity.label() if hasattr(entity, 'label') else str(entity),
                    "entity_uid": getattr(entity, 'entity_uid', None),
                    "group": battle.entities[entity]['group'] if entity in battle.entities else 'unknown'
                }
                turn_order.append(turn_info)
            
            battle_info["turn_order"] = turn_order
            
            # Get groups
            groups = {}
            for group_name, group_entities in battle.groups.items():
                groups[group_name] = [
                    entity.label() if hasattr(entity, 'label') else str(entity)
                    for entity in group_entities
                ]
            battle_info["groups"] = groups
            
            return battle_info
            
        except Exception as e:
            logger.error(f"Error getting battle status: {e}")
            return {"error": str(e)}
    
    def get_available_actions(self, entity_name: str) -> Dict[str, Any]:
        """Get available actions for a specific entity."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return {"error": "No current map available"}
            
            # Find entity by name
            target_entity = None
            for entity in battle_map.entities:
                if hasattr(entity, 'label') and entity.label().lower() == entity_name.lower():
                    target_entity = entity
                    break
            
            if not target_entity:
                return {"error": f"Entity '{entity_name}' not found"}
            
            battle = self.current_game.get_current_battle()
            
            # Get available actions
            if hasattr(target_entity, 'available_actions'):
                try:
                    actions = target_entity.available_actions({}, battle, auto_target=False, map=battle_map)
                    action_list = []
                    
                    for action in actions:
                        action_info = {
                            "name": str(action),
                            "action_type": action.__class__.__name__,
                            "description": getattr(action, 'description', 'No description available')
                        }
                        action_list.append(action_info)
                    
                    return {"actions": action_list}
                    
                except Exception as e:
                    logger.error(f"Error getting actions for {entity_name}: {e}")
                    return {"error": f"Could not retrieve actions: {str(e)}"}
            
            return {"error": "Entity does not support action retrieval"}
            
        except Exception as e:
            logger.error(f"Error getting available actions for '{entity_name}': {e}")
            return {"error": str(e)}
    
    def get_map_terrain_info(self, x: int, y: int) -> Dict[str, Any]:
        """Get terrain information for a specific location on the map."""
        try:
            battle_map = self.current_game.get_current_battle_map()
            if not battle_map:
                return {"error": "No current map available"}
            
            terrain_info = {
                "position": {"x": x, "y": y},
                "difficult_terrain": False,
                "impassable": False,
                "lighting": "bright"
            }
            
            # Check if position is within map bounds
            if hasattr(battle_map, 'size'):
                map_width, map_height = battle_map.size
                if x < 0 or x >= map_width or y < 0 or y >= map_height:
                    return {"error": "Position outside map bounds"}
            
            # Check terrain properties
            if hasattr(battle_map, 'terrain'):
                if (x, y) in getattr(battle_map.terrain, 'difficult_terrain', []):
                    terrain_info["difficult_terrain"] = True
                
                if (x, y) in getattr(battle_map.terrain, 'impassable', []):
                    terrain_info["impassable"] = True
            
            # Check lighting
            if hasattr(battle_map, 'light_at'):
                light_level = battle_map.light_at(x, y)
                if light_level == 0.0:
                    terrain_info["lighting"] = "darkness"
                elif light_level == 0.5:
                    terrain_info["lighting"] = "dim"
                else:
                    terrain_info["lighting"] = "bright"
            
            # Check for objects/entities at this position
            if hasattr(battle_map, 'thing_at'):
                things = battle_map.thing_at(x, y)
                if things:
                    terrain_info["objects"] = [
                        thing.label() if hasattr(thing, 'label') else str(thing)
                        for thing in things
                    ]
            
            return terrain_info
            
        except Exception as e:
            logger.error(f"Error getting terrain info for ({x}, {y}): {e}")
            return {"error": str(e)} 