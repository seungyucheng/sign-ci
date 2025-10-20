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


def get_main_app_path(app_dir: Path):
    """Get the main .app path in a directory."""
    return min(list(safe_glob(app_dir, "**/*.app")), key=lambda p: len(str(p)))


def generate_bundle_id_from_email(email: str) -> str:
    """Generate bundle ID in format com.hs.xx where xx is derived from email."""
    import hashlib
    # Extract username part before @ and create a short hash
    username = email.split('@')[0] if '@' in email else email
    # Create a short hash from the username
    hash_obj = hashlib.md5(username.encode())
    short_hash = hash_obj.hexdigest()[:6]  # Take first 6 characters
    return f"com.hs.{short_hash}"


def get_or_create_bundle_id(account_id: str, original_bundle_id: str, email: str) -> str:
    """Get existing bundle ID mapping or create new one for account."""
    from .webhooks import get_bundle_id_mapping, store_bundle_id_mapping
    
    # First try to get existing mapping
    existing_mapping = get_bundle_id_mapping(account_id, original_bundle_id)
    if existing_mapping:
        print(f"Reusing existing bundle ID mapping: {original_bundle_id} -> {existing_mapping}")
        return existing_mapping
    
    # Generate new bundle ID based on email
    new_bundle_id = generate_bundle_id_from_email(email)
    
    # Store the mapping for future reuse
    store_bundle_id_mapping(account_id, original_bundle_id, new_bundle_id, "main")
    
    print(f"Created new bundle ID mapping: {original_bundle_id} -> {new_bundle_id}")
    return new_bundle_id


def get_or_create_extension_bundle_id(account_id: str, main_bundle_id: str, original_extension_id: str, extension_type: str) -> str:
    """Get or create bundle ID for app extension."""
    from .webhooks import get_bundle_id_mapping, store_bundle_id_mapping, store_app_extension
    
    # Check if we already have a mapping for this extension
    existing_mapping = get_bundle_id_mapping(account_id, original_extension_id)
    if existing_mapping:
        print(f"Reusing existing extension bundle ID: {original_extension_id} -> {existing_mapping}")
        return existing_mapping
    
    # Generate extension bundle ID based on main app bundle ID
    # Format: main.bundle.id.extension-type
    extension_suffix = get_extension_suffix(extension_type)
    new_extension_id = f"{main_bundle_id}.{extension_suffix}"
    
    # Store mappings
    store_bundle_id_mapping(account_id, original_extension_id, new_extension_id, "extension")
    store_app_extension(account_id, main_bundle_id, new_extension_id, extension_type)
    
    print(f"Created new extension bundle ID: {original_extension_id} -> {new_extension_id}")
    return new_extension_id


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


def create_bundle_id_mapping_for_components(account_id: str, email: str, app_analysis: Dict[str, Any]) -> Dict[str, str]:
    """Create bundle ID mappings for all app components."""
    mappings = {}
    
    # Handle main app
    main_app = app_analysis.get("main_app", {})
    original_main_id = main_app.get("bundle_id", "")
    if original_main_id:
        new_main_id = get_or_create_bundle_id(account_id, original_main_id, email)
        mappings[original_main_id] = new_main_id
        
        # Handle extensions
        extensions = app_analysis.get("extensions", [])
        for extension in extensions:
            original_ext_id = extension.get("bundle_id", "")
            extension_type = extension.get("type", "app_extension")
            
            if original_ext_id:
                new_ext_id = get_or_create_extension_bundle_id(
                    account_id, new_main_id, original_ext_id, extension_type
                )
                mappings[original_ext_id] = new_ext_id
        
        # Handle other components (frameworks, etc.)
        components = app_analysis.get("components", [])
        for component in components:
            if component.get("type") != "framework":  # Skip frameworks, they don't need bundle IDs
                original_comp_id = component.get("bundle_id", "")
                comp_type = component.get("type", "unknown")
                
                if original_comp_id and original_comp_id not in mappings:
                    if comp_type.endswith("_extension"):
                        new_comp_id = get_or_create_extension_bundle_id(
                            account_id, new_main_id, original_comp_id, comp_type
                        )
                    else:
                        # For other component types, use similar logic to main app
                        new_comp_id = get_or_create_bundle_id(account_id, original_comp_id, email)
                    mappings[original_comp_id] = new_comp_id
    
    return mappings


