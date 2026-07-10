import hashlib
import secrets

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"

def verify_password(password, stored_hash):
    if '$' not in stored_hash:
        return False
    salt, _ = stored_hash.split('$', 1)
    return hash_password(password, salt) == stored_hash

# Test with existing users
stored_thiro = "f6c7cec3caa0abc8ac664a2d0de46998$d2032774d63dd2ad529583520d3d5411719ba35668129ae1a04e836571597466"
stored_thiroshika = "0dbdd75dd55cdb52c7e7a8f1b06b706d$49eedc41e904e04fdc29fb2bf373fd7b603745b62624c104bbf8e3ff5852a819"

print("Testing thiro with 'password':", verify_password("password", stored_thiro))
print("Testing thiroshika with 'test123':", verify_password("test123", stored_thiroshika))

# Let's also see what the hash SHOULD be
salt_thiro = "f6c7cec3caa0abc8ac664a2d0de46998"
computed = hashlib.sha256((salt_thiro + "password").encode()).hexdigest()
print(f"\nExpected hash for thiro: {computed}")
print(f"Stored hash for thiro:  d2032774d63dd2ad529583520d3d5411719ba35668129ae1a04e836571597466")

# Generate new hashes
new_thiro = hash_password("password")
new_thiroshika = hash_password("test123")
print(f"\nNew hash for thiro: {new_thiro}")
print(f"New hash for thiroshika: {new_thiroshika}")
