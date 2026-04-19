import json
import os
import random
import re
from typing import List, Optional, Tuple, Any

from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.look_action import LookAction
from natural20.map_renderer import MapRenderer
from natural20.ai.path_compute import PathCompute

# Optional import of webapp LLM provider abstraction; keep controller decoupled if unavailable
try:
	# Using provider interface from web layer without importing the entire app
	from webapp.llm_handler import OllamaProvider, OpenAIProvider, AnthropicProvider, LlamaCppProvider  # type: ignore
except Exception:
	OllamaProvider = None  # type: ignore
	OpenAIProvider = None  # type: ignore
	AnthropicProvider = None  # type: ignore
	LlamaCppProvider = None  # type: ignore


class LlmMcpController(GenericController):
	"""
	A controller that delegates action selection to an LLM with optional MCP tools.

	Behavior:
	- Builds a compact, text-based prompt from current map, entity status, and available actions.
	- If OpenAI client is available, can use tool calling to return an index.
	- If tools/MCP not available, falls back to parsing the first digit in the model's reply.
	- If anything fails, gracefully falls back to GenericController's heuristic ranking.
	
	Enhanced features:
	- Includes summary of entity's previous actions in prompt context
	- Includes received conversations from entity's memory buffer
	- Allows LLM to record short-term and long-term goals in session-persistent context
	- Allows LLM to communicate with other NPCs and players
	"""

	# Tool definitions for goal management and communication
	GOAL_TOOLS = [
		{
			"type": "function",
			"function": {
				"name": "set_short_term_goal",
				"description": "Set a short-term tactical goal for the current combat (e.g., 'eliminate the wizard', 'protect the cleric'). This persists until explicitly changed or combat ends.",
				"parameters": {
					"type": "object",
					"properties": {
						"goal": {
							"type": "string",
							"description": "The short-term tactical goal to pursue.",
						}
					},
					"required": ["goal"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "set_long_term_goal",
				"description": "Set a long-term strategic goal that persists across combats (e.g., 'survive at all costs', 'protect party members', 'gather information about enemies').",
				"parameters": {
					"type": "object",
					"properties": {
						"goal": {
							"type": "string",
							"description": "The long-term strategic goal to pursue.",
						}
					},
					"required": ["goal"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "add_memory_note",
				"description": "Record an observation or note for future reference (e.g., 'the goblin chieftain is vulnerable to fire', 'the door to the north is trapped').",
				"parameters": {
					"type": "object",
					"properties": {
						"note": {
							"type": "string",
							"description": "The observation or note to remember.",
						}
					},
					"required": ["note"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "speak",
				"description": "Say something out loud that nearby entities can hear. Use this to communicate with allies, taunt enemies, negotiate, warn others, or roleplay your character. The message will be heard by all entities within hearing range (30 ft by default).",
				"parameters": {
					"type": "object",
					"properties": {
						"message": {
							"type": "string",
							"description": "What you want to say out loud.",
						},
						"language": {
							"type": "string",
							"description": "The language to speak in (e.g., 'common', 'elvish', 'goblin'). Defaults to 'common'. Only entities who understand this language will comprehend the message.",
						},
						"target": {
							"type": "string",
							"description": "Optional: The name of a specific entity to address directly. If omitted, speaks to everyone nearby.",
						},
					},
					"required": ["message"],
				},
			},
		},
		# Perception tools
		{
			"type": "function",
			"function": {
				"name": "get_visible_entities",
				"description": "Get a list of all entities (creatures, NPCs, players) you can currently see along with their positions, distance from you, and basic status. Use this to assess the battlefield and identify potential targets or allies.",
				"parameters": {
					"type": "object",
					"properties": {},
					"required": [],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_visible_objects",
				"description": "Get a list of all interactable objects (doors, chests, traps, items, etc.) you can currently see along with their positions. Use this to identify environmental features you can interact with.",
				"parameters": {
					"type": "object",
					"properties": {},
					"required": [],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_terrain_at",
				"description": "Get information about the terrain at a specific position, including whether it's passable, difficult terrain, and any objects or entities there.",
				"parameters": {
					"type": "object",
					"properties": {
						"x": {
							"type": "integer",
							"description": "The x coordinate on the map grid.",
						},
						"y": {
							"type": "integer",
							"description": "The y coordinate on the map grid.",
						},
					},
					"required": ["x", "y"],
				},
			},
		},
		# Pathfinding tools
		{
			"type": "function",
			"function": {
				"name": "compute_path_to",
				"description": "Calculate the shortest path from your current position to a target position. Returns the path as a list of coordinates, the total movement cost in feet, and whether the path triggers any opportunity attacks. Use this to plan your movement tactically.",
				"parameters": {
					"type": "object",
					"properties": {
						"target_x": {
							"type": "integer",
							"description": "The target x coordinate on the map grid.",
						},
						"target_y": {
							"type": "integer",
							"description": "The target y coordinate on the map grid.",
						},
					},
					"required": ["target_x", "target_y"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "compute_path_to_entity",
				"description": "Calculate the shortest path from your current position to get adjacent to a named entity. Returns the path, movement cost, whether it triggers opportunity attacks, and viable attack positions near the target.",
				"parameters": {
					"type": "object",
					"properties": {
						"entity_name": {
							"type": "string",
							"description": "The name of the target entity to path towards.",
						},
					},
					"required": ["entity_name"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_reachable_positions",
				"description": "Get all positions you can reach with your remaining movement this turn. Returns a list of reachable positions with their movement costs. Use this to see your movement options at a glance.",
				"parameters": {
					"type": "object",
					"properties": {
						"max_positions": {
							"type": "integer",
							"description": "Maximum number of positions to return (default 20). Lower values for faster response.",
						},
					},
					"required": [],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_optimal_ranged_position",
				"description": "Find the best position for ranged attacks against a target entity. Considers cover, line of sight, distance, and safety from melee. Returns recommended positions ranked by tactical value.",
				"parameters": {
					"type": "object",
					"properties": {
						"target_name": {
							"type": "string",
							"description": "The name of the entity you want to attack from range.",
						},
						"preferred_range_ft": {
							"type": "integer",
							"description": "Your preferred attack range in feet (e.g., 30 for short bow, 120 for longbow). Defaults to 30.",
						},
					},
					"required": ["target_name"],
				},
			},
		},
	]

	def __init__(self, session, valid_move_types=None, llm_client=None, model: Optional[str] = None, use_tools: bool = True, llm_provider=None):
		super().__init__(session, valid_move_types)
		self.client = llm_client  # expected to be OpenAI-like client; optional
		self.model = model or os.getenv("N20_LLM_MODEL", "gpt-4o-mini")
		self.use_tools = use_tools
		# Generic LLMProvider backend (e.g., OllamaProvider). If none provided, try to wire Ollama by default.
		self.llm_provider = llm_provider or self._default_provider()
		# Session-persistent context for each entity (keyed by entity UID)
		# Stores: short_term_goal, long_term_goal, memory_notes, action_history_summary
		self._entity_context: dict[str, dict] = {}

	def _default_provider(self):
		"""
		Construct a default provider from environment variables.
		Respects LLM_PROVIDER in [ollama|openai|anthropic|llama_cpp], defaulting to ollama.
		Returns an initialized provider or None on failure.
		"""
		try:
			provider_name = os.getenv("LLM_PROVIDER", "ollama").lower()
			if provider_name == "openai" and OpenAIProvider is not None:
				api_key = os.getenv("OPENAI_API_KEY")
				model = os.getenv("OPENAI_MODEL", os.getenv("N20_LLM_MODEL", "gpt-4o-mini"))
				if not api_key:
					return None
				prov = OpenAIProvider()
				ok = prov.initialize({"api_key": api_key, "model": model})
				return prov if ok else None
			elif provider_name == "anthropic" and AnthropicProvider is not None:
				api_key = os.getenv("ANTHROPIC_API_KEY")
				model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
				if not api_key:
					return None
				prov = AnthropicProvider()
				ok = prov.initialize({"api_key": api_key, "model": model})
				return prov if ok else None
			elif provider_name in ("llama_cpp", "llama.cpp", "llamacpp") and LlamaCppProvider is not None:
				base_url = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8011")
				model = os.getenv("LLAMA_CPP_MODEL", os.getenv("N20_LLM_MODEL"))
				api_key = os.getenv("LLAMA_CPP_API_KEY", "llama-cpp")
				prov = LlamaCppProvider({"base_url": base_url, "api_key": api_key})
				init_config = {"base_url": base_url, "api_key": api_key}
				if model:
					init_config["model"] = model
				ok = prov.initialize(init_config)
				if not ok:
					return None
				if model:
					try:
						prov.set_model(model)
					except Exception:
						pass
				return prov
			# default to ollama
			if OllamaProvider is None:
				return None
			base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
			model = os.getenv("OLLAMA_MODEL", os.getenv("N20_LLM_MODEL", "gemma3:27b"))
			prov = OllamaProvider({"base_url": base_url})
			ok = prov.initialize({"base_url": base_url, "model": model})
			if not ok:
				return None
			try:
				prov.set_model(model)
			except Exception:
				pass
			return prov
		except Exception:
			return None

	# --- Entity Context Management (Session-Persistent Goals & Memory) ---
	def _get_entity_context(self, entity) -> dict:
		"""Get or create session-persistent context for an entity."""
		uid = str(getattr(entity, 'entity_uid', id(entity)))
		if uid not in self._entity_context:
			self._entity_context[uid] = {
				'short_term_goal': None,
				'long_term_goal': None,
				'memory_notes': [],
				'action_history': [],  # Brief summaries of past actions
			}
		return self._entity_context[uid]

	def set_short_term_goal(self, entity, goal: str) -> None:
		"""Set a short-term tactical goal for the entity."""
		ctx = self._get_entity_context(entity)
		ctx['short_term_goal'] = goal

	def set_long_term_goal(self, entity, goal: str) -> None:
		"""Set a long-term strategic goal for the entity."""
		ctx = self._get_entity_context(entity)
		ctx['long_term_goal'] = goal

	def add_memory_note(self, entity, note: str) -> None:
		"""Add an observation or note to the entity's memory."""
		ctx = self._get_entity_context(entity)
		# Keep only last 10 notes to prevent unbounded growth
		if len(ctx['memory_notes']) >= 10:
			ctx['memory_notes'].pop(0)
		ctx['memory_notes'].append(note)

	def clear_short_term_goal(self, entity) -> None:
		"""Clear the short-term goal (e.g., when combat ends)."""
		ctx = self._get_entity_context(entity)
		ctx['short_term_goal'] = None

	def get_goals_summary(self, entity) -> str:
		"""Return a formatted summary of the entity's current goals."""
		ctx = self._get_entity_context(entity)
		parts = []
		if ctx['long_term_goal']:
			parts.append(f"Long-term: {ctx['long_term_goal']}")
		if ctx['short_term_goal']:
			parts.append(f"Short-term: {ctx['short_term_goal']}")
		return " | ".join(parts) if parts else "(no goals set)"

	def get_memory_notes_summary(self, entity, n: int = 5) -> List[str]:
		"""Return the most recent memory notes."""
		ctx = self._get_entity_context(entity)
		return ctx['memory_notes'][-n:] if ctx['memory_notes'] else []

	def _record_action_to_history(self, entity, action_desc: str) -> None:
		"""Record a brief action summary to the entity's history."""
		ctx = self._get_entity_context(entity)
		# Keep only last 20 actions
		if len(ctx['action_history']) >= 20:
			ctx['action_history'].pop(0)
		ctx['action_history'].append(action_desc)

	def _process_goal_tool_calls(self, entity, battle, tool_calls: List[dict]) -> List[dict]:
		"""
		Process any goal-setting, memory, communication, or perception tool calls from the LLM response.
		Returns a list of results for informational tools (perception/pathfinding).
		"""
		results = []
		for call in tool_calls:
			try:
				func_name = call.get('function', {}).get('name', '')
				args_str = call.get('function', {}).get('arguments', '{}')
				args = json.loads(args_str) if isinstance(args_str, str) else args_str
				
				if func_name == 'set_short_term_goal':
					self.set_short_term_goal(entity, args.get('goal', ''))
				elif func_name == 'set_long_term_goal':
					self.set_long_term_goal(entity, args.get('goal', ''))
				elif func_name == 'add_memory_note':
					self.add_memory_note(entity, args.get('note', ''))
				elif func_name == 'speak':
					self._handle_speak(entity, battle, args)
				# Perception tools
				elif func_name == 'get_visible_entities':
					result = self._handle_get_visible_entities(entity, battle)
					results.append({'tool': func_name, 'result': result})
				elif func_name == 'get_visible_objects':
					result = self._handle_get_visible_objects(entity, battle)
					results.append({'tool': func_name, 'result': result})
				elif func_name == 'get_terrain_at':
					result = self._handle_get_terrain_at(entity, battle, args)
					results.append({'tool': func_name, 'result': result})
				# Pathfinding tools
				elif func_name == 'compute_path_to':
					result = self._handle_compute_path_to(entity, battle, args)
					results.append({'tool': func_name, 'result': result})
				elif func_name == 'compute_path_to_entity':
					result = self._handle_compute_path_to_entity(entity, battle, args)
					results.append({'tool': func_name, 'result': result})
				elif func_name == 'get_reachable_positions':
					result = self._handle_get_reachable_positions(entity, battle, args)
					results.append({'tool': func_name, 'result': result})
				elif func_name == 'get_optimal_ranged_position':
					result = self._handle_get_optimal_ranged_position(entity, battle, args)
					results.append({'tool': func_name, 'result': result})
			except Exception:
				pass  # Silently ignore malformed tool calls
		return results

	def _handle_speak(self, entity, battle, args: dict) -> None:
		"""
		Handle a speak tool call - make the entity say something out loud.
		
		Args:
			entity: The entity speaking
			battle: The current battle context
			args: Dictionary with 'message', optional 'language', optional 'target'
		"""
		message = args.get('message', '')
		if not message:
			return
		
		language = args.get('language', 'common')
		target_name = args.get('target')
		
		# Find the target entity if specified
		targets = None
		if target_name:
			try:
				# Search for the target in the battle
				all_entities = list(battle.entities.keys()) if hasattr(battle, 'entities') else []
				for e in all_entities:
					if getattr(e, 'name', '').lower() == target_name.lower():
						targets = [e]
						break
			except Exception:
				pass
		
		# Use the entity's send_conversation method
		try:
			if hasattr(entity, 'send_conversation'):
				entity.send_conversation(message, distance_ft=30, targets=targets, language=language)
				# Also record this in the entity's context
				self.add_memory_note(entity, f"I said: \"{message[:50]}{'...' if len(message) > 50 else ''}\"")
		except Exception:
			pass  # Silently fail if communication fails

	# --- Perception Tool Handlers ---
	def _handle_get_visible_entities(self, entity, battle) -> dict:
		"""
		Get a list of all entities the entity can currently see with positions and status.
		"""
		try:
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available', 'entities': []}
			
			visible_entities = current_map.look(entity)
			my_pos = current_map.position_of(entity)
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			
			entities_info = []
			for other_entity, pos in visible_entities.items():
				try:
					# Calculate distance
					dist_grids = current_map.distance(entity, other_entity)
					dist_ft = int(dist_grids * feet_per)
					
					# Determine relationship (ally or enemy)
					is_enemy = other_entity in battle.opponents_of(entity)
					relationship = 'enemy' if is_enemy else 'ally'
					
					# Get basic status
					hp_pct = int((other_entity.hp() / other_entity.max_hp()) * 100) if other_entity.max_hp() > 0 else 0
					conditions = []
					if other_entity.prone():
						conditions.append('prone')
					if other_entity.unconscious():
						conditions.append('unconscious')
					if getattr(other_entity, 'concentration', None):
						conditions.append('concentrating')
					
					entities_info.append({
						'name': other_entity.name,
						'position': list(pos),
						'distance_ft': dist_ft,
						'relationship': relationship,
						'hp_percent': hp_pct,
						'conditions': conditions,
						'size': getattr(other_entity, 'size', 'medium'),
					})
				except Exception:
					continue
			
			return {
				'my_position': list(my_pos),
				'entities': entities_info,
				'count': len(entities_info)
			}
		except Exception as e:
			return {'error': str(e), 'entities': []}

	def _handle_get_visible_objects(self, entity, battle) -> dict:
		"""
		Get a list of all interactable objects the entity can currently see.
		"""
		try:
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available', 'objects': []}
			
			my_pos = current_map.position_of(entity)
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			
			objects_info = []
			for obj, pos in current_map.interactable_objects.items():
				try:
					# Check if entity can see this object
					if not current_map.can_see(entity, obj, allow_dark_vision=True):
						continue
					
					# Calculate distance
					dist_grids = current_map.distance(entity, obj)
					dist_ft = int(dist_grids * feet_per)
					
					# Get object info
					obj_info = {
						'name': getattr(obj, 'name', str(obj)),
						'type': getattr(obj, 'object_type', type(obj).__name__),
						'position': list(pos),
						'distance_ft': dist_ft,
					}
					
					# Add specific properties if available
					if hasattr(obj, 'open') and callable(obj.open):
						obj_info['is_open'] = obj.open()
					if hasattr(obj, 'locked') and callable(obj.locked):
						obj_info['is_locked'] = obj.locked()
					if hasattr(obj, 'passable'):
						obj_info['passable'] = obj.passable(my_pos) if callable(obj.passable) else obj.passable
					
					objects_info.append(obj_info)
				except Exception:
					continue
			
			return {
				'my_position': list(my_pos),
				'objects': objects_info,
				'count': len(objects_info)
			}
		except Exception as e:
			return {'error': str(e), 'objects': []}

	def _handle_get_terrain_at(self, entity, battle, args: dict) -> dict:
		"""
		Get terrain information at a specific position.
		"""
		try:
			x = args.get('x')
			y = args.get('y')
			if x is None or y is None:
				return {'error': 'x and y coordinates are required'}
			
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available'}
			
			# Check if position is within map bounds
			max_x, max_y = current_map.size
			if not (0 <= x < max_x and 0 <= y < max_y):
				return {'error': f'Position ({x}, {y}) is out of bounds'}
			
			# Check if entity can see this square
			can_see = current_map.can_see_square(entity, (x, y), allow_dark_vision=True)
			if not can_see:
				return {'error': f'Cannot see position ({x}, {y})', 'visible': False}
			
			# Get terrain info
			terrain_info = {
				'position': [x, y],
				'visible': True,
				'passable': current_map.passable(entity, x, y, battle, allow_squeeze=True),
				'difficult_terrain': current_map.difficult_terrain(entity, x, y, battle) if hasattr(current_map, 'difficult_terrain') else False,
			}
			
			# Check for entity at position
			entity_at = current_map.entity_at(x, y)
			if entity_at:
				terrain_info['entity'] = {
					'name': entity_at.name,
					'is_enemy': entity_at in battle.opponents_of(entity)
				}
			
			# Check for objects at position
			obj_at = current_map.object_at(x, y) if hasattr(current_map, 'object_at') else None
			if obj_at:
				terrain_info['object'] = {
					'name': getattr(obj_at, 'name', str(obj_at)),
					'type': getattr(obj_at, 'object_type', type(obj_at).__name__),
				}
			
			# Check illumination
			if hasattr(current_map, 'light_at'):
				terrain_info['illumination'] = current_map.light_at(x, y)
			
			return terrain_info
		except Exception as e:
			return {'error': str(e)}

	# --- Pathfinding Tool Handlers ---
	def _handle_compute_path_to(self, entity, battle, args: dict) -> dict:
		"""
		Compute the shortest path to a target position.
		"""
		try:
			target_x = args.get('target_x')
			target_y = args.get('target_y')
			if target_x is None or target_y is None:
				return {'error': 'target_x and target_y are required'}
			
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available'}
			
			my_pos = current_map.position_of(entity)
			source_x, source_y = my_pos
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			
			# Use PathCompute for A* pathfinding
			path_compute = PathCompute(battle, current_map, entity)
			path = path_compute.compute_path(source_x, source_y, target_x, target_y)
			
			if not path:
				return {
					'error': f'No path found to ({target_x}, {target_y})',
					'reachable': False
				}
			
			# Calculate movement cost
			movement_cost_ft = (len(path) - 1) * feet_per
			
			# Check for opportunity attacks
			triggers_oa, oa_foe = self._move_oa_info(battle, entity, path)
			
			# Get available movement
			state = battle.entity_state_for(entity) or {}
			movement_left = state.get('movement', getattr(entity, 'speed', lambda: 0)())
			
			result = {
				'path': path,
				'movement_cost_ft': movement_cost_ft,
				'movement_available_ft': movement_left,
				'can_reach': movement_cost_ft <= movement_left,
				'triggers_opportunity_attack': triggers_oa,
				'opportunity_attack_from': oa_foe if triggers_oa else None,
				'reachable': True
			}
			
			return result
		except Exception as e:
			return {'error': str(e)}

	def _handle_compute_path_to_entity(self, entity, battle, args: dict) -> dict:
		"""
		Compute the shortest path to get adjacent to a named entity.
		"""
		try:
			entity_name = args.get('entity_name')
			if not entity_name:
				return {'error': 'entity_name is required'}
			
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available'}
			
			# Find the target entity
			target_entity = None
			for e in current_map.entities.keys():
				if getattr(e, 'name', '').lower() == entity_name.lower():
					target_entity = e
					break
			
			if not target_entity:
				return {'error': f'Entity "{entity_name}" not found'}
			
			my_pos = current_map.position_of(entity)
			target_pos = current_map.position_of(target_entity)
			source_x, source_y = my_pos
			target_x, target_y = target_pos
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			
			# Find adjacent positions to target that are passable
			adjacent_positions = []
			for dx in [-1, 0, 1]:
				for dy in [-1, 0, 1]:
					if dx == 0 and dy == 0:
						continue
					adj_x, adj_y = target_x + dx, target_y + dy
					if current_map.passable(entity, adj_x, adj_y, battle, allow_squeeze=True):
						adjacent_positions.append((adj_x, adj_y))
			
			if not adjacent_positions:
				return {'error': f'No reachable positions adjacent to {entity_name}'}
			
			# Find the shortest path to any adjacent position
			path_compute = PathCompute(battle, current_map, entity)
			best_path = None
			best_dest = None
			
			for adj_pos in adjacent_positions:
				path = path_compute.compute_path(source_x, source_y, adj_pos[0], adj_pos[1])
				if path:
					if best_path is None or len(path) < len(best_path):
						best_path = path
						best_dest = adj_pos
			
			if not best_path:
				return {
					'error': f'No path found to reach {entity_name}',
					'reachable': False
				}
			
			# Calculate movement cost
			movement_cost_ft = (len(best_path) - 1) * feet_per
			
			# Check for opportunity attacks
			triggers_oa, oa_foe = self._move_oa_info(battle, entity, best_path)
			
			# Get available movement
			state = battle.entity_state_for(entity) or {}
			movement_left = state.get('movement', getattr(entity, 'speed', lambda: 0)())
			
			result = {
				'target_entity': entity_name,
				'target_position': list(target_pos),
				'path': best_path,
				'destination': list(best_dest),
				'movement_cost_ft': movement_cost_ft,
				'movement_available_ft': movement_left,
				'can_reach': movement_cost_ft <= movement_left,
				'triggers_opportunity_attack': triggers_oa,
				'opportunity_attack_from': oa_foe if triggers_oa else None,
				'adjacent_positions': [list(p) for p in adjacent_positions],
				'reachable': True
			}
			
			return result
		except Exception as e:
			return {'error': str(e)}

	def _handle_get_reachable_positions(self, entity, battle, args: dict) -> dict:
		"""
		Get all positions reachable with remaining movement.
		"""
		try:
			max_positions = args.get('max_positions', 20)
			
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available'}
			
			my_pos = current_map.position_of(entity)
			source_x, source_y = my_pos
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			
			# Get available movement
			state = battle.entity_state_for(entity) or {}
			movement_left = state.get('movement', getattr(entity, 'speed', lambda: 0)())
			movement_grids = movement_left // feet_per
			
			if movement_grids <= 0:
				return {
					'my_position': list(my_pos),
					'movement_available_ft': movement_left,
					'reachable_positions': [],
					'count': 0
				}
			
			# BFS to find reachable positions
			from collections import deque
			visited = {(source_x, source_y): 0}
			queue = deque([(source_x, source_y, 0)])
			reachable = []
			
			while queue and len(reachable) < max_positions * 2:  # Gather more, then trim
				cx, cy, cost = queue.popleft()
				
				if cost > 0:  # Don't include starting position
					triggers_oa, oa_foe = self._move_oa_info(battle, entity, [(source_x, source_y), (cx, cy)])
					reachable.append({
						'position': [cx, cy],
						'movement_cost_ft': cost * feet_per,
						'triggers_oa': triggers_oa,
						'oa_from': oa_foe
					})
				
				# Explore neighbors
				for dx in [-1, 0, 1]:
					for dy in [-1, 0, 1]:
						if dx == 0 and dy == 0:
							continue
						nx, ny = cx + dx, cy + dy
						
						# Skip if out of bounds
						if not (0 <= nx < current_map.size[0] and 0 <= ny < current_map.size[1]):
							continue
						
						# Calculate move cost (diagonal = 1.5 rounded, or use map's method)
						move_cost = 1 if dx == 0 or dy == 0 else 1
						if hasattr(current_map, 'difficult_terrain') and current_map.difficult_terrain(entity, nx, ny, battle):
							move_cost = 2
						
						new_cost = cost + move_cost
						
						# Skip if already visited with lower cost or exceeds budget
						if (nx, ny) in visited and visited[(nx, ny)] <= new_cost:
							continue
						if new_cost > movement_grids:
							continue
						
						# Skip if not passable
						if not current_map.passable(entity, nx, ny, battle, allow_squeeze=True):
							continue
						
						visited[(nx, ny)] = new_cost
						queue.append((nx, ny, new_cost))
			
			# Sort by cost and limit
			reachable.sort(key=lambda x: x['movement_cost_ft'])
			reachable = reachable[:max_positions]
			
			return {
				'my_position': list(my_pos),
				'movement_available_ft': movement_left,
				'reachable_positions': reachable,
				'count': len(reachable)
			}
		except Exception as e:
			return {'error': str(e)}

	def _handle_get_optimal_ranged_position(self, entity, battle, args: dict) -> dict:
		"""
		Find optimal positions for ranged attacks against a target.
		"""
		try:
			target_name = args.get('target_name')
			preferred_range_ft = args.get('preferred_range_ft', 30)
			
			if not target_name:
				return {'error': 'target_name is required'}
			
			current_map = battle.map_for(entity)
			if not current_map:
				return {'error': 'No map available'}
			
			# Find the target entity
			target_entity = None
			for e in current_map.entities.keys():
				if getattr(e, 'name', '').lower() == target_name.lower():
					target_entity = e
					break
			
			if not target_entity:
				return {'error': f'Entity "{target_name}" not found'}
			
			my_pos = current_map.position_of(entity)
			target_pos = current_map.position_of(target_entity)
			source_x, source_y = my_pos
			feet_per = getattr(current_map, 'feet_per_grid', 5) or 5
			preferred_range_grids = preferred_range_ft / feet_per
			
			# Get available movement
			state = battle.entity_state_for(entity) or {}
			movement_left = state.get('movement', getattr(entity, 'speed', lambda: 0)())
			movement_grids = movement_left // feet_per
			
			# Get reachable positions
			reachable_data = self._handle_get_reachable_positions(entity, battle, {'max_positions': 50})
			reachable_positions = reachable_data.get('reachable_positions', [])
			
			# Include current position
			reachable_positions.insert(0, {
				'position': list(my_pos),
				'movement_cost_ft': 0,
				'triggers_oa': False,
				'oa_from': None
			})
			
			# Score each position
			scored_positions = []
			for pos_data in reachable_positions:
				pos = tuple(pos_data['position'])
				px, py = pos
				
				# Check line of sight to target
				if not current_map.can_see(entity, target_entity, entity_1_pos=pos):
					continue
				
				# Calculate distance to target
				dist_to_target = ((px - target_pos[0])**2 + (py - target_pos[1])**2)**0.5
				dist_ft = dist_to_target * feet_per
				
				# Score based on distance to preferred range (lower is better)
				range_score = abs(dist_ft - preferred_range_ft)
				
				# Penalize positions in melee range of enemies
				melee_penalty = 0
				for enemy in battle.opponents_of(entity):
					if enemy == target_entity:
						continue
					try:
						enemy_pos = current_map.position_of(enemy)
						enemy_dist = ((px - enemy_pos[0])**2 + (py - enemy_pos[1])**2)**0.5
						if enemy_dist <= 1.5:  # Adjacent
							melee_penalty += 50
					except Exception:
						continue
				
				# Penalize positions that trigger opportunity attacks
				oa_penalty = 30 if pos_data.get('triggers_oa') else 0
				
				# Calculate total score (lower is better)
				total_score = range_score + melee_penalty + oa_penalty
				
				scored_positions.append({
					'position': list(pos),
					'distance_to_target_ft': int(dist_ft),
					'movement_cost_ft': pos_data['movement_cost_ft'],
					'triggers_oa': pos_data.get('triggers_oa', False),
					'oa_from': pos_data.get('oa_from'),
					'in_melee_with_others': melee_penalty > 0,
					'tactical_score': int(total_score)
				})
			
			# Sort by score (lower is better) and return top 5
			scored_positions.sort(key=lambda x: x['tactical_score'])
			top_positions = scored_positions[:5]
			
			return {
				'target': target_name,
				'target_position': list(target_pos),
				'preferred_range_ft': preferred_range_ft,
				'recommended_positions': top_positions,
				'count': len(top_positions)
			}
		except Exception as e:
			return {'error': str(e)}

	# --- Public API ---
	def select_action(self, battle, entity, available_actions: Optional[List[Action]] = None) -> Optional[Action]:
		if not available_actions:
			return None

		# If only one action, just take it
		if len(available_actions) == 1:
			return available_actions[0]

		# Try LLM path first, then fallback to heuristic ranking
		try:
			idx = self._ask_llm_for_choice(battle, entity, available_actions)
			if idx is not None and 0 <= idx < len(available_actions):
				chosen = self._maybe_enrich_action_targets(battle, entity, available_actions[idx])
				return chosen
		except Exception as _e:
			# Silent fallback; don't spam logs during games
			pass

		# Fallback to GenericController ranking
		ranked = self._sort_actions(entity, battle, available_actions)
		return ranked[0] if ranked else None

	# --- LLM prompting ---
	def _ask_llm_for_choice(self, battle, entity, available_actions: List[Action]) -> Optional[int]:
		prompt = self._build_prompt(battle, entity, available_actions)

		# Optional MCP endpoint: if configured, try it first
		mcp_idx = self._call_mcp_tool(prompt, len(available_actions))
		if mcp_idx is not None:
			return mcp_idx

		# If an LLMProvider backend exists (e.g., Ollama), use it first
		prov = getattr(self, "llm_provider", None)
		if prov is not None and hasattr(prov, "send_message"):
			try:
				instructions = (
					"You are a tactical assistant. Given a list of actions indexed from 0, choose the single best index. "
					"Respond with ONLY the integer index (no text)."
				)
				messages = [
					{"role": "system", "content": instructions},
					{"role": "user", "content": prompt},
				]
				text = prov.send_message(messages)  # type: ignore[attr-defined]
				idx = self._local_parse_choice_from_text(text, len(available_actions))
				if idx is not None:
					return idx
			except Exception:
				# fall through to other options
				pass

		# If no OpenAI-style client configured, do a lightweight heuristic mix
		if self.client is None:
			return self._local_parse_choice_from_text(self._local_greedy_simulation(prompt), len(available_actions))

		tools = None
		if self.use_tools:
			# Combine choose_action tool with goal/memory tools
			choose_action_tool = {
				"type": "function",
				"function": {
					"name": "choose_action",
					"description": "Select the best action index for the NPC to execute now",
					"parameters": {
						"type": "object",
						"properties": {
							"index": {
								"type": "integer",
								"description": "Zero-based index into the provided list of actions.",
							},
							"why": {
								"type": "string",
								"description": "One-sentence rationale for the choice.",
							},
						},
						"required": ["index"],
					},
				},
			}
			tools = [choose_action_tool] + self.GOAL_TOOLS

		if tools:
			resp = self.client.chat.completions.create(
				model=self.model,
				messages=[{"role": "user", "content": prompt}],
				tools=tools,
				tool_choice="auto",  # Allow multiple tool calls
			)
			try:
				tool_calls = resp.choices[0].message.tool_calls or []
				action_index = None
				goal_tool_calls = []
				
				# Names of all non-action tools
				auxiliary_tool_names = (
					'set_short_term_goal', 'set_long_term_goal', 'add_memory_note', 'speak',
					'get_visible_entities', 'get_visible_objects', 'get_terrain_at',
					'compute_path_to', 'compute_path_to_entity', 'get_reachable_positions', 'get_optimal_ranged_position'
				)
				
				for call in tool_calls:
					func_name = call.function.name
					if func_name == 'choose_action':
						args = json.loads(call.function.arguments)
						action_index = int(args.get("index", 0))
					elif func_name in auxiliary_tool_names:
						# Collect auxiliary tool calls for processing
						goal_tool_calls.append({
							'function': {
								'name': func_name,
								'arguments': call.function.arguments
							}
						})
				
				# Process any auxiliary tool calls (goals, perception, pathfinding, etc.)
				if goal_tool_calls:
					self._process_goal_tool_calls(entity, battle, goal_tool_calls)
				
				if action_index is not None:
					return action_index
			except Exception:
				# Fallthrough to content parsing
				pass

		# No tools or tool parsing failed—parse content
		resp = self.client.chat.completions.create(
			model=self.model,
			messages=[{"role": "user", "content": prompt}],
		)
		text = resp.choices[0].message.content or ""
		return self._local_parse_choice_from_text(text, len(available_actions))

	def _build_prompt(self, battle, entity, available_actions: List[Action]) -> str:
		# Render a small text map around the entity for context
		current_map = battle.map_for(entity)
		renderer = MapRenderer(current_map, battle)
		map_text = renderer.render(entity=entity, line_of_sight=entity)

		# Strip ANSI color codes to keep the prompt clean for LLMs
		map_text = self._strip_ansi(map_text)

		feet_per = getattr(current_map, 'feet_per_grid', 5) or 5

		def _dist_ft(src, tgt) -> Optional[int]:
			try:
				m = battle.map_for(src)
				if not m:
					return None
				return int(round(m.distance(src, tgt) * m.feet_per_grid))
			except Exception:
				return None

		def action_label(a: Action, idx: int, compact: bool = False) -> str:
			try:
				if isinstance(a, MoveAction):
					if a.move_path:
						end = a.move_path[-1]
						if compact:
							return f"{idx}. move to {tuple(end)}"
						else:
							steps = max(0, len(a.move_path) - 1)
							ft = steps * feet_per
							# Simulate OA risk along path and include foe name when possible
							triggers, foe = self._move_oa_info(battle, entity, a.move_path)
							oa = f"; OA risk{f' (leaving {foe})' if foe else ''}" if triggers else ""
							return f"{idx}. move to {tuple(end)} (~{ft} ft{oa})"
					return f"{idx}. move"
				if isinstance(a, AttackAction):
					target = getattr(a, "target", None)
					tname = getattr(target, "name", None) if target else None
					weap = None
					try:
						npc_action = getattr(a, 'npc_action', None)
						if isinstance(npc_action, dict):
							weap = npc_action.get('name')
						if not weap:
							weap = getattr(a, 'using', None)
					except Exception:
						weap = getattr(a, 'using', None)
					# Try to enrich with hit chance and avg damage
					info = []
					try:
						if target and not compact:
							prob = a.compute_hit_probability(battle)
							if prob is not None:
								info.append(f"hit {int(round(prob*100))}%")
							avg = a.avg_damage(battle)
							if avg is not None:
								info.append(f"avg dmg {int(round(avg))}")
							d = _dist_ft(entity, target)
							if d is not None:
								info.append(f"dist {d} ft")
							# Range band and cover hints
							try:
								from natural20.weapons import compute_max_weapon_range
								from natural20.utils.ac_utils import effective_ac
								rmax = compute_max_weapon_range(self.session, a)
								if rmax:
									if d and d > rmax:
										info.append("long")
									else:
										info.append("normal")
								# cover bonus if any
								_, cov = effective_ac(battle, entity, target)
								if cov in (2, 5):
									cov_label = 'half' if cov == 2 else 'three-quarter'
									info.append(f"{cov_label} cover (+{cov})")
							except Exception:
								pass
						# Advantage/disadvantage marker
						try:
							adv_mod, _adv_info, _atk_mod = a.compute_advantage_info(battle)
							if adv_mod > 0:
								info.append("adv")
							elif adv_mod < 0:
								info.append("dis")
						except Exception:
							pass
					except Exception:
						pass
					metrics = f" ({', '.join(info)})" if info else ""
					return f"{idx}. attack {tname or 'enemy'} with {weap or 'weapon'}{metrics}"
				if isinstance(a, SpellAction):
					sp = getattr(a, 'spell', None) or (a.opts or {}).get('spell')
					t = getattr(a, 'target', None)
					info = []
					try:
						if not compact:
							prob = a.compute_hit_probability(battle)
							if prob not in (None, 0):
								info.append(f"hit {int(round(prob*100))}%")
							avg = a.avg_damage(battle)
							if avg not in (None, 0):
								info.append(f"avg dmg {int(round(avg))}")
						if t and not compact:
							d = _dist_ft(entity, t)
							if d is not None:
								info.append(f"dist {d} ft")
								# Range band/cover hints (spells have a single range)
								try:
									from natural20.weapons import compute_max_weapon_range
									from natural20.utils.ac_utils import effective_ac
									rmax = compute_max_weapon_range(self.session, a)
									if rmax:
										if d and d > rmax:
											info.append("long")
										else:
											info.append("normal")
									_, cov = effective_ac(battle, entity, t)
									if cov in (2, 5):
										cov_label = 'half' if cov == 2 else 'three-quarter'
										info.append(f"{cov_label} cover (+{cov})")
								except Exception:
									pass
						# Advantage/disadvantage marker, if any
						try:
							adv_info = a.compute_advantage_info(battle)
							if adv_info is not None:
								adv_mod = adv_info[0]
								if adv_mod > 0:
									info.append("adv")
								elif adv_mod < 0:
									info.append("dis")
						except Exception:
							pass
					except Exception:
						pass
					metrics = f" ({', '.join(info)})" if info else ""
					return f"{idx}. cast {sp or 'a spell'} on {getattr(t, 'name', 'target')}{metrics}"
				if isinstance(a, LookAction):
					return f"{idx}. look around"
				# Generic fallback
				return f"{idx}. {a.action_type}"
			except Exception:
				return f"{idx}. {getattr(a, 'action_type', 'action')}"

		action_lines = [action_label(a, i, False) for i, a in enumerate(available_actions)]

		hp_val = entity.hp()
		max_hp_val = entity.max_hp()
		hp = f"{hp_val}/{max_hp_val}"
		cond = []
		if entity.prone():
			cond.append("prone")
		# Dodge is tracked in battle state statuses
		try:
			st = battle.entity_state_for(entity)
			if st and 'dodge' in st.get('statuses', set()):
				cond.append("dodging")
		except Exception:
			pass
		cond_text = ", ".join(cond) if cond else "none"

		# Nearby enemies summary
		enemies = battle.opponents_of(entity)
		vis_enemies = [e for e in enemies if battle.can_see(entity, e)]
		def enemy_line(e, compact=False):
			d = _dist_ft(entity, e)
			if compact:
				return f"{e.name}"
			return f"{e.name}({e.hp()}/{e.max_hp()}{'' if d is None else f', {d} ft'})"
		enemy_summ_full = ", ".join(enemy_line(e, False) for e in vis_enemies) or "(none visible)"
		enemy_summ_compact = ", ".join(enemy_line(e, True) for e in vis_enemies) or "(none visible)"

		# Engagement and resources
		engaged = False
		try:
			engaged = bool(battle.enemy_in_melee_range(entity))
		except Exception:
			engaged = False
		state = battle.entity_state_for(entity) or {}
		movement_left = state.get('movement', getattr(entity, 'speed', lambda: 0)())
		resources = f"action={state.get('action', 0)}, bonus={state.get('bonus_action', 0)}, reaction={state.get('reaction', 0)}, movement={movement_left} ft"
		hp_pct = (hp_val / max_hp_val) if (hp_val is not None and max_hp_val) else 1.0
		concentration = self._concentration_label(entity)
		# Nearest enemy distance
		nearest_ft = None
		try:
			if enemies:
				dists = [v for v in (_dist_ft(entity, e) for e in enemies) if v is not None]
				if dists:
					nearest_ft = min(dists)
		except Exception:
			nearest_ft = None

		# Spell slot summary (levels with slots only)
		slot_summary = self._spell_slots_summary(entity)

		instructions = (
			"You're an NPC tactician in a D&D-like tactical sim. Choose the single best action for this turn. "
			"Guidelines: prefer lethal or high-impact attacks when safe; avoid provoking opportunity attacks unless payoff is high; "
			"use movement to get line of sight or optimal range; conserve limited resources when impact is low; "
			"if HP is low, favor defensive options like disengage/dodge/hide; maintain concentration on valuable effects. "
			"Only pick from the provided actions."
		)

		parts = [
			f"Map (visible):\n{map_text}\n",
			f"Round: {battle.current_round()} | You: {entity.name} HP {hp} ({int(hp_pct*100)}%), conditions: {cond_text}\n",
			f"Resources: {resources} | Engaged in melee: {'yes' if engaged else 'no'} | Concentration: {concentration} | Nearest enemy: {nearest_ft if nearest_ft is not None else 'n/a'} ft\n",
		]
		if slot_summary:
			parts.append(f"Slots: {slot_summary}\n")
		low_slots = self._low_slots_note(entity)
		if low_slots:
			parts.append(f"{low_slots}\n")

		# Recent actions by you/allies/enemies
		recent_you = self._recent_actions(battle, entity, n=5)
		allies = []
		try:
			if hasattr(battle, 'allies_of'):
				allies = [a for a in battle.allies_of(entity) if a is not entity]
			else:
				# Fallback: same group as you
				grp = battle.entity_group_for(entity)
				allies = [a for a in getattr(battle, 'entities', {}).keys() if battle.entity_group_for(a) == grp and a is not entity]
		except Exception:
			allies = []
		recent_allies = self._recent_actions_for(battle, allies, n=5)
		recent_enemies = self._recent_actions_for(battle, enemies, n=5)

		parts.append("Recent actions (you):\n" + ("\n".join(f"- {r}" for r in recent_you) if recent_you else "(none yet)") + "\n")
		parts.append("Recent actions (allies):\n" + ("\n".join(f"- {r}" for r in recent_allies) if recent_allies else "(none)\n"))
		parts.append("Recent actions (enemies):\n" + ("\n".join(f"- {r}" for r in recent_enemies) if recent_enemies else "(none)\n"))

		# Add conversation context from entity's memory buffer
		conversation_summary = self._get_conversation_summary(entity, n=5)
		if conversation_summary:
			parts.append("Recent conversations:\n" + "\n".join(f"- {c}" for c in conversation_summary) + "\n")

		# Add goals and memory notes from session-persistent context
		goals_summary = self.get_goals_summary(entity)
		if goals_summary and goals_summary != "(no goals set)":
			parts.append(f"Current goals: {goals_summary}\n")

		memory_notes = self.get_memory_notes_summary(entity, n=5)
		if memory_notes:
			parts.append("Memory notes:\n" + "\n".join(f"- {n}" for n in memory_notes) + "\n")

		# Add backstory context if available
		backstory = self._get_backstory_summary(entity)
		if backstory:
			parts.append(f"Character context: {backstory}\n")

		parts.extend([
			f"Visible enemies: {enemy_summ_full}\n\n",
			f"Available actions (index: description):\n" + "\n".join(action_lines) + "\n\n",
			f"{instructions}\n",
			"Available tools:\n",
			"- Goal/Memory: set_short_term_goal, set_long_term_goal, add_memory_note (update tactical context)\n",
			"- Communication: speak (say something to nearby entities)\n",
			"- Perception: get_visible_entities, get_visible_objects, get_terrain_at (gather battlefield info)\n",
			"- Pathfinding: compute_path_to, compute_path_to_entity, get_reachable_positions, get_optimal_ranged_position (plan movement)\n",
			"Return either a single integer index (0-based) or call choose_action with that index.",
		])
		prompt = "".join(parts)

		# If prompt is too long, build a compact version
		try:
			max_chars = int(os.getenv("N20_LLM_PROMPT_MAX_CHARS", "12000"))
		except Exception:
			max_chars = 12000
		if len(prompt) > max_chars:
			# Rebuild with compact info
			action_lines_compact = [action_label(a, i, True) for i, a in enumerate(available_actions)]
			recent_you_c = self._recent_actions(battle, entity, n=3)
			recent_allies_c = self._recent_actions_for(battle, allies, n=3)
			recent_enemies_c = self._recent_actions_for(battle, enemies, n=3)
			parts_c = [
				f"Map (visible):\n{map_text}\n",
				f"Round: {battle.current_round()} | You: {entity.name} HP {hp} ({int(hp_pct*100)}%), conditions: {cond_text}\n",
				f"Resources: {resources} | Engaged in melee: {'yes' if engaged else 'no'} | Concentration: {concentration} | Nearest enemy: {nearest_ft if nearest_ft is not None else 'n/a'} ft\n",
			]
			if slot_summary:
				parts_c.append(f"Slots: {slot_summary}\n")
			if low_slots:
				parts_c.append(f"{low_slots}\n")
			parts_c.append("Recent actions (you):\n" + ("\n".join(f"- {r}" for r in recent_you_c) if recent_you_c else "(none yet)\n"))
			parts_c.append("Recent actions (allies):\n" + ("\n".join(f"- {r}" for r in recent_allies_c) if recent_allies_c else "(none)\n"))
			parts_c.append("Recent actions (enemies):\n" + ("\n".join(f"- {r}" for r in recent_enemies_c) if recent_enemies_c else "(none)\n"))
			# Include goals even in compact mode (they're brief)
			if goals_summary and goals_summary != "(no goals set)":
				parts_c.append(f"Goals: {goals_summary}\n")
			parts_c.extend([
				f"Visible enemies: {enemy_summ_compact}\n\n",
				f"Available actions (index: description):\n" + "\n".join(action_lines_compact) + "\n\n",
				f"{instructions}\n",
				"Return either a single integer index (0-based) or call choose_action with that index.",
			])
			prompt = "".join(parts_c)

		return prompt

	def _move_triggers_oa(self, battle, entity, path: List[Tuple[int, int]]) -> bool:
		"""Estimate OA risk: if leaving any enemy's melee reach along the path without disengage."""
		try:
			triggers, _ = self._move_oa_info(battle, entity, path)
			return triggers
		except Exception:
			return False

	def _move_oa_info(self, battle, entity, path: List[Tuple[int, int]]) -> Tuple[bool, Optional[str]]:
		"""Return whether OA is triggered along the path and the first foe name causing it."""
		try:
			if entity.disengage(battle):
				return False, None
			m = battle.map_for(entity)
			if not m or not path:
				return False, None
			# Build positions including current start
			start_pos = m.entity_or_object_pos(entity)
			positions = [start_pos] + [tuple(p) for p in path[1:]] if path[0] == start_pos else [start_pos] + [tuple(p) for p in path]
			enemies = [e for e in battle.opponents_of(entity) if e.conscious()]
			if not enemies:
				return False, None
			feet_per = getattr(m, 'feet_per_grid', 5) or 5
			# For each enemy, track adjacency over positions and detect leaving reach
			for foe in enemies:
				reach_grids = (foe.melee_distance() or 5) / feet_per
				in_melee_prev = None
				for pos in positions:
					dist = m.distance(entity, foe, entity_1_pos=pos)
					in_melee = dist <= reach_grids
					if in_melee_prev is True and in_melee is False:
						return True, getattr(foe, 'name', None)
					in_melee_prev = in_melee if in_melee_prev is None else in_melee
			return False, None
		except Exception:
			return False, None

	def _strip_ansi(self, s: str) -> str:
		"""Remove ANSI escape sequences for clean LLM prompts."""
		if not s:
			return s
		ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
		return ansi_re.sub('', s)

	def _spell_slots_summary(self, entity) -> str:
		"""Return a compact spell slots summary like 'L1 3/4, L2 1/2'. Empty string if none."""
		parts = []
		try:
			get_max = getattr(entity, 'max_spell_slots', None)
			get_cur = getattr(entity, 'spell_slots_count', None)
			if not callable(get_max) or not callable(get_cur):
				return ""
			for lvl in range(1, 10):
				try:
					max_slots = get_max(lvl)
					if not max_slots:
						continue
					cur = get_cur(lvl)
					parts.append(f"L{lvl} {cur}/{max_slots}")
				except Exception:
					continue
			return ", ".join(parts)
		except Exception:
			return ""

	def _recent_actions(self, battle, entity, n: int = 5) -> List[str]:
		"""Return a most-recent-first list of up to n short descriptions of this entity’s past actions."""
		try:
			log = list(getattr(battle, 'battle_log', []))
			mine = [a for a in log if getattr(a, 'source', None) is entity]
			if not mine:
				return []
			last = mine[-n:]
			last.reverse()  # most recent first
			return [self._action_short_desc(a) for a in last]
		except Exception:
			return []

	def _recent_actions_for(self, battle, entities: List, n: int = 5) -> List[str]:
		"""Return most-recent-first list of up to n actions by any of the provided entities, with names."""
		try:
			if not entities:
				return []
			entities_set = set(entities)
			log = list(getattr(battle, 'battle_log', []))
			mine = [a for a in log if getattr(a, 'source', None) in entities_set]
			if not mine:
				return []
			last = mine[-n:]
			last.reverse()
			def fmt(a):
				actor = getattr(getattr(a, 'source', None), 'name', None) or str(getattr(a, 'source', None))
				return f"{actor}: {self._action_short_desc(a)}"
			return [fmt(a) for a in last]
		except Exception:
			return []

	def _action_short_desc(self, action: Action) -> str:
		"""Best-effort short description for an action."""
		try:
			label = None
			if hasattr(action, 'label') and callable(getattr(action, 'label')):
				label = action.label()
			if label:
				return str(label)
			# Try __str__ for many actions that implement it
			s = str(action)
			if s and s != action.__class__.__name__:
				return s
			# Fallback: action type + optional target name
			tgt = getattr(action, 'target', None)
			tname = getattr(tgt, 'name', None) if tgt else None
			return f"{getattr(action, 'action_type', 'action')}{f' {tname}' if tname else ''}"
		except Exception:
			return getattr(action, 'action_type', 'action')

	def _low_slots_note(self, entity) -> str:
		"""Return 'Low slots: L2 L3' if any levels have 1 or fewer slots remaining."""
		try:
			get_max = getattr(entity, 'max_spell_slots', None)
			get_cur = getattr(entity, 'spell_slots_count', None)
			if not callable(get_max) or not callable(get_cur):
				return ""
			low = []
			for lvl in range(1, 10):
				try:
					max_slots = get_max(lvl)
					if not max_slots:
						continue
					cur_any: Any = get_cur(lvl)
					# Normalize to int if possible for safe comparison
					try:
						cur_int = int(cur_any)
					except Exception:
						cur_int = None
					if cur_int is not None and cur_int <= 1:
						low.append(f"L{lvl}")
				except Exception:
					continue
			return f"Low slots: {' '.join(low)}" if low else ""
		except Exception:
			return ""

	def _concentration_label(self, entity) -> str:
		"""Return 'none' or a friendly effect name for current concentration."""
		eff = getattr(entity, 'concentration', None)
		if not eff:
			return 'none'
		# Prefer an explicit label/id if present
		name = None
		try:
			name = getattr(eff, 'label', None)
			if callable(name):
				name = name()
			if not name:
				name = getattr(eff, 'id', None)
			if not name and hasattr(eff, 'action') and getattr(eff.action, 'spell_action', None):
				try:
					name = eff.action.spell_action.short_name()
				except Exception:
					pass
			if not name:
				name = eff.__class__.__name__
		except Exception:
			name = eff.__class__.__name__ if eff else 'none'
		return str(name)

	# --- Utilities ---
	def _local_greedy_simulation(self, _prompt: str) -> str:
		# With no model, return empty to force heuristic fallback
		return ""

	def _local_parse_choice_from_text(self, text: str, n: int) -> Optional[int]:
		if not text:
			return None
		# Find first integer in text; accept [3], 3:, Choice 3, etc.
		m = re.search(r"(-?\d+)", text)
		if not m:
			return None
		try:
			val = int(m.group(1))
			# Accept 1-based answers; map to 0-based if it looks like a menu selection
			if val >= n:
				# Maybe user sent 1-based; convert if in range
				if 1 <= val <= n:
					return val - 1
				return None
			if val < 0:
				return None
			return val
		except Exception:
			return None

	def _maybe_enrich_action_targets(self, battle, entity, action: Action) -> Action:
		"""
		If the chosen action lacks required parameters (like target), pick a reasonable default.
		"""
		if isinstance(action, AttackAction) and not getattr(action, "target", None):
			# Pick the first valid target
			targets = battle.valid_targets_for(entity, action)
			if targets:
				action = action.clone()
				action.target = targets[0]
		elif isinstance(action, SpellAction) and not getattr(action, "target", None):
			# Assign a reasonable default spell target if any
			try:
				targets = battle.valid_targets_for(entity, action)
				if targets:
					action = action.clone()
					action.target = targets[0]
			except Exception:
				pass
		elif isinstance(action, MoveAction) and not action.move_path:
			# No path precomputed; just fallback to heuristic ranking overall
			pass
		return action

	def _call_mcp_tool(self, prompt: str, n_actions: int) -> Optional[int]:
		"""
		Optional MCP bridge:
		If env N20_MCP_URL is set, POST {prompt, n_actions} and expect {index:int}.
		This is a lightweight adapter for external MCP servers.
		"""
		url = os.getenv("N20_MCP_URL")
		if not url:
			return None
		try:
			import requests  # type: ignore
		except Exception:
			return None
		try:
			resp = requests.post(url, json={"prompt": prompt, "n_actions": n_actions}, timeout=8)
			if resp.status_code != 200:
				return None
			data = resp.json()
			idx = int(data.get("index", -1))
			if 0 <= idx < n_actions:
				return idx
			return None
		except Exception:
			return None

	# --- Conversation and Context Helpers ---
	def _get_conversation_summary(self, entity, n: int = 5) -> List[str]:
		"""
		Get a summary of recent conversations from the entity's memory buffer.
		Returns a list of formatted conversation snippets.
		"""
		try:
			memory_buffer = getattr(entity, 'memory_buffer', [])
			if not memory_buffer:
				return []
			
			# Get the most recent n conversation entries
			recent = memory_buffer[-n:] if len(memory_buffer) > n else memory_buffer
			summaries = []
			
			for entry in recent:
				try:
					source = entry.get('source')
					source_name = getattr(source, 'name', str(source)) if source else 'Unknown'
					message = entry.get('message', '')
					language = entry.get('language', 'common')
					directed_to = entry.get('directed_to', [])
					
					# Check if this entity can understand the language
					entity_languages = getattr(entity, 'languages', lambda: ['common'])()
					if language.lower() not in [l.lower() for l in entity_languages]:
						# Can't understand - show as unintelligible
						summaries.append(f"{source_name} said something in {language} (unintelligible)")
					else:
						# Truncate long messages
						msg_preview = message[:100] + "..." if len(message) > 100 else message
						if directed_to:
							targets = ", ".join(getattr(t, 'name', str(t)) for t in directed_to if t)
							summaries.append(f"{source_name} to {targets}: \"{msg_preview}\"")
						else:
							summaries.append(f"{source_name}: \"{msg_preview}\"")
				except Exception:
					continue
			
			return summaries
		except Exception:
			return []

	def _get_backstory_summary(self, entity, max_chars: int = 200) -> str:
		"""
		Get a brief backstory or personality summary for the entity.
		Returns a truncated version suitable for prompt context.
		"""
		try:
			backstory = ""
			
			# Try to get backstory from entity methods or properties
			if hasattr(entity, 'backstory') and callable(entity.backstory):
				backstory = entity.backstory() or ""
			elif hasattr(entity, 'properties'):
				backstory = entity.properties.get('backstory', '')
			
			# Also check for personality traits or description
			if not backstory:
				if hasattr(entity, 'description') and callable(entity.description):
					backstory = entity.description() or ""
				elif hasattr(entity, 'properties'):
					backstory = entity.properties.get('description', '')
			
			if not backstory:
				return ""
			
			# Truncate if too long
			if len(backstory) > max_chars:
				return backstory[:max_chars].rsplit(' ', 1)[0] + "..."
			return backstory
		except Exception:
			return ""

	def _summarize_entity_action_history(self, entity, battle, n: int = 10) -> str:
		"""
		Generate a narrative summary of the entity's recent actions.
		This provides more context than just listing actions.
		"""
		try:
			recent = self._recent_actions(battle, entity, n=n)
			if not recent:
				return ""
			
			# Create a brief narrative
			action_types = {}
			for desc in recent:
				# Categorize actions
				desc_lower = desc.lower()
				if 'attack' in desc_lower:
					action_types['attacks'] = action_types.get('attacks', 0) + 1
				elif 'move' in desc_lower:
					action_types['moves'] = action_types.get('moves', 0) + 1
				elif 'cast' in desc_lower or 'spell' in desc_lower:
					action_types['spells'] = action_types.get('spells', 0) + 1
				elif 'dodge' in desc_lower:
					action_types['defensive'] = action_types.get('defensive', 0) + 1
				elif 'disengage' in desc_lower:
					action_types['retreat'] = action_types.get('retreat', 0) + 1
			
			# Build narrative summary
			parts = []
			if action_types.get('attacks', 0) > 2:
				parts.append("aggressive combat stance")
			if action_types.get('defensive', 0) > 0 or action_types.get('retreat', 0) > 0:
				parts.append("defensive/evasive behavior")
			if action_types.get('spells', 0) > 1:
				parts.append("magical support/offense")
			
			return "Recent behavior: " + ", ".join(parts) if parts else ""
		except Exception:
			return ""

	def to_dict(self) -> dict:
		"""Serialize controller state including entity contexts for persistence."""
		base = super().to_dict()
		base['entity_context'] = self._entity_context
		return base

	@staticmethod
	def from_dict(data: dict) -> 'LlmMcpController':
		"""Restore controller from serialized state."""
		controller = LlmMcpController(data['session'])
		controller.battle_data = data.get('battle_data', {})
		controller._entity_context = data.get('entity_context', {})
		return controller
