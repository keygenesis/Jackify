import os
import signal
import subprocess
import time
import resource
import sys
import shutil

def get_safe_python_executable():
    """
    Get a safe Python executable for subprocess calls.
    When running as AppImage, returns system Python instead of AppImage path
    to prevent recursive AppImage spawning.
    
    Returns:
        str: Path to Python executable safe for subprocess calls
    """
    # Check if we're running as AppImage
    is_appimage = (
        'APPIMAGE' in os.environ or
        'APPDIR' in os.environ or
        (hasattr(sys, 'frozen') and sys.frozen) or
        (sys.argv[0] and sys.argv[0].endswith('.AppImage'))
    )
    
    if is_appimage:
        # Running as AppImage - use system Python to avoid recursive spawning
        # Try to find system Python (same logic as AppRun)
        for cmd in ['python3', 'python3.13', 'python3.12', 'python3.11', 'python3.10', 'python3.9', 'python3.8']:
            python_path = shutil.which(cmd)
            if python_path:
                return python_path
        # Fallback: if we can't find system Python, this is a problem
        # But we'll still return sys.executable as last resort
        return sys.executable
    else:
        # Not AppImage - sys.executable is safe
        return sys.executable

def get_clean_subprocess_env(extra_env=None):
    """
    Returns a copy of os.environ with bundled-runtime variables and other problematic entries removed.
    Optionally merges in extra_env dict.
    Also ensures bundled tools (lz4, unzip, etc.) are in PATH when running as AppImage.
    CRITICAL: Preserves system PATH to ensure system tools (like lz4) are available.
    """
    from pathlib import Path
    
    env = os.environ.copy()

    # Remove AppImage-specific variables that can confuse subprocess calls
    # These variables cause subprocesses to be interpreted as new AppImage launches
    for key in ['APPIMAGE', 'APPDIR', 'ARGV0', 'OWD']:
        env.pop(key, None)

    # Remove bundle-specific variables
    for k in list(env):
        if k.startswith('_MEIPASS'):
            del env[k]
    
    # Get current PATH - ensure we preserve system paths
    current_path = env.get('PATH', '')
    
    # Ensure common system directories are in PATH if not already present
    # This is critical for tools like lz4 that might be in /usr/bin, /usr/local/bin, etc.
    system_paths = ['/usr/bin', '/usr/local/bin', '/bin', '/sbin', '/usr/sbin']
    path_parts = current_path.split(':') if current_path else []
    for sys_path in system_paths:
        if sys_path not in path_parts and os.path.isdir(sys_path):
            path_parts.append(sys_path)
    
    # Add bundled tools directory to PATH if running as AppImage
    # This ensures lz4, unzip, xz, etc. are available to subprocesses
    appdir = env.get('APPDIR')
    tools_dir = None
    
    if appdir:
        # Running as AppImage - use APPDIR
        tools_dir = os.path.join(appdir, 'opt', 'jackify', 'tools')
        # Verify the tools directory exists and contains lz4
        if not os.path.isdir(tools_dir):
            tools_dir = None
        elif not os.path.exists(os.path.join(tools_dir, 'lz4')):
            # Tools dir exists but lz4 not there - might be a different layout
            tools_dir = None
    elif getattr(sys, 'frozen', False):
        # PyInstaller frozen - try to find tools relative to executable
        exe_path = Path(sys.executable)
        # In PyInstaller, sys.executable is the bundled executable
        # Tools should be in the same directory or a tools subdirectory
        possible_tools_dirs = [
            exe_path.parent / 'tools',
            exe_path.parent / 'opt' / 'jackify' / 'tools',
        ]
        for possible_dir in possible_tools_dirs:
            if possible_dir.is_dir() and (possible_dir / 'lz4').exists():
                tools_dir = str(possible_dir)
                break
    
    # Build final PATH: bundled tools first (if any), then original PATH with system paths
    final_path_parts = []
    if tools_dir and os.path.isdir(tools_dir):
        # Prepend tools directory so bundled tools take precedence
        # This is critical - bundled lz4 must come before system lz4
        final_path_parts.append(tools_dir)
    
    # Add all other paths (preserving order, removing duplicates)
    # Note: AppRun already sets PATH with tools directory, but we ensure it's first
    seen = set()
    if tools_dir:
        seen.add(tools_dir)  # Already added, don't add again
    for path_part in path_parts:
        if path_part and path_part not in seen:
            final_path_parts.append(path_part)
            seen.add(path_part)
    
    env['PATH'] = ':'.join(final_path_parts)
    
    # Optionally restore LD_LIBRARY_PATH to system default if needed
    # (You can add more logic here if you know your system's default)
    if extra_env:
        env.update(extra_env)
    return env

