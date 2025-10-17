# iOS App Signing Tools

## Description
This GitHub Action automatically signs iOS IPA files using Apple Developer certificates and provisioning profiles. It integrates with a backend server through webhook APIs to provide real-time progress tracking and job management.

## Features
- **Automated IPA Signing**: Signs iOS apps with proper certificates and provisioning profiles
- **Real-time Progress Tracking**: Reports signing progress through webhook APIs
- **Certificate Management**: Automatically generates and manages Apple Developer certificates
- **Provisioning Profile Generation**: Creates device-specific provisioning profiles
- **Direct S3 Integration**: Downloads IPA files directly from S3 URLs
- **Dynamic Bundle ID Generation**: Generates bundle IDs in format `com.hs.xx` based on developer email
- **No Legacy Dependencies**: Works without job.tar, cert_pass.txt or other legacy files
- **Error Handling**: Comprehensive error reporting and retry mechanisms
- **Tweak Injection**: Supports injecting tweaks and modifications into apps

## Environment Variables

### Required
- `JOB_ID`: Unique identifier for the signing job
- `API_TOKEN`: Authentication token for webhook API calls
- `SECRET_URL`: Base URL of the backend server

### Optional
- `SECRET_KEY`: Legacy authentication key (for backward compatibility)

## Webhook Integration

The signing tool communicates with the backend server through the following webhook endpoints:

### Job Management
- `POST /api/v1/webhook/job/start` - Fetch comprehensive job information
- `POST /api/v1/webhook/job/progress` - Report signing progress
- `POST /api/v1/webhook/job/complete` - Mark job as completed
- `POST /api/v1/webhook/job/fail` - Report job failure

### Certificate & Profile Management
- `POST /api/v1/webhook/certificate/status` - Report certificate generation status
- `POST /api/v1/webhook/profile/status` - Report provisioning profile status

## Usage

### Triggering a Signing Job

The GitHub Action is triggered via workflow dispatch with a job ID:

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/owner/repo/actions/workflows/sign.yml/dispatches \
  -d '{"ref":"main","inputs":{"job_id":"your-job-id-here"}}'
```

### Job Information Fetch

```sh
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Token: your-api-token" \
  -d '{"job_id": "5c9806a5-e3eb-4ce4-bcdb-4e1b5d39ef2e"}' \
  http://localhost:7020/api/v1/webhook/job/start
