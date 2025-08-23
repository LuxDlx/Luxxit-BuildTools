# patching.py

import os
import sys
import subprocess
from pathlib import Path
import shutil
import stat
def on_rm_error(func, path, exc_info):
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise

def check_git():
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def create_patch(original_dir, modified_dir, patch_file):
    """
    Create a unified diff patch between original_dir and modified_dir.
    Uses git if available (works on Windows), otherwise falls back to diff (Unix).
    """
    original_dir = Path(original_dir).resolve()
    modified_dir = Path(modified_dir).resolve()
    patch_file = Path(patch_file).resolve()

    print(f"Creating patch file {patch_file} ...")

    if check_git():
        # Use git diff for cross-platform compatibility
        temp_git = original_dir.parent / ".temp_patch_git"
        if temp_git.exists():
            shutil.rmtree(temp_git, onerror=on_rm_error)  # Ignore errors during cleanup
        shutil.copytree(original_dir, temp_git)
        try:
            subprocess.run(["git", "init"], cwd=temp_git, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run(["git", "add", "."], cwd=temp_git, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run(["git", "commit", "-m", "original"], cwd=temp_git, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            # Copy modified files over
            for root, dirs, files in os.walk(modified_dir):
                for file in files:
                    src = Path(root) / file
                    rel = src.relative_to(modified_dir)
                    dst = temp_git / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            subprocess.run(["git", "add", "."], cwd=temp_git, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            with open(patch_file, "w", encoding="utf-8") as f:
                subprocess.run(["git", "diff", "--cached"], cwd=temp_git, stdout=f, check=True)
            print(f"Patch created: {patch_file}")
        finally:
            shutil.rmtree(temp_git, onerror=on_rm_error)  # Ignore errors during cleanup
    else:
        # Use system diff for Unix
        cmd = [
            "diff", "-ruN",
            str(original_dir),
            str(modified_dir)
        ]
        try:
            with open(patch_file, "w", encoding="utf-8") as f:
                subprocess.run(cmd, stdout=f, check=True)
            print(f"Patch created: {patch_file}")
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                print(f"Patch created: {patch_file}")
            else:
                print("Error running diff:", e)
                sys.exit(1)
        except FileNotFoundError:
            print("The 'diff' command is required on Unix if git is not available.")
            sys.exit(1)

def apply_patch(target_dir, patch_file):
    """
    Apply a unified diff patch to target_dir.
    Uses git if available (works on Windows), otherwise falls back to patch (Unix).
    """
    target_dir = Path(target_dir).resolve()
    patch_file = Path(patch_file).resolve()

    print(f"Applying patch {patch_file} to {target_dir} ...")

    if check_git():
        # Use git apply for cross-platform compatibility
        try:
            subprocess.run(["git", "init"], cwd=target_dir, check=True)
            subprocess.run(["git", "add", "."], cwd=target_dir, check=True)
            subprocess.run(["git", "apply", "--ignore-space-change", "--ignore-whitespace", str(patch_file)], cwd=target_dir, check=True)
            print("Patch applied successfully!")
        except subprocess.CalledProcessError as e:
            print("Error applying patch with git:", e)
            sys.exit(1)
    else:
        # Use system patch for Unix
        cmd = [
            "patch", "-p1", "-d", str(target_dir), "-i", str(patch_file)
        ]
        try:
            subprocess.run(cmd, check=True)
            print("Patch applied successfully!")
        except FileNotFoundError:
            print("The 'patch' command is required on Unix if git is not available.")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print("Error applying patch:", e)
            sys.exit(1)

def usage():
    print("Usage:")
    print("  python patching.py create <original_dir> <modified_dir> <patch_file>")
    print("  python patching.py apply <target_dir> <patch_file>")
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
    action = sys.argv[1]
    if action == "create" and len(sys.argv) == 5:
        _, _, original_dir, modified_dir, patch_file = sys.argv
        create_patch(original_dir, modified_dir, patch_file)
    elif action == "apply" and len(sys.argv) == 4:
        _, _, target_dir, patch_file = sys.argv
        apply_patch(target_dir, patch_file)
    else:
        usage()
