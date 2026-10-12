"""Export an allowlisted public source snapshot for repository publication."""
import base64
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def entries():
    files = list(ROOT.glob("*.lua")) + [ROOT / name for name in ("MPlusLogs.toc", "LICENSE", ".gitignore", "realm-slugs.json", "Start-Companion.vbs")]
    for directory, patterns in {"Locales": ["*.lua", "*.json", "README.md"], "tools": ["*.py", "*.pyw", "*.ps1", "requirements.txt", "oauth_client.json"],
        "tools/assets": ["*.png", "*.ico", "*.svg"], "tests": ["*.py"], "packaging": ["*"], ".github/workflows": ["*.yml"]}.items():
        for pattern in patterns:
            files.extend((ROOT / directory).glob(pattern))
    files.extend([ROOT / "experiments/wcl-points-and-damage.json"])
    files.extend((ROOT / "experiments/ondemand").rglob("*.lua"))
    files.extend((ROOT / "experiments/ondemand").rglob("*.toc"))
    result = []
    for path in sorted(set(files)):
        if not path.is_file():
            raise ValueError(f"Missing source file: {path}")
        name = path.relative_to(ROOT).as_posix()
        if path.suffix in {".png", ".ico"}:
            result.append({"path": name, "encoding": "base64", "content": base64.b64encode(path.read_bytes()).decode()})
        else:
            result.append({"path": name, "encoding": "utf-8", "content": path.read_text(encoding="utf-8-sig")})
    result.append({"path": "README.md", "encoding": "utf-8", "content": (ROOT / "packaging/README-public.md").read_text(encoding="utf-8")})
    return result


if __name__ == "__main__":
    data = entries()
    if sys.argv[1:] == ["--snapshot"]:
        output = ROOT / ".build-tools/source-snapshot.json"
        output.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        with zipfile.ZipFile(ROOT / "release-output/MPlusLogs-0.5.0-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in data:
                content = base64.b64decode(entry["content"]) if entry["encoding"] == "base64" else entry["content"].encode()
                archive.writestr(entry["path"], content)
        print(len(data))
    else:
        snapshot = json.loads((ROOT / ".build-tools/source-snapshot.json").read_text())
        index = int(sys.argv[1])
        print(json.dumps(snapshot[index:index+8], ensure_ascii=True))