```

## Job Data

```json
{
    "code": 1,
    "message": "Job information retrieved successfully",
    "data": {
        "job": {
            "id": "f55aa862-0216-490b-95c8-f89466800504",
            "job_id": "5c9806a5-e3eb-4ce4-bcdb-4e1b5d39ef2e",
            "job_type": "ipa_signing",
            "code_id": "TQ2C-STFX-3UGX",
            "device_udid": "00008101-001451CC0E01001E",
            "account_id": "46cdeb45-4428-4c0a-be26-410e7d0aa1e8",
            "ipa_id": "a2cb4a5f-f7d0-4521-a892-09c52d14ca23",
            "input_path": "https://s3.cn-south-1.qiniucs.com/appss/uploads/2025-10-13/31a633d3-d5a4-46aa-93cc-08905151a151.ipa?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Checksum-Mode=ENABLED&X-Amz-Credential=LwtcvPzxpFKf91wwEJchT7bUJ7S-n65Hi-7mFasG%2F20251017%2Fcn-south-1%2Fs3%2Faws4_request&X-Amz-Date=20251017T081350Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&x-id=GetObject&X-Amz-Signature=fbff9f1c0a251b482d975e58c9857dedbdef2d1aa78206a0353ebcc9b5297710",
            "output_path": "",
            "progress": 0,
            "state": 0,
            "message": "",
            "error_details": "",
            "started_time": "0001-01-01T00:00:00Z",
            "completed_time": "0001-01-01T00:00:00Z",
            "created_time": "2025-10-16T23:11:02+08:00",
            "updated_time": "2025-10-16T23:11:02+08:00"
        },
        "account": {
            "name": "",
            "email": "damoncoo@gmail.com",
            "password": "uD7q58FjwIaeqhBdeHfk0g==",
            "uuid": "46cdeb45-4428-4c0a-be26-410e7d0aa1e8",
            "max_devices": 100,
            "current_devices": 1,
            "last_sync_time": "0001-01-01T00:00:00Z",
            "status": "active",
            "error_message": "",
            "created_time": "2025-10-14T16:40:48+08:00",
            "expired_time": "0001-01-01T00:00:00Z",
            "updated_time": "2025-10-14T18:06:51+08:00"
        },
        "ipa": {
            "id": "a2cb4a5f-f7d0-4521-a892-09c52d14ca23",
            "name": "\u5c0f\u8349",
            "message": "",
            "version": "2.3.6",
            "bundle_id": "com.cl.NewT66y.2023",
            "icon": "",
            "size": 1563395,
            "created_time": "2025-10-13T23:55:57+08:00"
        },
        "redeem_code": {
            "id": "e42967f4-efaa-4a45-973a-dba38c394ea1",
            "code": "TQ2C-STFX-3UGX",
            "status": "used",
            "duration": 365,
            "purchased_time": "2025-10-13T10:31:52+08:00",
            "redeemed_time": "0001-01-01T00:00:00Z",
            "expired_time": "2026-10-13T10:31:52+08:00",
            "created_time": "2025-10-13T10:31:52+08:00",
            "updated_time": "2025-10-13T10:31:52+08:00"
        }
    }
}
```


## Key Improvements

### Bundle ID Generation
The system automatically generates bundle IDs in the format `com.hs.xx` where `xx` is derived from the developer's email address:
- Extracts username from email (part before @)
- Creates MD5 hash of username
- Uses first 6 characters as the suffix
- Example: `damoncoo@gmail.com` → `com.hs.a1b2c3`

### Direct S3 Integration
- Downloads IPA files directly from S3 URLs provided in job data
- No dependency on legacy job archive files
- Supports pre-signed URLs with authentication parameters
- Fallback to legacy download method for backward compatibility

### Streamlined Configuration
- No more dependency on `job.tar`, `cert_pass.txt`, or other legacy files
- All configuration comes from webhook job data
- Account credentials handled securely with base64 decoding
- Team ID extracted from account UUID

## Signing Process

The signing process follows these steps with real-time progress reporting:

1. **Job Initialization (5%)** - Fetch comprehensive job information from server via webhook
2. **Bundle ID Generation** - Generate `com.hs.xx` format bundle ID from developer email
3. **IPA Download** - Download IPA directly from S3 URL or legacy endpoint
4. **Keychain Setup (10%)** - Create and configure signing keychain
5. **Certificate Validation (15%)** - Validate or generate code signing certificates
6. **IPA Extraction (20%)** - Extract the unsigned IPA file
7. **Tweak Injection (25%)** - Inject any tweaks or modifications (if applicable)
8. **Signing Process (30-80%)** - Sign all app components with certificates
9. **Apple Developer Authentication (40%)** - Authenticate with Apple Developer Portal
10. **Certificate Generation** - Generate signing certificates (reported via webhook)
11. **Provisioning Profile Creation** - Create device-specific profiles (reported via webhook)
12. **App Packaging (85%)** - Package the signed application
13. **Upload (90%)** - Upload signed IPA to server
14. **Completion (100%)** - Mark job as completed

## Progress Tracking

Progress is reported at key milestones:
- **5%**: Job initialization
- **10%**: Keychain setup
- **15%**: Certificate validation
- **20%**: IPA extraction
- **25%**: Tweak injection (if applicable)
- **30%**: Signing process start
- **40%**: Apple Developer authentication
- **50-80%**: Component signing progress
- **85%**: App packaging
- **90%**: Upload start
- **100%**: Job completion

## Error Handling

The system includes comprehensive error handling:
- **Automatic Retry**: Transient failures are automatically retried
- **Detailed Logging**: All errors are logged with full stack traces
- **Webhook Reporting**: Failures are reported to server with error details
- **Graceful Cleanup**: Keychains and temporary files are cleaned up on exit

## Security

- **Token Authentication**: All webhook calls use secure API token authentication
- **Encrypted Passwords**: Apple Developer passwords are encrypted in transit
- **Secure Keychain**: Temporary keychains are created with secure passwords
- **Clean Exit**: All sensitive data is cleaned up after job completion

## Utility Functions

### AES Decryption Function

The project includes a utility function for decrypting AES 256 CBC encrypted data with PKCS7 padding:

```python
from utils import decrypt_aes_256_cbc_pkcs7

