import pdb

class Notable:

    def has_notes(self):
        return "notes" in self.properties

    def list_notes(self, entity=None, perception=None, entity_pov=None, highlight=False):
        notes = self.properties.get("notes", [])
        result_notes = []
        new_note_source = {}
        
        for note in notes:
            # Skip notes that don't meet conditions
            if note.get("if") and not self.eval_if(note["if"]):
                continue
            if self.is_secret and note.get("secret"):
                continue
                
            note_json = {"note": note.get("note"), "image": note.get("image")}
            
            # Handle perception-based notes
            if 'perception_dc' in note:
                perception_dc = note.get("perception_dc", 0)
                effective_perception = None
                
                # Initialize perception results if needed
                if 'result' not in note:
                    note['result'] = {'perception': {}}
                
                # Get existing perception value
                if entity_pov is None:
                    effective_perception = note['result'].get('perception', {}).get(entity)
                else:
                    perceptions = [p for p in [note['result'].get('perception', {}).get(e) 
                                  for e in entity_pov] if p is not None]
                    if perceptions:
                        effective_perception = max(perceptions)
                
                effective_perception = perception if effective_perception is None else effective_perception
                    
                # Store new perception check
                if perception is not None and entity is not None:
                    note['result']['perception'][entity] = perception
                    if perception >= perception_dc:
                        new_note_source[entity] = perception
                
                # Skip if perception check fails
                if not effective_perception or effective_perception < perception_dc:
                    continue
                    
                # Process note content based on language
                if note.get("language"):
                    can_read = hasattr(entity, 'languages') and note.get("language") in entity.languages
                    content = note.get("note") if can_read else "???"
                    note_json["note"] = self.t("perception.note_with_language", 
                                              note_language=note.get("language"),
                                              note=content)
                
                # Add perception DC information
                if perception_dc > 0:
                    note_json["note"] = self.t("perception.passed", dc=perception_dc, note=note_json["note"])
                    
            # Add image offset if available
            if note.get("image_offset_px"):
                note_json["image_offset_px"] = note.get("image_offset_px")
                
            result_notes.append(note_json)
                
        return [result_notes, new_note_source]
