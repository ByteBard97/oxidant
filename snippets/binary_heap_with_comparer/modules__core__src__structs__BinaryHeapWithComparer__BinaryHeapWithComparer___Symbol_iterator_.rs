let mut result = Vec::new();
let heap_size_usize = self.heap_size as usize;
for i in 1..=heap_size_usize {
    if i < self.a.len() {
        result.push(self.a[i].clone());
    }
}
serde_json::Value::Array(result)