# Decrypt encrypted data
decrypted_text = decrypt_aes_256_cbc_pkcs7(
    encrypted_data="uD7q58FjwIaeqhBdeHfk0g==",  # Base64 encoded encrypted data
    key_string="pv3kd093jd9lep830d93lo93e99e933k",  # Key as UTF-8 string
    iv_string="pv3kd093jd9lep83"  # IV as UTF-8 string
)
```

**Function Parameters:**
- `encrypted_data`: The encrypted data (can be base64 string or bytes)
- `key_string`: The encryption key as UTF-8 string
- `iv_string`: The initialization vector as UTF-8 string

**Requirements:**
- Either `cryptography` or `pycryptodome` library must be installed
- Install with: `pip install cryptography`

**How it works:**
1. Converts the UTF-8 key string to a 32-byte AES key using SHA-256
2. Converts the UTF-8 IV string to a 16-byte IV using MD5
3. Decodes base64 data if provided as string
4. Decrypts using AES 256 CBC mode
5. Removes PKCS7 padding
6. Returns the decrypted text as a UTF-8 string

This function is used to decrypt Apple Developer account passwords and other sensitive data in the signing process.

## Webhook API Reference

### Authentication
All webhook requests must include the `X-API-Token` header:
```
X-API-Token: your-api-token-here
```

### Request/Response Format
All requests and responses use JSON format with the following structure:

**Request:**
```json
{
  "job_id": "uuid",
  "additional_fields": "..."
}
```

**Response:**
```json
{
  "code": 1,
  "message": "Success message",
  "data": {}
}
```

### Endpoint Details

#### Job Progress Updates
```bash
POST /api/v1/webhook/job/progress
Content-Type: application/json
X-API-Token: your-token

{
  "job_id": "uuid",
  "progress": 50,
  "state": 1,
  "message": "Signing in progress"
}
```

#### Certificate Status Updates
```bash
POST /api/v1/webhook/certificate/status
Content-Type: application/json
X-API-Token: your-token

{
  "job_id": "uuid",
  "status": "completed",
  "message": "Certificate generated successfully",
  "certificate_data": "base64-encoded-cert-data"
}
```

#### Profile Status Updates
```bash
POST /api/v1/webhook/profile/status
Content-Type: application/json
X-API-Token: your-token

{
  "job_id": "uuid",
  "status": "completed",
  "message": "Provisioning profile created",
  "profile_data": "base64-encoded-profile-data"
}
```

#### Job Completion
```bash
POST /api/v1/webhook/job/complete
Content-Type: application/json
X-API-Token: your-token

{
  "job_id": "uuid",
  "output_path": "signed/uuid/signed.ipa",
  "file_size": 52428800,
  "status": "completed",
  "message": "Job completed successfully"
}
```

#### Job Failure
```bash
POST /api/v1/webhook/job/fail
Content-Type: application/json
X-API-Token: your-token

{
  "job_id": "uuid",
  "message": "Signing failed: Certificate not found",
  "error_details": "Full stack trace here"
}
```

## Configuration

### GitHub Secrets Required
- `SECRET_URL`: Backend server URL
- `API_TOKEN`: Webhook authentication token
- `SECRET_KEY`: Legacy authentication key (optional)

### Workflow Inputs
- `job_id`: The unique identifier for the signing job to process

## Troubleshooting

### Common Issues

1. **Missing Environment Variables**: Ensure all required secrets are configured
2. **Authentication Failures**: Verify API_TOKEN is correct and has proper permissions
3. **Certificate Issues**: Check that valid certificates are available in the keychain
4. **Network Timeouts**: Increase timeout values for slow network connections

### Debug Mode
Enable debug logging by setting environment variable:
```bash
export PYTHONUNBUFFERED=1
```