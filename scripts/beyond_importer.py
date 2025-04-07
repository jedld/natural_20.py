#!/usr/bin/env python3

import yaml
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path

class BeyondImporter:
    def __init__(self):
        self.base_url = "https://character-service.dndbeyond.com/character/v5/character"
        
    def fetch_character(self, character_id: int) -> Dict[str, Any]:
        """Fetch character data from D&D Beyond API."""
        url = f"{self.base_url}/{character_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()["data"]

    def _get_ability_score(self, stats: List[Dict], bonus_stats: List[Dict], ability_id: int) -> int:
        """Calculate final ability score from base and bonus stats."""
        base = next((stat["value"] for stat in stats if stat["id"] == ability_id), 0)
        bonus = next((stat["value"] for stat in bonus_stats if stat["id"] == ability_id), 0) or 0
        return base + bonus

    def _map_alignment(self, alignment_id: int) -> str:
        """Map D&D Beyond alignment ID to alignment string."""
        alignment_map = {
            1: "lawful_good",
            2: "neutral_good",
            3: "chaotic_good",
            4: "lawful_neutral",
            5: "true_neutral",
            6: "chaotic_neutral",
            7: "lawful_evil",
            8: "neutral_evil",
            9: "chaotic_evil"
        }
        return alignment_map.get(alignment_id, "true_neutral")

    def _get_skills(self, character_data: Dict[str, Any]) -> List[str]:
        """Extract skills from character data."""
        skills = []
        if "skills" in character_data:
            for skill in character_data["skills"]:
                if skill.get("proficient", False):
                    skills.append(skill["definition"]["name"].lower())
        return skills

    def _get_equipment(self, character_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract equipment from character data."""
        equipment = []
        if "inventory" in character_data:
            for item in character_data["inventory"]:
                if item.get("equipped", False):
                    equipment.append({
                        "type": item["definition"]["name"].lower().replace(" ", "_"),
                        "qty": item.get("quantity", 1)
                    })
        return equipment

    def convert_to_yaml(self, character_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert D&D Beyond character data to YAML format."""
        # Get base stats
        stats = character_data.get("stats", [])
        bonus_stats = character_data.get("bonusStats", [])
        
        # Calculate current HP
        base_hp = character_data.get("baseHitPoints", 0)
        removed_hp = character_data.get("removedHitPoints", 0)
        temp_hp = character_data.get("temporaryHitPoints", 0)
        current_hp = base_hp - removed_hp + temp_hp
        
        # Create YAML structure
        yaml_data = {
            "name": character_data["name"],
            "race": character_data.get("race", {}).get("fullName", "").lower(),
            "classes": {
                character_data.get("classes", [{}])[0].get("definition", {}).get("name", "").lower(): 
                character_data.get("classes", [{}])[0].get("level", 1)
            },
            "level": character_data.get("classes", [{}])[0].get("level", 1),
            "max_hp": character_data.get("baseHitPoints", 0),
            "hp": current_hp,
            "ability": {
                "str": self._get_ability_score(stats, bonus_stats, 1),
                "dex": self._get_ability_score(stats, bonus_stats, 2),
                "con": self._get_ability_score(stats, bonus_stats, 3),
                "int": self._get_ability_score(stats, bonus_stats, 4),
                "wis": self._get_ability_score(stats, bonus_stats, 5),
                "cha": self._get_ability_score(stats, bonus_stats, 6)
            },
            "skills": self._get_skills(character_data),
            "equipped": [item["type"] for item in self._get_equipment(character_data)],
            "inventory": self._get_equipment(character_data),
            "token": [character_data["name"][0].upper()],
            "alignment": self._map_alignment(character_data.get("alignmentId", 5))
        }
        
        return yaml_data

    def import_character(self, character_id: int, output_path: Optional[str] = None) -> str:
        """Import a character from D&D Beyond and save as YAML."""
        # Fetch character data
        character_data = self.fetch_character(character_id)
        
        # Convert to YAML format
        yaml_data = self.convert_to_yaml(character_data)
        
        # Generate YAML string
        yaml_str = yaml.dump(yaml_data, sort_keys=False, default_flow_style=False)
        
        # Save to file if output path is provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(yaml_str)
        
        return yaml_str

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Import D&D Beyond characters to YAML format")
    parser.add_argument("character_id", type=int, help="D&D Beyond character ID")
    parser.add_argument("--output", "-o", help="Output file path (optional)")
    
    args = parser.parse_args()
    
    importer = BeyondImporter()
    try:
        yaml_str = importer.import_character(args.character_id, args.output)
        if not args.output:
            print(yaml_str)
    except Exception as e:
        print(f"Error importing character: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
