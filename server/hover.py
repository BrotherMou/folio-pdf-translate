"""Cross-platform Acrobat hover layers, using saved sentence pairs and native geometry.

Only exact normalized text matches are used. No mouse-catching annotations or rasterized text.
"""
from collections import defaultdict
import json
from pathlib import Path
import re
import unicodedata

import pymupdf


def normalized(text):
    text = re.sub(r'\{v\d+\}', '', text)
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def subtract(rect, protected):
    pieces = [pymupdf.Rect(rect)]
    for cut in protected:
        remaining = []
        for r in pieces:
            hit = r & cut
            if hit.is_empty:
                remaining.append(r)
            else:
                remaining.extend(p for p in [pymupdf.Rect(r.x0, r.y0, r.x1, hit.y0),
                    pymupdf.Rect(r.x0, hit.y1, r.x1, r.y1), pymupdf.Rect(r.x0, hit.y0, hit.x0, hit.y1),
                    pymupdf.Rect(hit.x1, hit.y0, r.x1, hit.y1)] if p.width > .1 and p.height > .1)
        pieces = remaining
    return pieces


def text_index(chars):
    text, indexes = '', []
    for i, char in enumerate(chars):
        value = normalized(char['text'])
        text += value
        indexes.extend([i] * len(value))
    return text, indexes


def rectangles(chars, indexes, start, end, protected):
    by_line = defaultdict(list)
    for i in sorted(set(indexes[max(0, start):max(0, end)])):
        by_line[chars[i]['line']].append(pymupdf.Rect(chars[i]['rect']))
    rects = []
    for boxes in by_line.values():
        current = None
        for r in sorted(boxes, key=lambda r: r.x0):
            if current is not None and r.x0 - current.x1 <= max(2, r.height * .6):
                current |= r
            else:
                if current is not None:
                    rects.extend(p for p in subtract(current, protected) if p.height >= current.height * .4)
                current = r
        if current is not None:
            rects.extend(p for p in subtract(current, protected) if p.height >= current.height * .4)
    return [list(r) for r in rects]


def alignment_records(exchange):
    records = []
    seen = set()
    for path in sorted((Path(exchange) / 'alignments').glob('*.json')):
        for i, item in enumerate(json.loads(path.read_text(encoding='utf-8'))['items']):
            parts = item['sentences']
            source = ''.join(normalized(p['source']) for p in parts)
            target = ''.join(normalized(p['translation']) for p in parts)
            if (source, target) in seen:
                continue
            seen.add((source, target))
            records.append((f'{path.stem}-{i}', source, target, parts))
    return records


