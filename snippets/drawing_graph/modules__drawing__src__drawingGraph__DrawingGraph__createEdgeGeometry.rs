let drawing_edge = DrawingEdge::get_drawing_obj(e.clone())
    .unwrap_or_else(|| Rc::new(RefCell::new(DrawingEdge::new(e.clone(), true))));
let geom_edge = Rc::new(RefCell::new(GeomEdge::new(e.clone())));

if drawing_edge.borrow().arrowhead != ArrowTypeEnum::None {
    geom_edge.borrow_mut().target_arrowhead = Some(Arrowhead::new());
}
if drawing_edge.borrow().arrowtail != ArrowTypeEnum::None {
    geom_edge.borrow_mut().source_arrowhead = Some(Arrowhead::new());
}
if let Some(label_text) = drawing_edge.borrow().label_text.clone() {
    if !label_text.is_empty() {
        let size = self.text_measure(
            &label_text,
            TextMeasureOptions {
                font_size: drawing_edge.borrow().fontsize,
                font_family: drawing_edge.borrow().fontname.clone(),
                font_style: "normal".to_string(),
            },
        );
        let label = Rc::new(RefCell::new(Label::new(e.clone())));
        e.borrow_mut().label = Some(label.clone());
        GeomLabel::new(
            label,
            Rectangle::mk_pp(
                Point::new(0.0, 0.0),
                Point::new(size.width, size.height),
            ),
        );
        drawing_edge.borrow_mut().measured_text_size = size;
    }
}
if drawing_edge.borrow().penwidth != 0.0 {
    geom_edge.borrow_mut().line_width = drawing_edge.borrow().penwidth;
}