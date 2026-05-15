self.a[1] = candidate.clone();
let mut j = 1usize;
let mut i = 2usize;
let mut done = false;
while (i as f64) < self.heap_size && !done {
    done = true;
    let left_son: serde_json::Value = self.a[i].clone();
    let right_son: serde_json::Value = self.a[i + 1].clone();
    let compare_result: bool = self.less(left_son.clone(), right_son.clone());
    if compare_result {
        if self.less(left_son.clone(), candidate.clone()) {
            self.a[j] = left_son;
            self.a[i] = candidate.clone();
            done = false;
            j = i;
            i = j << 1;
        }
    } else {
        if self.less(right_son.clone(), candidate.clone()) {
            self.a[j] = right_son;
            self.a[i + 1] = candidate.clone();
            done = false;
            j = i + 1;
            i = j << 1;
        }
    }
}

if (i as f64) == self.heap_size {
    let left_son: serde_json::Value = self.a[i].clone();
    if self.less(left_son.clone(), candidate.clone()) {
        self.a[j] = left_son;
        self.a[i] = candidate;
    }
}
