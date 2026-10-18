"""Best-effort, bounded cleanup of disposable profile caches only."""
from pathlib import Path
import re
import threading
import time

MAX_BYTES=128*1024*1024
MAX_AGE=30*86400
MIN_AGE=86400
INTERVAL=6*3600
_lock=threading.Lock()
_last={}
_owned=re.compile(r"(?:[0-9a-f]{64}|name-lookup-[0-9a-f]{64})\.json(\.tmp)?$")


def linked(path):
    return path.is_symlink() or (hasattr(path,"is_junction") and path.is_junction())


def clean(directory, now=None, max_bytes=MAX_BYTES, max_age=MAX_AGE):
    """Never recurse, follow links, or delete settings, SQLite, or update backups."""
    root=Path(directory)
    stats={"removed":0,"bytes":0}
    if root.name!=".wcl-cache" or linked(root) or not root.is_dir():
        return stats
    resolved=root.resolve()
    now=time.time() if now is None else now
    candidates=[]
    try:
        for path in root.iterdir():
            if not _owned.fullmatch(path.name) or linked(path) or not path.is_file(): continue
            if path.resolve().parent!=resolved: continue
            entry=path.stat()
            candidates.append((entry.st_mtime,path,entry.st_size))
    except OSError:
        return stats
    total=sum(size for _,_,size in candidates)
    for stamp,path,size in sorted(candidates):
        age=now-stamp
        expired=age>=max_age or (path.name.endswith(".tmp") and age>=MIN_AGE)
        if not expired and not (total>max_bytes and age>=MIN_AGE): continue
        try:
            # Recheck immediately before unlink: do not remove a refreshed entry.
            current=path.lstat()
            if current.st_mtime!=stamp or current.st_size!=size or linked(path): continue
            path.unlink()
            total-=size; stats["removed"]+=1; stats["bytes"]+=size
        except OSError:
            pass
    return stats


def maintain(directory):
    key=str(Path(directory).absolute())
    now=time.monotonic()
    with _lock:
        if now-_last.get(key,float("-inf"))<INTERVAL: return
        _last[key]=now
    try:
        clean(directory)
    except OSError:
        pass  # Cache maintenance must never prevent loading logs.
