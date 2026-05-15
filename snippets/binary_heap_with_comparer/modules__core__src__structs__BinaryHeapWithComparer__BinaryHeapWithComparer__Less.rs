
let cmp_result = self.compare.clone();
if let Some(n) = cmp_result.as_i64() {
    n < 0
} else {
    false
}