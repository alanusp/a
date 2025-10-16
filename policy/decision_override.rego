package fraudstack.decision

default action = "model"

action := "override" {
    input.metrics.p95_latency_ms > data.thresholds.max_latency_ms
}

action := "override" {
    input.metrics.alert_rate > data.thresholds.max_alert_rate
}

