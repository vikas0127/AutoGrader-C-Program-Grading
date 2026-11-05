import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.project_builder import build_flex_bison_project

class ProjectBuilderTests(unittest.TestCase):
    def test_rejects_project_without_lexer_and_parser(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'project'; root.mkdir()
            (root / 'main.c').write_text('int main(void){return 0;}')
            result = build_flex_bison_project(root, Path(td) / 'build')
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['error'], 'project_layout')

    def test_reports_missing_flex_bison_toolchain(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'project'; root.mkdir()
            (root / 'lexer.l').write_text('%%\\n. ECHO;\\n%%\\n')
            (root / 'parser.y').write_text('%%\\n%%\\n')
            (root / 'main.c').write_text('int main(void){return 0;}')
            with patch('src.project_builder.shutil.which', side_effect=lambda name: '/usr/bin/gcc' if name == 'gcc' else None):
                result = build_flex_bison_project(root, Path(td) / 'build')
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['error'], 'toolchain_missing')
            self.assertIn('flex', result['stderr'])
            self.assertIn('bison', result['stderr'])

if __name__ == '__main__':
    unittest.main()
