#!/usr/bin/env python3
"""
Tweak injection and modification functions.

This module handles the injection of tweaks, frameworks, and dynamic libraries
into iOS applications during the signing process.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict
from .utils import (
    safe_glob, extract_zip, extract_tar, move_merge_replace, 
    get_binary_map, get_otool_imports, install_name_change, 
    insert_dylib, plist_load, get_info_plist_path, get_main_app_path
)


def extract_deb(app_bin_name: str, app_bundle_id: str, archive: Path, dest_dir: Path):
    """Extract .deb package and filter relevant files for the target app."""
    from .utils import run_process, extract_tar
    
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        run_process("ar", "x", str(archive.resolve()), cwd=str(temp_dir))
        with tempfile.TemporaryDirectory() as temp_dir2_str:
            temp_dir2 = Path(temp_dir2_str)
            extract_tar(next(safe_glob(temp_dir, "data.tar*")), temp_dir2)

            for file in safe_glob(temp_dir2, "**/*"):
                if file.is_symlink():
                    target = file.resolve()
                    if target.is_absolute():
                        target = temp_dir2.joinpath(str(target)[1:])
                        os.unlink(file)
                        if target.is_dir():
                            shutil.copytree(target, file)
                        else:
                            shutil.copy2(target, file)

            rootless_dir = temp_dir2 / "var" / "jb"
            if rootless_dir.is_dir():
                temp_dir2 = rootless_dir

            for glob in [
                "Library/Application Support/*/*.bundle",
                "Library/Application Support/*",  # *.bundle, background@2x.png
                "Library/Frameworks/*.framework",
                "usr/lib/*.framework",
            ]:
                for file in safe_glob(temp_dir2, glob):
                    # skip empty directories
                    if file.is_dir() and next(safe_glob(file, "*"), None) is None:
                        continue
                    move_merge_replace(file, dest_dir)
            for glob in [
                "Library/MobileSubstrate/DynamicLibraries/*.dylib",
                "usr/lib/*.dylib",
            ]:
                for file in safe_glob(temp_dir2, glob):
                    if not file.is_file():
                        continue
                    file_plist = file.parent.joinpath(file.stem + ".plist")
                    if file_plist.exists():
                        info = plist_load(file_plist)
                        if "Filter" in info:
                            ok = False
                            if "Bundles" in info["Filter"] and app_bundle_id in info["Filter"]["Bundles"]:
                                ok = True
                            elif "Executables" in info["Filter"] and app_bin_name in info["Filter"]["Executables"]:
                                ok = True
                            if not ok:
                                continue
                    move_merge_replace(file, dest_dir)


def inject_tweaks(ipa_dir: Path, tweaks_dir: Path):
    """Inject tweaks, frameworks, and dynamic libraries into the app."""
    main_app = get_main_app_path(ipa_dir)
    main_info_plist = get_info_plist_path(main_app)
    info = plist_load(main_info_plist)
    app_bundle_id = info["CFBundleIdentifier"]
    app_bundle_exe = info["CFBundleExecutable"]
    is_mac_app = main_info_plist.parent.name == "Contents"

    if is_mac_app:
        base_dir = main_info_plist.parent
        app_bin = base_dir.joinpath("MacOS", app_bundle_exe)
        base_load_path = Path("@executable_path").joinpath("..")
    else:
        base_dir = main_app
        app_bin = base_dir.joinpath(app_bundle_exe)
        base_load_path = Path("@executable_path")

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        for tweak in safe_glob(tweaks_dir, "*"):
            print("Processing", tweak.name)
            if tweak.suffix == ".zip":
                extract_zip(tweak, temp_dir)
            elif tweak.suffix == ".tar":
                extract_tar(tweak, temp_dir)
            elif tweak.suffix == ".deb":
                extract_deb(app_bin.name, app_bundle_id, tweak, temp_dir)
            else:
                move_merge_replace(tweak, temp_dir)

        # move files if we know where they need to go
        move_map = {"Frameworks": ["*.framework", "*.dylib"], "PlugIns": ["*.appex"]}
        for dest_dir, globs in move_map.items():
            for glob in globs:
                for file in safe_glob(temp_dir, glob):
                    move_merge_replace(file, temp_dir.joinpath(dest_dir))

        # NOTE: https://iphonedev.wiki/index.php/Cydia_Substrate
        # hooking with "MSHookFunction" does not work in a jailed environment using any of the libs
        # libsubstrate will silently fail and continue, while the rest will crash the app
        # if you're a tweak developer, use fishhook instead, though it only works on public symbols
        support_libs = {
            # Path("./libhooker"): ["libhooker.dylib", "libblackjack.dylib"],
            # Path("./libsubstitute"): ["libsubstitute.dylib", "libsubstitute.0.dylib"],
            Path("./libsubstrate"): ["libsubstrate.dylib", "CydiaSubstrate"],
        }
        aliases = {
            "libsubstitute.0.dylib": "libsubstitute.dylib",
            "CydiaSubstrate": "libsubstrate.dylib",
        }

        binary_map = get_binary_map(temp_dir)

        # inject any user libs
        for binary_path in binary_map.values():
            binary_rel = binary_path.relative_to(temp_dir)
            if (len(binary_rel.parts) == 2 and binary_rel.parent.name == "Frameworks") or (
                len(binary_rel.parts) == 3
                and binary_rel.parent.suffix == ".framework"
                and binary_rel.parent.parent.name == "Frameworks"
            ):
                binary_fixed = base_load_path.joinpath(binary_rel)
                print("Injecting", binary_path, binary_fixed)
                insert_dylib(app_bin, binary_fixed, False)

        # detect any references to support libs and install missing files
        for binary_path in binary_map.values():
            for link in get_otool_imports(binary_path):
                link_path = Path(link)
                for lib_dir, lib_names in support_libs.items():
                    if link_path.name not in lib_names:
                        continue
                    print("Detected", lib_dir.name)
                    for lib_src in safe_glob(lib_dir, "*"):
                        lib_dest = temp_dir.joinpath("Frameworks").joinpath(lib_src.name)
                        if not lib_dest.exists():
                            print(f"Installing {lib_src.name} to {lib_dest}")
                            lib_dest.parent.mkdir(exist_ok=True, parents=True)
                            shutil.copy2(lib_src, lib_dest)

        # refresh the binary map with any new libs from previous step
        binary_map = get_binary_map(temp_dir)

        # re-link any dependencies
        for binary_path in binary_map.values():
            for link in get_otool_imports(binary_path):
                link_path = Path(link)
                link_name = aliases[link_path.name] if link_path.name in aliases else link_path.name
                if link_name in binary_map:
                    link_fixed = base_load_path.joinpath(binary_map[link_name].relative_to(temp_dir))
                    print("Re-linking", binary_path, link_path, link_fixed)
                    install_name_change(binary_path, link_path, link_fixed, False)

        for file in safe_glob(temp_dir, "*"):
            move_merge_replace(file, base_dir)
