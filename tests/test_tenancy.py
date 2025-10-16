from app.core.tenancy import TenantResolver


def test_tenant_resolution_from_api_key():
    resolver = TenantResolver({"api-key-1": "alpha"})
    tenant = resolver.resolve({"X-API-Key": "api-key-1"})
    assert tenant.tenant_id == "alpha"
    assert tenant.key("foo") == "alpha:foo"


def test_tenant_resolution_default():
    resolver = TenantResolver({})
    tenant = resolver.resolve({})
    assert tenant.tenant_id == "public"
    assert tenant.metrics_namespace == "tenant.public"
