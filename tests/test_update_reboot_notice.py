"""Restart advice must survive transient update results and collapsed logs."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1]
          / "overlays/usr/lib/spaced-linux/spaced-update.py")


class RebootNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(SOURCE.read_text())

    def test_notice_is_wrapped_selectable_and_explains_recovery(self):
        nodes = [node for node in self.tree.body
                 if (isinstance(node, ast.FunctionDef)
                     and node.name == "make_reboot_notice")
                 or (isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name)
                             and target.id == "ELOGIND_REBOOT_NOTICE"
                             for target in node.targets))]
        properties = {}
        label = SimpleNamespace(
            set_max_width_chars=lambda value: properties.update(width=value),
            set_selectable=lambda value: properties.update(selectable=value))

        def make_label(text, style, wrap=False):
            properties.update(text=text, style=style, wrap=wrap)
            return label

        namespace = {"make_label": make_label}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"),
             namespace)
        self.assertIs(namespace["make_reboot_notice"](), label)
        self.assertTrue(properties["wrap"])
        self.assertTrue(properties["selectable"])
        self.assertEqual(properties["width"], 80)
        for phrase in ("Restart required after elogind updates", "save your work",
                       "network or audio", "reboot from a terminal",
                       "wait until package installation has stopped"):
            self.assertIn(phrase, properties["text"])

    def test_both_tabs_pack_notice_directly_outside_status_and_logs(self):
        for class_name, method_name, parent in (
                ("App", "_build_updates_page", "page"),
                ("OsUpdateTab", "__init__", "self")):
            with self.subTest(tab=class_name):
                cls = next(node for node in self.tree.body
                           if isinstance(node, ast.ClassDef) and node.name == class_name)
                method = next(node for node in cls.body
                              if isinstance(node, ast.FunctionDef)
                              and node.name == method_name)
                expected = f"{parent}.pack_start(make_reboot_notice(), False, False, 0)"
                self.assertIn(expected, [ast.unparse(node) for node in method.body])


if __name__ == "__main__":
    unittest.main()
