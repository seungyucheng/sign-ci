#!/usr/bin/env python3
"""
Fastlane integration functions.

This module handles all interactions with Fastlane for app registration,
provisioning profile generation, and Apple Developer Portal operations.
"""

from calendar import c
import os
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
from multiprocessing.pool import ThreadPool
from .utils import run_process, clean_dev_portal_name, decode_clean
from .webhooks import webhook_request, job_id
from .security import security_import

def fastlane_auth(account_name: str, account_pass: str, team_id: str):
    """Authenticate with Apple Developer Portal using Fastlane."""
    my_env = os.environ.copy()
    my_env["FASTLANE_USER"] = account_name
    my_env["FASTLANE_PASSWORD"] = account_pass
    my_env["FASTLANE_TEAM_ID"] = team_id

    auth_pipe = subprocess.Popen(
        # enable copy to clipboard so we're not interactively prompted
        ["fastlane", "spaceauth", "--copy_to_clipboard"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=my_env,
    )

    start_time = time.time()
    while True:
        if time.time() - start_time > 60:
            raise Exception("Operation timed out")
        else:
            result = auth_pipe.poll()
            if result == 0:
                print("Logged in!")
                break
            elif result is not None:
                stdout, stderr = auth_pipe.communicate()
                result = {"error_code": result, "stdout": stdout, "stderr": stderr}
                raise Exception(f"Error logging in: {result}")

            # Try to get 2FA code from server
            try:
                result = webhook_request("job/2fa", {"job_id": job_id}, check=False)
                if result.returncode == 0:
                    response_data = json.loads(decode_clean(result.stdout))
                    if response_data.get("code") == 1 and response_data.get("data", {}).get("two_factor_code"):
                        account_2fa = response_data["data"]["two_factor_code"]
                        auth_pipe.communicate((account_2fa + "\n").encode())
                        print(f"Used 2FA code from server: {account_2fa}")
                        continue
            except Exception as e:
                print(f"Failed to get 2FA from server: {e}")

            # If no 2FA available, wait a bit and try again
            print("Waiting for 2FA code from server...")
        time.sleep(2)


def fastlane_register_app_extras(
    my_env: Dict[Any, Any],
    bundle_id: str,
    extra_type: str,
    extra_prefix: str,
    matchable_entitlements: List[str],
    entitlements: Dict[Any, Any],
):
    """Register app extras (groups, iCloud containers) with Apple Developer Portal."""
    from .utils import run_process_async, popen_check

    matched_ids: Set[str] = set()
    for k, v in entitlements.items():
        if k in matchable_entitlements:
            if type(v) is list:
                matched_ids.update(v)
            elif type(v) is str:
                matched_ids.add(v)
            else:
                raise Exception(f"Unknown value type for {v}: {type(v)}")

    # ensure all ids are prefixed correctly or registration will fail
    # some matchable entitlements are incorrectly prefixed with team id
    matched_ids = set(
        id if id.startswith(extra_prefix) else extra_prefix + id[id.index(".") + 1 :] for id in matched_ids
    )

    jobs: List[subprocess.Popen] = []

    for id in matched_ids:
        jobs.append(
            run_process_async(
                "fastlane",
                "produce",
                extra_type,
                "--skip_itc",
                "-g",
                id,
                "-n",
                clean_dev_portal_name(f"ST {id}"),
                env=my_env,
            )
        )

    for pipe in jobs:
        if pipe.poll() is None:
            pipe.wait()
        popen_check(pipe)

    run_process(
        "fastlane",
        "produce",
        f"associate_{extra_type}",
        "--skip_itc",
        "--app_identifier",
        bundle_id,
        *matched_ids,
        env=my_env,
    )


def fastlane_register_app(
    account_name: str, account_pass: str, team_id: str, bundle_id: str, entitlements: Dict[Any, Any]
):
    """Register app with Apple Developer Portal and configure services."""

    my_env = os.environ.copy()
    my_env["FASTLANE_USER"] = account_name
    my_env["FASTLANE_PASSWORD"] = account_pass
    my_env["FASTLANE_TEAM_ID"] = team_id

    # no-op if already exists
    run_process(
        "fastlane",
        "produce",
        "create",
        "--skip_itc",
        "--app_identifier",
        bundle_id,
        "--app-name",
        clean_dev_portal_name(f"ST {bundle_id}"),
        env=my_env,
    )

    supported_services = [
        "--push-notification",
        "--health-kit",
        "--home-kit",
        "--wireless-accessory",
        "--inter-app-audio",
        "--extended-virtual-address-space",
        "--multipath",
        "--network-extension",
        "--personal-vpn",
        "--access-wifi",
        "--nfc-tag-reading",
        "--siri-kit",
        "--associated-domains",
        "--icloud",
        "--app-group",
    ]

    # clear any previous services
    run_process(
        "fastlane",
        "produce",
        "disable_services",
        "--skip_itc",
        "--app_identifier",
        bundle_id,
        *supported_services,
        env=my_env,
    )

    icloud_entitlements = [
        "com.apple.developer.icloud-container-development-container-identifiers",
        "com.apple.developer.icloud-container-identifiers",
        "com.apple.developer.ubiquity-container-identifiers",
        "com.apple.developer.ubiquity-kvstore-identifier",
    ]

    group_entitlements = ["com.apple.security.application-groups"]

    entitlement_map: Dict[str, Tuple[str, ...]] = {
        "aps-environment": tuple(["--push-notification"]),  # iOS
        "com.apple.developer.aps-environment": tuple(["--push-notification"]),  # macOS
        "com.apple.developer.healthkit": tuple(["--health-kit"]),
        "com.apple.developer.homekit": tuple(["--home-kit"]),
        "com.apple.external-accessory.wireless-configuration": tuple(["--wireless-accessory"]),
        "inter-app-audio": tuple(["--inter-app-audio"]),
        "com.apple.developer.kernel.extended-virtual-addressing": tuple(["--extended-virtual-address-space"]),
        "com.apple.developer.networking.multipath": tuple(["--multipath"]),
        "com.apple.developer.networking.networkextension": tuple(["--network-extension"]),
        "com.apple.developer.networking.vpn.api": tuple(["--personal-vpn"]),
        "com.apple.developer.networking.wifi-info": tuple(["--access-wifi"]),
        "com.apple.developer.nfc.readersession.formats": tuple(["--nfc-tag-reading"]),
        "com.apple.developer.siri": tuple(["--siri-kit"]),
        "com.apple.developer.associated-domains": tuple(["--associated-domains"]),
    }
    for k in icloud_entitlements:
        entitlement_map[k] = tuple(["--icloud", "xcode6_compatible"])
    for k in group_entitlements:
        entitlement_map[k] = tuple(["--app-group"])

    service_flags = set(entitlement_map[f] for f in entitlements.keys() if f in entitlement_map)
    service_flags = [item for sublist in service_flags for item in sublist]

    print("Enabling services:", service_flags)

    run_process(
        "fastlane",
        "produce",
        "enable_services",
        "--skip_itc",
        "--app_identifier",
        bundle_id,
        *service_flags,
        env=my_env,
    )

    app_extras = [("cloud_container", "iCloud.", icloud_entitlements), ("group", "group.", group_entitlements)]
    with ThreadPool(len(app_extras)) as p:
        p.starmap(
            lambda extra_type, extra_prefix, matchable_entitlements: fastlane_register_app_extras(
                my_env, bundle_id, extra_type, extra_prefix, matchable_entitlements, entitlements
            ),
            app_extras,
        )


def fastlane_get_prov_profile(
    account_name: str, account_pass: str, team_id: str, bundle_id: str, prov_type: str, platform: str, out_file: Path
):
    """Generate provisioning profile using Fastlane."""
    import tempfile
    import shutil
    from .webhooks import report_progress

    my_env = os.environ.copy()
    my_env["FASTLANE_USER"] = account_name
    my_env["FASTLANE_PASSWORD"] = account_pass
    my_env["FASTLANE_TEAM_ID"] = team_id

    report_progress(65, f"Generating provisioning profile for {bundle_id}")

    with tempfile.TemporaryDirectory() as tmpdir_str:
        run_process(
            "fastlane",
            "sigh",
            "renew",
            "--app_identifier",
            bundle_id,
            "--provisioning_name",
            clean_dev_portal_name(f"ST {bundle_id} {prov_type}"),
            "--force",
            "--skip_install",
            "--include_mac_in_profiles",
            "--platform",
            platform,
            "--" + prov_type,
            "--output_path",
            tmpdir_str,
            "--filename",
            "prov.mobileprovision",
            env=my_env,
        )
        shutil.copy2(Path(tmpdir_str).joinpath("prov.mobileprovision"), out_file)


def fastlane_get_certificate(
    account_name: str,
    account_pass: str,
    team_id: str,
    account_id: str,
    cert_pass: str,
    cert_type: str = "development"
) -> Optional[str]:
    """
    Generate or retrieve certificate using Fastlane.

    Args:
        account_name: Apple Developer account email
        account_pass: Apple Developer account password
        team_id: Apple Developer team ID
        account_id: Server account ID for certificate storage
        keychain_name: Keychain name for certificate storage
        cert_type: Certificate type (development or distribution)

    Returns:
        Path to certificate file or None if failed
    """
    import tempfile
    import shutil
    import base64
    from .webhooks import get_certificate_from_server, upload_certificate, report_progress

    # tmpdir = Path(tmpdir_str)
    current_directory = os.getcwd()
    tmpdir = Path(current_directory + "/tmp")
    os.makedirs(tmpdir, exist_ok=True)

    report_progress(22, "Checking for existing certificate")

    # Try to get certificate from server first
    cert_info = get_certificate_from_server(account_id)
    if cert_info and cert_info.get("certificate_data"):
        print("Using existing certificate from server")
        report_progress(28, "Using cached certificate")

        # Save certificate data to temporary file
        cert_data = cert_info["certificate_data"]
        decoded_bytes = base64.b64decode(cert_data)

        file_path = os.path.join(tmpdir, "downloaded_cert.p12")
        with open(file_path, "wb") as f:   # use "wb" for binary data
            f.write(decoded_bytes)
            return f.name

    # No certificate found on server, generate new one
    print("Generating new certificate with Fastlane")
    report_progress(24, "Generating new certificate (this may take a moment)")

    my_env = os.environ.copy()
    my_env["FASTLANE_USER"] = account_name
    my_env["FASTLANE_PASSWORD"] = account_pass
    my_env["FASTLANE_TEAM_ID"] = team_id

    with tempfile.TemporaryDirectory() as tmpdir_str:
        try:
            # Generate certificate using Fastlane cert
            # The cert_type_flag tells Fastlane what kind of certificate to create
            # Think of it like choosing between a "student ID" (development) or "official ID" (distribution)
            cert_type_flag = "--development" if cert_type == "development" else "--distribution"

            run_process(
                "fastlane",
                "cert",
                "create",
                "--force",
                cert_type_flag,
                "--output_path",
                str(tmpdir),
                "--filename",
                "cert.p12",
                env=my_env,
            )

            # Fastlane creates THREE files:
            # 1. xx.p12 - contains ONLY the private key
            # 2. xx.cer - contains ONLY the certificate
            # 3. xx.certSigningRequest - the signing request (not needed anymore)
            #
            # We need to COMBINE the private key and certificate into ONE final .p12 file
            # that can be used for iOS signing

            private_key_p12 = None
            certificate_cer = None

            # Find the private key file (.p12)
            for file in tmpdir.glob("*.p12"):
                if not str(file).endswith(".p12.cer"):
                    private_key_p12 = file
                    print(f"Found private key file: {file.name}")
                    break

            # Find the certificate file (.cer)
            for file in tmpdir.glob("*.cer"):
                if str(file).endswith(".p12.cer"):
                    certificate_cer = file
                    print(f"Found certificate file: {file.name}")
                    break

            if not private_key_p12 or not certificate_cer:
                all_files = list(tmpdir.glob("*"))
                raise Exception(f"Certificate generation failed - missing files. Found: {[f.name for f in all_files]}")

            # Now combine the private key and certificate into a final .p12 file
            # This is like putting the key and lock together so they work as one
            print("Combining private key and certificate into final .p12 file...")
            report_progress(30, "Combining certificate components")

            actual_cert_path = Path(str(tmpdir) + "/combined.p12")
            run_process(
                "openssl",
                "pkcs12",
                "-export",
                "-in", str(certificate_cer),
                "-inkey", str(private_key_p12),
                "-out", str(actual_cert_path),
                "-passout", f"pass:{cert_pass}",
            )

            # Read and encode certificate
            with open(actual_cert_path, 'rb') as f:
                cert_bytes = f.read()
                cert_data_encoded = base64.b64encode(cert_bytes).decode('utf-8')

            report_progress(33, "Certificate generated, uploading to server")

            # Upload to server
            upload_certificate(account_id, team_id, cert_data_encoded)

            report_progress(35, "Certificate uploaded and ready")

            return str(actual_cert_path)

        except Exception as e:
            print(f"Certificate generation failed: {e}")
            report_progress(0, f"Certificate generation failed: {e}", state=0)
            raise

def fastlane_register_device(
    account_name: str,
    account_pass: str,
    team_id: str,
    device_udid: str,
    device_name: str = None
):
    """
    Register device with Apple Developer Portal using Fastlane.

    Args:
        account_name: Apple Developer account email
        account_pass: Apple Developer account password
        team_id: Apple Developer team ID
        device_udid: Device UDID to register (e.g., "00008101-001451CC0E01001E")
        device_name: Optional device name (defaults to "Device {UDID[:8]}")

    This function registers a new device with your Apple Developer account so it can
    be included in development provisioning profiles. Think of it like adding someone's
    name to a guest list before sending them an invitation!
    """
    from .webhooks import report_progress

    # Generate a friendly device name if not provided
    # Using first 8 characters of UDID to make it recognizable
    if device_name is None:
        device_name = f"Device {device_udid[:8]}"

    print(f"Registering device: {device_name} (UDID: {device_udid})")
    report_progress(48, f"Registering device with Apple")

    my_env = os.environ.copy()
    my_env["FASTLANE_USER"] = account_name
    my_env["FASTLANE_PASSWORD"] = account_pass
    my_env["FASTLANE_TEAM_ID"] = team_id

    try:
        # Register the device using Fastlane
        # The 'run' command executes a Fastlane action directly
        # register_device is the action that adds a device to your Apple Developer account
        run_process(
            "fastlane",
            "run",
            "register_device",
            f"udid:{device_udid}",
            f"name:{clean_dev_portal_name(device_name)}",
            env=my_env,
        )

        print(f"✓ Device registered successfully: {device_name}")
        report_progress(49, "Device registered successfully")

    except Exception as e:
        # If device is already registered, Fastlane will throw an error
        # but that's actually okay - we just want to make sure it exists
        error_message = str(e)
        if "already exists" in error_message.lower() or "already registered" in error_message.lower():
            print(f"✓ Device already registered: {device_name}")
            report_progress(50, "Device already registered")
        else:
            print(f"✗ Failed to register device: {error_message}")
            raise