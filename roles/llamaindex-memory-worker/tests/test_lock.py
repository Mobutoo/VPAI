# roles/llamaindex-memory-worker/tests/test_lock.py
import os, tempfile, subprocess, sys
from pathlib import Path

# Mirror of the HARDENED ensure_lock/release_lock (must match index.py.j2 after Task 1).
def ensure_lock(lock_path: Path) -> None:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            pid = int(lock_path.read_text().strip() or "0")
        except Exception:
            pid = 0
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0); alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True
        if alive:
            raise RuntimeError(f"lock held by live pid {pid}: {lock_path}") from exc
        lock_path.unlink(missing_ok=True)  # stale → reclaim
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))

def test_stale_lock_reclaimed():
    d = Path(tempfile.mkdtemp()); lp = d / "index.lock"
    lp.write_text("999999")  # almost-certainly-dead PID
    ensure_lock(lp)  # must NOT raise
    assert lp.read_text() == str(os.getpid())
    print("ok: stale lock reclaimed")

def test_live_lock_blocks():
    d = Path(tempfile.mkdtemp()); lp = d / "index.lock"
    lp.write_text(str(os.getpid()))  # our own (live) pid
    try:
        ensure_lock(lp); print("FAIL: live lock not blocked"); sys.exit(1)
    except RuntimeError:
        print("ok: live lock blocks")

if __name__ == "__main__":
    test_stale_lock_reclaimed(); test_live_lock_blocks(); print("ALL OK")
