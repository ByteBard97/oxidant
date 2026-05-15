
let v_idx = v as usize;
let mut edges = self.out_edges[v_idx].clone();
edges.extend(self.in_edges[v_idx].clone());
serde_json::Value::Array(edges)