# Consul server configuration
datacenter = "talkie"
data_dir = "/consul/data"
log_level = "INFO"

# Server configuration
server = true
bootstrap_expect = 1
ui_config {
  enabled = true
}

# Network configuration
client_addr = "0.0.0.0"
bind_addr = "0.0.0.0"

# Ports: DNS on 8600 to avoid binding to 53 (requires root in rootless Podman)
ports {
  http = 8500
  dns = 8600
  grpc = 8502
}

# Performance tuning
performance {
  raft_multiplier = 1
}

# ACLs (disabled for development, enable for production)
# acl {
#   enabled = true
#   default_policy = "deny"
#   enable_token_persistence = true
# }
