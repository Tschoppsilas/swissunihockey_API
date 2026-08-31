from tvo_social import layout


def test_compute_scale_is_baseline_when_content_fills_page():
    # A category count/size chosen so total height roughly equals capacity.
    categorized = {"A": list(range(20))}  # only length matters
    scale = layout.compute_scale(categorized, "announce")
    assert scale == layout.MIN_SCALE


def test_compute_scale_is_capped_for_very_sparse_content():
    categorized = {"A": list(range(1))}
    scale = layout.compute_scale(categorized, "announce")
    assert scale == layout.MAX_SCALE


def test_compute_scale_is_between_bounds_for_moderate_content():
    # Pick a game count whose 1x height is meaningfully below capacity but
    # not tiny, so the ideal scale lands strictly between MIN and MAX.
    for n in range(1, 20):
        categorized = {"A": list(range(n))}
        total = layout.total_content_height(categorized, "announce")
        if layout.MIN_SCALE < layout.FEED_PROFILE.page_capacity() / total < layout.MAX_SCALE:
            scale = layout.compute_scale(categorized, "announce")
            assert layout.MIN_SCALE < scale < layout.MAX_SCALE
            return
    raise AssertionError("no game count produced a moderate scale - adjust the test")


def test_compute_scale_empty_categories_returns_min_scale():
    assert layout.compute_scale({}, "announce") == layout.MIN_SCALE


def test_total_content_height_sums_categories():
    categorized = {"A": list(range(2)), "B": list(range(3))}
    expected = layout.category_height(2, "results") + layout.category_height(3, "results")
    assert layout.total_content_height(categorized, "results") == expected
