# iOS App Signing Library

This library provides a modular approach to iOS app signing, breaking down the complex signing process into manageable, well-organized modules.

## 📁 Module Structure

### `utils.py` - Core Utilities
**What it does:** Contains helper functions used throughout the signing process
- File operations (reading, extracting, archiving)
- Process execution with error handling
- Data conversion and manipulation
- Bundle ID generation from email addresses

**Key functions:**
- `safe_glob()` - Safely iterate through files
- `run_process()` - Execute commands with proper error handling
- `extract_zip()`, `archive_zip()` - Handle ZIP archives
- `plist_load()`, `plist_dump()` - Work with property list files
- `generate_bundle_id_from_email()` - Create unique app identifiers

### `security.py` - Security & Keychain Management
**What it does:** Handles all security-related operations
- Keychain creation and management
- Certificate importing and validation
- Provisioning profile operations
- Code signing preparation

**Key functions:**
- `security_import()` - Import certificates into keychain
- `security_remove_keychain()` - Clean up keychains
- `dump_prov_entitlements()` - Extract entitlements from profiles
- `codesign_async()` - Start code signing processes

### `webhooks.py` - API Communication
**What it does:** Manages communication with the signing service
- Progress reporting during signing
- Job status updates
- Certificate and profile status reporting
- Error reporting and job completion

**Key functions:**
- `report_progress()` - Update job progress
- `complete_job()` - Mark job as successful
- `fail_job()` - Report job failures
- `get_job_info()` - Retrieve job details from server

### `fastlane_integration.py` - Apple Developer Portal
**What it does:** Interfaces with Apple's Developer Portal through Fastlane
- Developer account authentication (including 2FA)
- App registration and service configuration
- Provisioning profile generation
- Certificate management

**Key functions:**
- `fastlane_auth()` - Authenticate with Apple
- `fastlane_register_app()` - Register app and configure services
- `fastlane_get_prov_profile()` - Generate provisioning profiles

### `tweak_injection.py` - Tweak & Framework Injection
**What it does:** Handles injection of tweaks and additional frameworks
- Extract and process tweak packages (.deb, .zip, .tar)
- Inject dynamic libraries and frameworks
- Handle dependency linking and path resolution
- Support for Cydia Substrate and other hooking frameworks

**Key functions:**
- `inject_tweaks()` - Main tweak injection process
- `extract_deb()` - Extract Debian packages with filtering

### `signer.py` - Main Signing Logic
**What it does:** Orchestrates the entire signing process
- Component preparation and entitlement processing
- Bundle ID management and remapping
- Binary patching for identifier changes
- Coordinated signing of all app components

**Key classes:**
- `Signer` - Main signing orchestrator
- `SignOpts` - Configuration options
- `ComponentData` - Component signing information

## 🚀 Usage Example

```python
from lib import Signer, SignOpts, report_progress

# Configure signing options
opts = SignOpts(
    app_dir=Path("MyApp.app"),
    common_name="Apple Development",
    team_id="ABCD123456",
    account_name="developer@example.com",
    account_pass="password",
    prov_file=None,  # Will generate automatically
    bundle_id="com.example.myapp",
    bundle_name="My App",
    patch_debug=True,
    patch_all_devices=True,
    patch_mac=False,
    patch_file_sharing=False,
    encode_ids=True,
    patch_ids=False,
    force_original_id=False
)

# Report progress
report_progress(10, "Starting signing process")

# Create and run signer
signer = Signer(opts)
signer.sign()

report_progress(100, "Signing completed")
```

## 🔧 Benefits of Modular Structure

1. **Maintainability**: Each module has a single responsibility
2. **Testability**: Individual modules can be tested in isolation
3. **Reusability**: Modules can be imported and used independently
4. **Readability**: Code is organized logically and easier to understand
5. **Debugging**: Issues can be traced to specific modules
6. **Extensibility**: New features can be added without affecting other modules

## 📝 Simple Explanation

Think of this like organizing your school supplies:

- **Before**: Everything was in one big messy backpack (the original large file)
- **After**: Now we have separate folders for different subjects:
  - 📁 Math folder (`utils.py`) - Basic tools everyone needs
  - 📁 Science folder (`security.py`) - Special security equipment
  - 📁 Art folder (`webhooks.py`) - Communication and presentation tools
  - 📁 History folder (`fastlane_integration.py`) - Dealing with Apple's systems
  - 📁 PE folder (`tweak_injection.py`) - Adding extra features to apps
  - 📁 Main notebook (`signer.py`) - Coordinates everything together

Each folder contains related tools, making it easy to find what you need and keep everything organized!

## 🛠 Development Notes

- All modules follow Python best practices with proper docstrings
- Error handling is consistent across modules
- Type hints are used for better code clarity
- Each module can be imported independently
- The main `sign.py` file now serves as a clean entry point
