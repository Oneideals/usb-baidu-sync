"""BaiduPCS-Go execution wrapper for uploading files to Baidu Netdisk."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

logger = logging.getLogger(__name__)

AUTH_ERROR_TOKENS = ["未登录", "401", "bduss invalid", "token expired", "errno: -6", "请重新登录"]


@dataclass
class UploadResult:
    """Result of an upload operation."""
    success: bool = False
    is_auth_error: bool = False
    is_interrupted: bool = False
    error_message: str | None = None

    def __bool__(self) -> bool:
        """Allow UploadResult to be evaluated directly as boolean for backward compatibility."""
        return self.success


class BaiduEngine:
    """Wrapper around BaiduPCS-Go CLI tool."""

    def __init__(
        self,
        binary_path: str | Path | None = None,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.binary_path = self._locate_binary(binary_path)
        self._current_process: subprocess.Popen | None = None
        self._is_aborted = False

    def _locate_binary(self, binary_path: str | Path | None) -> str:
        if self.dry_run:
            return "mock-baidupcs-go"

        if binary_path:
            p = str(binary_path)
            if shutil.which(p) or Path(p).is_file():
                return p

        # Check common locations
        candidates = [
            shutil.which("BaiduPCS-Go"),
            shutil.which("baidupcs-go"),
            Path.home() / "Library" / "Application Support" / "USBBaiduSync" / "bin" / "BaiduPCS-Go",
            Path.home() / ".baidupcsgo" / "BaiduPCS-Go",
            Path("/usr/local/bin/BaiduPCS-Go"),
            Path("/opt/homebrew/bin/BaiduPCS-Go"),
        ]
        for c in candidates:
            if c and Path(c).is_file():
                return str(c)

        return "BaiduPCS-Go"

    def is_binary_available(self) -> bool:
        if self.dry_run:
            return True
        return bool(shutil.which(self.binary_path) or Path(self.binary_path).is_file())

    def check_login(self) -> bool:
        """Check if BaiduPCS-Go currently has a valid login session."""
        if self.dry_run:
            return True

        if not self.is_binary_available():
            logger.warning("BaiduPCS-Go binary is not found on system.")
            return False

        try:
            res = subprocess.run(
                [self.binary_path, "who"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = res.stdout + res.stderr
            if res.returncode == 0 and "未登录" not in output and "uid" in output.lower():
                return True
            return False
        except Exception as e:
            logger.error("Failed to check BaiduPCS-Go login: %s", e)
            return False

    def login_with_bduss(self, bduss: str) -> bool:
        """Log in to Baidu Netdisk using BDUSS token."""
        if self.dry_run:
            return True

        if not bduss or not self.is_binary_available():
            return False

        try:
            res = subprocess.run(
                [self.binary_path, "login", f"-bduss={bduss.strip()}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = res.stdout + res.stderr
            if res.returncode == 0 and ("登录成功" in output or "uid" in output.lower()):
                return True
            logger.error("Login failed output: %s", output)
            return False
        except Exception as e:
            logger.error("Error executing login: %s", e)
            return False

    def upload_file(
        self,
        local_path: Path | str,
        remote_path: str,
        progress_cb: Callable[[str], None] | None = None,
    ) -> UploadResult:
        """Upload a local file to remote Baidu Netdisk destination."""
        if self.dry_run:
            if progress_cb:
                progress_cb("DRY_RUN: Uploaded 100%")
            return UploadResult(success=True)

        local_p = Path(local_path)
        if not local_p.is_file():
            logger.error("Local file does not exist: %s", local_p)
            return UploadResult(success=False, error_message=f"Local file does not exist: {local_p}")

        remote_parent_dir = str(PurePosixPath(remote_path).parent)
        cmd = [self.binary_path, "upload", str(local_p.resolve()), remote_parent_dir]
        logger.info("Executing upload command: %s", " ".join(cmd))

        self._is_aborted = False
        captured_output: list[str] = []

        try:
            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if self._current_process.stdout:
                for line in self._current_process.stdout:
                    clean_line = line.strip()
                    if clean_line:
                        captured_output.append(clean_line)
                        logger.debug("BaiduPCS: %s", clean_line)
                        if progress_cb:
                            progress_cb(clean_line)

            self._current_process.wait()
            ret = self._current_process.returncode
            was_aborted = self._is_aborted
            self._current_process = None

            if was_aborted:
                return UploadResult(success=False, is_interrupted=True, error_message="Aborted by unmount")

            full_text = "\n".join(captured_output).lower()
            is_auth = any(tok in full_text for tok in AUTH_ERROR_TOKENS)

            if ret == 0:
                return UploadResult(success=True)
            return UploadResult(
                success=False,
                is_auth_error=is_auth,
                error_message=captured_output[-1] if captured_output else f"Process exited with {ret}",
            )
        except Exception as e:
            logger.error("Upload process encountered exception: %s", e)
            was_aborted = self._is_aborted
            self._current_process = None
            return UploadResult(
                success=False,
                is_interrupted=was_aborted,
                error_message=str(e),
            )

    def abort_current_upload(self) -> None:
        """Terminate currently running upload process safely."""
        self._is_aborted = True
        if self._current_process and self._current_process.poll() is None:
            try:
                logger.warning("Terminating current upload process (PID: %s)...", self._current_process.pid)
                self._current_process.terminate()
                self._current_process.wait(timeout=2)
            except Exception:
                self._current_process.kill()
            finally:
                self._current_process = None
