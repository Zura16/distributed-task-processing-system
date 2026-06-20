#!/usr/bin/env python3
import os
import sys
import subprocess
import math

def run_command(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command {' '.join(args)}:\n{result.stderr}", file=sys.stderr)
        return None
    return result.stdout.strip()

def main():
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(repo_dir)

    print(f"[*] Running progressive git push inside: {repo_dir}")

    if not os.path.exists(".git"):
        print("[!] Error: Not a git repository.", file=sys.stderr)
        sys.exit(1)

    status_output = run_command(["git", "status", "--porcelain"])
    if status_output is None:
        sys.exit(1)

    if not status_output:
        print("[*] No modified or untracked files found. Nothing to commit.")
        sys.exit(0)

    files = []
    for line in status_output.split("\n"):
        if not line:
            continue
        path = line[3:].strip()
        # Clean up surrounding quotes and trailing slashes
        path = path.strip('"').rstrip('/')
        # Skip submodules/nested git repositories
        if os.path.isdir(path) and os.path.exists(os.path.join(path, ".git")):
            continue
        files.append(path)

    total_files = len(files)
    files_to_commit_count = math.ceil(total_files * 0.2)
    files_to_commit = files[:files_to_commit_count]

    print(f"[*] Found {total_files} modified/untracked file(s).")
    print(f"[*] Progressive target (20%): committing {files_to_commit_count} file(s).")
    
    for file_path in files_to_commit:
        print(f"    [+] Adding {file_path}")
        run_command(["git", "add", file_path])

    file_basenames = [os.path.basename(f) for f in files_to_commit]
    commit_msg = f"Progressive commit: {', '.join(file_basenames)}"
    if len(commit_msg) > 70:
        commit_msg = f"Progressive commit of {files_to_commit_count} file(s)"

    print(f"[*] Committing with message: '{commit_msg}'")
    commit_result = run_command(["git", "commit", "-m", commit_msg])
    if commit_result is None:
        print("[!] Commit failed.")
        sys.exit(1)

    print("[*] Pushing to remote repository...")
    push_result = run_command(["git", "push", "origin", "main"])
    if push_result is None:
        print("[!] Push failed.")
        sys.exit(1)

    print("[*] Progressive push complete! Remaining modified files:")
    for remaining in files[files_to_commit_count:]:
        print(f"    [-] {remaining}")

if __name__ == "__main__":
    main()
