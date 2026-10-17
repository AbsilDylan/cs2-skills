#!/usr/bin/env python3
"""Bounded subprocess capture, including descendants that inherit output pipes.

Windows children start suspended and enter a kill-on-close Job Object before
their initial thread runs. Unix children start a new session. Capture has one
deadline; cleanup may take at most one additional second. Only this invocation's
job or process group is terminated, including after a successful parent exit.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time


_CLEANUP_SECONDS = 1.0


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimits),
                    ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _ThreadEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                    ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD)]

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for _name, _arguments, _result in (
        ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        ("Thread32First", [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
        ("Thread32Next", [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
        ("OpenThread", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        ("ResumeThread", [wintypes.HANDLE], wintypes.DWORD),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ):
        _function = getattr(_kernel, _name)
        _function.argtypes = _arguments
        _function.restype = _result

    def _wincheck(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    class _WindowsJob:
        def __init__(self):
            self.handle = _wincheck(_kernel.CreateJobObjectW(None, None))
            try:
                limits = _ExtendedLimits()
                limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
                _wincheck(_kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            except BaseException:
                self.close()
                raise

        def assign_and_resume(self, process, deadline):
            # The child is still suspended and cannot have created descendants.
            handle = _wincheck(_kernel.OpenProcess(0x0101, False, process.pid))  # SET_QUOTA | TERMINATE
            try:
                _wincheck(_kernel.AssignProcessToJobObject(self.handle, handle))
            finally:
                _kernel.CloseHandle(handle)
            snapshot = _kernel.CreateToolhelp32Snapshot(0x4, 0)  # SNAPTHREAD
            if snapshot == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                entry = _ThreadEntry()
                entry.dwSize = ctypes.sizeof(entry)
                found = _kernel.Thread32First(snapshot, ctypes.byref(entry))
                while found:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(process.args, 0)
                    if entry.th32OwnerProcessID == process.pid:
                        thread = _wincheck(_kernel.OpenThread(0x2, False, entry.th32ThreadID))  # SUSPEND_RESUME
                        try:
                            if _kernel.ResumeThread(thread) == 0xFFFFFFFF:
                                raise ctypes.WinError(ctypes.get_last_error())
                        finally:
                            _kernel.CloseHandle(thread)
                        return
                    found = _kernel.Thread32Next(snapshot, ctypes.byref(entry))
                raise OSError("Suspended child has no discoverable initial thread")
            finally:
                _kernel.CloseHandle(snapshot)

        def close(self):
            if self.handle is not None:
                _kernel.CloseHandle(self.handle)
                self.handle = None


def bounded_process(command: list[str], timeout: int, stdout_limit: int = 16 * 1024 * 1024,
                    stderr_limit: int = 1024 * 1024) -> dict:
    """Capture bounded bytes and enforce a deadline on parent and pipe drainage.

    No shell is used. Reader threads are daemons, and all joins share a bounded
    cleanup deadline, so an unexpectedly leaked pipe cannot hang the caller.
    """
    if timeout <= 0 or stdout_limit < 0 or stderr_limit < 0:
        raise ValueError("Timeout must be positive and output limits nonnegative")
    if os.name != "nt" and not all(hasattr(os, name) for name in ("waitid", "WNOWAIT", "WEXITED", "WNOHANG")):
        raise OSError("Safe Unix process-group cleanup requires waitid with WNOWAIT")
    deadline = time.monotonic() + timeout
    job = _WindowsJob() if os.name == "nt" else None
    process = None
    readers = []
    buffers = [bytearray(), bytearray()]
    finished = [threading.Event(), threading.Event()]
    overflow = threading.Event()
    timed_out = False
    cleanup_deadline = None

    def stop_tree():
        if job is not None:
            job.close()
        elif process is not None:
            # Keep the direct child unreaped until this signal; its PID cannot
            # be recycled into another invocation's process group beforehand.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def drain(stream, limit, number):
        try:
            while chunk := stream.read(65536):
                remaining = limit - len(buffers[number])
                if remaining > 0:
                    buffers[number].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
        except (OSError, ValueError):
            pass
        finally:
            stream.close()
            finished[number].set()

    try:
        options = {"creationflags": 0x08000004} if job is not None else {"start_new_session": True}
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False, bufsize=0, **options)
        if job is not None:
            job.assign_and_resume(process, deadline)
        for number, (stream, limit) in enumerate(((process.stdout, stdout_limit), (process.stderr, stderr_limit))):
            reader = threading.Thread(target=drain, args=(stream, limit, number), daemon=True)
            reader.start()
            readers.append(reader)

        # Waiting for EOF first keeps the direct child's PID reserved on Unix.
        # Descendants holding either pipe remain subject to the same deadline.
        while not all(event.is_set() for event in finished):
            if overflow.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            finished[0].wait(min(remaining, 0.02)) if not finished[0].is_set() else finished[1].wait(min(remaining, 0.02))

        if not timed_out and not overflow.is_set():
            remaining = deadline - time.monotonic()
            try:
                # Pipes have closed. Wait without reaping on Unix, so group
                # cleanup can still never target a recycled PID.
                if os.name != "nt":
                    while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(command, timeout)
                        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
                else:
                    process.wait(timeout=max(0, remaining))
            except subprocess.TimeoutExpired:
                timed_out = True
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        cleanup_deadline = time.monotonic() + _CLEANUP_SECONDS
        stop_tree()
        if process is not None:
            # On startup failure before job assignment, the suspended child is
            # still ours and has never run; terminate it explicitly as well.
            if job is not None and process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
            for reader in readers:
                reader.join(max(0, cleanup_deadline - time.monotonic()))
            if not readers:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
        if job is not None:
            job.close()
    return {"exitCode": process.returncode, "timedOut": timed_out,
            "outputLimitExceeded": overflow.is_set(),
            "stdout": bytes(buffers[0]), "stderr": bytes(buffers[1])}
