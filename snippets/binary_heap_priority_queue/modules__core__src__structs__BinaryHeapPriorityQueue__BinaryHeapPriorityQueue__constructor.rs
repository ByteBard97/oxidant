
let n_usize = n as usize;
Self {
    _priors: vec![0.0; n_usize],
    _heap: vec![0.0; n_usize + 1],
    _reverse_heap: vec![0.0; n_usize],
    heap_size: 0.0,
}