import json
import os
import random
import re
import requests
from typing import List, Optional, Tuple

from natural20.generic_controller import GenericController
from natural20.action import Action
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.look_action import LookAction
from natural20.map_renderer import MapRenderer

# Optional import of webapp LLM provider abstraction; keep controller decoupled if unavailable
try:
	# Using provider interface from web layer without importing the entire app
	from webapp.llm_handler import OllamaProvider, OpenAIProvider, AnthropicProvider  # type: ignore
except Exception:
	OllamaProvider = None  # type: ignore
	OpenAIProvider = None  # type: ignore
	AnthropicProvider = None  # type: ignore


class LlmMcpController(GenericController):
	"""
	A controller that delegates action selection to an LLM with optional MCP tools.

	Behavior:
	- Builds a compact, text-based prompt from current map, entity status, and available actions.
	- If OpenAI client is available, can use tool calling to return an index.
	- If tools/MCP not available, falls back to parsing the first digit in the model's reply.
	- If anything fails, gracefully falls back to GenericController's heuristic ranking.
	"""

	def __init__(self, session, valid_move_types=None, llm_client=None, model: Optional[str] = None, use_tools: bool = True, llm_provider=None):
		super().__init__(session, valid_move_types)
		self.client = llm_client  # expected to be OpenAI-like client; optional
		self.model = model or os.getenv("N20_LLM_MODEL", "gpt-4o-mini")
		self.use_tools = use_tools
		# Generic LLMProvider backend (e.g., OllamaProvider). If none provided, try to wire Ollama by default.
		self.llm_provider = llm_provider or self._default_provider()

	def _default_provider(self):
		"""
		Construct a default provider from environment variables.
		Respects LLM_PROVIDER in [ollama|openai|anthropic], defaulting to ollama.
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
		if getattr(self, "llm_provider", None) is not None:
			try:
				instructions = (
					"You are a tactical assistant. Given a list of actions indexed from 0, choose the single best index. "
					"Respond with ONLY the integer index (no text)."
				)
				messages = [
					{"role": "system", "content": instructions},
					{"role": "user", "content": prompt},
				]
				text = self.llm_provider.send_message(messages)
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
			tools = [
				{
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
			]

		if tools:
			resp = self.client.chat.completions.create(
				model=self.model,
				messages=[{"role": "user", "content": prompt}],
				tools=tools,
				tool_choice="required",
			)
			try:
				args = resp.choices[0].message.tool_calls[0].function.arguments
				data = json.loads(args)
				return int(data.get("index", 0))
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

		def action_label(a: Action, idx: int) -> str:
			try:
				if isinstance(a, MoveAction):
					if a.move_path:
						end = a.move_path[-1]
						return f"{idx}. move to {tuple(end)}"
					return f"{idx}. move"
				if isinstance(a, AttackAction):
					target = getattr(a, "target", None)
					tname = getattr(target, "name", None) if target else None
					weap = a.npc_action['name'] if getattr(a, 'npc_action', None) else a.using
					return f"{idx}. attack {tname or 'enemy'} with {weap}"
				if isinstance(a, SpellAction):
					sp = getattr(a, 'spell', None) or (a.opts or {}).get('spell')
					t = getattr(a, 'target', None)
					return f"{idx}. cast {sp or 'a spell'} on {getattr(t, 'name', 'target')}"
				if isinstance(a, LookAction):
					return f"{idx}. look around"
				# Generic fallback
				return f"{idx}. {a.action_type}"
			except Exception:
				return f"{idx}. {getattr(a, 'action_type', 'action')}"

		action_lines = [action_label(a, i) for i, a in enumerate(available_actions)]

		hp = f"{entity.hp()}/{entity.max_hp()}"
		cond = []
		if entity.prone():
			cond.append("prone")
		if hasattr(entity, 'dodging') and entity.dodging:
			cond.append("dodging")
		cond_text = ", ".join(cond) if cond else "none"

		# Nearby enemies summary
		enemies = battle.opponents_of(entity)
		vis_enemies = [e for e in enemies if battle.can_see(entity, e)]
		enemy_summ = ", ".join(f"{e.name}({e.hp()}/{e.max_hp()})" for e in vis_enemies) or "(none visible)"

		instructions = (
			"You're an NPC tactician in a D&D-like tactical sim. Choose the single best action for this turn. "
			"Prefer actions that increase win odds: secure lethal hits, avoid unnecessary opportunity attacks, "
			"use movement intelligently to engage or gain line of sight, and conserve scarce resources unless impactful."
		)

		prompt = (
			f"Map (visible):\n{map_text}\n"
			f"You are: {entity.name} HP {hp}, conditions: {cond_text}\n"
			f"Visible enemies: {enemy_summ}\n\n"
			f"Available actions (index: description):\n" + "\n".join(action_lines) + "\n\n"
			f"{instructions}\n"
			"Return either a single integer index (0-based) or call choose_action with that index."
		)
		return prompt

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

