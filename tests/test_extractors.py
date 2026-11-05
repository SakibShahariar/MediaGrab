from __future__ import annotations

from mediagrab import extractors


class FakeEntryPoint:
    def __init__(self, name, loaded=None, error=None):
        self.name = name
        self.loaded = loaded
        self.error = error

    def load(self):
        if self.error:
            raise self.error
        return self.loaded


class GoodExtractor:
    name = "example"
    capabilities = frozenset({extractors.CAPABILITY_CANDIDATE_EXPANSION})

    def supports(self, url):
        return "example.test" in url

    def extract(self, _url):
        return [
            extractors.ExtractedMedia("https://cdn.example.test/video.mp4", "Video", "video/mp4"),
            extractors.ExtractedMedia("https://cdn.example.test/video.mp4", "Duplicate"),
            extractors.ExtractedMedia("file:///etc/passwd", "Unsafe"),
            extractors.ExtractedMedia("https://user:secret@cdn.example.test/private.mp4", "Credentials"),
            "not a candidate",
        ]


def test_discovery_returns_only_valid_unique_http_candidates(monkeypatch):
    monkeypatch.setattr(
        extractors,
        "entry_points",
        lambda **_kwargs: [FakeEntryPoint("example", GoodExtractor)],
    )

    result = extractors.discover_media_candidates("https://example.test/watch/1")

    assert result == [
        extractors.ExtractedMedia(
            "https://cdn.example.test/video.mp4", "Video", "video/mp4"
        )
    ]


def test_plugin_failures_are_isolated_and_later_plugins_still_run(monkeypatch):
    class BrokenExtractor:
        capabilities = frozenset({extractors.CAPABILITY_CANDIDATE_EXPANSION})

        def supports(self, _url):
            raise RuntimeError("failure with https://secret.test/?token=hidden")

        def extract(self, _url):
            return []

    monkeypatch.setattr(
        extractors,
        "entry_points",
        lambda **_kwargs: [
            FakeEntryPoint("broken", BrokenExtractor),
            FakeEntryPoint("good", GoodExtractor),
        ],
    )

    result = extractors.discover_media_candidates("https://example.test/watch/1")

    assert len(result) == 1
    assert result[0].title == "Video"


def test_plugins_without_candidate_expansion_capability_are_not_called(monkeypatch):
    class UnprivilegedExtractor:
        capabilities = frozenset({"manifest-inspection"})

        def supports(self, _url):
            raise AssertionError("unsupported capability must not be invoked")

        def extract(self, _url):
            raise AssertionError("unsupported capability must not be invoked")

    monkeypatch.setattr(
        extractors,
        "entry_points",
        lambda **_kwargs: [FakeEntryPoint("other", UnprivilegedExtractor)],
    )

    assert extractors.discover_media_candidates("https://example.test/watch/1") == []


def test_missing_plugins_and_invalid_input_keep_core_capture_available(monkeypatch):
    monkeypatch.setattr(extractors, "entry_points", lambda **_kwargs: [])
    assert extractors.discover_media_candidates("https://example.test/watch/1") == []
    assert extractors.discover_media_candidates("file:///etc/passwd") == []


def test_discovery_failure_is_non_fatal(monkeypatch):
    def fail(**_kwargs):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(extractors, "entry_points", fail)
    assert extractors.discover_media_candidates("https://example.test/watch/1") == []


def test_plugin_output_is_bounded_per_plugin(monkeypatch):
    class ManyCandidates:
        capabilities = frozenset({extractors.CAPABILITY_CANDIDATE_EXPANSION})

        def supports(self, _url):
            return True

        def extract(self, _url):
            return [
                extractors.ExtractedMedia(f"https://cdn.example.test/{index}.mp4")
                for index in range(extractors.MAX_CANDIDATES_PER_PLUGIN + 20)
            ]

    monkeypatch.setattr(
        extractors,
        "entry_points",
        lambda **_kwargs: [FakeEntryPoint("many", ManyCandidates)],
    )

    result = extractors.discover_media_candidates("https://example.test/watch/1")

    assert len(result) == extractors.MAX_CANDIDATES_PER_PLUGIN


def test_extractor_worker_slots_are_bounded_and_nonblocking():
    acquired = [
        extractors.reserve_extractor_worker()
        for _ in range(extractors.MAX_CONCURRENT_EXTRACTOR_RUNS + 1)
    ]
    try:
        assert acquired == [True] * extractors.MAX_CONCURRENT_EXTRACTOR_RUNS + [False]
    finally:
        for reserved in acquired:
            if reserved:
                extractors.release_extractor_worker()

def test_plugin_output_is_bounded_across_all_plugins(monkeypatch):
    class ManyCandidates:
        capabilities = frozenset({extractors.CAPABILITY_CANDIDATE_EXPANSION})

        def __init__(self, plugin_index):
            self.plugin_index = plugin_index

        def supports(self, _url):
            return True

        def extract(self, _url):
            return [
                extractors.ExtractedMedia(
                    f"https://cdn{self.plugin_index}.example.test/{index}.mp4"
                )
                for index in range(extractors.MAX_CANDIDATES_PER_PLUGIN + 10)
            ]

    plugins = [
        FakeEntryPoint(f"many-{index}", lambda index=index: ManyCandidates(index))
        for index in range(3)
    ]
    monkeypatch.setattr(extractors, "entry_points", lambda **_kwargs: plugins)

    result = extractors.discover_media_candidates("https://example.test/watch/1")

    assert len(result) == extractors.MAX_CANDIDATES_TOTAL
    assert len({item.url for item in result}) == len(result)

