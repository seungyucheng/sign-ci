#!/usr/bin/env python3
"""
Webhook and API communication functions.

This module handles all communication with the server including progress reporting,
job status updates, and certificate/profile status reporting.
"""

import os
import json
from typing import Dict, Any, Optional
from .utils import run_process, decode_clean

# Environment variables for API communication
secret_url = os.path.expandvars("$SECRET_URL").strip().rstrip("/")
secret_key = os.path.expandvars("$SECRET_KEY")
api_token = os.path.expandvars("$API_TOKEN")
job_id = os.path.expandvars("$JOB_ID")

def curl_with_auth(
    url: str,
    form_data: list = None,
    output: Optional[str] = None,
    check: bool = True,
    capture: bool = True,
):
    """Make authenticated curl request with form data."""
    if form_data is None:
        form_data = []

    args = []
    for key, value in form_data:
        args.extend(["-F", f"{key}={value}"])

    if output:
        args.extend(["-o", str(output)])

    return run_process(
        "curl",
        *["-S", "-f", "-L", "-H"],
        f"Authorization: Bearer {secret_key}",
        *args,
        url,
        check=check,
        capture=capture,
    )


def webhook_request(
    endpoint: str,
    data: Dict[str, Any],
    method: str = "POST",
    check: bool = True,
):
    """Make authenticated webhook request to server."""
    url = f"{secret_url}/api/v1/webhook/{endpoint}"
    json_data = json.dumps(data)

    return run_process(
        "curl",
        "-X", method,
        "-H", "Content-Type: application/json",
        "-H", f"X-API-Token: {api_token}",
        "-d", json_data,
        url,
        check=check,
        capture=True,
    )


def report_progress(progress: int, message: str = "", state: int = 1):
    """Report job progress to server."""
    try:
        webhook_request("job/progress", {
            "job_id": job_id,
            "progress": progress,
            "state": state,
            "message": message
        })
        print(f"Progress reported: {progress}% - {message}")
    except Exception as e:
        print(f"Failed to report progress: {e}")


def get_certificate_from_server(account_id: str) -> Optional[Dict[str, Any]]:
    """Get existing certificate from server."""
    try:
        result = webhook_request("certificate/get", {
            "account_id": account_id
        })
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") == 1:
            print("Certificate found on server")
            return response_data.get("data")
        return None
    except Exception as e:
        print(f"Failed to get certificate from server: {e}")
        return None


def upload_certificate(account_id: str, team_id: str, certificate_data: str):
    """Upload certificate to server."""
    try:
        webhook_request("certificate/store", {
            "account_id": account_id,
            "team_id": team_id,
            "certificate_data": certificate_data
        })
        print(f"Certificate uploaded successfully for account {account_id}")
    except Exception as e:
        print(f"Failed to upload certificate: {e}")
        raise


def upload_provisioning_profile(account_id: str, bundle_id: str, device_udid: str, profile_data: str, profile_id: str, expiry_date: str):
    """Upload provisioning profile to server."""
    try:
        webhook_request("profile/store", {
            "job_id": job_id,
            "bundle_id": bundle_id,
            "profile_data": profile_data,
            "profile_id": profile_id,
            "expiry_date": expiry_date
        })
        print(f"Provisioning profile uploaded successfully for bundle {bundle_id}")
    except Exception as e:
        print(f"Failed to upload provisioning profile: {e}")
        raise


def complete_job(output_path: str):
    """Mark job as completed."""
    try:
        print("Marking job as completed...")
        webhook_request("job/complete", {
            "job_id": job_id,
            "output_path": output_path,
        })
        print("Job marked as completed")
    except Exception as e:
        print(f"Failed to mark job as completed: {e}")


def fail_job(error_message: str, error_details: str = ""):
    """Mark job as failed."""
    try:
        webhook_request("job/fail", {
            "job_id": job_id,
            "message": error_message,
            "error_details": error_details
        })
        print(f"Job marked as failed: {error_message}")
    except Exception as e:
        print(f"Failed to mark job as failed: {e}")


def get_job_info():
    """Get comprehensive job information from server."""
    try:
        result = webhook_request("job/start", {"job_id": job_id})
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") != 1:
            raise Exception(f"Failed to get job info: {response_data.get('message', 'Unknown error')}")

        return response_data.get("data")
    except Exception as e:
        print(f"Failed to get job info: {e}")
        raise

def get_bundle_id_mapping(job_id: str, app_type: str):
    """Get existing bundle ID mapping for an account and original bundle ID."""
    try:
        result = webhook_request("bundle/get", {
            "job_id": job_id,
            "app_type": app_type
        })
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") == 1:
            return response_data.get("data", {}).get("mapped_bundle_id")
        return None
    except Exception as e:
        print(f"Failed to get bundle ID mapping: {e}")
        return None


def get_certificate_info(account_id: str, capabilities: list):
    """Get existing certificate for account with required capabilities."""
    try:
        result = webhook_request("certificate/get", {
            "account_id": account_id,
            "capabilities": capabilities
        })
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") == 1:
            return response_data.get("data")
        return None
    except Exception as e:
        print(f"Failed to get certificate info: {e}")
        return None


