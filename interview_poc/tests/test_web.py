"""The static meeting page: syntax, the pinned and hash-checked script, and the privacy rules as lint checks.

These are static checks of the page source. They do not open a browser or a room; the camera, microphone and avatar
behaviour has to be tried by hand (see README.md).
"""
import re
import shutil
import subprocess

import pytest

from config import WEB_DIR

HTML = (WEB_DIR / "index.html").read_text(encoding="utf-8")
JS = (WEB_DIR / "app.js").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_app_js_has_valid_syntax():
    result = subprocess.run(["node", "--check", str(WEB_DIR / "app.js")], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_livekit_client_is_pinned_and_integrity_checked():
    tag = re.search(r"<script[^>]*livekit-client[^>]*>", HTML, re.S)
    assert tag, "livekit-client script tag missing"
    assert "livekit-client@2.24.1/dist/livekit-client.umd.js" in tag.group(0)  # an exact version, never a range or latest
    assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{64}"', tag.group(0)) and 'crossorigin="anonymous"' in tag.group(0)
    assert HTML.count("<script") == 2  # the library and app.js; no inline script


def test_the_page_never_publishes_a_camera_or_screen_track():
    for forbidden in ("setCameraEnabled", "setScreenShareEnabled", "createLocalVideoTrack", "createLocalTracks", "LocalVideoTrack", "publishTrack", "Track.Source.Camera"):
        assert forbidden not in JS, forbidden
    assert "setMicrophoneEnabled(true)" in JS  # the only track published
    assert "getVideoTracks()" in JS and "dom.previewVideo.srcObject" in JS  # the camera feeds the local preview only


def test_the_preview_is_local_and_muted():
    assert re.search(r'<video id="preview-video"[^>]*\bmuted\b', HTML)
    assert "preview" in HTML and "전송되지 않습니다" in HTML


def test_only_the_interviewer_agent_may_subscribe_to_the_microphone():
    assert "setTrackSubscriptionPermissions(false, [])" in JS  # nobody, until the agent joins
    assert "participant.kind !== ParticipantKind.AGENT || isAvatarWorker(participant)" in JS  # never the avatar worker
    assert "participant.attributes[PUBLISH_ON_BEHALF]" in JS and "'lk.publish_on_behalf'" in JS  # the documented marker of an avatar worker
    assert "participant.identity === AVATAR_IDENTITY" in JS  # and the plugin's default identity as a second guard
    assert "allowAll: true" in JS


def test_transcript_text_is_never_parsed_as_html():
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS and "document.write" not in JS
    assert "textContent = text" in JS


def test_the_page_discloses_the_ai_and_the_privacy_rules():
    assert "AI로 만든 가상 아바타" in HTML  # banner
    assert "점수나 합격 여부를 판단하지 않습니다" in HTML
    assert "녹음·녹화하거나 저장하지 않습니다" in HTML
    assert "가상의 정보" in HTML  # synthetic data only
    assert 'id="agree"' in HTML and 'id="start" type="button" disabled' in HTML  # start needs the acknowledgement


def test_nothing_is_stored_in_the_browser():
    for storage in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
        assert storage not in JS, storage
