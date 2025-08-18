import json
import os
import random
import re
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

		def action_label(a: Action, idx: int) -> str:
			try:
				if isinstance(a, MoveAction):
					if a.move_path:
						end = a.move_path[-1]
						steps = max(0, len(a.move_path) - 1)
						ft = steps * feet_per
						# Simulate OA risk along path
						oa = "; OA risk" if self._move_triggers_oa(battle, entity, a.move_path) else ""
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
						if target:
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
									info.append(f"cover +{cov}")
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
						prob = a.compute_hit_probability(battle)
						if prob not in (None, 0):
							info.append(f"hit {int(round(prob*100))}%")
						avg = a.avg_damage(battle)
						if avg not in (None, 0):
							info.append(f"avg dmg {int(round(avg))}")
						if t:
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
										info.append(f"cover +{cov}")
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

		action_lines = [action_label(a, i) for i, a in enumerate(available_actions)]

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
		def enemy_line(e):
			d = _dist_ft(entity, e)
			return f"{e.name}({e.hp()}/{e.max_hp()}{'' if d is None else f', {d} ft'})"
		enemy_summ = ", ".join(enemy_line(e) for e in vis_enemies) or "(none visible)"

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
		parts.extend([
			f"Visible enemies: {enemy_summ}\n\n",
			f"Available actions (index: description):\n" + "\n".join(action_lines) + "\n\n",
			f"{instructions}\n",
			"Return either a single integer index (0-based) or call choose_action with that index.",
		])
		prompt = "".join(parts)
		return prompt

	def _move_triggers_oa(self, battle, entity, path: List[Tuple[int, int]]) -> bool:
		"""Estimate OA risk: if leaving any enemy's melee reach along the path without disengage."""
		try:
			if entity.disengage(battle):
				return False
			m = battle.map_for(entity)
			if not m or not path:
				return False
			# Build positions including current start
			start_pos = m.entity_or_object_pos(entity)
			positions = [start_pos] + [tuple(p) for p in path[1:]] if path[0] == start_pos else [start_pos] + [tuple(p) for p in path]
			enemies = [e for e in battle.opponents_of(entity) if e.conscious()]
			if not enemies:
				return False
			feet_per = getattr(m, 'feet_per_grid', 5) or 5
			# For each enemy, track adjacency over positions and detect leaving reach
			for foe in enemies:
				reach_grids = (foe.melee_distance() or 5) / feet_per
				in_melee_prev = None
				for pos in positions:
					dist = m.distance(entity, foe, entity_1_pos=pos)
					in_melee = dist <= reach_grids
					if in_melee_prev is True and in_melee is False:
						return True
					in_melee_prev = in_melee if in_melee_prev is None else in_melee
			return False
		except Exception:
			return False

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

