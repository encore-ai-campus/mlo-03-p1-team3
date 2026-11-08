"""Private, host-bound account pool with an fsynced preparation journal in .env."""

import fcntl
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path


class PoolError(ValueError):
    """Messages deliberately contain neither credentials nor file contents."""


class PoolStore:
    def __init__(self, path, host):
        self.path = Path(path).absolute()
        self.host = host.rstrip("/")
        self.metadata = None
        self.accounts = []
        self._lock = None

    def __enter__(self):
        if self.path.name != ".env":
            raise PoolError("Pool credentials require a dedicated .env file")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self._lock = os.open(
                self.path.with_name(".pool.lock"),
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600,
            )
            self._check_private(self._lock)
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() or self.path.is_symlink():
                self._load()
            return self
        except (OSError, ValueError, KeyError, TypeError):
            self.__exit__(None, None, None)
            raise PoolError("Pool is locked, unsafe, corrupt, or belongs to another host") from None

    def __exit__(self, *_args):
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None

    @staticmethod
    def _check_private(fd):
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise PoolError("Pool file must be privately owned with mode 0600")

    @staticmethod
    def _line(key, value):
        return (key + "=" + json.dumps(value, separators=(",", ":")) + "\n").encode()

    @staticmethod
    def _validate_account(account):
        if (
            not isinstance(account, dict)
            or set(account) != {"phone_number", "password", "poor", "state", "funded"}
            or not isinstance(account["phone_number"], str)
            or not re.fullmatch(r"019\d{8}", account["phone_number"])
            or not isinstance(account["password"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", account["password"])
            or type(account["poor"]) is not bool
            or account["state"] not in {"new", "signup", "signed_up", "funding", "ready"}
            or type(account["funded"]) is not int
            or not 0 <= account["funded"] <= 30_000_000
        ):
            raise PoolError("Invalid pool account record")

    def _load(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            self._check_private(fd)
            if os.fstat(fd).st_size > 64 * 1024 * 1024:
                raise PoolError("Pool journal is too large")
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read()
            # A crash may leave the last append incomplete. It cannot authorize a
            # money request: update() only returns after the complete record fsync.
            if raw and not raw.endswith(b"\n"):
                end = raw.rfind(b"\n") + 1
                complete = raw[:end]
            else:
                end = len(raw)
                complete = raw
            records = {}
            metadata = None
            for line in complete.decode("utf-8").splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                key, value = line.split("=", 1)
                data = json.loads(value)
                if key == "PODOBANK_TRANSFER_POOL":
                    if metadata is not None:
                        raise PoolError("Duplicate pool metadata")
                    metadata = data
                elif re.fullmatch(r"PODOBANK_TRANSFER_ACCOUNT_\d{5}", key):
                    self._validate_account(data)
                    records[int(key.rsplit("_", 1)[1])] = data
                else:
                    raise PoolError("Use a dedicated pool .env file")
            if (
                not isinstance(metadata, dict)
                or metadata.get("version") != 1
                or metadata.get("host") != self.host
                or not isinstance(metadata.get("id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", metadata["id"])
                or type(metadata.get("count")) is not int
                or not 2 <= metadata["count"] <= 10000
                or set(records) != set(range(metadata["count"]))
            ):
                raise PoolError("Invalid pool metadata or host")
            accounts = [records[i] for i in range(metadata["count"])]
            if len({a["phone_number"] for a in accounts}) != len(accounts):
                raise PoolError("Duplicate pool account")
            # Only repair a validated, host-matching pool, never another .env.
            if end != len(raw):
                os.ftruncate(fd, end)
                os.fsync(fd)
            self.metadata, self.accounts = metadata, accounts
        finally:
            os.close(fd)

    def create(self, count):
        if type(count) is not int or not 2 <= count <= 10000:
            raise PoolError("Pool size must be between 2 and 10000")
        if self.metadata is not None:
            if self.metadata["count"] != count:
                raise PoolError("Existing pool size differs; existing credentials preserved")
            return
        prefix = secrets.randbelow(10000)
        metadata = {"version": 1, "host": self.host, "id": secrets.token_hex(16), "count": count}
        accounts = [
            {
                "phone_number": f"019{prefix:04d}{i:04d}",
                "password": secrets.token_urlsafe(18),
                "poor": i % 10 == 9,
                "state": "new",
                "funded": 0,
            }
            for i in range(count)
        ]
        # The only temporary file containing credentials is also named .env,
        # inside a private directory on the same filesystem for atomic rename.
        with tempfile.TemporaryDirectory(prefix=".pool-", dir=self.path.parent) as folder:
            pending = Path(folder) / ".env"
            fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(self._line("PODOBANK_TRANSFER_POOL", metadata))
                for i, account in enumerate(accounts):
                    stream.write(self._line(f"PODOBANK_TRANSFER_ACCOUNT_{i:05d}", account))
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists() or self.path.is_symlink():
                raise PoolError("Destination appeared; existing file preserved")
            os.rename(pending, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        self.metadata, self.accounts = metadata, accounts

    def update(self, index, **changes):
        if not changes.keys() <= {"state", "funded"}:
            raise PoolError("Only preparation state can change")
        account = self.accounts[index] | changes
        self._validate_account(account)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            self._check_private(fd)
            line = self._line(f"PODOBANK_TRANSFER_ACCOUNT_{index:05d}", account)
            if os.write(fd, line) != len(line):
                raise PoolError("Incomplete pool journal write; stop preparation")
            os.fsync(fd)
        finally:
            os.close(fd)
        self.accounts[index] = account

    def select(self, count):
        if (
            type(count) is not int
            or not 2 <= count <= len(self.accounts)
            or any(a["state"] != "ready" for a in self.accounts[:count])
        ):
            raise PoolError("Requested accounts are missing or not ready")
        return [dict(a) for a in self.accounts[:count]]
