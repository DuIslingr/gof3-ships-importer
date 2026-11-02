"""Content fingerprints and atomic completion records for import.py (stdlib only)."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

SCHEMA = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    """Interrupted writes must never turn incomplete work into a cache hit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def record(folder):
    try:
        with open(Path(folder) / '.done', encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, dict) and value.get('schema') == SCHEMA else None
    except (OSError, ValueError):
        return None


def done(folder, fingerprint):
    value = record(folder)
    return value is not None and value.get('fingerprint') == fingerprint


def mark(folder, fingerprint, **details):
    write_json(Path(folder) / '.done', dict(details, schema=SCHEMA, fingerprint=fingerprint))


def recipe(root, entries):
    """Follow local Python imports and literal helper-script names, including Blender subprocesses.

    Include importer orchestration and this helper in every recipe; follow conversion tables too.
    Third-party imports are represented separately by the caller's environment identity.
    """
    root = Path(root)
    tools = root / 'tools'
    pending = [root / 'import.py', tools / 'build_cache.py'] + [tools / p for p in entries]
    files = {}
    while pending:
        path = pending.pop()
        rel = path.relative_to(root).as_posix()
        if rel in files or not path.is_file():
            continue
        files[rel] = file_hash(path)
        if path.suffix != '.py' or path == root / 'import.py' or path == tools / 'build_cache.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(tools / (n.name.split('.')[0] + '.py') for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                pending.append(tools / (node.module.split('.')[0] + '.py'))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Scripts invoked by subprocess are not Python imports.
                if node.value.endswith(('.py', '.json', '.txt')) and '/' not in node.value and '\\' not in node.value:
                    pending.append(tools / node.value)
    return dict(sorted(files.items()))


def stage(root, entries, inputs, options=None):
    code = recipe(root, entries)
    return {'fingerprint': digest({'schema': SCHEMA, 'code': code, 'inputs': inputs, 'options': options}),
            'code': code, 'inputs': inputs, 'options': options}


def revision(root):
    try:
        r = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    except OSError:
        return None


def materialize_member(archive, member, destination):
    """Compare the complete member before reusing it. Same-size replacements still rewrite.

    Return the SHA-256 verified during comparison/copy so this invocation need not reread it.
    No file-size, timestamp or ZIP CRC is accepted as proof of equal contents.
    """
    destination = Path(destination)
    if destination.is_file():
        h = hashlib.sha256()
        with archive.open(member) as src, open(destination, 'rb') as old:
            while True:
                chunk = src.read(4 << 20)
                if old.read(len(chunk) if chunk else 1) != chunk:
                    break
                if not chunk:
                    return h.hexdigest()
                h.update(chunk)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + '.', dir=destination.parent)
    try:
        h = hashlib.sha256()
        with os.fdopen(fd, 'wb') as dst, archive.open(member) as src:
            for chunk in iter(lambda: src.read(4 << 20), b''):
                h.update(chunk)
                dst.write(chunk)
        os.replace(temporary, destination)
        return h.hexdigest()
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
