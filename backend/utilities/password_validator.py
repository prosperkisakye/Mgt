import re
from django.core.exceptions import ValidationError

def validate_password_strength(password):
    """
    Validate that the password meets the minimum strength requirements:
    - At least 8 characters long
    - Contains at least one digit
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter
    - Contains at least one special character
    """
    if len(password) < 8:
        raise ValidationError({"error": "Password must be at least 8 characters long."})
    
    if not re.search(r'\d', password):
        raise ValidationError({"error": "Password must contain at least one digit."})
    
    if not re.search(r'[A-Z]', password):
        raise ValidationError({"error": "Password must contain at least one uppercase letter."})
    
    if not re.search(r'[a-z]', password):
        raise ValidationError({"error": "Password must contain at least one lowercase letter."})
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError({"error": "Password must contain at least one special character."})
    
    return password