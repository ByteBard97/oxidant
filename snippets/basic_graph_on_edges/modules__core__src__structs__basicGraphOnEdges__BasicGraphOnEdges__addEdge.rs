
self.edges.push(e.clone());

if let (Some(source), Some(target)) = (
    e.get("source").and_then(|s| s.as_f64()),
    e.get("target").and_then(|t| t.as_f64())
) {
    if source != target {
        self.out_edges[source as usize].push(e.clone());
        self.in_edges[target as usize].push(e);
    } else {
        self.self_edges[source as usize].push(e);
    }
}