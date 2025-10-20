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


def report_certificate_status(status: str, message: str = "", cert_data: Optional[str] = None):
    """Report certificate generation status to server."""
    try:
        data = {
            "job_id": job_id,
            "status": status,
            "message": message
        }
        if cert_data:
            data["certificate_data"] = cert_data

        webhook_request("certificate/status", data)
        print(f"Certificate status reported: {status} - {message}")
    except Exception as e:
        print(f"Failed to report certificate status: {e}")


def report_profile_status(status: str, message: str = "", profile_data: Optional[str] = None):
    """Report provisioning profile generation status to server."""
    try:
        data = {
            "job_id": job_id,
            "status": status,
            "message": message
        }
        if profile_data:
            data["profile_data"] = profile_data

        webhook_request("profile/status", data)
        print(f"Profile status reported: {status} - {message}")
    except Exception as e:
        print(f"Failed to report profile status: {e}")


def complete_job(output_path: str, file_size: int = 0):
    """Mark job as completed."""
    try:
        webhook_request("job/complete", {
            "job_id": job_id,
            "output_path": output_path,
            "file_size": file_size,
            "status": "completed",
            "message": "Job completed successfully"
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

def get_bundle_id_mapping(account_id: str, original_bundle_id: str):
    """Get existing bundle ID mapping for an account and original bundle ID."""
    try:
        result = webhook_request("bundle/get", {
            "account_id": account_id,
            "original_bundle_id": original_bundle_id
        })
        response_data = json.loads(decode_clean(result.stdout))
        
        if response_data.get("code") == 1:
            return response_data.get("data", {}).get("mapped_bundle_id")
        return None
    except Exception as e:
        print(f"Failed to get bundle ID mapping: {e}")
        return None


def store_bundle_id_mapping(account_id: str, original_bundle_id: str, mapped_bundle_id: str, app_type: str = "main"):
    """Store bundle ID mapping for future reuse."""
    try:
        webhook_request("bundle/store", {
            "account_id": account_id,
            "original_bundle_id": original_bundle_id,
            "mapped_bundle_id": mapped_bundle_id,
            "app_type": app_type,
            "job_id": job_id
        })
        print(f"Bundle ID mapping stored: {original_bundle_id} -> {mapped_bundle_id}")
    except Exception as e:
        print(f"Failed to store bundle ID mapping: {e}")


def get_app_extensions(account_id: str, main_bundle_id: str):
    """Get all extensions associated with a main app bundle ID."""
    try:
        result = webhook_request("bundle/extensions", {
            "account_id": account_id,
            "main_bundle_id": main_bundle_id
        })
        response_data = json.loads(decode_clean(result.stdout))
        
        if response_data.get("code") == 1:
            return response_data.get("data", {}).get("extensions", [])
        return []
    except Exception as e:
        print(f"Failed to get app extensions: {e}")
        return []


def store_app_extension(account_id: str, main_bundle_id: str, extension_bundle_id: str, extension_type: str):
    """Store app extension relationship."""
    try:
        webhook_request("bundle/extension/store", {
            "account_id": account_id,
            "main_bundle_id": main_bundle_id,
            "extension_bundle_id": extension_bundle_id,
            "extension_type": extension_type,
            "job_id": job_id
        })
        print(f"Extension relationship stored: {main_bundle_id} -> {extension_bundle_id} ({extension_type})")
    except Exception as e:
        print(f"Failed to store extension relationship: {e}")


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
