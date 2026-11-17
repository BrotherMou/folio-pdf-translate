"""Stable sentence units for translation, not inferred bilingual correspondences."""
import re

ABBREVIATION = re.compile(r"(?:\b(?:e\.g|i\.e|et\s+al|figs?|eqs?|refs?|sec|no|vol|pp|dr|prof|mr|mrs|vs)|\b(?-i:[A-Z]))\.$", re.I)


def split_sentences(text: str) -> list[str]:
    starts, begin = [], 0
    # A period only ends a sentence before whitespace/end; decimals and placeholders stay intact.
    for match in re.finditer(r'[。！？!?]+[”’"\)]*|\.[”’"\)]*(?=\s|$)', text):
        end = match.end()
        if text[match.start()] == '.' and ABBREVIATION.search(text[:end]):
            continue
        # A list number belongs to its following sentence, not a separate hover pair.
        if re.fullmatch(r'\s*\d{1,3}\.', text[begin:end]) and text[end:].strip():
            continue
        if text[begin:end].strip():
            starts.append(text[begin:end].strip())
        begin = end
    if text[begin:].strip():
        starts.append(text[begin:].strip())
    return starts or [text]


def expand(request: dict) -> dict:
    items = []
    for item in request['items']:
        parts = split_sentences(item['source'])
        for index, source in enumerate(parts):
            items.append({**item, 'id': item['id'] if len(parts) == 1 else f"{item['id']}.s{index + 1}",
                          'source': source, 'paragraph_id': item['id'], 'paragraph_source': item['source']})
    return {**request, 'items': items, 'sentence_alignment': True,
            'instructions': request.get('instructions', '') + '\nTranslate each item separately. Each item is a sentence or sentence fragment. Use paragraph_source for context; do not move text between IDs. Preserve all formula and page placeholders.'}
