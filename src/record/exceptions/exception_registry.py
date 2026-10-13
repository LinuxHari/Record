from typing import Mapping
from pydantic import validate_call, ConfigDict

from record.app.user.models import CONSTRAINT_EXCEPTIONS as USER_CONSTRAINT_EXCEPTIONS

@validate_call(config=ConfigDict(strict=True))
def _merge_constraint_exceptions(
    *registries: Mapping[str, Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    merged: dict[str, Mapping[str, str]] = {}
    for registry in registries:
        duplicates = merged.keys() & registry.keys()
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate database constraint error mapping(s): {names}")
        merged.update(registry)
    return merged


CONSTRAINT_EXCEPTIONS = _merge_constraint_exceptions(USER_CONSTRAINT_EXCEPTIONS)
