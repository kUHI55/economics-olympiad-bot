"""Version-controlled theory files and their validation contracts.

This package deliberately has no dependency on Telegram handlers or database models.
"""

from app.theory_data.validator import TheoryValidationError, validate_theory_repository

__all__ = ["TheoryValidationError", "validate_theory_repository"]
