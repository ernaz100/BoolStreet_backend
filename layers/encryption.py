"""Encryption utilities for securely storing API keys and secrets."""

import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Get encryption key from environment variable or generate one
# In production, this should be set in environment variables
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

# If no key is provided, generate one (for development only)
# WARNING: In production, you MUST set ENCRYPTION_KEY in environment variables
# If you lose the key, you cannot decrypt existing encrypted data
if not ENCRYPTION_KEY:
    # Generate a key for development (this will be different each time the server restarts)
    # In production, use: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    print("WARNING: No ENCRYPTION_KEY found in environment. Generating a temporary key for development.")
    print("WARNING: This key will not persist across restarts. Set ENCRYPTION_KEY in .env for production.")
    ENCRYPTION_KEY = Fernet.generate_key()  # Keep as bytes
else:
    # Convert string from environment variable to bytes
    ENCRYPTION_KEY = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY

# Initialize Fernet cipher with the key
try:
    cipher = Fernet(ENCRYPTION_KEY)
except Exception as e:
    raise ValueError(f"Invalid encryption key format: {e}. Generate a new key using: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")


def encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext string.
    
    Args:
        plaintext: The string to encrypt
        
    Returns:
        Encrypted string (base64 encoded)
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty string")
    
    encrypted_bytes = cipher.encrypt(plaintext.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')


def decrypt(ciphertext: str) -> str:
    """
    Decrypt an encrypted string.
    
    Args:
        ciphertext: The encrypted string to decrypt
        
    Returns:
        Decrypted plaintext string
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty string")
    
    try:
        decrypted_bytes = cipher.decrypt(ciphertext.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}. The encrypted data may be corrupted or the encryption key may be incorrect.")


def mask_secret(secret: str, show_first: int = 4, show_last: int = 4) -> str:
    """
    Mask a secret string by showing only first and last characters.
    
    Args:
        secret: The secret string to mask
        show_first: Number of characters to show at the beginning
        show_last: Number of characters to show at the end
        
    Returns:
        Masked string (e.g., "abcd...xyz")
    """
    if not secret:
        return ""
    
    if len(secret) <= show_first + show_last:
        # If secret is too short, just show asterisks
        return "*" * len(secret)
    
    return f"{secret[:show_first]}...{secret[-show_last:]}"

