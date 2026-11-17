"""Real compiled-engine checks against a local deterministic HTTP stub.

Run: python -m unittest discover -s tests -p test_engine.py -v
These checks exercise PDF parsing, formula placeholders and output rendering.
They do not measure translation quality or validate arbitrary scientific PDFs.
"""
from contextlib import contextmanager
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import tempfile
import threading
import unittest

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / ("bin/windows/pdf-translate-engine.exe" if os.name == "nt"
                         else "bin/pdf-translate-engine")
ENGINE = Path(os.environ.get("FOLIO_TRANSLATE_ENGINE", DEFAULT_ENGINE))
PLACEHOLDER = re.compile(r"\{v[1-9][0-9]*\}")


def specimen(path: Path) -> None:
    """One real text paragraph, with mathematical letters in Times Italic."""
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        x, baseline, size = 54.0, 100.0, 12.0
        for text, font in [
            ("The displacement ", "Times-Roman"),
            ("u", "Times-Italic"),
            (" depends on the force ", "Times-Roman"),
            ("f", "Times-Italic"),
            (" and the observation time.", "Times-Roman"),
        ]:
            page.insert_text((x, baseline), text, fontname=font, fontsize=size)
            x += pymupdf.get_text_length(text, fontname=font, fontsize=size)
        document.save(path)