def analyze_ipa_capabilities(app_dir: Path) -> Dict[str, Any]:
    """Analyze IPA to detect capabilities, extensions, and requirements."""
    analysis = {
        "main_app": {},
        "extensions": [],
        "capabilities": set(),
        "entitlements": {},
        "components": []
    }
    
    try:
        # Find main app
        main_app = get_main_app_path(app_dir)
        main_info_plist = get_info_plist_path(main_app)
        main_info = plist_load(main_info_plist)
        
        analysis["main_app"] = {
            "bundle_id": main_info.get("CFBundleIdentifier", ""),
            "name": main_info.get("CFBundleDisplayName", main_info.get("CFBundleName", "")),
            "version": main_info.get("CFBundleShortVersionString", ""),
            "path": main_app
        }
        
        # Find all components (apps, extensions, frameworks)
        component_patterns = ["**/*.app", "**/*.appex", "**/*.framework"]
        components = []
        
        for pattern in component_patterns:
            for component in safe_glob(app_dir, pattern):
                if component != main_app:  # Skip main app, we'll handle it separately
                    components.append(component)
        
        # Analyze each component
        for component in components:
            component_info = analyze_component_capabilities(component)
            if component_info:
                analysis["components"].append(component_info)
                
                # If it's an extension, add to extensions list
                if component.suffix == ".appex":
                    analysis["extensions"].append(component_info)
                
                # Collect all capabilities
                analysis["capabilities"].update(component_info.get("capabilities", []))
        
        # Analyze main app capabilities
        main_capabilities = analyze_component_capabilities(main_app)
        if main_capabilities:
            analysis["main_app"].update(main_capabilities)
            analysis["capabilities"].update(main_capabilities.get("capabilities", []))
            analysis["entitlements"] = main_capabilities.get("entitlements", {})
        
        # Convert set to list for JSON serialization
        analysis["capabilities"] = list(analysis["capabilities"])
        
    except Exception as e:
        print(f"Error analyzing IPA capabilities: {e}")
    
    return analysis


def analyze_component_capabilities(component_path: Path) -> Dict[str, Any]:
    """Analyze a single component (app/extension) for capabilities."""
    try:
        info_plist = get_info_plist_path(component_path)
        info = plist_load(info_plist)
        
        component_info = {
            "path": component_path,
            "bundle_id": info.get("CFBundleIdentifier", ""),
            "name": info.get("CFBundleDisplayName", info.get("CFBundleName", "")),
            "type": detect_component_type(component_path, info),
            "capabilities": [],
            "entitlements": {}
        }
        
        # Try to extract entitlements from the component
        try:
            from .security import codesign_dump_entitlements
            entitlements = codesign_dump_entitlements(component_path)
            component_info["entitlements"] = entitlements
            
            # Detect capabilities from entitlements
            capabilities = detect_capabilities_from_entitlements(entitlements)
            component_info["capabilities"] = capabilities
            
        except Exception as e:
            print(f"Could not extract entitlements from {component_path}: {e}")
            # Fallback to detecting from Info.plist
            component_info["capabilities"] = detect_capabilities_from_info_plist(info)
        
        return component_info
        
    except Exception as e:
        print(f"Error analyzing component {component_path}: {e}")
        return None


def detect_component_type(component_path: Path, info_plist: Dict[str, Any]) -> str:
    """Detect the type of component (main_app, extension, framework, etc.)."""
    if component_path.suffix == ".app":
        return "main_app"
    elif component_path.suffix == ".appex":
        # Detect extension type from Info.plist
        extension_point = info_plist.get("NSExtension", {}).get("NSExtensionPointIdentifier", "")
        if "widget" in extension_point or "today" in extension_point:
            return "today_extension"
        elif "share" in extension_point:
            return "share_extension"
        elif "action" in extension_point:
            return "action_extension"
        elif "photo" in extension_point:
            return "photo_extension"
        elif "keyboard" in extension_point:
            return "keyboard_extension"
        elif "notification" in extension_point:
            return "notification_extension"
        else:
            return "app_extension"
    elif component_path.suffix == ".framework":
        return "framework"
    else:
        return "unknown"


