#!/usr/bin/env python3
"""
iOS App Signing Library

This library provides modular components for iOS app signing, including:
- Utility functions for file operations and process execution
- Security and keychain management
- Fastlane integration for Apple Developer Portal operations
- Tweak injection capabilities
- Webhook communication with signing services
- Core signing logic and orchestration

The library is organized into separate modules for better maintainability:
- utils: Core utility functions
- security: Keychain and certificate management
- fastlane_integration: Apple Developer Portal operations
- tweak_injection: Tweak and framework injection
- webhooks: API communication
- signer: Main signing orchestration

Example usage:
    from lib.signer import Signer, SignOpts
    from lib.webhooks import report_progress
    
    # Configure signing options
    opts = SignOpts(...)
    
    # Create and run signer
    signer = Signer(opts)
    signer.sign()
"""

# Import main classes and functions for easy access
from .signer import Signer, SignOpts, ComponentData, RemapDef
from .webhooks import (
    report_progress,
    complete_job, fail_job, get_job_info,
    upload_signed_ipa
)
from .utils import rand_str, read_file
from .security import security_import, security_remove_keychain
from .tweak_injection import inject_tweaks

__version__ = "1.0.0"
__author__ = "iOS Signer Team"

__all__ = [
    # Main classes
    'Signer', 'SignOpts', 'ComponentData', 'RemapDef',
    
    # Webhook functions
    'report_progress', 'report_certificate_status', 'report_profile_status',
    'complete_job', 'fail_job', 'get_job_info', 'upload_signed_ipa',
    
    # Utility functions
    'generate_bundle_id_from_email', 'rand_str', 'read_file',
    
    # Security functions
    'security_import', 'security_remove_keychain',
    
    # Tweak injection
    'inject_tweaks',
]
