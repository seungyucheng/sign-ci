#!/usr/bin/env python3
"""
Security and keychain management functions.

This module handles all security-related operations including keychain management,
certificate importing, and provisioning profile operations.
"""

import re
from pathlib import Path
from typing import List, Dict, Any
from .utils import run_process, decode_clean, plist_loads

def security_get_keychain_list():
    """Get list of user keychains."""
    return map(
        lambda x: x.strip('"'),
        decode_clean(run_process("security", "list-keychains", "-d", "user").stdout).split(),
    )


def security_remove_keychain(keychain: str):
    """Remove a keychain from the system."""
    keychains = security_get_keychain_list()
    keychains = filter(lambda x: keychain not in x, keychains)
    run_process("security", "list-keychains", "-d", "user", "-s", *keychains)
    run_process("security", "delete-keychain", keychain)


def security_import(cert: str, cert_pass: str, keychain: str) -> List[str]:
    """Import certificate into keychain and return identity names."""
    import os

    # make the cert pass and keychain pass the same
    password = cert_pass

    # Create keychain with full path: ~/Library/Keychains/build.keychain-db
    # This is like creating a secure storage box in the right location
    home_dir = os.path.expanduser("~")
    created_keychain = f"{home_dir}/Library/Keychains/{keychain}"

    try:
        run_process("security", "delete-keychain", created_keychain)
    except Exception as e:
        print(f"Error deleting keychain: {e}")

    keychains = [*security_get_keychain_list(), created_keychain]
    run_process("security", "create-keychain", "-p", password, created_keychain)
    run_process("security", "unlock-keychain", "-p", password, created_keychain)
    run_process("security", "set-keychain-settings", created_keychain)
    run_process("security", "list-keychains", "-d", "user", "-s", *keychains)
    run_process("security", "import", cert, "-P", cert_pass, "-A", "-k", created_keychain, "-f", "pkcs12")

    # Set key partition list - IMPORTANT: use created_keychain, not keychain
    run_process(
        "security",
        *["set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-s", "-k"],
        password,
        created_keychain,
    )

    identity: str = decode_clean(run_process("security", "find-identity", "-p", "appleID", "-v", created_keychain).stdout)
    return [line.strip('"') for line in re.findall('".*"', identity)]


def security_dump_prov(f: Path):
    """Dump provisioning profile using security command."""
    return decode_clean(run_process("security", "cms", "-D", "-i", str(f)).stdout)


def dump_prov(prov_file: Path) -> Dict[Any, Any]:
    """Parse provisioning profile and return as dictionary."""
    s = security_dump_prov(prov_file)
    return plist_loads(s)


def dump_prov_entitlements(prov_file: Path) -> Dict[Any, Any]:
    """Extract entitlements from provisioning profile."""
    return dump_prov(prov_file)["Entitlements"]


def codesign_async(identity: str, component: Path, entitlements: Path = None):
    """Start codesign process asynchronously."""
    from .utils import run_process_async

    cmd = ["codesign", "--continue", "-f", "--no-strict", "-s", identity]
    if entitlements:
        cmd.extend(["--entitlements", str(entitlements)])
    return run_process_async(*cmd, str(component))


def codesign_dump_entitlements(component: Path) -> Dict[Any, Any]:
    """Dump entitlements from signed component."""
    entitlements_str = decode_clean(
        run_process("codesign", "--no-strict", "-d", "--entitlements", "-", "--xml", str(component)).stdout
    )
    return plist_loads(entitlements_str)
