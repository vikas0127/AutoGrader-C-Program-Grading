"""C compiler and bounded process runner.

POSIX resource limits are best-effort process limits, not a security sandbox.
"""
import threading
import tempfile
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path


def _terminate_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, text=True, timeout=3)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def compile_c_program(source, build_dir, timeout=15, flags=None):
    source_path = Path(source).resolve()
    if not source_path.is_file():
        return {"status":"error", "error":"source_not_found", "stderr":"Source file not found."}
    if source_path.suffix.lower() != ".c":
        return {"status":"error", "error":"invalid_extension", "stderr":"Source must be a .c file."}
    gcc = shutil.which("gcc")
    if not gcc:
        return {"status":"error", "error":"gcc_missing", "stderr":"GCC not found on PATH."}
    out_dir=Path(build_dir); out_dir.mkdir(parents=True,exist_ok=True)
    executable=out_dir/('submission.exe' if os.name=='nt' else 'submission')
    command=[gcc, *(flags or ["-std=c11","-Wall","-Wextra","-Wpedantic"]), str(source_path), "-o", str(executable)]
    start=time.monotonic()
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=timeout,check=False)
        return {"status":"ok" if result.returncode==0 else "error",
                "executable_path":str(executable) if result.returncode==0 else None,
                "returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr,
                "duration_seconds":round(time.monotonic()-start,3),
                "error":None if result.returncode==0 else "compile_failed", "command":command}
    except subprocess.TimeoutExpired as exc:
        stderr=exc.stderr.decode(errors='replace') if isinstance(exc.stderr,bytes) else (exc.stderr or "")
        return {"status":"error","error":"compile_timeout","stderr":stderr,
                "duration_seconds":round(time.monotonic()-start,3)}
    except OSError as exc:
        return {"status":"error","error":"compiler_execution_failed","stderr":str(exc),
                "duration_seconds":round(time.monotonic()-start,3)}


def _resource_limiter(memory_limit_mb, cpu_limit_s=None):
    """Return a POSIX pre-exec callback that applies address-space/CPU limits."""
    if os.name == "nt" or (memory_limit_mb is None and cpu_limit_s is None):
        return None
    def apply_limits():
        import resource
        if memory_limit_mb is not None:
            amount=max(1,int(memory_limit_mb))*1024*1024
            resource.setrlimit(resource.RLIMIT_AS,(amount,amount))
        if cpu_limit_s is not None:
            cpu=max(1,int(cpu_limit_s))
            resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
    return apply_limits




