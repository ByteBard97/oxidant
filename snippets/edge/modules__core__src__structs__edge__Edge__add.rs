
let self_rc = Rc::new(RefCell::new(self.clone()));
if !Rc::ptr_eq(&self.source, &self.target) {
    self.source.borrow_mut().out_edges.push(self_rc.clone());
    self.target.borrow_mut().in_edges.push(self_rc);
} else {
    self.source.borrow_mut().self_edges.push(self_rc);
}