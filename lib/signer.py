#!/usr/bin/env python3
"""
Main signing logic and Signer class.

This module contains the core signing functionality including the Signer class
that orchestrates the entire app signing process.
"""

import copy
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, NamedTuple, Set, Tuple, Any, Optional

from .utils import (
    safe_glob, plist_load, plist_dump, print_object, 
    get_info_plist_path, get_main_app_path, rand_str, binary_replace
)
from .security import codesign_async, codesign_dump_entitlements, dump_prov_entitlements
from .fastlane_integration import fastlane_auth, fastlane_register_app, fastlane_get_prov_profile
from .webhooks import report_progress


class SignOpts(NamedTuple):
    """Configuration options for the signing process."""
    app_dir: Path
    common_name: str
    team_id: str
    account_name: str
    account_pass: str
    prov_file: Optional[Path]
    bundle_id: Optional[str]
    bundle_name: Optional[str]
    patch_debug: bool
    patch_all_devices: bool
    patch_mac: bool
    patch_file_sharing: bool
    encode_ids: bool
    patch_ids: bool
    force_original_id: bool
    account_id: Optional[str] = None
    use_master_capabilities: bool = True


class RemapDef(NamedTuple):
    """Definition for remapping entitlement identifiers."""
    entitlements: List[str]
    prefix: str
    prefix_only: bool
    is_list: bool


class ComponentData(NamedTuple):
    """Data for a component being signed."""
    old_bundle_id: str
    bundle_id: str
    entitlements: Dict[Any, Any]
    info_plist: Path


