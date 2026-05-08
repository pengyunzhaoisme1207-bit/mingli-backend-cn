"""Smoke test for /generate-report endpoint (streaming)."""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"


def test_health():
    print("▸ GET /health")
    with urllib.request.urlopen(f"{BASE}/health", timeout=10) as res:
        data = json.loads(res.read())
        print(f"  status: {res.status}")
        print(f"  body:   {data}")
        assert res.status == 200
        assert data["api_key_configured"], "DASHSCOPE_API_KEY not set"
        print("  ✅ health OK\n")


def test_streaming_report():
    """Test SSE streaming endpoint with timing metrics."""
    print("▸ POST /generate-report (streaming)")
    payload = {
        "name": "Stream Test",
        "birth_date": "1990-06-15",
        "birth_time": "14:30",
        "birth_place": "Shanghai, China",
        "gender": "male",
    }
    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE}/generate-report",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    first_byte_time = None
    full_text = ""
    event_count = 0
    done_data = None

    with urllib.request.urlopen(req, timeout=600) as res:
        print(f"  status: {res.status}")
        assert res.status == 200, f"Expected 200, got {res.status}"

        buffer = ""
        while True:
            chunk = res.read(1024).decode("utf-8")
            if not chunk:
                break

            if first_byte_time is None:
                first_byte_time = time.time() - start
                print(f"  ⏱ first byte: {first_byte_time:.1f}s")

            buffer += chunk

            # Parse complete SSE events from buffer
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                event_str = event_str.strip()
                if not event_str:
                    continue

                # Extract data line
                for line in event_str.split("\n"):
                    if line.startswith("data: "):
                        event_count += 1
                        try:
                            data = json.loads(line[6:])
                            if "error" in data:
                                print(f"  ❌ stream error: {data['error']}")
                                sys.exit(1)

                            if data.get("done"):
                                done_data = data
                                break

                            if "chunk" in data:
                                full_text += data["chunk"]
                        except json.JSONDecodeError:
                            pass
                if done_data:
                    break
            if done_data:
                break

    total_time = time.time() - start

    # Verify content
    chapters = _parse_chapters(full_text)
    print(f"  ⏱ total time: {total_time:.1f}s")
    print(f"  ⏱ SSE events: {event_count}")
    print(f"  total chars:  {len(full_text)}")
    print(f"  chapters:     {len(chapters)} found")

    for key in ["ch1", "ch2", "ch5", "ch10"]:
        content = chapters.get(key, "")
        preview = content[:80].replace("\n", " ")
        print(f"    {key}: {preview}{'...' if len(content) > 80 else ''}")

    # Verify all 10 chapters present
    expected = [f"ch{i}" for i in range(1, 11)]
    for ch in expected:
        assert ch in chapters, f"Missing {ch}"
        assert len(chapters[ch]) > 10, f"{ch} too short: {len(chapters[ch])} chars"

    if done_data:
        print(f"  done payload: total_chars={done_data.get('total_chars')}, "
              f"chapters={len(done_data.get('chapters', []))}")

    print("  ✅ Streaming test passed\n")


def _parse_chapters(text: str) -> dict:
    """Parse chapters from raw text."""
    import re
    chapters = {}
    current_chapter = None
    current_lines = []

    for line in text.split("\n"):
        if line.strip().startswith("## Chapter "):
            if current_chapter is not None:
                chapters[current_chapter] = "\n".join(current_lines).strip()
            match = re.search(r"## Chapter (\d+)", line)
            if match:
                num = int(match.group(1))
                current_chapter = f"ch{num}"
                current_lines = [line]
            else:
                current_chapter = None
                current_lines = [line]
        else:
            if current_chapter is not None:
                current_lines.append(line)

    if current_chapter is not None:
        chapters[current_chapter] = "\n".join(current_lines).strip()

    return chapters


if __name__ == "__main__":
    print("=" * 50)
    print("  MÍNG LÌ — API Streaming Test")
    print("=" * 50 + "\n")

    try:
        test_health()
        test_streaming_report()
        print("=" * 50)
        print("  ALL TESTS PASSED ✅")
        print("=" * 50)
    except urllib.error.URLError as e:
        print(f"❌ Cannot connect to backend: {e}")
        sys.exit(1)
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
