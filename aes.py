import base64

def decrypt_aes_cbc_pkcs7(encrypted_data, key_string):
    """
    Decrypt AES CBC encrypted data with PKCS7 padding (matches Go AesEncrypt function)

    This function matches the Go encryption where:
    - The key is used directly as bytes
    - The IV is the first 16 bytes of the key (k[:blockSize])

    Parameters:
    - encrypted_data: The encrypted data (base64 string or bytes)
    - key_string: The encryption key as UTF-8 string

    Returns:
    - The decrypted text as a string

    Example:
    decrypted_text = decrypt_aes_cbc_pkcs7(
        "base64_encrypted_data_here",
        "your_key_string"
    )

    Note: This function requires either the 'cryptography' or 'pycryptodome' library to be installed.
    Install with: pip install cryptography
    """
    try:
        # Try to import cryptography library first (preferred)
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import padding
        except ImportError:
            raise Exception("'cryptography' library is not installed. Please install it with: pip install cryptography")

        # Step 1: Convert the key from string to bytes (matching Go code)
        # The Go code uses the key directly as bytes, and first 16 bytes as IV
        key = key_string.encode('utf-8')  # Convert to bytes

        # Ensure key is the right length (16, 24, or 32 bytes for AES)
        if len(key) not in [16, 24, 32]:
            # If key is not the right length, we need to pad or truncate
            if len(key) < 16:
                key = key.ljust(16, b'\0')  # Pad with null bytes
            elif len(key) < 24:
                key = key[:16]  # Use first 16 bytes for AES-128
            elif len(key) < 32:
                key = key[:24]  # Use first 24 bytes for AES-192
            else:
                key = key[:32]  # Use first 32 bytes for AES-256

        # IV is the first 16 bytes of the key (matching Go: k[:blockSize])
        iv = key[:16]

        # Step 2: If the encrypted data is a base64 string, convert it to bytes
        # This is like converting a coded message back to its original form
        if isinstance(encrypted_data, str):
            ciphertext = base64.b64decode(encrypted_data)
        else:
            ciphertext = encrypted_data

        # Step 3 & 4: Decrypt using the available library
            # Using cryptography library
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded_content = decryptor.update(ciphertext) + decryptor.finalize()

        # Step 5: Remove the padding
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext_bytes = unpadder.update(decrypted_padded_content) + unpadder.finalize()

        # Step 6: Convert the result back to readable text
        # This converts the unlocked message back to readable text
        plaintext = plaintext_bytes.decode('utf-8')

        return plaintext

    except Exception as e:
        raise Exception(f"Decryption failed: {str(e)}. Check your key, IV, and encrypted data.")