def store_certificate_info(account_id: str, certificate_data: str, capabilities: list, team_id: str):
    """Store certificate information for reuse."""
    try:
        webhook_request("certificate/store", {
            "account_id": account_id,
            "certificate_data": certificate_data,
            "capabilities": capabilities,
            "team_id": team_id,
            "job_id": job_id
        })
        print(f"Certificate stored for account {account_id} with {len(capabilities)} capabilities")
    except Exception as e:
        print(f"Failed to store certificate: {e}")


def store_app_capabilities(account_id: str, bundle_id: str, capabilities: list, entitlements: dict):
    """Store app capabilities and entitlements for analysis."""
    try:
        webhook_request("app/capabilities", {
            "account_id": account_id,
            "bundle_id": bundle_id,
            "capabilities": capabilities,
            "entitlements": entitlements,
            "job_id": job_id
        })
        print(f"App capabilities stored for {bundle_id}: {len(capabilities)} capabilities")
    except Exception as e:
        print(f"Failed to store app capabilities: {e}")


def initiate_ipa_upload() -> Optional[Dict[str, Any]]:
    """
    Step 1: Request a pre-signed URL for uploading the signed IPA.

    This is like asking the server for permission and a special address
    where we can upload our file. Think of it as getting a delivery address
    with a temporary access code.

    Returns:
        Dictionary with upload_id, s3_key, upload_url, and expires_in
    """
    try:
        result = webhook_request("ipa/upload/initiate", {})
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") == 1:
            print("✓ Received upload URL from server")
            return response_data
        else:
            print(f"Failed to get upload URL: {response_data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"Failed to initiate IPA upload: {e}")
        return None


def upload_file_to_s3(file_path: str, upload_url: str) -> bool:
    """
    Step 2: Upload the file directly to S3 using the pre-signed URL.

    This is like actually delivering the package to the address we got earlier.
    We use a PUT request (which means "store this file here") with curl.

    Args:
        file_path: Path to the signed IPA file on disk
        upload_url: The pre-signed URL from step 1

    Returns:
        True if upload succeeded, False otherwise
    """
    try:
        print(f"Uploading file: {file_path}")
        print(f"File size: {os.path.getsize(file_path) / (1024*1024):.2f} MB")

        # Use curl to upload the file with PUT method
        # -X PUT: Use PUT HTTP method (required for S3 uploads)
        # -T: Upload file from this path
        # --progress-bar: Show a nice progress indicator
        result = run_process(
            "curl",
            "-X", "PUT",
            "-T", str(file_path),
            "--progress-bar",
            upload_url,
            check=True,
            capture=False  # Let curl show progress to console
        )

        print("✓ File uploaded successfully to S3")
        return True
    except Exception as e:
        print(f"Failed to upload file to S3: {e}")
        return False


def complete_signed_ipa_upload(s3_key: str) -> bool:
    """
    Step 3: Notify the server that the upload is complete.

    This is like confirming with the server that "Hey, I've delivered the package
    to the address you gave me, it's there now!" The server will then verify
    the file exists and update the database.

    Args:
        s3_key: The S3 key from step 1 (where the file was stored)

    Returns:
        True if completion was successful, False otherwise
    """
    try:
        result = webhook_request("ipa/upload/complete", {
            "s3_key": s3_key,
            "job_id": job_id
        })
        response_data = json.loads(decode_clean(result.stdout))

        if response_data.get("code") == 1:
            print("✓ Upload completion confirmed by server")
            return True
        else:
            print(f"Failed to complete upload: {response_data.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"Failed to complete IPA upload: {e}")
        return False


def upload_signed_ipa(file_path: str) -> bool:
    """
    Complete 3-step process to upload a signed IPA file.

    This function handles the entire upload workflow:
    1. Get a pre-signed URL from the server (like getting a delivery address)
    2. Upload the file directly to S3 (like delivering the package)
    3. Notify the server that upload is complete (like confirming delivery)

    Args:
        file_path: Path to the signed IPA file

    Returns:
        True if all steps succeeded, False if any step failed
    """
    print("Starting IPA upload process...")

    # Step 1: Get upload URL
    print("Step 1/3: Requesting upload URL...")
    report_progress(86, "Requesting upload URL from server")
    init_response = initiate_ipa_upload()
    if not init_response:
        print("✗ Failed to get upload URL")
        return False

    upload_url = init_response.get("upload_url")
    s3_key = init_response.get("s3_key")
    expires_in = init_response.get("expires_in", 900)

    print(f"Upload URL expires in {expires_in // 60} minutes")

    # Step 2: Upload file to S3
    print("Step 2/3: Uploading file to S3...")
    report_progress(88, "Uploading signed IPA to storage")
    if not upload_file_to_s3(file_path, upload_url):
        print("✗ Failed to upload file")
        return False

    # Step 3: Complete the upload
    print("Step 3/3: Confirming upload with server...")
    report_progress(94, "Confirming upload completion")
    if not complete_signed_ipa_upload(s3_key):
        print("✗ Failed to complete upload")
        return False

    print("✓ IPA upload completed successfully!")
    return True
