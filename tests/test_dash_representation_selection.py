"""Tests for DASH representation ordering."""

from mediagrab.capture import parse_dash_representations


def test_single_period_representation_indices_follow_manifest_order() -> None:
    manifest = """<MPD type="static"><Period>
      <AdaptationSet mimeType="video/mp4">
        <Representation id="low" width="320" height="180"><SegmentTemplate media="low-$Number$.m4s"/></Representation>
        <Representation id="high" width="640" height="360"><SegmentTemplate media="high-$Number$.m4s"/></Representation>
      </AdaptationSet>
      <AdaptationSet mimeType="audio/mp4">
        <Representation id="audio"><SegmentTemplate media="audio-$Number$.m4s"/></Representation>
      </AdaptationSet>
    </Period></MPD>"""
    reps = parse_dash_representations("https://cdn.example/manifest.mpd", manifest)
    assert [item.stream_index for item in reps] == [0, 1, 2]
    assert [item.id for item in reps] == ["low", "high", "audio"]


def test_multi_period_manifest_has_no_ambiguous_stream_indices() -> None:
    manifest = """<MPD type="static">
      <Period><AdaptationSet mimeType="video/mp4"><Representation id="first"><SegmentTemplate media="a-$Number$.m4s"/></Representation></AdaptationSet></Period>
      <Period><AdaptationSet mimeType="video/mp4"><Representation id="second"><SegmentTemplate media="b-$Number$.m4s"/></Representation></AdaptationSet></Period>
    </MPD>"""
    reps = parse_dash_representations("https://cdn.example/manifest.mpd", manifest)
    assert [item.stream_index for item in reps] == [None, None]
