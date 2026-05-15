
self.edges = valEdges;
self.node_count = nov;
let n = nov as usize;
let mut out_edges_counts: Vec<usize> = vec![0usize; n];
let mut in_edges_counts: Vec<usize> = vec![0usize; n];
let mut self_edges_counts: Vec<usize> = vec![0usize; n];
self.out_edges = vec![vec![]; n];
self.in_edges = vec![vec![]; n];
self.self_edges = vec![vec![]; n];
let edges_clone = self.edges.clone();
for e in &edges_clone {
    let u = e["source"].as_f64().unwrap_or(0.0) as usize;
    let v = e["target"].as_f64().unwrap_or(0.0) as usize;
    if u != v {
        out_edges_counts[u] += 1;
        in_edges_counts[v] += 1;
    } else {
        self_edges_counts[u] += 1;
    }
}
for i in 0..n {
    self.out_edges[i] = vec![serde_json::Value::Null; out_edges_counts[i]];
    out_edges_counts[i] = 0;
    self.in_edges[i] = vec![serde_json::Value::Null; in_edges_counts[i]];
    in_edges_counts[i] = 0;
    self.self_edges[i] = vec![serde_json::Value::Null; self_edges_counts[i]];
    self_edges_counts[i] = 0;
}
for e in edges_clone {
    let u = e["source"].as_f64().unwrap_or(0.0) as usize;
    let v = e["target"].as_f64().unwrap_or(0.0) as usize;
    if u != v {
        self.out_edges[u][out_edges_counts[u]] = e.clone();
        out_edges_counts[u] += 1;
        self.in_edges[v][in_edges_counts[v]] = e;
        in_edges_counts[v] += 1;
    } else {
        self.self_edges[u][self_edges_counts[u]] = e;
        self_edges_counts[u] += 1;
    }
}