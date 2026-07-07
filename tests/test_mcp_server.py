"""Tests du serveur MCP (sautés si l'extra `mcp` n'est pas installé)."""

import asyncio
import subprocess

import pytest

pytest.importorskip("mcp")

from vidai import mcp_server  # noqa: E402
from vidai.ffmpeg_utils import ffmpeg_path  # noqa: E402

EXPECTED_TOOLS = {"video_transcript", "video_frames_at", "video_timeline", "check_dependencies"}


def test_all_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_tool_docs_mention_token_tradeoff():
    # Transparence ADR-012 : les outils qui produisent des images documentent le
    # compromis coût/qualité de frame_width et son caractère model-agnostic.
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    for name in ("video_frames_at", "video_timeline"):
        desc = tools[name].description or ""
        assert "frame_width" in desc
        assert "1568" in desc
        assert "coût" in desc


def test_check_dependencies_shape():
    out = mcp_server.check_dependencies()
    assert set(out) == {"ok", "dependencies"}
    assert {d["name"] for d in out["dependencies"]} == {"ffmpeg", "yt-dlp", "faster-whisper"}


def test_video_timeline_on_local_video(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=s=320x240:d=4:r=10",
         "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True,
    )
    out = mcp_server.video_timeline(
        source=str(video), outdir=str(tmp_path / "out"), visual_only=True
    )
    assert "error" not in out
    assert out["keyframes"] >= 1
    assert out["frames_extracted"] == out["keyframes"]
    assert (tmp_path / "out" / "output.json").exists()


def test_error_is_reported_not_raised(tmp_path):
    out = mcp_server.video_timeline(source="/nulle/part.mp4", outdir=str(tmp_path / "o"))
    assert "error" in out and out["error"]
