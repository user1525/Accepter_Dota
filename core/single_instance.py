"""Per-user process lock; unrelated installations share the same input owner."""
import getpass,hashlib
from pathlib import Path
from PyQt5.QtCore import QLockFile,QDir

def acquire_instance(path=None):
    suffix=hashlib.sha256(getpass.getuser().encode('utf-8')).hexdigest()[:16]
    lock=QLockFile(str(path or Path(QDir.tempPath())/('dota-accepter-'+suffix+'.lock')))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(0) else None
