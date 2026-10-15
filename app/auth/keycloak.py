"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from fastapi_keycloak import FastAPIKeycloak

from ..core.config import TenantSettings


def build_idp(tenant_settings: TenantSettings) -> FastAPIKeycloak | None:
    """Build a Keycloak IDP for a tenant, or return None when disabled.

    ``FastAPIKeycloak.__init__`` eagerly calls ``_get_admin_token()`` (sync HTTP).
    We only use ``public_key`` / ``client_id`` for JWT verify, so skip that admin
    login — an unreachable IdP must not block tenant load (or CI).
    """
    if tenant_settings.auth_mode != "keycloak":
        return None

    idp = FastAPIKeycloak.__new__(FastAPIKeycloak)
    idp.server_url = tenant_settings.keycloak_url
    idp.realm = tenant_settings.keycloak_realm
    idp.client_id = tenant_settings.keycloak_client_id
    idp.client_secret = tenant_settings.keycloak_client_secret
    idp.admin_client_id = tenant_settings.keycloak_admin_client_id
    idp.admin_client_secret = tenant_settings.keycloak_admin_client_secret
    idp.callback_uri = tenant_settings.keycloak_callback_uri
    idp.timeout = 10
    idp.scope = "openid profile email"
    idp.ssl_verification = True
    idp.algorithms = None
    idp._admin_token = None
    return idp
