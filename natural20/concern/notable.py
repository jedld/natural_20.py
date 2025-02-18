import pdb

class Notable:

    def has_notes(self):
        return "notes" in self.properties

    def list_notes(self, entity=None, perception=None, entity_pov = None, highlight=False):
        notes = self.properties.get("notes", [])
        result_notes = []
        new_note_source = {}
        for note in notes:
            if note.get("if") and not self.eval_if(note["if"]):
                continue

            if 'perception_dc' in note:
                perception_dc = note.get("perception_dc", 0)
                existing_perception = None
                if 'result' not in note:
                    note['result'] = { 'perception': {} }

                if entity_pov is None:
                    existing_perception = note['result'].get('perception', {}).get(entity)
                else:
                    existing_perceptions = []
                    for entity_p in entity_pov:
                        if entity_p in note['result'].get('perception', {}):
                            _perception = note['result'].get('perception', {}).get(entity_p)
                            if _perception is not None:
                                existing_perceptions.append(_perception)
                    if len(existing_perceptions) > 0:
                        existing_perception = max(existing_perceptions)

                if existing_perception is not None:
                    perception = existing_perception

                elif perception is not None and entity is not None:
                    note['result']['perception'][entity] = perception
                    if perception >= perception_dc:
                        new_note_source[entity] = perception
  
                if perception and perception >= perception_dc:
                    note_language = note.get("language")
                    if note_language:
                        if note_language in entity.languages:
                            note_content = note.get("note")
                        else:
                            note_content = "???"
                        result = self.t("perception.note_with_language", note_language=note_language, note=note_content)
                    else:
                        result = note.get("note")
                    if perception_dc > 0:
                        result = self.t("perception.passed", dc=perception_dc, note=result)
                    note_json = { "note": result }
                    if note.get("image_offset_px"):
                        note_json["image_offset_px"] = note.get("image_offset_px")
                    result_notes.append(note_json)
            else:
                if note.get("image_offset_px"):
                        note_json["image_offset_px"] = note.get("image_offset_px")

                note_json = { "note": note.get("note") }

                result_notes.append(note_json)
        return [result_notes, new_note_source]
