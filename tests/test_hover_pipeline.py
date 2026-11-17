"""Real engine + Agent exchange + hover PDF. Acrobat UI still needs manual acceptance."""
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
import shutil
import subprocess

import pymupdf

from server.jobs import JobManager, ROOT, TERMINAL
from server.hover import subtract

ENGINE = Path(os.environ.get('FOLIO_TRANSLATE_ENGINE', ROOT / ('bin/windows/pdf-translate-engine.exe' if os.name == 'nt' else 'bin/pdf-translate-engine')))


@unittest.skipUnless(ENGINE.is_file(), 'Build the native engine first')
class HoverPipelineTests(unittest.TestCase):
    def test_real_translation_builds_copyable_hover_without_highlighting_formulas_or_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'sentences.pdf'
            with pymupdf.open() as d:
                page = d.new_page(width=612, height=792)
                x = 54
                for text, font in [('The displacement ', 'Times-Roman'), ('u', 'Times-Italic'),
                                   (' depends on force. A second sentence follows.', 'Times-Roman')]:
                    page.insert_text((x, 100), text, fontname=font, fontsize=12)
                    x += pymupdf.get_text_length(text, fontname=font, fontsize=12)
                pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 24, 24), False)
                pix.clear_with(80)
                page.insert_image(pymupdf.Rect(54, 230, 154, 330), pixmap=pix)
                d.save(source)
            manager = JobManager(root / 'state', ENGINE)
            try:
                job = manager.start(str(source), str(root / 'out'))
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    pending = manager.pending(job['job_id'])
                    for request in pending['requests']:
                        self.assertTrue(request['sentence_alignment'])
                        values = {}
                        for i, item in enumerate(request['items']):
                            values[item['id']] = ('位移关系为 ' if i == 0 else '第二句文本为 ') + ' '.join(re.findall(r'\{v\d+\}', item['source'])) + '。'
                        manager.submit(job['job_id'], request['request_id'], values)
                    status = manager.get(job['job_id'])
                    if status['state'] in TERMINAL:
                        break
                    time.sleep(.05)
                self.assertEqual(status['state'], 'completed', status)
                report = json.loads(Path(status['artifacts']['hover_report']).read_text())
                self.assertGreaterEqual(report['sentence_pairs'], 2)
                self.assertEqual(report['skipped'], [])
                with pymupdf.open(status['artifacts']['plain_dual_pdf']) as plain, pymupdf.open(status['artifacts']['dual_pdf']) as hover:
                    self.assertEqual(plain[0].get_text(), hover[0].get_text())
                    self.assertEqual(plain[0].annot_xrefs(), hover[0].annot_xrefs())
                    self.assertEqual(plain[0].get_pixmap().samples, hover[0].get_pixmap().samples)
                    protected = []
                    for side, boxes in report['protected']['0'].items():
                        shift = 612 if side == 'right' else 0
                        protected += [pymupdf.Rect(r) + (shift, 0, shift, 0) for r in boxes]
                    self.assertTrue(protected)
                    before = [hover[0].get_pixmap(clip=r).samples for r in protected]
                    for layer in hover.layer_ui_configs():
                        hover.set_layer_ui_config(layer['number'], action=0)
                    self.assertNotEqual(plain[0].get_pixmap().samples, hover[0].get_pixmap().samples)
                    self.assertEqual(before, [hover[0].get_pixmap(clip=r).samples for r in protected])
                    for group in report['groups']:
                        for region in group['regions']:
                            for side in ('left', 'right'):
                                for r in region[side]:
                                    self.assertTrue(all((pymupdf.Rect(r) & p).is_empty for p in protected))
            finally:
                manager.shutdown()

    def test_sentence_split_keeps_numbered_items_with_their_text(self):
        from server.sentences import split_sentences
        self.assertEqual(split_sentences("1. Compute force. 2. Update displacement."),
                         ["1. Compute force.", "2. Update displacement."])
        self.assertEqual(split_sentences("The time is 2.5 s. See Eq. (3)."),
                         ["The time is 2.5 s.", "See Eq. (3)."])

    def test_protection_subtraction_preserves_only_unprotected_area(self):
        cuts = [pymupdf.Rect(4, -2, 6, 12)]
        pieces = subtract(pymupdf.Rect(0, 0, 10, 10), cuts)
        self.assertEqual(sum(r.get_area() for r in pieces), 80)
        self.assertTrue(all((r & cuts[0]).is_empty for r in pieces))

    def test_acrobat_runtime_with_mock_reader(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node required for JavaScript check, not for PDF readers')
        harness = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const layers=[{name:'a',state:false},{name:'b',state:false}];
let stopped=false, timer;
const c={pageNum:0,mouseX:0,mouseY:0,getOCGs:()=>layers,
 folioHoverPages:[[0,0,600,800],[0,0,600,800]],
 folioHoverData:[{name:'a',page:0,rects:[[10,10,20,20],[310,10,330,20]]},
 {name:'a',page:1,rects:[[10,10,20,20]]},{name:'b',page:1,rects:[[40,10,50,20],[340,10,350,20]]}],
 app:{setInterval:(s,t)=>{assert.equal(t,100);timer=s;return 1},clearInterval:()=>{stopped=true}}};
vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
function move(p,x,y){c.pageNum=p;c.mouseX=x;c.mouseY=y;vm.runInContext(timer,c)}
function active(){return layers.filter(l=>l.state).map(l=>l.name)}
move(0,15,15);assert.deepEqual(active(),['a']);
move(0,320,15);assert.deepEqual(active(),['a']);
move(1,15,15);assert.deepEqual(active(),['a']);
move(1,345,15);assert.deepEqual(active(),['b']);
move(1,100,100);assert.deepEqual(active(),[]);
move(1,45,15);c.folioHoverPause();assert.deepEqual(active(),[]);
move(1,45,15);assert.deepEqual(active(),[]);
c.folioHoverResume();move(1,45,15);assert.deepEqual(active(),['b']);
move(1,undefined,undefined);assert.deepEqual(active(),[]);
move(0,15,15);c.folioHoverStop();assert.deepEqual(active(),[]);assert.ok(stopped);
'''
        subprocess.run([node, '-e', harness, str(ROOT / 'server/pdf_hover.js')], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
