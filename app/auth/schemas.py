"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AuthMethod = Literal["none", "keycloak", "basic"]


@dataclass(frozen=True)
class ApiUser:
    """Unified tenant API identity for all auth modes."""

    sub: str
    preferred_username: str
    auth_method: AuthMethod
    roles: frozenset[str] = frozenset()
    db_role: str | None = None

    @property
    def is_anonymous(self) -> bool:
        return self.auth_method == "none"

    def has_role(self, *names: str) -> bool:
        return any(role in self.roles for role in names)

    def has_any_role(self, names: Iterable[str]) -> bool:
        return bool(self.roles.intersection(names))

    @classmethod
    def anonymous(cls) -> "ApiUser":
        return cls(
            sub="anonymous",
            preferred_username="anonymous",
            auth_method="none",
        )


class GwapiRoleOut(BaseModel):
    name: str
    description: str | None = None


class GwapiUserOut(BaseModel):
    username: str
    db_role: str
    enabled: bool
    roles: list[str]
    created_at: datetime
    updated_at: datetime


class GwapiUserCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8)
    db_role: str | None = Field(default=None, description="PostgreSQL role for SET ROLE; defaults to username")
    enabled: bool = True
    roles: list[str] = Field(default_factory=lambda: ["basic"])


class GwapiUserUpdateIn(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    db_role: str | None = None
    enabled: bool | None = None
    roles: list[str] | None = None
