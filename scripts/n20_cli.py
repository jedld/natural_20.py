"""Interactive CLI for natural20.

This tool loads a scenario from ./user_levels/<scenario>/ (or an explicit path)
and provides a small interactive REPL for stepping the environment/battle loop
and issuing basic commands (list entities, take actions, end turn).

Usage:
  python scripts/n20_cli.py --scenario death_house
  python scripts/n20_cli.py --path /abs/path/to/scenario
"""

from __future__ import annotations

import argparse
import cmd
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map_renderer import MapRenderer
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _repo_root() -> Path:
	return Path(__file__).resolve().parents[1]


def _default_user_levels_dir() -> Path:
	return _repo_root() / "user_levels"


def _resolve_scenario_path(scenario: Optional[str], explicit_path: Optional[str]) -> Path:
	if explicit_path:
		p = Path(explicit_path).expanduser().resolve()
	else:
		if not scenario:
			raise SystemExit("Provide either --scenario <name> or --path <dir>.")
		p = (_default_user_levels_dir() / scenario).resolve()

	if not p.exists() or not p.is_dir():
		raise SystemExit(f"Scenario directory not found: {p}")

	if not (p / "game.yml").exists():
		raise SystemExit(f"Scenario is missing game.yml: {p}")

	return p


def _load_index_json(scenario_root: Path) -> dict:
	index_path = scenario_root / "index.json"
	if not index_path.exists():
		return {}
	try:
		return json.loads(index_path.read_text())
	except Exception:
		return {}


def _safe_uid(obj) -> str:
	return str(getattr(obj, "entity_uid", None) or "")


def _entity_label(entity) -> str:
	try:
		return entity.label()
	except Exception:
		return getattr(entity, "name", None) or str(entity)


@dataclass
class TurnState:
	started: bool = False
	entity_uid: Optional[str] = None


