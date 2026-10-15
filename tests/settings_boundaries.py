"""Architecture regression checks, not a sandbox for hostile Python code."""
import ast
from importlib.util import resolve_name


def within(name, prefix):
    return name == prefix or name.startswith(prefix + ".")


def layer_for(module):
    if within(module, "ui.dashboard") or within(module, "ui.settings"):
        return "view"
    if within(module, "app.contracts"):
        return "contract"
    if within(module, "app.presentation.settings"):
        return "presentation"
    if within(module, "app.settings"):
        return "logic"
    return None


def import_allowed(layer, name):
    if layer == "contract":
        return any(within(name, prefix) for prefix in ("dataclasses", "enum", "typing"))
    if layer == "view":
        return any(within(name, prefix) for prefix in (
            "contextlib", "dataclasses", "typing", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
            "ui.dashboard", "ui.settings", "app.contracts",
        ))
    if layer == "logic":
        return not any(within(name, prefix) for prefix in (
            "ui", "app.presentation", "PySide6.QtWidgets", "PySide6.QtQuick",
            "PySide6.QtQml",
        )) and name != "PySide6"
    if layer == "presentation":
        if within(name, "PySide6"):
            return within(name, "PySide6.QtCore")
        if within(name, "app"):
            return any(within(name, prefix) for prefix in (
                "app.contracts", "app.settings", "app.presentation.settings",
                "app.utils.logger", "app.ai.prompt_builder",
            ))
        return not any(within(name, prefix) for prefix in (
            "ui", "os", "pathlib", "io", "requests", "urllib", "http", "socket", "subprocess",
        ))
    return True


def boundary_violations(source, module, view_members=(), *, is_package=False):
    tree = ast.parse(source)
    layer = layer_for(module)
    errors = []
    package = module if is_package else module.rpartition(".")[0]
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}

    def fail(node, message):
        errors.append(f"{node.lineno}: {message}")

    for node in ast.walk(tree):
        imports = []
        if isinstance(node, ast.Import):
            for item in node.names:
                imports.append(item.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name('.' * node.level + base, package)
            for item in node.names:
                name = base + "." + item.name
                imports.append(name)
        for name in imports:
            if not import_allowed(layer, name):
                fail(node, f"{layer} imports {name}")
            # Composition is allowed in the exact function, not all of core.
            if within(module, "app.core") and within(name, "app.presentation"):
                owner = parents.get(node)
                while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    owner = parents.get(owner)
                owner_class = parents.get(owner)
                if not (module == "app.core.window_manager"
                        and isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and owner.name == "show_settings"
                        and isinstance(owner_class, ast.ClassDef) and owner_class.name == "WindowManager"
                        and parents.get(owner_class) is tree):
                    fail(node, "presentation assembly outside WindowManager.show_settings")

    class Operations(ast.NodeVisitor):
        """Resolve ordinary aliases in source order, isolated per lexical scope.

        This intentionally does not model branch merging or arbitrary dynamic code.
        """
        def __init__(self):
            self.aliases = {}

        def dotted(self, node):
            if isinstance(node, ast.Name):
                return self.aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return self.dotted(node.value) + "." + node.attr
            return ""

        def visit_Import(self, node):
            for item in node.names:
                self.aliases[item.asname or item.name.split('.')[0]] = (
                    item.name if item.asname else item.name.split('.')[0])

        def visit_ImportFrom(self, node):
            base = node.module or ""
            if node.level:
                base = resolve_name('.' * node.level + base, package)
            for item in node.names:
                self.aliases[item.asname or item.name] = base + "." + item.name

        def visit_FunctionDef(self, node):
            for value in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
                if value is not None:
                    self.visit(value)
            outer = self.aliases
            self.aliases = outer.copy()
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                        node.args.vararg, node.args.kwarg):
                if arg is not None:
                    self.aliases.pop(arg.arg, None)
            for statement in node.body:
                self.visit(statement)
            self.aliases = outer

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            for value in (*node.decorator_list, *node.bases, *node.keywords):
                self.visit(value)
            outer = self.aliases
            self.aliases = outer.copy()
            for statement in node.body:
                self.visit(statement)
            self.aliases = outer

        def visit_Assign(self, node):
            self.generic_visit(node)
            name = self.dotted(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.aliases[target.id] = name or target.id

        def visit_Call(self, node):
            name = self.dotted(node.func)
            if layer in ("view", "contract", "presentation") and (
                name in ("open", "eval", "exec", "__import__", "compile") or any(
                within(name, prefix) for prefix in (
                    "builtins.open", "builtins.__import__", "importlib", "os.environ", "os.getenv",
                    "PySide6.QtCore.QFile", "PySide6.QtCore.QSaveFile", "PySide6.QtCore.QSettings",
                    "PySide6.QtCore.QProcess", "PySide6.QtGui.QDesktopServices",
                )
            )):
                fail(node, f"{layer} performs external operation {name}")
            self.generic_visit(node)

        def visit_Attribute(self, node):
            if layer == "presentation":
                name = self.dotted(node)
                for root in ("self.view.", "view."):
                    if name.startswith(root):
                        member = name[len(root):].split('.')[0]
                        if member not in view_members:
                            fail(node, f"view member outside public port: {member}")
            self.generic_visit(node)

    Operations().visit(tree)
    return errors


def public_view_members(source):
    view = next(node for node in ast.parse(source).body
                if isinstance(node, ast.ClassDef) and node.name == "SettingsView")
    return {node.name for node in view.body if isinstance(node, ast.FunctionDef)} | {
        node.target.id for node in view.body if isinstance(node, ast.AnnAssign)
    }
