"""NLP entity extraction using spaCy."""

from __future__ import annotations

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_lg")
        except OSError:
            try:
                _nlp = spacy.load("en_core_web_sm")
            except OSError:
                raise RuntimeError(
                    "No spaCy model found. Run: python -m spacy download en_core_web_lg"
                ) from None
    return _nlp


INVESTIGATION_TYPES = {"PERSON", "GPE", "LOC", "FAC", "ORG", "DATE", "TIME", "EVENT"}


def extract_entities(text: str) -> list[dict]:
    if not text or not text.strip():
        return []

    nlp = _get_nlp()
    doc = nlp(text)

    entities = []
    for ent in doc.ents:
        if ent.label_ in INVESTIGATION_TYPES:
            entities.append({
                "text": ent.text,
                "type": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char,
            })
    return entities