def increase_file_descriptor_limit(target_limit=1048576):
    """
    Temporarily increase the file descriptor limit for the current process.
    
    Args:
        target_limit (int): Desired file descriptor limit (default: 1048576)
        
    Returns:
        tuple: (success: bool, old_limit: int, new_limit: int, message: str)
    """
    try:
        # Get current soft and hard limits
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        
        # Don't decrease the limit if it's already higher
        if soft_limit >= target_limit:
            return True, soft_limit, soft_limit, f"Current limit ({soft_limit}) already sufficient"
        
        # Set new limit (can't exceed hard limit)
        new_limit = min(target_limit, hard_limit)
        resource.setrlimit(resource.RLIMIT_NOFILE, (new_limit, hard_limit))
        
        return True, soft_limit, new_limit, f"Increased file descriptor limit from {soft_limit} to {new_limit}"
        
    except (OSError, ValueError) as e:
        # Get current limit for reporting
        try:
            soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        except:
            soft_limit = "unknown"
        
        return False, soft_limit, soft_limit, f"Failed to increase file descriptor limit: {e}"

class ProcessManager:
    """
    Shared process manager for robust subprocess launching, tracking, and cancellation.
    """
    def __init__(self, cmd, env=None, cwd=None, text=False, bufsize=0):
        self.cmd = cmd
        # Default to cleaned environment if None to prevent AppImage variable inheritance
        if env is None:
            self.env = get_clean_subprocess_env()
        else:
            self.env = env
        self.cwd = cwd
        self.text = text
        self.bufsize = bufsize
        self.proc = None
        self.process_group_pid = None
        self._start_process()

    def _start_process(self):
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self.env,
            cwd=self.cwd,
            text=self.text,
            bufsize=self.bufsize,
            start_new_session=True
        )
        self.process_group_pid = os.getpgid(self.proc.pid)

    def cancel(self, timeout_terminate=2, timeout_kill=1, max_cleanup_attempts=3):
        """
        Attempt to robustly terminate the process and its children.
        """
        cleanup_attempts = 0
        if self.proc:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=timeout_terminate)
                    return
                except subprocess.TimeoutExpired:
                    pass
            except Exception:
                pass
            try:
                self.proc.kill()
                try:
                    self.proc.wait(timeout=timeout_kill)
                    return
                except subprocess.TimeoutExpired:
                    pass
            except Exception:
                pass
            # Kill process group if possible
            if self.process_group_pid:
                try:
                    os.killpg(self.process_group_pid, signal.SIGKILL)
                except Exception:
                    pass
            # Last resort: pkill by command name
            while cleanup_attempts < max_cleanup_attempts:
                try:
                    subprocess.run(['pkill', '-f', os.path.basename(self.cmd[0])], timeout=5, capture_output=True)
                except Exception:
                    pass
                cleanup_attempts += 1

    def is_running(self):
        return self.proc and self.proc.poll() is None

    def wait(self, timeout=None):
        if self.proc:
            return self.proc.wait(timeout=timeout)
        return None

    def read_stdout_line(self):
        if self.proc and self.proc.stdout:
            return self.proc.stdout.readline()
        return None

    def read_stdout_char(self):
        if self.proc and self.proc.stdout:
            return self.proc.stdout.read(1)
        return None 