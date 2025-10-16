package fraudstack.admission

default allow = false

default deny = []

allow {
    input.schema_version == data.config.allowed_schema_version
    some tenant
    tenant := data.config.allowed_tenants[_]
    input.request_tenant == tenant
}

deny[msg] {
    input.schema_version != data.config.allowed_schema_version
    msg := "schema_version mismatch"
}

