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
        "name": "典籍检索测试",
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
            chunk = res.read(4096).decode("utf-8")
            if not chunk:
                break

            if first_byte_time is None:
                first_byte_time = time.time() - start
                print(f"  ⏱ first byte: {first_byte_time:.1f}s")

            buffer += chunk

            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                event_str = event_str.strip()
                if not event_str:
                    continue

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

    # Parse chapters
    chapters = _parse_chapters(full_text)
    print(f"  ⏱ total time: {total_time:.1f}s")
    print(f"  ⏱ SSE events: {event_count}")
    print(f"  total chars:  {len(full_text)}")
    print(f"  chapters:     {len(chapters)} found")

    # Print Chapter 1 preview
    ch1 = chapters.get("ch1", "")
    print(f"\n{'='*50}")
    print("  CHAPTER 1 PREVIEW:")
    print(f"{'='*50}")
    # Print first 2000 chars of chapter 1
    preview = ch1[:2000]
    print(preview)
    if len(ch1) > 2000:
        print(f"\n... (truncated, total {len(ch1)} chars)")
    print(f"{'='*50}\n")

    # Check for classical citations
    citation_keywords = ["来源", "滴天髓", "子平真诠", "穷通宝鉴", "渊海子平",
                         "三命通会", "命理探原", "Dripping Sky", "Zi Ping",
                         "Qiong Tong", "原著", "出处"]
    citations_found = []
    for kw in citation_keywords:
        if kw in full_text:
            citations_found.append(kw)

    print(f"  📚 Classical citations detected: {len(citations_found)}")
    if citations_found:
        for c in citations_found[:10]:
            print(f"    ✓ {c}")
    else:
        print("    ⚠ No classical citation keywords found")

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
    print("  MÍNG LÌ — API Streaming Test (with KB retrieval)")
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
