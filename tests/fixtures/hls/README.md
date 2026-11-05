# HLS manifest fixtures

These two small master-playlist fixtures are copied from the Apache-2.0-licensed
[mtoczko/hls-test-streams](https://github.com/mtoczko/hls-test-streams) project.

- `mtoczko-test-group.m3u8`: three variant renditions, three external audio
  renditions, and three subtitle renditions.
- `mtoczko-test-vtt.m3u8`: a Shaka Packager-generated master with an external
  audio track, subtitle track, and I-frame playlist declaration.

Original sources:

- https://github.com/mtoczko/hls-test-streams/blob/master/test-group/playlist.m3u8
- https://github.com/mtoczko/hls-test-streams/blob/master/test-vtt/playlist.m3u8

The original project is distributed under Apache License 2.0; see
[its license](https://github.com/mtoczko/hls-test-streams/blob/master/LICENSE).
The fixtures are retained as parser regression inputs only. Tests do not depend
on the upstream host being online and do not imply that its media segments,
codecs, or live services are guaranteed to remain available.
