#!/usr/bin/env python3
"""
Utility functions for file operations, process execution, and data manipulation.

This module contains helper functions that are used throughout the signing process,
including file operations, process execution, and data conversion utilities.
"""

import os
import re
import sys
import subprocess
import tempfile
import json
import random
import string
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Mapping, Union
import plistlib

StrPath = Union[str, Path]


def safe_glob(input: Path, pattern: str):
    """Safely iterate through files matching a pattern, excluding system files."""
    for f in sorted(input.glob(pattern)):
        if not f.name.startswith("._") and f.name not in [".DS_Store", ".AppleDouble", "__MACOSX"]:
            yield f


def decode_clean(b: bytes):
    """Decode bytes to clean UTF-8 string."""
    return "" if not b else b.decode("utf-8").strip()


def run_process(
    *cmd: str,
    capture: bool = True,
    check: bool = True,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
):
    """Run a subprocess with error handling."""
    try:
        result = subprocess.run(cmd, capture_output=capture, check=check, env=env, cwd=cwd, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise (
            Exception(
                {
                    "stdout": decode_clean(e.stdout),
                    "stderr": decode_clean(e.stderr),
                }
            )
        ) from e
    return result


def run_process_async(
    *cmd: str,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
):
    """Run a subprocess asynchronously."""
    return subprocess.Popen(cmd, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def rand_str(len: int, seed: Any = None):
    """Generate a random string of specified length."""
    old_state: object = None
    if seed is not None:
        old_state = random.getstate()
        random.seed(seed)
    result = "".join(random.choices(string.ascii_lowercase + string.digits, k=len))
    if old_state is not None:
        random.setstate(old_state)
    return result


def read_file(file_path: StrPath):
    """Read text file content."""
    with open(file_path) as f:
        return f.read()


def extract_zip(archive: Path, dest_dir: Path):
    """Extract a ZIP archive to destination directory."""
    return run_process("unzip", "-o", str(archive), "-d", str(dest_dir))


def archive_zip(content_dir: Path, dest_file: Path):
    """Create a ZIP archive from directory contents."""
    return run_process("zip", "-r", str(dest_file.resolve()), ".", cwd=str(content_dir))


def extract_tar(archive: Path, dest_dir: Path):
    """Extract a TAR archive to destination directory."""
    return run_process("tar", "-x", "-f", str(archive), "-C" + str(dest_dir))


def print_object(obj: Any):
    """Pretty print an object as JSON."""
    print(json.dumps(obj, indent=4, sort_keys=True, default=str))


def plutil_convert(plist: Path):
    """Convert plist to XML format using plutil."""
    return run_process("plutil", "-convert", "xml1", "-o", "-", str(plist), capture=True).stdout


def plist_load(plist: Path):
    """Load a plist file."""
    return plistlib.loads(plutil_convert(plist))


def plist_loads(plist: str) -> Any:
    """Load plist from string."""
    with tempfile.NamedTemporaryFile(suffix=".plist", mode="w") as f:
        f.write(plist)
        f.flush()
        return plist_load(Path(f.name))


def plist_dump(data: Any, f):
    """Dump data to plist format."""
    return plistlib.dump(data, f)


def file_is_type(file: Path, type: str):
    """Check if file is of specified type using the 'file' command."""
    return type in decode_clean(run_process("file", str(file)).stdout)


def get_otool_imports(binary: Path):
    """Get library imports from a binary using otool."""
    output = decode_clean(run_process("otool", "-L", str(binary)).stdout).splitlines()[1:]
    matches = [re.search(r"(.+)\s\(.+\)", line.strip()) for line in output]
    results = [match.group(1) for match in matches if match]
    if len(output) != len(results):
        raise Exception("Failed to parse imports", {"output": output, "parsed": results})
    return results


def install_name_change(binary: Path, old: Path, new: Path, capture: bool = True):
    """Change install name in binary using install_name_tool."""
    return run_process("install_name_tool", "-change", str(old), str(new), str(binary), capture=capture)


def insert_dylib(binary: Path, path: Path, capture: bool = True):
    """Insert dylib into binary using insert_dylib tool."""
    return run_process(
        "./insert_dylib", "--inplace", "--no-strip-codesig", "--all-yes", str(path), str(binary), capture=capture
    )


def get_binary_map(dir: Path):
    """Get a mapping of binary names to their paths in a directory."""
    return {file.name: file for file in safe_glob(dir, "**/*") if file_is_type(file, "Mach-O")}


def clean_dev_portal_name(name: str):
    """Clean a name for use in Apple Developer Portal."""
    return re.sub("[^0-9a-zA-Z]+", " ", name).strip()


def binary_replace(pattern: str, f: Path):
    """Replace patterns in binary file using perl."""
    if not f.exists() or not f.is_file():
        raise Exception(f, "does not exist or is a directory")
    return run_process("perl", "-p", "-i", "-e", pattern, str(f))


def move_merge_replace(src: Path, dest_dir: Path):
    """Move and merge source to destination directory."""
    dest = dest_dir.joinpath(src.name)
    if src == dest:
        return
    dest_dir.mkdir(exist_ok=True, parents=True)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
        shutil.rmtree(src)
    else:
        shutil.copy2(src, dest)
        os.remove(src)


def popen_check(pipe: subprocess.Popen):
    """Check if a subprocess completed successfully."""
    if pipe.returncode != 0:
        data = {"message": f"{pipe.args} failed with status code {pipe.returncode}"}
        if pipe.stdout:
            data["stdout"] = decode_clean(pipe.stdout.read())
        if pipe.stderr:
            data["stderr"] = decode_clean(pipe.stderr.read())
        raise Exception(data)


def get_info_plist_path(app_dir: Path):
    """Get the Info.plist path for an app directory."""
    return min(list(safe_glob(app_dir, "**/Info.plist")), key=lambda p: len(str(p)))

# get to know if this app is iOS app, apple watch app, apple tv app, etc.
def get_app_type(app_dir: Path):
    """
    Determine the app type from the app directory by analyzing the Info.plist file.
    
    This function examines the app bundle structure and Info.plist contents to identify
    whether the app is for iOS, watchOS, tvOS, macOS, or other Apple platforms.
    
    Args:
        app_dir (Path): Path to the app directory (usually extracted from IPA)
        
    Returns:
        str: App type - one of: "ios", "watchos", "tvos", "macos", "catalyst", "unknown"
        
    Detection Logic:
    - macOS: Info.plist parent directory is named "Contents" (standard macOS bundle structure)
    - watchOS: UIDeviceFamily contains 4 or CFBundleSupportedPlatforms contains "WatchOS"
    - tvOS: UIDeviceFamily contains 3 or CFBundleSupportedPlatforms contains "AppleTVOS"
    - Mac Catalyst: CFBundleSupportedPlatforms contains "MacOSX" but UIDeviceFamily indicates iOS
    - iOS: Default fallback for mobile apps (UIDeviceFamily 1 or 2, or no specific platform)
    """
    try:
        # Get the main app path and Info.plist
        main_app = get_main_app_path(app_dir)
        info_plist_path = get_info_plist_path(main_app)
        
        # Check for macOS app structure first (most distinctive)
        if info_plist_path.parent.name == "Contents":
            return "macos"
        
        # Load and analyze Info.plist
        info = plist_load(info_plist_path)
        
        # Check CFBundleSupportedPlatforms (most reliable when present)
        supported_platforms = info.get("CFBundleSupportedPlatforms", [])
        if supported_platforms:
            # Convert to lowercase for case-insensitive comparison
            platforms_lower = [p.lower() for p in supported_platforms]
            
            if "watchos" in platforms_lower:
                return "watchos"
            elif "appletvos" in platforms_lower:
                return "tvos"
            elif "macosx" in platforms_lower:
                # Could be macOS or Mac Catalyst
                device_family = info.get("UIDeviceFamily", [])
                if device_family and any(family in [1, 2] for family in device_family):
                    return "catalyst"  # Mac Catalyst (iOS app running on macOS)
                else:
                    return "macos"
        
        # Check UIDeviceFamily for platform detection
        device_family = info.get("UIDeviceFamily", [])
        if device_family:
            # UIDeviceFamily values:
            # 1 = iPhone, 2 = iPad, 3 = Apple TV, 4 = Apple Watch
            if 4 in device_family:
                return "watchos"
            elif 3 in device_family:
                return "tvos"
            elif any(family in [1, 2] for family in device_family):
                return "ios"
        
        # Check for watchOS-specific keys
        if any(key in info for key in ["WKApplication", "WKCompanionAppBundleIdentifier"]):
            return "watchos"
        
        # Check for tvOS-specific keys
        if any(key in info for key in ["TVTopShelfImage", "TVTopShelfProvider"]):
            return "tvos"
        
        # Check bundle identifier patterns (some apps use platform-specific naming)
        bundle_id = info.get("CFBundleIdentifier", "")
        if ".watchkitapp" in bundle_id.lower() or ".watchkitextension" in bundle_id.lower():
            return "watchos"
        
        # Default to iOS for mobile apps
        return "ios"
        
    except Exception as e:
        print(f"Warning: Could not determine app type from {app_dir}: {e}")
        # Fallback to iOS as it's the most common case
        return "ios"

def get_main_app_path(app_dir: Path):
    """Get the main .app path in a directory."""
    return min(list(safe_glob(app_dir, "**/*.app")), key=lambda p: len(str(p)))

def get_or_create_bundle_id(job_id: str, app_type: str) -> str:
    """Get existing bundle ID mapping or create new one for account."""
    from .webhooks import get_bundle_id_mapping
    
    # First try to get existing mapping
    new_bundle_id = get_bundle_id_mapping(job_id, app_type)
    
    return new_bundle_id

def get_extension_suffix(extension_type: str) -> str:
    """Get appropriate suffix for extension type."""
    extension_suffixes = {
        "today_extension": "widget",
        "share_extension": "share",
        "action_extension": "action", 
        "photo_extension": "photo",
        "keyboard_extension": "keyboard",
        "notification_extension": "notification",
        "app_extension": "extension"
    }
    return extension_suffixes.get(extension_type, "extension")
