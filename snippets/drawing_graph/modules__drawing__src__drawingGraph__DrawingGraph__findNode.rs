let gr = &self.graph;
let n = gr.borrow().find_node(id);
if n.is_none() {
    return Rc::new(RefCell::new(crate::drawing_node::DrawingNode::default()));
}
crate::drawing_object::DrawingObject::get_drawing_obj(n.unwrap())