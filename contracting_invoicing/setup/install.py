# Copyright (c) 2026, Arslan
"""Install / migrate entry points. Everything here must be idempotent."""

from contracting_invoicing.setup.accounts import create_accounts, create_roles
from contracting_invoicing.setup.custom_fields import sync_custom_fields


def after_install():
    create_roles()
    sync_custom_fields()
    create_accounts()


def after_migrate():
    create_roles()
    sync_custom_fields()
    create_accounts()
