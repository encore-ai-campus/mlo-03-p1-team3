import os
import threading
from pathlib import Path


class AppendFile:
    """한 줄씩 덧붙이는 로그 파일. 파일을 계속 열어 두고 logrotate로 바뀌면 다시 연다.

    매번 열고 닫던 비용(mkdir, open, 텍스트 래퍼, close)을 없앤다. 쓸 때마다 경로의 inode를
    열린 파일과 비교하므로(WatchedFileHandler와 같은 방식) 회전·삭제 직후 줄도 새 파일에 들어간다.
    O_APPEND 한 번의 write라 여러 worker 프로세스가 같은 파일에 써도 줄이 섞이지 않는다.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._fd = None
        self._identity = None
        self._lock = threading.Lock()

    def _current_identity(self):
        try:
            stat = os.stat(self.path)
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino

    def _reopen(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o666)
        stat = os.fstat(fd)
        self._fd, self._identity = fd, (stat.st_dev, stat.st_ino)

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._fd is None or self._current_identity() != self._identity:
                self._reopen()
            view = memoryview(data)
            while view:
                view = view[os.write(self._fd, view):]
