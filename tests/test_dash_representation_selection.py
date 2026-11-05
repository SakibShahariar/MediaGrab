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


def test_ffmpeg_maps_selected_video_stream_and_keeps_audio_subtitles() -> None:
    from mediagrab.media_stream import build_ffmpeg_command

    command = build_ffmpeg_command(
        "/usr/bin/ffmpeg", "https://cdn.example/manifest.mpd",
        "/tmp/output.mkv", dash_video_stream_index=1,
    )
    maps = [
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "-map"
    ]
    assert maps == ["0:1", "0:a?", "0:s?"]


def test_ffmpeg_rejects_invalid_selected_stream_index() -> None:
    import pytest
    from mediagrab.media_stream import build_ffmpeg_command

    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match="non-negative integer"):
            build_ffmpeg_command(
                "/usr/bin/ffmpeg", "https://cdn.example/manifest.mpd",
                "/tmp/output.mkv", dash_video_stream_index=invalid,
            )


def test_dashjs_real_world_template_manifest_shape() -> None:
    # Adapted from BSD-licensed Dash Industry Forum dash.js: https://github.com/Dash-Industry-Forum/dash.js/blob/development/samples/cmcd/mpds/basic-cmcd-config.mpd
    manifest = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
      <BaseURL serviceLocation="cdn-a">https://cdn-a.example/bbb/</BaseURL>
      <BaseURL serviceLocation="cdn-b">https://cdn-b.example/bbb/</BaseURL>
      <BaseURL serviceLocation="cdn-c">https://cdn-c.example/bbb/</BaseURL>
      <Period>
        <AdaptationSet mimeType="audio/mp4">
          <SegmentTemplate duration="1984" initialization="$RepresentationID$/init.mp4" media="$RepresentationID$/seg-$Number$.m4f"/>
          <Representation id="audio_128kbps" bandwidth="131556" codecs="mp4a.40.2"/>
        </AdaptationSet>
        <AdaptationSet mimeType="video/mp4">
          <SegmentTemplate duration="2000" initialization="$RepresentationID$/init.mp4" media="$RepresentationID$/seg-$Number$.m4f"/>
          <Representation id="video_1920x1080" bandwidth="4530860" width="1920" height="1080" codecs="avc1.640028"/>
          <Representation id="video_1280x720" bandwidth="2445034" width="1280" height="720" codecs="avc1.4D401F"/>
          <Representation id="video_640x360" bandwidth="783322" width="640" height="360" codecs="avc1.4D401E"/>
        </AdaptationSet>
      </Period>
    </MPD>"""
    reps = parse_dash_representations("https://cdn.example/manifest.mpd", manifest)

    assert [item.id for item in reps] == [
        "audio_128kbps", "video_1920x1080", "video_1280x720", "video_640x360"
    ]
    assert [item.stream_index for item in reps] == [0, 1, 2, 3]
    assert [item.height for item in reps if item.mime_type == "video/mp4"] == [1080, 720, 360]
    assert all(item.url is None for item in reps)


def test_dashjs_real_world_segment_list_and_template_mix() -> None:
    # Adapted from BSD-licensed Dash Industry Forum dash.js: https://github.com/Dash-Industry-Forum/dash.js/blob/development/test/functional/content/gap/video_gap_mid_period.mpd
    manifest = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
      <BaseURL>https://cdn.example/akamai/bbb_30fps/</BaseURL>
      <Period>
        <AdaptationSet contentType="video" mimeType="video/mp4">
          <Representation id="video_640x360" width="640" height="360">
            <SegmentList duration="120" timescale="30">
              <Initialization sourceURL="init.m4v"/>
              <SegmentURL media="part-1.m4v"/>
              <SegmentURL media="part-2.m4v"/>
            </SegmentList>
          </Representation>
        </AdaptationSet>
        <AdaptationSet contentType="audio" mimeType="audio/mp4">
          <SegmentTemplate duration="192512" initialization="$RepresentationID$/$RepresentationID$_0.m4a" media="$RepresentationID$/$RepresentationID$_$Number$.m4a"/>
          <Representation id="bbb_a64k" bandwidth="67071" codecs="mp4a.40.5"/>
        </AdaptationSet>
      </Period>
    </MPD>"""
    reps = parse_dash_representations("https://cdn.example/manifest.mpd", manifest)

    assert [item.id for item in reps] == ["video_640x360", "bbb_a64k"]
    assert [item.stream_index for item in reps] == [0, 1]
    assert reps[0].mime_type == "video/mp4"
    assert reps[1].mime_type == "audio/mp4"
    assert all(item.url is None for item in reps)