@contextmanager
def local_model(mode: str = "valid", sources: list[str] | None = None):
    """The same chat-completion wire format used by both extracted engines."""
    seen = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            system = next(item["content"] for item in body["messages"] if item["role"] == "system")
            user = next(item["content"] for item in body["messages"] if item["role"] == "user")
            if system.startswith("You build glossaries"):
                reply = {"terms": []}
            else:
                # LLMBatch appends short-item notes after its JSON object.
                items, _ = json.JSONDecoder().raw_decode(user)
                reply = {}
                for key, source in items.items():
                    formulas = PLACEHOLDER.findall(source)
                    with lock:
                        seen.extend(formulas)
                        if sources is not None:
                            sources.append(source)
                    if mode == "duplicate" and formulas:
                        formulas += formulas[:1]
                    elif mode == "missing":
                        formulas = []
                    reply[key] = "位移与载荷的关系为 " + "，".join(formulas) + "。"
            payload = json.dumps({"choices": [{"message": {
                "role": "assistant", "content": json.dumps(reply, ensure_ascii=False)},
                "finish_reason": "stop"}]}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@unittest.skipUnless(ENGINE.is_file(), f"Compiled engine missing: {ENGINE}; build the platform engine first")
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source = self.directory / "inline formulas.pdf"
        specimen(self.source)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).digest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), self.source_hash,
                         "Engine changed the source PDF")
        self.temp.cleanup()

    def invoke(self, base_url: str, *, pages: str | None = None, name="output"):
        request = {
            "input": str(self.source), "output_directory": str(self.directory / name),
            "cache_directory": str(self.directory / (name + "-cache")),
            "service": "openaicompatible", "lang_in": "en", "lang_out": "zh",
            "outputs": "both", "pages": pages,
            "fields": {"--openai-compatible-base-url": base_url,
                       "--openai-compatible-model": "local-test-stub"},
            "secrets": {}, "translate_images": False,
        }
        process = subprocess.run([str(ENGINE)], input=json.dumps(request), text=True,
                                 capture_output=True, timeout=150)
        events = []
        for line in process.stdout.splitlines():
            self.assertTrue(line.startswith("{"), "Non-JSON engine stdout: " + line)
            events.append(json.loads(line))
        self.assertTrue(events, process.stderr)
        return process, events

    def test_algorithm_prose_lists_and_isolated_top_body_are_translated(self):
        self.source.unlink()
        with pymupdf.open() as doc:
            page = doc.new_page(width=612, height=792)
            rows = [
                (80, "3 | Implementation", "Times-Bold"),
                (105, "We illustrate the algorithm by four examples:", "Times-Roman"),
                (130, "1. Example one: Efficiency of the matrix inversion.", "Times-Roman"),
                (150, "2. Example two: A composite under cyclic loading.", "Times-Roman"),
                (170, "3. Example three: A lattice under pure shear.", "Times-Roman"),
                (190, "4. Example four: A substructure assembly.", "Times-Roman"),
                (240, "ALGORITHM 1 | Offline stage.", "Times-Bold"),
                (265, "Input", "Times-Bold"),
                (285, "The number of uniform mesh grids.", "Times-Roman"),
                (310, "procedure", "Times-Bold"),
                (330, "1) Perform direct simulation for elastic strain fields.", "Times-Roman"),
                (350, "2) Cluster elements according to the computed strain results.", "Times-Roman"),
                (370, "3) Compute interaction tensors within a super element.", "Times-Roman"),
                (390, "end procedure", "Times-Bold"),
                (440, "for i in range(n):", "Courier"),
                (460, "    result[i] = solve(matrix)", "Courier"),
            ]
            for y, text, font in rows:
                page.insert_text((54,y), text, fontname=font, fontsize=11)
            page.draw_line((54,249),(555,249))
            page.draw_line((54,405),(555,405))
            second = doc.new_page(width=612, height=792)
            second.insert_text((54,35), "First, the averaging operator maps the element strain to each cluster. Hence the matrix reads", fontname="Times-Roman", fontsize=9)
            second.insert_text((54,230), "The following paragraph explains the resulting matrix in detail.", fontname="Times-Roman", fontsize=11)
            second.insert_text((54,760), "Data Availability Statement", fontname="Times-Bold", fontsize=10)
            doc.save(self.source)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).digest()
        sources = []
        with local_model(sources=sources) as (endpoint, _):
            process, events = self.invoke(endpoint)
        self.assertEqual(process.returncode, 0, (events, process.stderr))
        combined = " ".join(sources)
        for needle in ["Implementation", "four examples", "Example one", "Example two", "Example three", "Example four",
                       "uniform mesh grids", "Perform direct simulation", "Cluster elements", "Compute interaction", "First, the averaging", "Data Availability Statement"]:
            self.assertIn(needle, combined)
        self.assertNotIn("range(n)", combined)
        self.assertNotIn("solve(matrix)", combined)
        coverage = json.loads((self.directory / "output/translation-coverage.json").read_text(encoding="utf-8"))
        self.assertTrue(any(not b["translate"] and "range(n)" in b["text"] for b in coverage["blocks"]))

    def test_real_pdf_outputs_preserve_source_and_pair_pages(self):
        with local_model() as (endpoint, seen):
            process, events = self.invoke(endpoint)
        self.assertEqual(process.returncode, 0, (events, process.stderr))
        self.assertTrue(seen, "Fixture did not exercise formula detection")
        finished = [event for event in events if event["type"] == "finished"]
        self.assertEqual(len(finished), 1, events)
        self.assertFalse(any(event["type"] == "failed" for event in events), events)
        with pymupdf.open(self.source) as original, \
                pymupdf.open(finished[0]["mono_pdf"]) as mono, \
                pymupdf.open(finished[0]["dual_pdf"]) as dual:
            self.assertEqual((len(mono), len(dual)), (len(original), len(original)))
            self.assertEqual(mono[0].rect, original[0].rect)
            self.assertAlmostEqual(dual[0].rect.width, 2 * original[0].rect.width, places=2)
            self.assertAlmostEqual(dual[0].rect.height, original[0].rect.height, places=2)
            # Original content must be the left half, without rescaling.
            self.assertEqual(original[0].get_pixmap().samples,
                             dual[0].get_pixmap(clip=original[0].rect).samples)
            text = mono[0].get_text()
            self.assertIn("位移", text)
            self.assertIn("u", text)
            self.assertIn("f", text)
            self.assertNotRegex(text, r"\{v\d+\}")

    def test_keywords_before_abstract_are_translated_without_author_details(self):
        for label in ("Keywords:", "KEY WORDS:", "Index terms:"):
            with self.subTest(label=label):
                with pymupdf.open() as document:
                    page = document.new_page(width=612, height=792)
                    for y, text, size, font in [
                        (80, "Nonlinear Substructuring Analysis", 20, "Times-Bold"),
                        (115, "Alice Example and Bob Example", 10, "Times-Roman"),
                        (135, "Department of Mechanics, Example University", 10, "Times-Roman"),
                        (165, label, 11, "Times-Bold"),
                        (180, "clustering analysis; elastoplasticity;", 11, "Times-Roman"),
                        (194, "nonlinear substructuring analysis; reduced order modeling", 11, "Times-Roman"),
                        (230, "ABSTRACT", 12, "Times-Bold"),
                        (250, "The proposed method reduces numerical costs for complex structures.", 11, "Times-Roman"),
                    ]:
                        page.insert_text((54, y), text, fontsize=size, fontname=font)
                    document.save(self.source)
                self.source_hash = hashlib.sha256(self.source.read_bytes()).digest()
                sources = []
                with local_model(sources=sources) as (endpoint, _):
                    process, events = self.invoke(endpoint, name=label.replace(":", ""))
                self.assertEqual(process.returncode, 0, (events, process.stderr))
                submitted = " ".join(sources)
                for term in ("clustering analysis", "elastoplasticity",
                             "nonlinear substructuring analysis", "reduced order modeling"):
                    self.assertIn(term, submitted)
                self.assertNotIn("Alice Example", submitted)
                self.assertNotIn("Example University", submitted)
                finished = next(event for event in events if event["type"] == "finished")
                with pymupdf.open(finished["mono_pdf"]) as mono:
                    self.assertIn("Alice Example", mono[0].get_text())
                    self.assertNotIn("reduced order modeling", mono[0].get_text())

    def test_missing_and_duplicate_formula_placeholders_fail(self):
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode), local_model(mode) as (endpoint, seen):
                process, events = self.invoke(endpoint, name=mode)
                self.assertTrue(seen, "Fixture did not exercise formula detection")
                self.assertNotEqual(process.returncode, 0, events)
                self.assertGreater(process.returncode, 0, "Engine crashed rather than reporting JSON failure")
                self.assertTrue(any(event["type"] == "failed" for event in events), events)
                self.assertFalse(any(event["type"] == "finished" for event in events), events)
                self.assertFalse(list((self.directory / mode).glob("*.mono.pdf")))
                self.assertFalse(list((self.directory / mode).glob("*.dual.pdf")))

    def test_overflow_page_range_is_json_failure_before_network(self):
        with local_model() as (endpoint, seen):
            process, events = self.invoke(endpoint, pages="1-999999999999999999999999999999")
        self.assertGreater(process.returncode, 0)
        self.assertEqual(events[-1]["type"], "failed")
        self.assertFalse(seen, "Invalid page range reached the translation service")
        self.assertFalse(any(event["type"] == "finished" for event in events))

    def test_computer_modern_matrix_tail_keeps_original_glyphs(self):
        # Portable LaTeX-generated fixture: no Tectonic or font installation needed.
        fixture = ROOT / "examples/formula-sample.pdf"
        self.assertTrue(fixture.is_file(), "The scientific regression fixture is missing")
        shutil.copyfile(fixture, self.source)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).digest()
        sources = []
        with local_model(sources=sources) as (endpoint, seen):
            process, events = self.invoke(endpoint)
        self.assertEqual(process.returncode, 0, (events, process.stderr))
        self.assertTrue(seen)
        self.assertFalse(any("MV" in value for value in sources),
                         "The matrix tail escaped its formula placeholder")
        finished = next(event for event in events if event["type"] == "finished")

        def math_glyphs(page):
            counts = Counter()
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        font = span["font"].split("+")[-1].upper()
                        if font.startswith(("CMMI", "CMSY", "CMEX", "CMMIB", "CMB", "CMR", "CMSS")):
                            counts.update((font, character) for character in span["text"] if not character.isspace())
            return counts

        with pymupdf.open(self.source) as original, pymupdf.open(finished["mono_pdf"]) as translated:
            for index in range(len(original)):
                before, after = math_glyphs(original[index]), math_glyphs(translated[index])
                self.assertTrue(before)
                self.assertEqual(before, after, f"Math font/character inventory changed on page {index + 1}")

        def math_font_programs(page):
            programs = set()
            for font in page.get_fonts(full=True):
                name = font[3].split("+")[-1].upper()
                if name.startswith(("CMMI", "CMSY", "CMEX", "CMMIB", "CMB", "CMR", "CMSS")):
                    data = page.parent.extract_font(font[0])[3]
                    programs.add((name, hashlib.sha256(data).hexdigest()))
            return programs

        # Equal compressed/raw byte lengths must not lose the font stream's Filter
        # during bilingual composition (CMSY8/CMMIB10 exercise the C# regression).
        with pymupdf.open(self.source) as original, pymupdf.open(finished["dual_pdf"]) as bilingual:
            for before, after in zip(original, bilingual):
                expected = math_font_programs(before)
                self.assertTrue(expected)
                self.assertTrue(expected.issubset(math_font_programs(after)),
                                f"Bilingual PDF changed embedded math fonts on page {before.number + 1}")

    def test_separate_bold_acronym_remains_translatable_text(self):
        # The matrix-tail rule must not protect arbitrary Computer Modern bold prose.
        with pymupdf.open(ROOT / "examples/formula-sample.pdf") as fixture:
            font_id = next(font[0] for font in fixture[0].get_fonts() if font[3].endswith("CMBX10"))
            font_bytes = fixture.extract_font(font_id)[3]
        matrix_font = pymupdf.Font(fontbuffer=font_bytes)
        with pymupdf.open() as document:
            page = document.new_page(width=612, height=792)
            font_id = page.insert_font(fontname="MatrixBold", fontbuffer=font_bytes)
            # PyMuPDF uses the generic family name for this small embedded CFF; preserve
            # its actual PDF face name so the engine exercises the CMBX boundary rule.
            document.xref_set_key(font_id, "BaseFont", "/CMBX10")
            x = 54.0
            for text, font in [
                ("A normal acronym ", "Times-Roman"), ("MV", "MatrixBold"),
                (" is used next to the variable ", "Times-Roman"), ("u", "Times-Italic"),
                (" in the text.", "Times-Roman"),
            ]:
                page.insert_text((x, 100), text, fontname=font, fontsize=12)
                x += (matrix_font.text_length(text, fontsize=12) if font == "MatrixBold"
                      else pymupdf.get_text_length(text, fontname=font, fontsize=12))
            document.save(self.source)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).digest()
        sources = []
        with local_model(sources=sources) as (endpoint, seen):
            process, events = self.invoke(endpoint)
        self.assertEqual(process.returncode, 0, (events, process.stderr))
        self.assertTrue(seen, "Fixture did not include a real adjacent mathematical variable")
        self.assertTrue(any("MV" in value for value in sources), "Ordinary bold acronym was consumed as a formula")


if __name__ == "__main__":
    unittest.main()
