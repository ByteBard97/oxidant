let sources: Vec<serde_json::Value> = self.in_edges[n as usize]
    .iter()
    .filter_map(|e| e.get("source").cloned())
    .collect();
serde_json::Value::Array(sources)
