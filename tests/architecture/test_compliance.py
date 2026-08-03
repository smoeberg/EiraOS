import ast
import os
import yaml

def load_architecture_spec():
    spec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../docs/architecture_spec.yaml"))
    if not os.path.exists(spec_path):
        return {"daemons": {}}
    with open(spec_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_python_files(root_dir):
    py_files = {}
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                full_path = os.path.join(dirpath, filename)
                with open(full_path, "r", encoding="utf-8") as f:
                    py_files[full_path] = f.read()
    return py_files

def test_dynamic_daemon_isolation():
    spec = load_architecture_spec()
    daemons = list(spec.get("daemons", {}).keys())

    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../app"))
    py_files = get_python_files(app_dir)

    violations = []
    for filename, content in py_files.items():
        if "daemons" in filename:
            tree = ast.parse(content, filename=filename)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if any(d in module_name for d in daemons if d not in filename):
                        violations.append((filename, module_name))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(d in alias.name for d in daemons if d not in filename):
                            violations.append((filename, alias.name))

    assert not violations, f"Daemon isolation violations found: {violations}"
