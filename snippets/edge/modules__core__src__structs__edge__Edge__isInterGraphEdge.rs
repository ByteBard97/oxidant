let source_parent = self.source.borrow()._parent.clone();
let target_parent = self.target.borrow()._parent.clone();
match (&source_parent, &target_parent) {
    (Some(sp), Some(tp)) => !Rc::ptr_eq(sp, tp),
    (None, None) => false,
    _ => true,
}