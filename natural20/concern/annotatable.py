"""NPC-only object annotations (separate from player-visible notes)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _observer_is_npc(observer) -> bool:
    if observer is None:
        return False
    try:
        if callable(getattr(observer, 'is_npc', None)):
            return bool(observer.is_npc())
    except Exception:
        pass
    return False


def _viewer_allowed(annotation: dict, observer) -> bool:
    viewers = annotation.get('viewers') or annotation.get('npcs') or annotation.get('npc')
    if not viewers:
        return True
    if isinstance(viewers, str):
        viewers = [viewers]

    uid = str(getattr(observer, 'entity_uid', '') or '').strip().lower()
    props = getattr(observer, 'properties', None) or {}
    sub_type = str(props.get('sub_type') or '').strip().lower()
    label = ''
    try:
        label_fn = getattr(observer, 'label', None)
        label = str(label_fn() if callable(label_fn) else label_fn or '').strip().lower()
    except Exception:
        label = ''

    allowed = {str(entry).strip().lower() for entry in viewers if str(entry).strip()}
    return uid in allowed or sub_type in allowed or label in allowed


class Annotatable:
    def has_annotations(self) -> bool:
        annotations = (getattr(self, 'properties', None) or {}).get('annotations')
        return isinstance(annotations, list) and len(annotations) > 0

    def list_annotations(
        self,
        observer=None,
        *,
        perception: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[Any, int]]:
        """Return annotations visible to an NPC observer.

        Player characters always receive an empty list — use ``notes`` for clues
        that adventurers can discover.

        Visibility rules:
        - Observer must be an NPC (not a player character).
        - Optional ``viewers`` allowlist on each annotation; omit to allow any NPC.
        - Line of sight / range are enforced by callers (Observe, Look, etc.),
          not inside this method.
        - ``perception_dc`` is ignored (deprecated); use ``notes`` for hidden clues.
        """
        del perception

        if observer is not None and not _observer_is_npc(observer):
            return [], {}

        annotations = (getattr(self, 'properties', None) or {}).get('annotations') or []
        if not isinstance(annotations, list):
            return [], {}

        visible: List[Dict[str, Any]] = []
        new_sources: Dict[Any, int] = {}

        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue

            if annotation.get('if') and hasattr(self, 'eval_if') and not self.eval_if(annotation['if']):
                continue

            if observer is not None and not _viewer_allowed(annotation, observer):
                continue

            text = str(
                annotation.get('text')
                or annotation.get('note')
                or annotation.get('annotation')
                or ''
            ).strip()
            if not text:
                continue

            visible.append({'text': text, 'label': annotation.get('label')})
            if observer is not None:
                new_sources[observer] = 1

        return visible, new_sources