def detect_capabilities_from_entitlements(entitlements: Dict[str, Any]) -> List[str]:
    """Detect required capabilities from app entitlements."""
    capabilities = []
    
    # Map entitlements to capabilities
    entitlement_capability_map = {
        "aps-environment": "push_notifications",
        "com.apple.developer.aps-environment": "push_notifications",
        "com.apple.developer.healthkit": "healthkit",
        "com.apple.developer.healthkit.access": "healthkit",
        "com.apple.developer.homekit": "homekit",
        "com.apple.external-accessory.wireless-configuration": "wireless_accessory",
        "com.apple.security.application-groups": "app_groups",
        "inter-app-audio": "inter_app_audio",
        "keychain-access-groups": "keychain_sharing",
        "com.apple.developer.icloud-container-identifiers": "icloud",
        "com.apple.developer.icloud-services": "icloud",
        "com.apple.developer.ubiquity-container-identifiers": "icloud",
        "com.apple.developer.ubiquity-kvstore-identifier": "icloud",
        "com.apple.developer.networking.networkextension": "network_extensions",
        "com.apple.developer.networking.vpn.api": "personal_vpn",
        "com.apple.developer.networking.wifi-info": "wifi_info",
        "com.apple.developer.nfc.readersession.formats": "nfc_tag_reading",
        "com.apple.developer.siri": "sirikit",
        "com.apple.developer.associated-domains": "associated_domains",
        "com.apple.developer.networking.multipath": "multipath",
        "com.apple.developer.kernel.extended-virtual-addressing": "extended_virtual_addressing",
        # macOS specific
        "com.apple.security.app-sandbox": "app_sandbox",
        "com.apple.security.network.client": "network_client",
        "com.apple.security.network.server": "network_server",
        "com.apple.security.device.audio-input": "microphone",
        "com.apple.security.device.camera": "camera",
        "com.apple.security.files.user-selected.read-only": "file_access_read",
        "com.apple.security.files.user-selected.read-write": "file_access_write"
    }
    
    for entitlement, capability in entitlement_capability_map.items():
        if entitlement in entitlements:
            capabilities.append(capability)
    
    return list(set(capabilities))  # Remove duplicates


def detect_capabilities_from_info_plist(info_plist: Dict[str, Any]) -> List[str]:
    """Detect capabilities from Info.plist when entitlements are not available."""
    capabilities = []
    
    # Check for background modes
    background_modes = info_plist.get("UIBackgroundModes", [])
    if background_modes:
        if "background-fetch" in background_modes:
            capabilities.append("background_app_refresh")
        if "remote-notification" in background_modes:
            capabilities.append("push_notifications")
        if "background-audio" in background_modes:
            capabilities.append("background_audio")
        if "location" in background_modes:
            capabilities.append("location_services")
    
    # Check for URL schemes
    url_types = info_plist.get("CFBundleURLTypes", [])
    if url_types:
        capabilities.append("url_schemes")
    
    # Check for document types
    document_types = info_plist.get("CFBundleDocumentTypes", [])
    if document_types:
        capabilities.append("document_types")
    
    return capabilities


def get_master_capabilities_list() -> List[str]:
    """Get comprehensive list of all possible iOS/macOS capabilities."""
    return [
        # Core capabilities
        "push_notifications",
        "healthkit",
        "homekit", 
        "wireless_accessory",
        "app_groups",
        "inter_app_audio",
        "keychain_sharing",
        "icloud",
        "network_extensions",
        "personal_vpn",
        "wifi_info",
        "nfc_tag_reading",
        "sirikit",
        "associated_domains",
        "multipath",
        "extended_virtual_addressing",
        
        # Background capabilities
        "background_app_refresh",
        "background_audio",
        "location_services",
        
        # Data access
        "contacts",
        "calendar",
        "reminders",
        "photos",
        "microphone",
        "camera",
        "location",
        
        # macOS specific
        "app_sandbox",
        "network_client",
        "network_server",
        "file_access_read",
        "file_access_write",
        "usb_access",
        "bluetooth",
        
        # Extension types
        "today_extension",
        "share_extension",
        "action_extension",
        "photo_extension",
        "keyboard_extension",
        "notification_extension",
        
        # Document handling
        "url_schemes",
        "document_types",
        "file_sharing"
    ]