class Natural20Cli(cmd.Cmd):
	intro = "Natural20 interactive CLI. Type 'help' or '?' for commands."
	prompt = "n20> "

	def __init__(
		self,
		session: Session,
		scenario_root: Path,
		index_data: dict,
		manual_groups: Iterable[str] = ("a",),
		npc_controller: str = "ai",
	):
		super().__init__()
		self.session = session
		self.scenario_root = scenario_root
		self.index_data = index_data
		self.manual_groups = set(manual_groups)
		self.npc_controller = npc_controller

		# Map selection for viewing / battle detection
		self.current_map_name = "index" if "index" in self.session.maps else next(iter(self.session.maps.keys()))
		self.battle: Optional[Battle] = None

		# Turn bookkeeping
		self._turn = TurnState()
		self._last_actions = []
		self._last_actions_for_uid: Optional[str] = None

	# ---------- helpers ----------

	def _current_map(self):
		return self.session.maps[self.current_map_name]

	def _reset_turn_state(self):
		self._turn = TurnState(started=False, entity_uid=None)
		self._last_actions = []
		self._last_actions_for_uid = None

	def _ensure_battle(self) -> Battle:
		if not self.battle:
			raise RuntimeError("No active battle. Use 'battle detect' or 'battle start'.")
		return self.battle

	def _ensure_turn_started(self):
		battle = self._ensure_battle()
		cur = battle.current_turn()
		if cur is None:
			raise RuntimeError("Battle has no current turn.")

		cur_uid = _safe_uid(cur)
		if not self._turn.started or self._turn.entity_uid != cur_uid:
			battle.start_turn()
			try:
				cur.reset_turn(battle)
			except Exception:
				pass
			self._turn.started = True
			self._turn.entity_uid = cur_uid
			self._last_actions = []
			self._last_actions_for_uid = None

	def _controller_for(self, entity):
		# Keep a straightforward mapping: PCs are manual by default (unless overridden)
		if isinstance(entity, PlayerCharacter) or getattr(entity, "group", None) in self.manual_groups:
			return None
		# NPC controller option hooks
		if self.npc_controller == "ai":
			return GenericController(self.session)
		return GenericController(self.session)

	def _list_entities(self, map_name: Optional[str] = None):
		map_obj = self.session.maps[map_name or self.current_map_name]
		for ent in list(map_obj.entities.keys()):
			pos = map_obj.entity_or_object_pos(ent)
			hp = None
			ac = None
			try:
				hp = ent.hp()
			except Exception:
				pass
			try:
				ac = ent.armor_class()
			except Exception:
				pass
			group = getattr(ent, "group", None)
			extra = []
			if hp is not None:
				try:
					extra.append(f"hp={hp}/{ent.max_hp()}")
				except Exception:
					extra.append(f"hp={hp}")
			if ac is not None:
				extra.append(f"ac={ac}")
			if group is not None:
				extra.append(f"group={group}")
			flags = []
			try:
				if ent.dead():
					flags.append("dead")
				elif ent.unconscious():
					flags.append("unconscious")
			except Exception:
				pass

			uid = _safe_uid(ent)
			label = _entity_label(ent)
			pos_s = "?" if pos is None else f"{pos[0]},{pos[1]}"
			meta = " ".join(extra + flags).strip()
			print(f"- {label} uid={uid} pos={pos_s}{(' ' + meta) if meta else ''}")

	def _battle_status_line(self) -> str:
		if not self.battle:
			return "battle=none"
		cur = self.battle.current_turn()
		cur_s = "none" if cur is None else f"{_entity_label(cur)} uid={_safe_uid(cur)}"
		return f"battle=active round={self.battle.round} turn={self.battle.current_turn_index} current={cur_s}"

	def _available_actions_for_current(self):
		battle = self._ensure_battle()
		self._ensure_turn_started()
		entity = battle.current_turn()
		actions = entity.available_actions(self.session, battle, auto_target=True, map=battle.map_for(entity))
		self._last_actions = list(actions)
		self._last_actions_for_uid = _safe_uid(entity)
		return self._last_actions

	def _is_manual_turn(self) -> bool:
		if not self.battle:
			return False
		cur = self.battle.current_turn()
		if cur is None:
			return False
		return self.battle.controller_for(cur) is None

	def _format_action(self, idx: int, action) -> str:
		parts = [f"[{idx}] {action.action_type}"]
		# Best-effort: include target, weapon/spell, movement endpoint
		try:
			tgt = getattr(action, "target", None)
			if tgt is not None:
				if isinstance(tgt, list):
					parts.append("target=" + ",".join(_entity_label(t) if hasattr(t, "__dict__") else str(t) for t in tgt))
				else:
					parts.append("target=" + _entity_label(tgt))
		except Exception:
			pass
		try:
			if getattr(action, "attack_name", None):
				parts.append(f"with={action.attack_name}")
		except Exception:
			pass
		try:
			spell = getattr(action, "spell_action", None)
			if spell is not None:
				parts.append(f"spell={spell.short_name()}")
		except Exception:
			pass
		try:
			mp = getattr(action, "move_path", None)
			if mp:
				parts.append(f"to={mp[-1][0]},{mp[-1][1]}")
		except Exception:
			pass
		return " ".join(parts)

	def _end_turn_and_advance(self):
		battle = self._ensure_battle()
		entity = battle.current_turn()
		if entity is not None:
			try:
				entity.resolve_trigger("end_of_turn")
			except Exception:
				pass
		battle.end_turn()
		result = battle.next_turn()
		self._reset_turn_state()

		if result == "tpk" or (battle.started and battle.battle_ends()):
			print(f"Battle ended. Winning groups: {battle.winning_groups()}")
			self.battle = None
			self._reset_turn_state()
			return

		# Start the next turn so the user sees the new actor immediately
		try:
			self._ensure_turn_started()
		except Exception:
			pass

	# ---------- cmd hooks ----------

	def emptyline(self):
		# Do nothing (avoid repeating last command)
		return

	def default(self, line: str):
		print(f"Unknown command: {line}. Try 'help'.")

	# ---------- basic commands ----------

	def do_status(self, arg: str):
		"""Show high-level status."""
		print(f"scenario={self.scenario_root}")
		print(f"map={self.current_map_name}")
		print(f"game_time={self.session.game_time}")
		print(self._battle_status_line())

	def do_maps(self, arg: str):
		"""List available maps in this scenario."""
		for name in self.session.maps.keys():
			marker = "*" if name == self.current_map_name else " "
			print(f"{marker} {name}")

	def do_usemap(self, arg: str):
		"""Switch current map for viewing and battle detection: usemap <map_name>"""
		name = arg.strip()
		if not name:
			print("usage: usemap <map_name>")
			return
		if name not in self.session.maps:
			print(f"Unknown map: {name}")
			return
		self.current_map_name = name
		print(f"current_map={name}")

	def do_render(self, arg: str):
		"""Render the current map as ANSI/text."""
		m = self._current_map()
		try:
			print(MapRenderer(m).render())
		except Exception as e:
			print(f"Render failed: {e}")

	def do_entities(self, arg: str):
		"""List entities on the current map (or a specified map): entities [map_name]"""
		name = arg.strip() or None
		if name and name not in self.session.maps:
			print(f"Unknown map: {name}")
			return
		self._list_entities(name)

	# ---------- battle commands ----------

	def do_battle(self, arg: str):
		"""Battle management.

		battle status
		battle detect
		battle start
		battle end
		"""
		argv = shlex.split(arg)
		if not argv:
			print("usage: battle <status|detect|start|end>")
			return
		sub = argv[0]

		if sub == "status":
			print(self._battle_status_line())
			return

		if sub == "end":
			if not self.battle:
				print("No active battle.")
				return
			self.battle = None
			self._reset_turn_state()
			print("Battle cleared.")
			return

		if sub in {"detect", "start"}:
			if self.battle:
				print("Battle already active.")
				return

			# Start battle on current map, using group opposition rules.
			m = self._current_map()
			entities_by_group = {}
			for ent in list(m.entities.keys()):
				g = getattr(ent, "group", None) or "a"
				entities_by_group.setdefault(g, set()).add(ent)

			add_to_initiative_set = set()
			start_battle = False

			groups = list(entities_by_group.keys())
			for i, g1 in enumerate(groups):
				for g2 in groups[i + 1 :]:
					try:
						if not self.session.opposing(g1, g2):
							continue
					except Exception:
						continue
					for e1 in entities_by_group.get(g1, set()):
						for e2 in entities_by_group.get(g2, set()):
							try:
								if not e1.conscious() or not e2.conscious():
									continue
							except Exception:
								continue
							try:
								if e2.passive():
									continue
							except Exception:
								pass
							try:
								if m.can_see(e2, e1):
									add_to_initiative_set.add((e1, g1))
									add_to_initiative_set.add((e2, g2))
									start_battle = True
							except Exception:
								continue

			if sub == "start" and not start_battle:
				# Manual start: include everyone conscious on map
				for g, ents in entities_by_group.items():
					for e in ents:
						try:
							if e.conscious():
								add_to_initiative_set.add((e, g))
						except Exception:
							add_to_initiative_set.add((e, g))
				start_battle = len(add_to_initiative_set) > 0

			if not start_battle:
				print("No opposing entities detected on current map.")
				return

			battle = Battle(self.session, self.session.maps)
			for ent, group in sorted(add_to_initiative_set, key=lambda x: _safe_uid(x[0])):
				ctrl = self._controller_for(ent)
				if ctrl is not None:
					ctrl.register_handlers_on(ent)
				battle.add(ent, group, controller=ctrl)

			battle.start()
			self.battle = battle
			self._reset_turn_state()
			self._ensure_turn_started()
			cur = battle.current_turn()
			print(f"Battle started. Current turn: {_entity_label(cur)} uid={_safe_uid(cur)}")
			return

		print(f"Unknown battle subcommand: {sub}")

	# ---------- turn / action commands ----------

	def do_turn(self, arg: str):
		"""Show current turn info."""
		if not self.battle:
			print("No active battle.")
			return
		self._ensure_turn_started()
		e = self.battle.current_turn()
		m = self.battle.map_for(e)
		pos = None
		try:
			pos = m.entity_or_object_pos(e) if m else None
		except Exception:
			pos = None
		pos_s = "?" if pos is None else f"{pos[0]},{pos[1]}"
		print(f"round={self.battle.round} idx={self.battle.current_turn_index} entity={_entity_label(e)} uid={_safe_uid(e)} pos={pos_s}")

	def do_actions(self, arg: str):
		"""List available actions for the current turn entity."""
		try:
			actions = self._available_actions_for_current()
		except Exception as e:
			print(f"actions failed: {e}")
			return
		if not actions:
			print("(no actions)")
			return
		for i, a in enumerate(actions):
			print(self._format_action(i, a))

	def do_act(self, arg: str):
		"""Execute an action by index for the current turn entity: act <index>"""
		if not self.battle:
			print("No active battle.")
			return

		s = arg.strip()
		if not s:
			print("usage: act <index>")
			return
		try:
			idx = int(s)
		except ValueError:
			print("index must be an integer")
			return

		self._ensure_turn_started()
		entity = self.battle.current_turn()
		uid = _safe_uid(entity)
		if self._last_actions_for_uid != uid or not self._last_actions:
			self._available_actions_for_current()

		if idx < 0 or idx >= len(self._last_actions):
			print(f"index out of range (0..{len(self._last_actions) - 1})")
			return

		action = self._last_actions[idx]
		try:
			self.battle.action(action)
			self.battle.commit(action)
		except Exception as e:
			print(f"action failed: {e}")
			return

		try:
			if entity.unconscious() or entity.dead():
				print(f"{_entity_label(entity)} is down. Ending turn.")
				self._end_turn_and_advance()
		except Exception:
			pass

	def do_ai(self, arg: str):
		"""Run the AI loop for the current turn entity until it decides to end turn."""
		if not self.battle:
			print("No active battle.")
			return
		self._ensure_turn_started()
		battle = self.battle
		entity = battle.current_turn()

		if battle.controller_for(entity) is None:
			ctrl = GenericController(self.session)
			ctrl.register_handlers_on(entity)
			battle.set_controller_for(entity, ctrl)
			print(f"Assigned AI controller to {_entity_label(entity)} for this battle.")

		cycles = 0
		while True:
			cycles += 1
			if cycles > 50:
				print("AI loop safety stop (50 cycles).")
				break
			action = battle.move_for(entity)
			if not action:
				break
			battle.action(action)
			battle.commit(action)
			try:
				if entity.unconscious() or entity.dead():
					break
			except Exception:
				break
		print(f"AI done for {_entity_label(entity)}. Use 'endturn' to advance.")

	def do_control(self, arg: str):
		"""Set controller for the current turn entity: control <manual|ai>"""
		if not self.battle:
			print("No active battle.")
			return
		mode = arg.strip().lower()
		if mode not in {"manual", "ai"}:
			print("usage: control <manual|ai>")
			return
		self._ensure_turn_started()
		battle = self._ensure_battle()
		entity = battle.current_turn()

		if mode == "manual":
			battle.set_controller_for(entity, None)
			print(f"Controller set to manual for {_entity_label(entity)}")
			return

		ctrl = GenericController(self.session)
		ctrl.register_handlers_on(entity)
		battle.set_controller_for(entity, ctrl)
		print(f"Controller set to AI for {_entity_label(entity)}")

	def do_endturn(self, arg: str):
		"""End the current entity's turn and advance to the next."""
		if not self.battle:
			print("No active battle.")
			return
		self._end_turn_and_advance()

	def do_step(self, arg: str):
		"""Advance the game by N turns (default 1). Stops when manual input is needed."""
		if not self.battle:
			print("No active battle.")
			return
		n_s = arg.strip() or "1"
		try:
			n = int(n_s)
		except ValueError:
			print("usage: step [n]")
			return

		for _ in range(max(1, n)):
			self._ensure_turn_started()
			battle = self._ensure_battle()
			entity = battle.current_turn()

			if self._is_manual_turn():
				print(f"Manual turn: {_entity_label(entity)} uid={_safe_uid(entity)}")
				print("Use 'actions' and 'act <idx>' (or 'ai') then 'endturn'.")
				break

			# AI full turn
			cycles = 0
			while True:
				cycles += 1
				if cycles > 50:
					print("AI loop safety stop (50 cycles).")
					break
				action = battle.move_for(entity)
				if not action:
					break
				battle.action(action)
				battle.commit(action)
				try:
					if entity.unconscious() or entity.dead():
						break
				except Exception:
					break

			self._end_turn_and_advance()
			if not self.battle:
				break

	# ---------- quitting ----------

	def do_quit(self, arg: str):
		"""Quit."""
		return True

	def do_exit(self, arg: str):
		"""Quit."""
		return True


def main(argv: Optional[list[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Natural20 interactive CLI")
	parser.add_argument("--scenario", help="Scenario folder name under ./user_levels")
	parser.add_argument("--path", help="Explicit path to scenario root (contains game.yml)")
	parser.add_argument(
		"--manual-groups",
		default="a",
		help="Comma-separated groups treated as manual (default: a)",
	)
	parser.add_argument(
		"--npc-controller",
		choices=["ai"],
		default="ai",
		help="NPC controller (default: ai)",
	)
	args = parser.parse_args(argv)

	scenario_root = _resolve_scenario_path(args.scenario, args.path)
	index_data = _load_index_json(scenario_root)

	event_manager = EventManager(movement_consolidation=True)
	event_manager.standard_cli()
	session = Session(str(scenario_root), event_manager=event_manager)
	session.render_for_text = True

	manual_groups = [g.strip() for g in (args.manual_groups or "").split(",") if g.strip()]
	cli = Natural20Cli(
		session=session,
		scenario_root=scenario_root,
		index_data=index_data,
		manual_groups=manual_groups,
		npc_controller=args.npc_controller,
	)
	try:
		cli.cmdloop()
	except KeyboardInterrupt:
		print("\nExiting.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

