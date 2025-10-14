"""
gittools.py

Description: Repository Management Utilities like cloning and keeping local copies up to date

1. Clones repos in a cache folder repos_cache/
2. Updates existing clones by fetching all remote changes 
3. Performs fast forward oulls without creating new commits

"""
import subprocess
from pathlib import Path
from constants import CACHE_DIR

#################### Helper Function for cloning the git repository ####################

def git_clone_or_update(url: str) -> Path:
    name = url.rstrip("/").split("/")[-1].replace(".git","")
    dest = CACHE_DIR / name
    if dest.exists():
        try:
            #for cleaning outdated branches
            subprocess.run(["git", "-C", str(dest), "fetch", "--all", "--prune"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            #update branch only if it can be fast forwarded without creating new commits
            subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"Warning: fetch/pull failed for {name}: {e}")
    else:
        subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
    return dest
