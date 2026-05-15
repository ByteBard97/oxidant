

    if edgeCount <= Self::LOWER_EDGE_BOUND {
        return Self::MAX_GRANULARITY;
    }
    if edgeCount >= Self::UPPER_EDGE_BOUND {
        return Self::MIN_GRANULARITY;
    }

    let delta = (Self::UPPER_EDGE_BOUND - Self::LOWER_EDGE_BOUND) / (edgeCount - Self::LOWER_EDGE_BOUND);
    (Self::MIN_GRANULARITY + delta).ceil()