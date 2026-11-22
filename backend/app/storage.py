"""File storage. On disk (BP_STORAGE_DIR) or inside the database (BP_STORAGE=db, the default with Postgres)."""
import os

from . import config


def _safe_rel(rel: str) -> str:
    """Reject absolute paths and traversal before using a storage key on disk or in the DB."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or rel.startswith(("/", "\\")):
        raise ValueError("Invalid storage path")
    normalized = os.path.normpath(rel.replace("\\", os.sep))
    if normalized in ("", ".", "..") or normalized.startswith(".." + os.sep):
        raise ValueError("Invalid storage path")
    if any(part == ".." for part in normalized.split(os.sep)):
        raise ValueError("Invalid storage path")
    root = os.path.abspath(config.storage_dir())
    target = os.path.abspath(os.path.join(root, normalized))
    if os.path.commonpath((root, target)) != root:
        raise ValueError("Invalid storage path")
    return normalized

def _abs(rel: str) -> str:
    return os.path.join(config.storage_dir(), _safe_rel(rel))


def _use_db() -> bool:
    return config.storage_mode() == "db"


def _scope(sess):
    """Use the caller's session when given (no commit, caller owns the transaction), else open our own."""
    from . import db
    return (sess, False) if sess is not None else (db.session(), True)


def save(rel: str, data: bytes, sess=None) -> str:
    rel = _safe_rel(rel)
    if _use_db():
        from . import db
        s, own = _scope(sess)
        try:
            row = s.get(db.StoredFile, rel)
            if row:
                row.data = data
            else:
                s.add(db.StoredFile(path=rel, data=data))
            s.commit() if own else s.flush()
        finally:
            s.close() if own else None
        return rel
    p = _abs(rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return rel


def read(rel: str, sess=None) -> bytes:
    rel = _safe_rel(rel)
    if _use_db():
        from . import db
        s, own = _scope(sess)
        try:
            row = s.get(db.StoredFile, rel)
            if row is None:
                raise FileNotFoundError(rel)
            return bytes(row.data)
        finally:
            s.close() if own else None
    with open(_abs(rel), "rb") as f:
        return f.read()


def delete(rel: str, sess=None) -> None:
    rel = _safe_rel(rel)
    if _use_db():
        from . import db
        s, own = _scope(sess)
        try:
            row = s.get(db.StoredFile, rel)
            if row:
                s.delete(row)
                s.commit() if own else s.flush()
        finally:
            s.close() if own else None
        return
    try:
        os.remove(_abs(rel))
    except FileNotFoundError:
        pass