def make_groups(source, mono, layout, records, cancelled):
    protected = {}
    for item in layout['pages']:
        n = item['page']
        protected[n] = {}
        for side, doc, key in [('left', source, 'source_protected'), ('right', mono, 'target_protected')]:
            rects = [pymupdf.Rect(r) * doc[n].transformation_matrix for r in item[key]]
            rects += [pymupdf.Rect(info['bbox']) for info in doc[n].get_image_info()]
            # A small guard band prevents antialiasing from painting formula ink.
            protected[n][side] = [r + (-.3, -.3, .3, .3) for r in rects if not r.is_empty]
    groups, skipped = {}, []
    mapped = 0
    for block in layout['blocks']:
        if cancelled():
            raise InterruptedError('Translation cancelled')
        n = block['page']
        if source[n].rotation or mono[n].rotation:
            skipped.append({'id': block['id'], 'reason': 'rotated page'})
            continue
        left = [{**c, 'rect': list(pymupdf.Rect(c['rect']) * source[n].transformation_matrix)} for c in block['source_chars']]
        lines = [pymupdf.Rect(r) * mono[n].transformation_matrix for r in block['target_lines']]
        right = []
        raw = mono[n].get_text('rawdict')
        for b in raw['blocks']:
            for line in b.get('lines', []):
                for span in line['spans']:
                    for c in span['chars']:
                        r = pymupdf.Rect(c['bbox'])
                        point = pymupdf.Point((r.x0 + r.x1) / 2, c['origin'][1] - span['size'] * .25)
                        candidates = [i for i, area in enumerate(lines) if area.contains(point)]
                        if not candidates or any(cut.contains(point) for cut in protected[n]['right']):
                            continue
                        k = min(candidates, key=lambda i: abs((lines[i].y0 + lines[i].y1) / 2 - point.y))
                        # PDF font ascent/descent boxes can overlap neighboring lines even when ink does not.
                        # Use the text band, not the oversized font box, for both painting and hit testing.
                        r.y0 = max(r.y0, c['origin'][1] - span['size'] * .9)
                        r.y1 = min(r.y1, c['origin'][1] + span['size'] * .2)
                        center = (lines[k].y0 + lines[k].y1) / 2
                        for other in lines:
                            other_center = (other.y0 + other.y1) / 2
                            if other.x1 <= r.x0 or other.x0 >= r.x1 or abs(other_center - center) < .1:
                                continue
                            boundary = (other_center + center) / 2
                            if other_center < center:
                                r.y0 = max(r.y0, boundary)
                            else:
                                r.y1 = min(r.y1, boundary)
                        if r.is_empty:
                            continue
                        right.append({'text': c['c'], 'rect': list(r), 'line': k})
        right.sort(key=lambda c: (c['line'], c['rect'][0]))
        s, si = text_index(left)
        t, ti = text_index(right)
        expected_s, expected_t = normalized(block['source']), normalized(block['translation'])
        if not s or not t or s != expected_s or t != expected_t:
            skipped.append({'id': block['id'], 'reason': 'PDF text/geometry mismatch',
                            'source_match': s == expected_s, 'target_match': t == expected_t,
                            'source': block['source'], 'extracted_source': s, 'extracted_target': t,
                            'expected_target': expected_t})
            continue
        covered_s, covered_t = set(), set()
        # Prefer the complete paragraph over independently cached phrases contained inside it.
        ordered = sorted(records, key=lambda r: (r[1] == s and r[2] == t,
                         min(len(s), len(r[1])) + min(len(t), len(r[2]))), reverse=True)
        # Native fixed-heading translations (e.g. Abstract) bypass the Agent but are explicit pairs.
        if block.get('kind') == 'heading':
            ordered.append(('heading-' + block['id'], s, t,
                            [{'source': block['source'], 'translation': block['translation']}]))
        for key, full_s, full_t, parts in ordered:
            if not full_s or not full_t:
                continue
            if s in full_s and t in full_t:
                so, to = -full_s.index(s), -full_t.index(t)
                suffix = '' if (s != full_s or t != full_t) else ':' + block['id']
            elif full_s in s and full_t in t:
                so, to = s.index(full_s), t.index(full_t)
                suffix = ':' + block['id']
            else:
                continue
            for i, part in enumerate(parts):
                sl, tl = len(normalized(part['source'])), len(normalized(part['translation']))
                ss = set(range(max(0, so), min(len(s), so + sl)))
                ts = set(range(max(0, to), min(len(t), to + tl)))
                if covered_s.intersection(ss) or covered_t.intersection(ts):
                    so += sl; to += tl
                    continue
                sr = rectangles(left, si, max(0, so), min(len(s), so + sl), protected[n]['left']) if so + sl > 0 else []
                tr = rectangles(right, ti, max(0, to), min(len(t), to + tl), protected[n]['right']) if to + tl > 0 else []
                if sr or tr:
                    group = groups.setdefault(key + suffix + f':{i}', {'id': key + suffix + f':{i}',
                        'source': part['source'], 'translation': part['translation'], 'regions': {}})
                    region = group['regions'].setdefault(n, {'page': n, 'left': [], 'right': []})
                    region['left'] += sr
                    region['right'] += tr
                covered_s.update(ss)
                covered_t.update(ts)
                so += sl; to += tl
        if len(covered_s) == len(s) and len(covered_t) == len(t):
            mapped += 1
        else:
            skipped.append({'id': block['id'], 'reason': 'sentence alignment unavailable', 'source': block['source']})
    result = []
    for group in groups.values():
        regions = list(group['regions'].values())
        if not any(r['left'] for r in regions) or not any(r['right'] for r in regions):
            skipped.append({'id': group['id'], 'reason': 'no matching prose on both sides'})
            continue
        group['regions'] = regions
        result.append(group)
    return result, protected, skipped, mapped


def js_action(doc, code):
    stream = doc.get_new_xref()
    doc.update_object(stream, '<< >>')
    doc.update_stream(stream, code.encode('utf-8'))
    action = doc.get_new_xref()
    doc.update_object(action, f'<< /S /JavaScript /JS {stream} 0 R >>')
    return action, stream


