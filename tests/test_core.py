import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cleaner", ROOT / "gphotos_short_video_cleaner.py")
cleaner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleaner
assert SPEC.loader is not None
SPEC.loader.exec_module(cleaner)


class DurationTests(unittest.TestCase):
    def test_m_ss(self):
        self.assertEqual(cleaner.duration_text_to_seconds("0:03"), 3)
        self.assertEqual(cleaner.duration_text_to_seconds("12:34"), 754)

    def test_h_mm_ss(self):
        self.assertEqual(cleaner.duration_text_to_seconds("1:02:03"), 3723)

    def test_fullwidth_colon(self):
        self.assertEqual(cleaner.duration_text_to_seconds("0：03"), 3)

    def test_invalid(self):
        for value in ("3", "0:3", "00:60", "text", "1:2:03"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    cleaner.duration_text_to_seconds(value)


class NormalizeTests(unittest.TestCase):
    def test_vietnamese_diacritics(self):
        self.assertEqual(cleaner.normalize_text("Chuyển vào Thùng rác"), "chuyen vao thung rac")
        self.assertEqual(cleaner.normalize_text("Xoá vĩnh viễn"), "xoa vinh vien")
        self.assertEqual(cleaner.normalize_text("Đóng"), "dong")


class ArgumentTests(unittest.TestCase):
    def test_delete_flag_is_enabled(self):
        args = cleaner.parse_args(["--threshold", "4", "--delete"])
        self.assertTrue(args.delete)
        self.assertEqual(args.threshold, 4)


class DedupeTests(unittest.TestCase):
    def test_identity_dedupe(self):
        first = cleaner.MediaItem("k", "photo-href", "Video - now", "0:03", 3)
        same_media_new_label = cleaner.MediaItem("k", "photo-href", "Video - later", "0:03", 3)
        self.assertEqual(cleaner._dedupe_items([first, same_media_new_label]), [first])


class ScanObservationTests(unittest.TestCase):
    def test_visible_duration_replaces_earlier_unresolved_observation(self):
        unresolved = cleaner.MediaItem("same", "photo-href", "Video", None, None)
        resolved = cleaner.MediaItem("same", "photo-href", "Video", "0:03", 3)
        all_seen = {}
        candidates = {}
        without_duration = {}

        cleaner._record_scan_item(unresolved, 4, all_seen, candidates, without_duration)
        cleaner._record_scan_item(resolved, 4, all_seen, candidates, without_duration)

        self.assertEqual(all_seen[resolved.identity], resolved)
        self.assertEqual(candidates[resolved.identity], resolved)
        self.assertNotIn(resolved.identity, without_duration)

    def test_resolved_long_video_is_not_reported_without_duration(self):
        unresolved = cleaner.MediaItem("same", "photo-href", "Video", None, None)
        resolved = cleaner.MediaItem("same", "photo-href", "Video", "0:10", 10)
        all_seen = {}
        candidates = {}
        without_duration = {}

        cleaner._record_scan_item(unresolved, 4, all_seen, candidates, without_duration)
        cleaner._record_scan_item(resolved, 4, all_seen, candidates, without_duration)

        self.assertEqual(all_seen[resolved.identity], resolved)
        self.assertEqual(candidates, {})
        self.assertNotIn(resolved.identity, without_duration)


class PageContextTests(unittest.TestCase):
    class Driver:
        def __init__(self, url):
            self.current_url = url

    def test_video_search_is_allowed(self):
        cleaner.assert_safe_page_context(self.Driver("https://photos.google.com/u/0/search/_tv_Videos"))

    def test_trash_and_other_hosts_are_blocked(self):
        blocked = (
            "https://photos.google.com/u/0/trash",
            "https://photos.google.com/u/0/album/example",
            "https://photos.google.com.evil.invalid/search/_tv_Videos",
        )
        for url in blocked:
            with self.subTest(url=url):
                with self.assertRaises(cleaner.SafetyStop):
                    cleaner.assert_safe_page_context(self.Driver(url))


class FakeWait:
    def __init__(self, driver, timeout, poll_frequency=0.1):
        self.driver = driver

    def until(self, predicate):
        result = predicate(self.driver)
        if result:
            return result
        raise cleaner.TimeoutException()

    def until_not(self, predicate):
        if not predicate(self.driver):
            return True
        raise cleaner.TimeoutException()


class ScanGalleryTests(unittest.TestCase):
    def test_scan_scrolls_all_pages_and_upgrades_duration_observations(self):
        pages = [
            {
                "items": [
                    {"key": "A", "key_source": "photo-href", "label": "Video A", "duration_text": None, "duration_seconds": None},
                    {"key": "B", "key_source": "photo-href", "label": "Video B", "duration_text": "0:10", "duration_seconds": 10},
                ],
                "scroll": {"top": 0, "height": 3000, "client": 800, "at_bottom": False},
                "stats": {"video_tiles": 2},
            },
            {
                "items": [
                    {"key": "A", "key_source": "photo-href", "label": "Video A", "duration_text": "0:03", "duration_seconds": 3},
                    {"key": "C", "key_source": "photo-href", "label": "Video C", "duration_text": "0:02", "duration_seconds": 2},
                ],
                "scroll": {"top": 800, "height": 3000, "client": 800, "at_bottom": False},
                "stats": {"video_tiles": 2},
            },
            {
                "items": [
                    {"key": "D", "key_source": "photo-href", "label": "Video D", "duration_text": "0:05", "duration_seconds": 5},
                ],
                "scroll": {"top": 2200, "height": 3000, "client": 800, "at_bottom": True},
                "stats": {"video_tiles": 1},
            },
        ]
        state = {"page": 0}
        originals = {
            name: getattr(cleaner, name)
            for name in (
                "assert_safe_page_context",
                "scroll_to_top",
                "take_snapshot",
                "get_scroll_state",
                "scroll_forward",
            )
        }
        original_sleep = cleaner.time.sleep
        try:
            cleaner.assert_safe_page_context = lambda driver: None
            cleaner.scroll_to_top = lambda driver, settle: state.update(page=0)
            cleaner.take_snapshot = lambda *args, **kwargs: pages[state["page"]]
            cleaner.get_scroll_state = lambda driver: pages[state["page"]]["scroll"]

            def scroll_forward(driver, current_state, settle):
                if state["page"] >= len(pages) - 1:
                    return False
                state["page"] += 1
                return True

            cleaner.scroll_forward = scroll_forward
            cleaner.time.sleep = lambda seconds: None
            result = cleaner.scan_gallery(
                object(),
                cleaner.RuntimeConfig(4, 25, 0, 10, 0.1, 5),
            )
        finally:
            for name, value in originals.items():
                setattr(cleaner, name, value)
            cleaner.time.sleep = original_sleep

        self.assertEqual({item.key for item in result.all_videos}, {"A", "B", "C", "D"})
        self.assertEqual({item.key for item in result.candidates}, {"A", "C"})
        self.assertEqual(result.videos_without_duration, [])
        self.assertEqual(result.stopped_reason, "end-of-gallery")


class FakeElement:
    def __init__(self, name):
        self.name = name


class DeleteDialogDriver:
    current_url = "https://photos.google.com/u/0/search/_tv_Videos"

    def __init__(self, selected=2, permanent=False, dialog_visible=False):
        self.selected = selected
        self.permanent = permanent
        self.dialog_visible = dialog_visible
        self.toolbar = FakeElement("toolbar")
        self.confirm = FakeElement("confirm")
        self.clicks = []

    def execute_script(self, script, *args):
        if script == cleaner.SELECTED_COUNT_JS:
            return {"count": self.selected, "source": "fake-counter"}
        if script == cleaner.FIND_TOOLBAR_DELETE_JS:
            return {"status": "ok", "element": self.toolbar, "label": "Chuyển vào thùng rác"}
        if script == cleaner.FIND_CONFIRM_ACTION_JS:
            if self.permanent:
                return {"status": "permanent_delete_refused", "label": "Xoá vĩnh viễn"}
            return {"status": "ok", "element": self.confirm, "label": "Chuyển vào thùng rác"}
        if script == cleaner.DIALOG_VISIBLE_JS:
            return self.dialog_visible
        if script == "arguments[0].click();":
            element = args[0]
            self.clicks.append(element.name)
            if element is self.toolbar:
                self.dialog_visible = True
            elif element is self.confirm:
                self.selected = 0
                self.dialog_visible = False
            return None
        raise AssertionError(f"Unexpected script: {script[:50]!r}")


class DeleteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_wait = cleaner.WebDriverWait
        cleaner.WebDriverWait = FakeWait

    def tearDown(self):
        cleaner.WebDriverWait = self.original_wait

    def test_move_to_trash_success_path(self):
        driver = DeleteDialogDriver(selected=2)
        cleaner.move_current_selection_to_trash(driver, expected_count=2, timeout_seconds=5)
        self.assertEqual(driver.clicks, ["toolbar", "confirm"])
        self.assertEqual(driver.selected, 0)

    def test_selection_count_mismatch_stops_before_click(self):
        driver = DeleteDialogDriver(selected=3)
        with self.assertRaises(cleaner.SafetyStop):
            cleaner.move_current_selection_to_trash(driver, expected_count=2, timeout_seconds=5)
        self.assertEqual(driver.clicks, [])

    def test_existing_dialog_stops_before_click(self):
        driver = DeleteDialogDriver(selected=2, dialog_visible=True)
        with self.assertRaises(cleaner.SafetyStop):
            cleaner.move_current_selection_to_trash(driver, expected_count=2, timeout_seconds=5)
        self.assertEqual(driver.clicks, [])

    def test_permanent_delete_is_refused(self):
        driver = DeleteDialogDriver(selected=2, permanent=True)
        with self.assertRaises(cleaner.SafetyStop):
            cleaner.move_current_selection_to_trash(driver, expected_count=2, timeout_seconds=5)
        self.assertEqual(driver.clicks, ["toolbar"])
        self.assertEqual(driver.selected, 2)


class DeletePlanTests(unittest.TestCase):
    def test_only_items_from_dry_run_allow_list_are_selected(self):
        planned = cleaner.MediaItem("https://photos.google.com/photo/A", "photo-href", "Video - A", "0:03", 3)
        raw_unplanned = {
            "key": "https://photos.google.com/photo/B",
            "key_source": "photo-href",
            "label": "Video - B",
            "duration_text": "0:02",
            "duration_seconds": 2,
            "is_candidate": True,
            "checkbox": "B",
        }
        raw_planned = {
            "key": planned.key,
            "key_source": planned.key_source,
            "label": planned.label,
            "duration_text": planned.duration_text,
            "duration_seconds": planned.duration_seconds,
            "is_candidate": True,
            "checkbox": "A",
        }
        config = cleaner.RuntimeConfig(4, 1, 0, 3, 0.1, 5)
        state = {"selected": 0, "clicked": [], "moved": []}

        originals = {
            name: getattr(cleaner, name)
            for name in (
                "assert_safe_page_context",
                "get_selected_count",
                "scroll_to_top",
                "take_snapshot",
                "_click_candidate_checkbox",
                "move_current_selection_to_trash",
            )
        }
        try:
            cleaner.assert_safe_page_context = lambda driver: None
            cleaner.get_selected_count = lambda driver: (state["selected"], "fake")
            cleaner.scroll_to_top = lambda driver, settle: None
            cleaner.take_snapshot = lambda *args, **kwargs: {
                "items": [raw_unplanned, raw_planned],
                "scroll": {"at_bottom": True, "top": 0, "height": 100, "client": 100},
            }

            def click(driver, checkbox):
                state["clicked"].append(checkbox)
                state["selected"] += 1
                return True

            def move(driver, expected_count, timeout_seconds):
                self.assertEqual(expected_count, 1)
                self.assertEqual(state["selected"], 1)
                state["moved"].append(expected_count)
                state["selected"] = 0

            cleaner._click_candidate_checkbox = click
            cleaner.move_current_selection_to_trash = move
            result = cleaner.delete_candidates(object(), config, [planned])
        finally:
            for name, value in originals.items():
                setattr(cleaner, name, value)

        self.assertEqual(state["clicked"], ["A"])
        self.assertEqual(state["moved"], [1])
        self.assertEqual([item.identity for item in result.deleted], [planned.identity])

    def test_aria_label_only_identity_is_never_deleted(self):
        weak = cleaner.MediaItem("Video - same label", "aria-label", "Video - same label", "0:03", 3)
        config = cleaner.RuntimeConfig(4, 25, 0, 3, 0.1, 5)
        result = cleaner.delete_candidates(object(), config, [weak])
        self.assertEqual(result.planned, 0)
        self.assertEqual(result.deleted, [])



if __name__ == "__main__":
    unittest.main()
