from typing import Mapping
from pydantic import validate_call, ConfigDict

from record.user.errors import CONSTRAINT_ERRORS as USER_CONSTRAINT_ERRORS

@validate_call(config=ConfigDict(strict=True))
def _merge_constraint_errors(*registries: Mapping[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for registry in registries:
        duplicates = merged.keys() & registry.keys()
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate database constraint error mapping(s): {names}")
        merged.update(registry)
    return merged


CONSTRAINT_ERRORS = _merge_constraint_errors(USER_CONSTRAINT_ERRORS)
