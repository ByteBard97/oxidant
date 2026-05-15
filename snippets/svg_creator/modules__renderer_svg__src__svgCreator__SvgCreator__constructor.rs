
    let dummy_node_collection = Rc::new(RefCell::new(crate::node_collection::NodeCollection {
        node_map: std::collections::HashMap::new(),
    }));
    let dummy_graph = Rc::new(RefCell::new(crate::graph::Graph {
        node_collection: dummy_node_collection,
    }));
    Self {
        rubber_edge: serde_json::Value::Null,
        node_insertion_circle: serde_json::Value::Null,
        edge_insertion_port_elem: serde_json::Value::Null,
        svg: serde_json::Value::Null,
        super_trans_group: serde_json::Value::Null,
        transform_group: serde_json::Value::Null,
        graph: dummy_graph,
        _text_measurer: serde_json::Value::Null,
        container,
        get_smoothed_polyline_radius: serde_json::Value::Null,
    }