import ast
from pathlib import Path

imports = set()

for f in Path(".").rglob("*.py"):
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
    except:
        pass

print("\n".join(sorted(imports)))