def run_compiled_program(
    executable,
    stdin="",
    timeout=2,
    memory_limit_mb=None,
    cpu_limit_s=None,
    output_limit_bytes=1024 * 1024,
    args=None,
    cwd=None,
    sandbox_mode="off",
):
    """Run a compiled program with timeout and bounded output capture.

    output_limit_bytes applies independently to stdout and stderr.
    POSIX process-group termination is used to clean up child processes.
    """
    executable_path = Path(executable).resolve()
    start = time.monotonic()

    if not executable_path.is_file():
        return {
            "status": "error",
            "error": "executable_not_found",
            "stdout": "",
            "stderr": "",
        }

    if output_limit_bytes <= 0:
        return {
            "status": "error",
            "error": "invalid_output_limit",
            "stdout": "",
            "stderr": "",
        }

    process = None
    output_exceeded = threading.Event()
    output_buffers = {
        "stdout": bytearray(),
        "stderr": bytearray(),
    }

    def read_stream(stream, name):
        """Continuously drain a pipe, retaining at most the configured cap."""
        buffer = output_buffers[name]

        try:
            while True:
                chunk = stream.read(4096)

                if not chunk:
                    break

                remaining = output_limit_bytes - len(buffer)

                if remaining > 0:
                    buffer.extend(chunk[:remaining])

                if len(chunk) > remaining:
                    output_exceeded.set()
                    break

        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def write_stdin():
        """Send input without blocking the main timeout-monitoring loop."""
        try:
            if stdin:
                process.stdin.write(stdin.encode())
                process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    try:
        kwargs = {}

        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        limiter = _resource_limiter(memory_limit_mb, cpu_limit_s)

        if limiter is not None:
            kwargs["preexec_fn"] = limiter

        safe_args = [str(x) for x in (args or [])]
        command = [str(executable_path), *safe_args]
        sandbox_used = False
        if sandbox_mode not in {"off", "bubblewrap"}:
            return {"status":"error","error":"invalid_sandbox_mode","stdout":"","stderr":"sandbox_mode must be off or bubblewrap."}
        if sandbox_mode == "bubblewrap":
            bwrap = shutil.which("bwrap")
            if not bwrap:
                return {"status":"error","error":"sandbox_unavailable","stdout":"","stderr":"Bubblewrap requested but bwrap is not installed; execution was not started."}
            if os.name != "posix":
                return {"status":"error","error":"sandbox_unsupported","stdout":"","stderr":"Bubblewrap isolation is supported only on Linux/POSIX."}
            workdir = Path(cwd).resolve() if cwd else Path(tempfile.mkdtemp(prefix="autograder_bwrap_")).resolve()
            workdir.mkdir(parents=True, exist_ok=True)
            # Host filesystem is visible read-only; only the per-test working
            # directory is writable. Network namespace is disabled.
            command = [bwrap, "--die-with-parent", "--new-session", "--unshare-net",
                       "--ro-bind", "/", "/", "--bind", str(workdir), str(workdir),
                       "--proc", "/proc", "--dev", "/dev", "--chdir", str(workdir),
                       str(executable_path), *safe_args]
            sandbox_used = True
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(cwd).resolve()) if cwd else None,
            **kwargs,
        )

        stdout_thread = threading.Thread(
            target=read_stream,
            args=(process.stdout, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(process.stderr, "stderr"),
            daemon=True,
        )
        stdin_thread = threading.Thread(
            target=write_stdin,
            daemon=True,
        )

        stdout_thread.start()
        stderr_thread.start()
        stdin_thread.start()

        deadline = start + timeout
        status = None

        while process.poll() is None:
            if output_exceeded.is_set():
                status = "output_limit_exceeded"
                _terminate_process(process)
                break

            if time.monotonic() >= deadline:
                status = "timeout"
                _terminate_process(process)
                break

            time.sleep(0.01)

        # Check once more in case the output cap was reached as the process
        # exited.
        if status is None and output_exceeded.is_set():
            status = "output_limit_exceeded"

        if status is not None:
            _terminate_process(process)

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _terminate_process(process)

        # Reader threads drain remaining pipe data and finish after cleanup.
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        stdin_thread.join(timeout=2)

        stdout = output_buffers["stdout"].decode(errors="replace")
        stderr = output_buffers["stderr"].decode(errors="replace")
        rc = process.returncode

        if status is None:
            status = "ok" if rc == 0 else "error"

        if status == "timeout":
            error = "timeout"
        elif status == "output_limit_exceeded":
            error = "output_limit_exceeded"
        elif status == "ok":
            error = None
        else:
            error = (
                "resource_limit_or_runtime_error"
                if rc in (-9, -11, -6)
                else "runtime_error"
            )

        return {
            "status": status,
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": round(time.monotonic() - start, 3),
            "error": error,
            "sandbox": {"requested": sandbox_mode, "used": sandbox_used,
                        "network_isolated": sandbox_used,
                        "filesystem_policy": "host read-only; test working directory writable" if sandbox_used else "host defaults"},
        }

    except (OSError, ValueError) as exc:
        if process is not None:
            _terminate_process(process)

        return {
            "status": "error",
            "returncode": None,
            "stdout": output_buffers["stdout"].decode(errors="replace"),
            "stderr": str(exc),
            "duration_seconds": round(time.monotonic() - start, 3),
            "error": "runtime_execution_failed",
        }
