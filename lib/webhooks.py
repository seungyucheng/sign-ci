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