class Signer:
    """Main class that handles the iOS app signing process."""
    
    def __init__(self, opts: SignOpts):
        """Initialize the signer with configuration options."""
        self.opts = opts
        main_app = get_main_app_path(opts.app_dir)
        main_info_plist = get_info_plist_path(main_app)
        main_info: Dict[Any, Any] = plist_load(main_info_plist)
        self.old_main_bundle_id = main_info["CFBundleIdentifier"]
        self.is_distribution = "Distribution" in opts.common_name
        self.is_mac_app = main_info_plist.parent.name == "Contents"

        if self.is_distribution and self.is_mac_app:
            raise Exception(
                "Cannot use distribution certificate for macOS as the platform does not support adhoc provisioning profiles."
            )

        self.mappings: Dict[str, str] = {}
        self.removed_entitlements = set()

        # Determine main bundle ID based on configuration
        self._determine_main_bundle_id()
        
        # Configure bundle name if specified
        if opts.bundle_name:
            print(f"Setting CFBundleDisplayName to {opts.bundle_name}")
            main_info["CFBundleDisplayName"] = opts.bundle_name

        # Apply device compatibility patches
        if self.opts.patch_all_devices:
            if self.is_mac_app:
                # https://developer.apple.com/documentation/bundleresources/information_property_list/lsminimumsystemversion
                main_info["LSMinimumSystemVersion"] = "10.0"
            else:
                # https://developer.apple.com/documentation/bundleresources/information_property_list/minimumosversion
                main_info["MinimumOSVersion"] = "3.0"

        # Write bundle ID to file for reference
        with open("bundle_id.txt", "w") as f:
            if opts.force_original_id:
                f.write(self.old_main_bundle_id)
            else:
                f.write(self.main_bundle_id)

        # Save modified Info.plist
        with main_info_plist.open("wb") as f:
            plist_dump(main_info, f)

        # Remove Watch components if present
        for watch_name in ["com.apple.WatchPlaceholder", "Watch"]:
            watch_dir = main_app.joinpath(watch_name)
            if watch_dir.exists():
                print(f"Removing {watch_name} directory")
                shutil.rmtree(watch_dir)

        # Analyze IPA capabilities and components
        self.app_analysis = self._analyze_app_capabilities()
        
        # Create comprehensive bundle ID mappings
        if opts.encode_ids and opts.account_id:
            self._create_comprehensive_bundle_mappings()
        
        # Identify all components to be signed (depth-first order)
        component_exts = ["*.app", "*.appex", "*.framework", "*.dylib", "PlugIns/*.bundle"]
        self.components = [item for e in component_exts for item in safe_glob(main_app, "**/" + e)][::-1]
        self.components.append(main_app)

    def _determine_main_bundle_id(self):
        """Determine the main bundle ID based on configuration."""
        from .utils import generate_bundle_id_from_email, get_or_create_bundle_id
        
        if self.opts.prov_file:
            if self.opts.bundle_id is None:
                print("Using original bundle id")
                self.main_bundle_id = self.old_main_bundle_id
            elif self.opts.bundle_id == "":
                print("Using provisioning profile's application id")
                prov_app_id = dump_prov_entitlements(self.opts.prov_file)[self._get_application_identifier_key()]
                self.main_bundle_id = prov_app_id[prov_app_id.find(".") + 1 :]
                if self.main_bundle_id == "*":
                    print("Provisioning profile is wildcard, using original bundle id")
                    self.main_bundle_id = self.old_main_bundle_id
            else:
                print("Using custom bundle id")
                self.main_bundle_id = self.opts.bundle_id
        else:
            if self.opts.bundle_id:
                print("Using custom bundle id")
                self.main_bundle_id = self.opts.bundle_id
            elif self.opts.encode_ids:
                print("Using managed bundle ID system")
                # Use new bundle ID management system
                account_id = getattr(self.opts, 'account_id', None)
                if account_id:
                    self.main_bundle_id = get_or_create_bundle_id(
                        account_id, self.old_main_bundle_id, self.opts.account_name
                    )
                else:
                    # Fallback to old system
                    self.main_bundle_id = generate_bundle_id_from_email(self.opts.account_name)
                
                if not self.opts.force_original_id and self.old_main_bundle_id != self.main_bundle_id:
                    self.mappings[self.old_main_bundle_id] = self.main_bundle_id
            else:
                print("Using original bundle id")
                self.main_bundle_id = self.old_main_bundle_id

    def _analyze_app_capabilities(self):
        """Analyze the app to detect capabilities and components."""
        from .utils import analyze_ipa_capabilities
        from .webhooks import store_app_capabilities
        
        print("Analyzing app capabilities and components...")
        analysis = analyze_ipa_capabilities(self.opts.app_dir)
        
        # Store capabilities analysis on server if account_id is available
        if self.opts.account_id and analysis.get("capabilities"):
            store_app_capabilities(
                self.opts.account_id,
                analysis.get("main_app", {}).get("bundle_id", ""),
                analysis.get("capabilities", []),
                analysis.get("entitlements", {})
            )
        
        print(f"Detected {len(analysis.get('capabilities', []))} capabilities and {len(analysis.get('extensions', []))} extensions")
        return analysis
    
    def _create_comprehensive_bundle_mappings(self):
        """Create bundle ID mappings for all app components."""
        from .utils import create_bundle_id_mapping_for_components
        
        print("Creating comprehensive bundle ID mappings...")
        component_mappings = create_bundle_id_mapping_for_components(
            self.opts.account_id, self.opts.account_name, self.app_analysis
        )
        
        # Merge with existing mappings
        self.mappings.update(component_mappings)
        print(f"Created {len(component_mappings)} bundle ID mappings")

    def gen_id(self, input_id: str):
        """Encode the provided id into a different but constant id."""
        if not input_id.strip():
            return input_id
        if not self.opts.encode_ids:
            return input_id
        
        # Check if we have a mapping from the comprehensive system
        if input_id in self.mappings:
            return self.mappings[input_id]
            
        # Fallback to original random generation
        new_parts = map(lambda x: rand_str(len(x), x + self.opts.team_id), input_id.split("."))
        result = ".".join(new_parts)
        return result

    def _get_application_identifier_key(self):
        """Get the correct application identifier key for the platform."""
        return "com.apple.application-identifier" if self.is_mac_app else "application-identifier"

    def _get_aps_environment_key(self):
        """Get the correct APS environment key for the platform."""
        return "com.apple.developer.aps-environment" if self.is_mac_app else "aps-environment"

    def _sign_secondary(self, component: Path, tmpdir: Path):
        """Sign secondary components (frameworks, etc.) with original entitlements."""
        print("Signing with original entitlements")
        return codesign_async(self.opts.common_name, component)

    def _sign_primary(self, component: Path, tmpdir: Path, data: ComponentData):
        """Sign primary components (apps, extensions) with custom entitlements."""
        info = plist_load(data.info_plist)

        # Set bundle identifier
        if self.opts.force_original_id:
            print("Keeping original CFBundleIdentifier")
            info["CFBundleIdentifier"] = data.old_bundle_id
        else:
            print(f"Setting CFBundleIdentifier to {data.bundle_id}")
            info["CFBundleIdentifier"] = data.bundle_id

        # Configure debugging
        if self.opts.patch_debug:
            data.entitlements["get-task-allow"] = True
            print("Enabled app debugging")
        else:
            data.entitlements.pop("get-task-allow", False)
            print("Disabled app debugging")

        # Apply iOS-specific patches
        if not self.is_mac_app:
            if self.opts.patch_all_devices:
                print("Force enabling support for all devices")
                info.pop("UISupportedDevices", False)
                info["UIDeviceFamily"] = [1, 2, 3, 4]  # iOS, iPadOS, tvOS, watchOS

            if self.opts.patch_mac:
                info.pop("UIRequiresFullScreen", False)
                for device in ["ipad", "iphone", "ipod"]:
                    info.pop("UISupportedInterfaceOrientations~" + device, False)
                info["UISupportedInterfaceOrientations"] = [
                    "UIInterfaceOrientationPortrait",
                    "UIInterfaceOrientationPortraitUpsideDown",
                    "UIInterfaceOrientationLandscapeLeft",
                    "UIInterfaceOrientationLandscapeRight",
                ]

            if self.opts.patch_file_sharing:
                print("Force enabling file sharing")
                info["UIFileSharingEnabled"] = True
                info["UISupportsDocumentBrowser"] = True

        # Save modified Info.plist
        with data.info_plist.open("wb") as f:
            plist_dump(info, f)

        print("Signing with entitlements:")
        print_object(data.entitlements)

        # Handle provisioning profile
        embedded_prov = data.info_plist.parent.joinpath(
            "embedded.provisionprofile" if self.is_mac_app else "embedded.mobileprovision"
        )
        if self.opts.prov_file is not None:
            shutil.copy2(self.opts.prov_file, embedded_prov)
        else:
            print("Registering component with Apple...")
            if self.opts.use_master_capabilities:
                from .fastlane_integration import fastlane_register_app_with_master_capabilities
                # Get required capabilities from analysis
                required_capabilities = self.app_analysis.get("capabilities", [])
                fastlane_register_app_with_master_capabilities(
                    self.opts.account_name, self.opts.account_pass, self.opts.team_id, 
                    data.bundle_id, required_capabilities
                )
            else:
                fastlane_register_app(
                    self.opts.account_name, self.opts.account_pass, self.opts.team_id, data.bundle_id, data.entitlements
                )

            print("Generating provisioning profile...")
            prov_type = "adhoc" if self.is_distribution else "development"
            platform = "macos" if self.is_mac_app else "ios"
            fastlane_get_prov_profile(
                self.opts.account_name,
                self.opts.account_pass,
                self.opts.team_id,
                data.bundle_id,
                prov_type,
                platform,
                embedded_prov,
            )

        # Create entitlements file and sign
        entitlements_plist = Path(tmpdir).joinpath("entitlements.plist")
        with open(entitlements_plist, "wb") as f:
            plist_dump(data.entitlements, f)

        print("Signing component...")
        return codesign_async(self.opts.common_name, component, entitlements_plist)

    def _prepare_primary(self, component: Path, workdir: Path):
        """Prepare primary component for signing by processing entitlements."""
        info_plist = get_info_plist_path(component)
        info: Dict[Any, Any] = plist_load(info_plist)
        old_bundle_id = info["CFBundleIdentifier"]
        
        # Create bundle id by suffixing the existing main bundle id with the original suffix
        bundle_id = f"{self.main_bundle_id}{old_bundle_id[len(self.old_main_bundle_id):]}"
        if not self.opts.force_original_id and old_bundle_id != bundle_id:
            if len(old_bundle_id) != len(bundle_id):
                print(
                    f"WARNING: Component's bundle id '{bundle_id}' is different length from the original bundle id '{old_bundle_id}'.",
                    "The signed app may crash!",
                )
            else:
                self.mappings[old_bundle_id] = bundle_id

        # Extract existing entitlements
        old_entitlements: Dict[Any, Any]
        try:
            old_entitlements = codesign_dump_entitlements(component)
        except:
            print("Failed to dump entitlements, using empty")
            old_entitlements = {}

        print("Original entitlements:")
        print_object(old_entitlements)

        # Process team ID mappings
        self._process_team_id_mappings(old_entitlements)

        # Process entitlements based on whether we have a provisioning profile
        if self.opts.prov_file is not None:
            entitlements = self._process_prov_entitlements(old_entitlements, bundle_id)
        else:
            entitlements = self._process_generated_entitlements(old_entitlements, bundle_id)

        return ComponentData(old_bundle_id, bundle_id, entitlements, info_plist)

    def _process_team_id_mappings(self, old_entitlements: Dict[Any, Any]):
        """Process team ID and app ID prefix mappings."""
        old_team_id: Optional[str] = old_entitlements.get("com.apple.developer.team-identifier", None)
        if not old_team_id:
            print("Failed to read old team id")
        elif old_team_id != self.opts.team_id:
            if len(old_team_id) != len(self.opts.team_id):
                print("WARNING: Team ID length mismatch:", old_team_id, self.opts.team_id)
            else:
                self.mappings[old_team_id] = self.opts.team_id

        # Process app ID prefix
        old_app_id_prefix: Optional[str] = old_entitlements.get(self._get_application_identifier_key(), "").split(".")[0]
        if not old_app_id_prefix:
            old_app_id_prefix = None
            print("Failed to read old app id prefix")
        elif old_app_id_prefix != self.opts.team_id:
            if len(old_app_id_prefix) != len(self.opts.team_id):
                print("WARNING: App ID Prefix length mismatch:", old_app_id_prefix, self.opts.team_id)
            else:
                self.mappings[old_app_id_prefix] = self.opts.team_id

    def _process_prov_entitlements(self, old_entitlements: Dict[Any, Any], bundle_id: str) -> Dict[Any, Any]:
        """Process entitlements when using a provisioning profile."""
        entitlements = dump_prov_entitlements(self.opts.prov_file)

        prov_app_id = entitlements[self._get_application_identifier_key()]
        component_app_id = f"{self.opts.team_id}.{bundle_id}"
        wildcard_app_id = f"{self.opts.team_id}.*"

        # Handle wildcard app ID
        if prov_app_id == wildcard_app_id:
            entitlements[self._get_application_identifier_key()] = component_app_id
        elif prov_app_id != component_app_id:
            print(
                f"WARNING: Provisioning profile's app id '{prov_app_id}' does not match component's app id '{component_app_id}'.",
                "Using provisioning profile's app id - the component will run, but some functions such as file importing will not work!",
                sep="\n",
            )

        # Handle keychain access groups
        keychain: Optional[List[str]] = entitlements.get("keychain-access-groups", None)
        old_keychain: Optional[List[str]] = old_entitlements.get("keychain-access-groups", None)
        if old_keychain is None:
            entitlements.pop("keychain-access-groups", None)
        elif keychain and any(item == wildcard_app_id for item in keychain):
            keychain.clear()
            for item in old_keychain:
                keychain.append(f"{self.opts.team_id}.{item[item.index('.')+1:]}")

        return entitlements

    def _process_generated_entitlements(self, old_entitlements: Dict[Any, Any], bundle_id: str) -> Dict[Any, Any]:
        """Process entitlements when generating new ones."""
        supported_entitlements = [
            self._get_application_identifier_key(),
            "com.apple.developer.team-identifier",
            "com.apple.developer.healthkit",
            "com.apple.developer.healthkit.access",
            "com.apple.developer.homekit",
            "com.apple.external-accessory.wireless-configuration",
            "com.apple.security.application-groups",
            "inter-app-audio",
            "get-task-allow",
            "keychain-access-groups",
            self._get_aps_environment_key(),
            "com.apple.developer.icloud-container-development-container-identifiers",
            "com.apple.developer.icloud-container-environment",
            "com.apple.developer.icloud-container-identifiers",
            "com.apple.developer.icloud-services",
            "com.apple.developer.kernel.extended-virtual-addressing",
            "com.apple.developer.networking.multipath",
            "com.apple.developer.networking.networkextension",
            "com.apple.developer.networking.vpn.api",
            "com.apple.developer.networking.wifi-info",
            "com.apple.developer.nfc.readersession.formats",
            "com.apple.developer.siri",
            "com.apple.developer.ubiquity-container-identifiers",
            "com.apple.developer.ubiquity-kvstore-identifier",
            "com.apple.developer.associated-domains",
            # macOS only
            "com.apple.security.app-sandbox",
            "com.apple.security.assets.pictures.read-write",
            "com.apple.security.cs.allow-jit",
            "com.apple.security.cs.allow-unsigned-executable-memory",
            "com.apple.security.cs.disable-library-validation",
            "com.apple.security.device.audio-input",
            "com.apple.security.device.bluetooth",
            "com.apple.security.device.usb",
            "com.apple.security.files.user-selected.read-only",
            "com.apple.security.files.user-selected.read-write",
            "com.apple.security.network.client",
            "com.apple.security.network.server",
        ]
        
        entitlements = copy.deepcopy(old_entitlements)
        for entitlement in list(entitlements):
            if entitlement not in supported_entitlements:
                self.removed_entitlements.add(entitlement)
                entitlements.pop(entitlement)

        # Set environment-sensitive entitlements
        for entitlement, value in {
            "com.apple.developer.icloud-container-environment": (
                "Production" if self.is_distribution else "Development"
            ),
            self._get_aps_environment_key(): "production" if self.is_distribution else "development",
            "get-task-allow": False if self.is_distribution else True,
        }.items():
            if entitlement in entitlements:
                entitlements[entitlement] = value

        # Set required identifiers
        entitlements["com.apple.developer.team-identifier"] = self.opts.team_id
        entitlements[self._get_application_identifier_key()] = f"{self.opts.team_id}.{bundle_id}"

        # Remap IDs if encoding is enabled
        if self.opts.encode_ids:
            self._remap_entitlement_ids(entitlements)

        return entitlements

    def _remap_entitlement_ids(self, entitlements: Dict[Any, Any]):
        """Remap entitlement IDs when encoding is enabled."""
        for remap_def in (
            RemapDef(["com.apple.security.application-groups"], "group.", False, True),
            RemapDef(
                [
                    "com.apple.developer.icloud-container-identifiers",
                    "com.apple.developer.ubiquity-container-identifiers",
                    "com.apple.developer.icloud-container-development-container-identifiers",
                ],
                "iCloud.",
                False,
                True,
            ),
            RemapDef(["keychain-access-groups"], self.opts.team_id + ".", True, True),
            RemapDef(
                ["com.apple.developer.ubiquity-kvstore-identifier"], self.opts.team_id + ".", False, False
            ),
        ):
            for entitlement in remap_def.entitlements:
                remap_ids = entitlements.get(entitlement, [])
                if isinstance(remap_ids, str):
                    remap_ids = [remap_ids]

                if len(remap_ids) < 1:
                    continue

                entitlements[entitlement] = []

                for remap_id in [id[len(remap_def.prefix) :] for id in remap_ids]:
                    if remap_def.prefix_only:
                        new_id = remap_def.prefix + remap_id
                    else:
                        new_id = remap_def.prefix + self.gen_id(remap_id)
                        self.mappings[remap_def.prefix + remap_id] = new_id

                    entitlements[entitlement].append(new_id)
                    if not remap_def.is_list:
                        entitlements[entitlement] = entitlements[entitlement][0]

    def sign(self):
        """Execute the complete signing process."""
        from .utils import popen_check
        
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)

            # Prepare all components
            job_defs: List[Tuple[Path, Optional[ComponentData]]] = []
            for component in self.components:
                print(f"Preparing component {component}")

                if component.suffix in [".appex", ".app"]:
                    job_defs.append((component, self._prepare_primary(component, tmpdir)))
                else:
                    job_defs.append((component, None))

            print("ID mappings:")
            print_object(self.mappings)

            print("Removed entitlements:")
            print_object(list(self.removed_entitlements))

            # Authenticate if needed
            if self.opts.prov_file is None:
                print(
                    "Logging in...",
                    "If you receive a two-factor authentication (2FA) code, please submit it to the web service.",
                    sep="\n",
                )
                report_progress(40, "Authenticating with Apple Developer Portal")
                fastlane_auth(self.opts.account_name, self.opts.account_pass, self.opts.team_id)

            # Sign all components
            jobs: Dict[Path, subprocess.Popen] = {}
            total_components = len(job_defs)
            current_component = 0

            for component, data in job_defs:
                current_component += 1
                progress = 50 + (current_component * 30 // total_components)  # 50-80% for signing components
                print(f"Processing component {component}")
                report_progress(progress, f"Signing component {current_component}/{total_components}")

                # Wait for sub-components to finish
                for path in list(jobs.keys()):
                    pipe = jobs[path]
                    try:
                        path.relative_to(component)
                    except:
                        continue
                    if pipe.poll() is None:
                        print("Waiting for sub-component to finish signing:", path)
                        pipe.wait()
                    popen_check(pipe)
                    jobs.pop(path)

                # Remove AppStore metadata
                sc_info = component.joinpath("SC_Info")
                if sc_info.exists():
                    print(
                        f"WARNING: Found leftover AppStore metadata - removing it.",
                        "If the app is encrypted, it will fail to launch!",
                        sep="\n",
                    )
                    shutil.rmtree(sc_info)

                # Apply binary patches
                if self.opts.patch_ids:
                    self._apply_binary_patches(component, data)

                # Start signing process
                if data is not None:
                    jobs[component] = self._sign_primary(component, tmpdir, data)
                else:
                    jobs[component] = self._sign_secondary(component, tmpdir)

            # Wait for all signing jobs to complete
            print("Waiting for any remaining components to finish signing")
            for pipe in jobs.values():
                pipe.wait()
                popen_check(pipe)

    def _apply_binary_patches(self, component: Path, data: Optional[ComponentData]):
        """Apply binary patches to replace old identifiers with new ones."""
        # Only patch mappings with same length to avoid breaking binary structure
        patches = {k: v for k, v in self.mappings.items() if len(k) == len(v)}
        patches = dict(sorted(self.mappings.items(), key=lambda x: len(x[0]), reverse=True))

        if len(patches) < 1:
            print("Nothing to patch")
        else:
            targets = [
                x for x in [component, component.joinpath(component.stem)] if x.exists() and x.is_file()
            ]
            if data is not None:
                targets.append(data.info_plist)
            for target in targets:
                print(f"Patching {len(patches)} patterns in {target}")
                for old, new in patches.items():
                    binary_replace(f"s/{re.escape(old)}/{re.escape(new)}/g", target)
