#!/usr/bin/env python3
"""Portable end-to-end install check, with fixed test translations and no API."""
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import site
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify_environment():
    if sys.prefix == sys.base_prefix or site.ENABLE_USER_SITE:
        raise RuntimeError('Run this check with the project virtual-environment Python.')
    cfg = Path(sys.prefix, 'pyvenv.cfg').read_text(encoding='utf-8').lower()
    if 'include-system-site-packages = true' in cfg:
        raise RuntimeError('The virtual environment must not use system site-packages.')
    versions = {}
    for name in ('mcp', 'PyMuPDF', 'setuptools'):
        dist = importlib.metadata.distribution(name)
        if not Path(dist.locate_file('')).resolve().is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError(f'{name} was imported from outside the virtual environment.')
        versions[name] = dist.version
    return versions


async def verify_pipeline():
    import pymupdf
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    with tempfile.TemporaryDirectory(prefix='folio-install-') as temporary:
        base = Path(temporary)
        source = base / 'sample with spaces.pdf'
        with pymupdf.open() as document:
            page = document.new_page(width=612, height=792)
            x = 54
            for text, font in [('The displacement ', 'Times-Roman'), ('u', 'Times-Italic'),
                               (' depends on force. A second sentence follows.', 'Times-Roman')]:
                page.insert_text((x, 100), text, fontname=font, fontsize=12)
                x += pymupdf.get_text_length(text, fontname=font, fontsize=12)
            document.save(source)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        env = dict(os.environ)
        env.update(FOLIO_TRANSLATE_STATE_DIR=str(base / 'state'), PYTHONNOUSERSITE='1')
        # Test the checkout's own engine; do not silently use a developer override.
        env.pop('FOLIO_TRANSLATE_ENGINE', None)
        params = StdioServerParameters(command=sys.executable,
                                       args=[str(ROOT / 'scripts/launch_mcp.py')], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                async def call(name, arguments):
                    reply = await client.call_tool(name, arguments)
                    if reply.isError:
                        raise RuntimeError(str(reply.content))
                    return reply.structuredContent
                tools = await client.list_tools()
                if {t.name for t in tools.tools} != {'start_translation', 'get_translation_status',
                        'get_pending_translations', 'submit_translations', 'cancel_translation'}:
                    raise RuntimeError('Unexpected MCP tools.')
                job = await call('start_translation', {'input_path': str(source),
                        'output_directory': str(base / 'results'), 'hover_highlight': True})
                identifier = job['job_id']
                done = False
                try:
                    async with asyncio.timeout(120):
                        while True:
                            pending = await call('get_pending_translations', {'job_id': identifier})
                            for request in pending['requests']:
                                known = {
                                    'The displacement {v1} depends on force.': '位移 {v1} 取决于力。',
                                    'A second sentence follows.': '接下来是第二句话。',
                                }
                                translations = {i['id']: known[i['source']] for i in request['items']}
                                await call('submit_translations', {'job_id': identifier,
                                        'request_id': request['request_id'], 'translations': translations})
                            status = await call('get_translation_status', {'job_id': identifier})
                            if status['state'] in {'completed', 'failed', 'cancelled', 'interrupted'}:
                                done = True
                                if status['state'] != 'completed':
                                    raise RuntimeError(str(status))
                                break
                            await asyncio.sleep(.05)
                finally:
                    if not done:
                        await call('cancel_translation', {'job_id': identifier})
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise RuntimeError('Source PDF changed.')
        a = status['artifacts']
        report = json.loads(Path(a['hover_report']).read_text(encoding='utf-8'))
        coverage = json.loads(Path(a['coverage_report']).read_text(encoding='utf-8'))
        if report['sentence_pairs'] != 2 or report['skipped'] or not coverage['blocks']:
            raise RuntimeError('Missing sentence alignment or classification coverage.')
        with pymupdf.open(a['plain_dual_pdf']) as plain, pymupdf.open(a['dual_pdf']) as hover:
            if plain[0].get_text() != hover[0].get_text() or plain[0].annot_xrefs() != hover[0].annot_xrefs():
                raise RuntimeError('Hover changed the text layer or added overlay annotations.')
            if plain[0].get_pixmap().samples != hover[0].get_pixmap().samples:
                raise RuntimeError('Inactive hover changed the page appearance.')
            text = hover[0].get_text()
            if 'The displacement' not in text or '位移' not in text or '第二句话' not in text:
                raise RuntimeError('Bilingual text is missing.')
        return {'mcp_tools': 5, 'translated_sentences': 2, 'hover_pairs': 2,
                'source_unchanged': True, 'text_layer_preserved': True,
                'new_overlay_annotations': False, 'adobe_ui_verified': False}


if __name__ == '__main__':
    versions = verify_environment()
    result = asyncio.run(verify_pipeline())
    print(json.dumps({'platform': sys.platform, 'python': sys.version.split()[0],
                      'dependencies': versions, 'checks': result}, ensure_ascii=False, indent=2))
