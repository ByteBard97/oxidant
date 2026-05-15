let edges = &self.out_edges[n as usize];
let targets: Vec<serde_json::Value> = edges.iter()
    .map(|e| e["target"].clone())
    .collect();
serde_json::Value::Array(targets)
