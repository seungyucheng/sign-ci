#!/usr/bin/env python3
"""
iOS App Signing Tool - Main Entry Point

This is the main entry point for the iOS app signing tool. It has been refactored
into a modular structure with separate libraries for better maintainability.

The signing process includes:
1. Job initialization and data retrieval
2. Certificate and keychain setup
3. IPA extraction and tweak injection
4. App signing with proper entitlements
5. Packaging and upload of signed app

For detailed information about each module, see the lib/ directory.
"""

import sys
import traceback
import tempfile
from pathlib import Path

# Import from our modular library
from lib import (
    Signer, SignOpts, 
    report_progress, complete_job, fail_job, get_job_info,
    generate_bundle_id_from_email, rand_str, read_file,
    security_import, security_remove_keychain,
    inject_tweaks
)
from lib.utils import extract_zip, archive_zip, run_process
from lib.webhooks import job_id, api_token
import aes

def run(job_data, account_data, ipa_data):
    """Execute the main signing process."""
    print("Initializing signing process...")
    report_progress(5, "Initializing job")

    print("Creating keychain...")
    report_progress(10, "Setting up keychain")

    # Check if we have a certificate file, if not, we'll generate one
    cert_file = Path("cert.p12")
    cert_pass = "defaultpass"
    keychain_name = "ios-signer-" + rand_str(8)
    team_id = ""
    user_bundle_id = ""

    if not cert_file.exists():
        print("No certificate file found, will generate certificate during signing process")
        common_names = {"Development": "Apple Development", "Distribution": None}
        common_name = "Apple Development"
    else:
        common_names = security_import(cert_file, cert_pass, keychain_name)
        if len(common_names) < 1:
            raise Exception("No valid code signing certificate found, aborting.")
        common_names = {
            # "Apple Development" for paid dev account
            # "iPhone Developer" for free dev account, etc
            "Development": next((n for n in common_names if "Develop" in n), None),
            "Distribution": next((n for n in common_names if "Distribution" in n), None),
        }

        if common_names["Distribution"] is not None:
            print("Using distribution certificate")
            common_name = common_names["Distribution"]

        elif common_names["Development"] is not None:
            print("Using development certificate")
            common_name = common_names["Development"]
        else:
            raise Exception("Unrecognized code signing certificate, aborting.")

    report_progress(15, "Certificate validation completed")

    # Use account data from job info
    prov_profile = Path("prov.mobileprovision")
    account_name_file = Path("account_name.txt")
    account_pass_file = Path("account_pass.txt")
    bundle_name = Path("bundle_name.txt")

    # Write account data from server
    if account_data and account_data.get("email") and account_data.get("password"):
        with open(account_name_file, "w") as f:
            f.write(account_data["email"])
        # Handle encrypted password - decode base64 if it looks encoded
        password = account_data["password"]
        if password and len(password) > 10 and password.endswith("=="):
            try:
                from lib.webhooks import secret_key
                decrypted_password = aes.decrypt_aes_cbc_pkcs7(password, secret_key)
                print("Decoded base64 password")
            except Exception as e:
                print(f"Failed to decode password, using as-is: {e}")
                decrypted_password = password
        else:
            decrypted_password = password

        with open(account_pass_file, "w") as f:
            f.write(decrypted_password)
        print("Using developer account from server")
    else:
        raise Exception("Developer account information required but not found in job data.")

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        print("Extracting app...")
        report_progress(20, "Extracting IPA")
        extract_zip(Path("unsigned.ipa"), temp_dir)

        tweaks_dir = Path("tweaks")
        if tweaks_dir.exists():
            print("Found tweaks, injecting...")
            report_progress(25, "Injecting tweaks")
            inject_tweaks(temp_dir, tweaks_dir)

        print("Signing...")
        report_progress(30, "Starting signing process")
        Signer(
            SignOpts(
                temp_dir,
                common_name,
                team_id,
                read_file(account_name_file) if account_name_file.is_file() else "",
                read_file(account_pass_file) if account_pass_file.is_file() else "",
                prov_profile if prov_profile.is_file() else None,
                user_bundle_id,
                read_file(bundle_name) if bundle_name.exists() else None,
                True,  # patch_debug
                True,  # patch_all_devices
                False, # patch_mac
                False, # patch_file_sharing
                True,  # encode_ids
                False, # patch_ids
                False, # force_original_id
            )
        ).sign()

        report_progress(85, "Signing completed, packaging app")
        print("Packaging signed app...")
        signed_ipa = Path("signed.ipa")
        archive_zip(temp_dir, signed_ipa)

    print("Uploading...")
    report_progress(90, "Uploading signed IPA")
    file_id = read_file(Path("file_id.txt")) if Path("file_id.txt").exists() else ""
    bundle_id = read_file(Path("bundle_id.txt"))

    # Get file size for completion report
    file_size = signed_ipa.stat().st_size if signed_ipa.exists() else 0

    # Use new webhook system for completion
    complete_job(f"signed/{job_id}/signed.ipa", file_size)
    report_progress(100, "Job completed successfully")


def main():
    """Main entry point for the signing tool."""
    # Job ID should be provided as environment variable
    if not job_id:
        print("ERROR: JOB_ID environment variable is required")
        sys.exit(1)

    if not api_token:
        print("ERROR: API_TOKEN environment variable is required")
        sys.exit(1)

    print(f"Processing job: {job_id}")

    # Get job information from server - no more legacy file dependencies
    try:
        print("Fetching job information from server...")
        job_info = get_job_info()
        job_data = job_info.get("job", {})
        account_data = job_info.get("account", {})
        ipa_data = job_info.get("ipa", {})

        print(f"Job data received: {job_data.get('job_type', 'unknown')}")

        # Extract required data from job info
        input_path = job_data.get("input_path", "")

        # Generate bundle ID from developer email
        developer_email = account_data.get("email", "")
        if developer_email:
            user_bundle_id = generate_bundle_id_from_email(developer_email)
            print(f"Generated bundle ID: {user_bundle_id}")
        else:
            user_bundle_id = None

        keychain_name = "ios-signer-" + rand_str(8)

    except Exception as e:
        error_msg = f"Failed to fetch job information: {e}"
        print(error_msg)
        fail_job(error_msg, str(traceback.format_exc()))
        sys.exit(1)

    print("Downloading app...")
    unsigned_ipa = Path("unsigned.ipa")
    try:
       # Direct S3 URL - download directly
        print(f"Downloading from S3 URL: {input_path}")
        run_process("curl", "-L", "-o", str(unsigned_ipa), input_path)
    except Exception as e:
        error_msg = f"Failed to download unsigned IPA: {e}"
        print(error_msg)
        fail_job(error_msg, str(traceback.format_exc()))
        sys.exit(1)

    failed = False
    error_message = ""
    error_details = ""

    try:
        run(job_data, account_data, ipa_data)
    except Exception as e:
        failed = True
        error_message = str(e)
        error_details = traceback.format_exc()
        print(f"ERROR: {error_message}")
        traceback.print_exc()
    finally:
        print("Cleaning up...")
        try:
            security_remove_keychain(keychain_name)
        except Exception as e:
            print(f"Warning: Failed to remove keychain: {e}")

        if failed:
            fail_job(error_message, error_details)
            sys.exit(1)


if __name__ == "__main__":
    main()