def build_hover(source_path, mono_path, dual_path, exchange, cancelled=lambda: False):
    dual_path = Path(dual_path)
    layout = json.loads((dual_path.parent / 'hover-layout.json').read_text(encoding='utf-8'))
    if layout.get('version') != 1:
        raise ValueError('Unsupported hover geometry version; rebuild the native engine')
    with pymupdf.open(source_path) as source, pymupdf.open(mono_path) as mono, pymupdf.open(dual_path) as doc:
        groups, protected, skipped, mapped = make_groups(source, mono, layout, alignment_records(exchange), cancelled)
        if not groups:
            raise ValueError('No exact bilingual sentence locations found; hover PDF was not generated')
        data = []
        for group in groups:
            if cancelled():
                raise InterruptedError('Translation cancelled')
            name = 'FolioHover:' + group['id']
            group['ocg'] = doc.add_ocg(name, on=False)
            doc.xref_set_key(group['ocg'], 'Usage', '<< /Print << /PrintState /OFF >> >>')
            for region in group['regions']:
                page = doc[region['page']]
                rects = []
                for side in ('left', 'right'):
                    shift = source[region['page']].rect.width if side == 'right' else 0
                    final = []
                    for r in region[side]:
                        r = pymupdf.Rect(r) + (shift, 0, shift, 0)
                        final.append(list(r))
                        page.draw_rect(r, color=None, fill=(1, .78, .12), fill_opacity=.3, overlay=True, oc=group['ocg'])
                        rects.append(list(r * ~page.transformation_matrix))
                    region[side] = final
                data.append({'name': name, 'page': region['page'], 'rects': rects})
        script = 'var folioHoverData = ' + json.dumps(data) + ';\n'
        script += 'var folioHoverPages = ' + json.dumps([list(p.rect * ~p.transformation_matrix) for p in doc]) + ';\n'
        script += Path(__file__).with_name('pdf_hover.js').read_text(encoding='utf-8')
        catalog = doc.pdf_catalog()
        if doc.xref_get_key(catalog, 'Names/JavaScript')[0] != 'null':
            raise ValueError('Output already has document JavaScript')
        action, stream = js_action(doc, script)
        kind, value = doc.xref_get_key(catalog, 'Names')
        names = int(value.split()[0]) if kind == 'xref' else catalog
        doc.xref_set_key(names, 'JavaScript' if kind == 'xref' else 'Names/JavaScript', f'<< /Names [(FolioHover) {action} 0 R] >>')
        for event, code in [('WC', 'folioHoverStop();'), ('WP', 'folioHoverPause();'), ('DP', 'folioHoverResume();')]:
            action, _ = js_action(doc, code)
            doc.xref_set_key(catalog, 'AA/' + event, f'{action} 0 R')
        for page in doc:
            action, _ = js_action(doc, 'folioHoverClear();')
            doc.xref_set_key(page.xref, 'AA/C', f'{action} 0 R')
        doc.xref_set_key(catalog, 'PageLayout', '/SinglePage')
        doc.xref_set_key(catalog, 'OpenAction', f'[{doc[0].xref} 0 R /Fit]')
        refs = ' '.join(f"{g['ocg']} 0 R" for g in groups)
        doc.xref_set_key(catalog, 'OCProperties/D/AS', f'[<< /Event /Print /Category [/Print] /OCGs [{refs}] >>]')
        target = dual_path.with_name(dual_path.stem + '.hover.pdf')
        temporary = target.with_suffix('.tmp.pdf')
        try:
            doc.save(temporary, deflate=True)
            if cancelled():
                raise InterruptedError('Translation cancelled')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        report = {'version': 1, 'pdf': str(target), 'sentence_pairs': len(groups), 'mapped_blocks': mapped,
            'total_blocks': len(layout['blocks']), 'skipped': skipped, 'groups': groups,
            'protected': {str(n): {s: [list(r) for r in rs] for s, rs in sides.items()} for n, sides in protected.items()},
            'javascript_xref': stream, 'acrobat_ui_verified': False, 'target_reader': 'Adobe Acrobat desktop; JavaScript enabled',
            'alignment': 'Agent translations submitted separately for each source sentence', 'mcp_integration': True}
        report_path = target.with_suffix('.json')
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(target), str(report_path), report
