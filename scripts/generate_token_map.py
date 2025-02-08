from natural20.gym.tools import generate_entity_token_map, generate_spell_token_map, generate_weapon_token_map
from natural20.session import Session


# Get location of game template from the commandline


import argparse
parser = argparse.ArgumentParser(description='Generate entity token map')
parser.add_argument('game_template', type=str, help='Path to the game template')

args = parser.parse_args()


entity_output_file = f"{args.game_template}/entity_token_map.csv"
weapon_output_file = f"{args.game_template}/weapon_token_map.csv"
spell_output_file = f"{args.game_template}/spell_token_map.csv"

session = Session(root_path=args.game_template)
generate_entity_token_map(session, entity_output_file)
generate_weapon_token_map(session, weapon_output_file)
generate_spell_token_map(session, spell_output_file)
