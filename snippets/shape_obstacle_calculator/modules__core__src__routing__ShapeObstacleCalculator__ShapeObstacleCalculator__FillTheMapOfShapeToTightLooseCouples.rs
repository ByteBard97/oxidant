
        let children: Vec<std::rc::Rc<std::cell::RefCell<crate::shape::Shape>>> =
            self.main_shape.borrow().children.iter().cloned().collect();
        let nodes: Vec<serde_json::Value> = children.iter()
            .map(|_s| {
                let shape_val = serde_json::Value::Null;
                let bbox_val = serde_json::Value::Null;
                crate::rectangle_node::mk_rectangle_node(shape_val, bbox_val)
            })
            .collect();
        let children_shape_hierarchy =
            crate::rectangle_node::create_rect_node_on_array_of_rect_nodes(nodes);
        crate::rectangle_node_utils::cross_rectangle_nodes(
            children_shape_hierarchy,
            self.couple_hierarchy.clone(),
            serde_json::Value::Null,
        );