import string
import secrets


def generate_compliant_password(length=12):
    if length < 8:
        raise ValueError("Password must be at least 8 characters long.")

    # Required components
    lower = secrets.choice(string.ascii_lowercase)
    upper = secrets.choice(string.ascii_uppercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice("!@#$%^&*()-_=+[]{};:,.<>?")

    # Remaining random characters
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{};:,.<>?"
    remaining = [secrets.choice(all_chars) for _ in range(length - 4)]

    # Combine and shuffle
    password_list = [lower, upper, digit, special] + remaining
    secrets.SystemRandom().shuffle(password_list)

    return "".join(password_list)
