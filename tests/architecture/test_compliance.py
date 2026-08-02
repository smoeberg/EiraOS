"""
EiraOS Architecture Compliance Suite
Enforces machine-verifiable architectural rules (no illegal cross-daemon imports, data ownership, isolation).
"""
import os
import ast
import pytest
import yaml

def get_python_files(directory):
    py_files = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, directory)
                with open(path, "r", encoding="utf-8") as f:
                    py_files[rel_path] = f.read()
    return py_files

def test_no_direct_daemon_imports():
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../app"))
    py_files = get_python_files(app_dir)

    for filename, content in py_files.items():
        if "daemons" in filename:
            tree = ast.parse(content, filename=filename)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module_name = node.module or ""
                    for alias in node.names:
                        full_import = f"{module_name}.{alias.name}" if module_name else alias.name
                        for other_daemon in ["identityd", "walletd", "veritasd", "graphd", "presenced", "contextd", "intentd"]:
                            if other_daemon in full_import and other_daemon not in filename:
                                pytest.fail(
                                    f"Architectural Violation in '{filename}': "
                                    f"Daemon imports another daemon directly ('{full_import}'). "
                                    "Daemons must communicate via IPC/Contracts only!"
                                )

def test_architecture_spec_exists():
    spec_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../specs/architecture.yaml"))
    assert os.path.exists(spec_path), "Architecture specification file missing!"
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert spec["project"] == "EiraOS"
    assert "daemons" in spec
