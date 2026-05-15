
let self_ptr = self as *const Edge;
if !Rc::ptr_eq(&self.source, &self.target) {
    self.source
        .borrow_mut()
        .out_edges
        .retain(|e| e.as_ptr() as *const Edge != self_ptr);
    self.target
        .borrow_mut()
        .in_edges
        .retain(|e| e.as_ptr() as *const Edge != self_ptr);
} else {
    self.source
        .borrow_mut()
        .self_edges
        .retain(|e| e.as_ptr() as *const Edge != self_ptr);
}