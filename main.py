import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="MÍNG LÌ — Bazi Destiny Report API")

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file mount ──
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "homepage"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Load SKILL.md as system prompt ──
SKILL_PATH = Path.home() / ".hermes" / "skills" / "08-external-skills" / "bazi-ziwei-mingli" / "SKILL.md"
if SKILL_PATH.exists():
    with open(SKILL_PATH, "r", encoding="utf-8") as f:
        SKILL_CONTENT = f.read()
else:
    SKILL_CONTENT = ""

# Build a concise system prompt from SKILL.md
SYSTEM_PROMPT = """You are a master-level Chinese astrology analyst specializing in Bazi (八字, Four Pillars) and Zi Wei Dou Shu (紫微斗数, Purple Star Astrology).

## Core Rules (Iron Laws)
1. ALL chart calculations must be done MANUALLY step by step
2. NEVER guess — if you don't know, say so
3. NEVER reverse-engineer from known facts
4. NEVER use a single perspective to judge
5. NEVER split major luck cycles into fragments

## Bilingual Output Requirement (MANDATORY)
All reports MUST be bilingual Chinese-English:
- Section titles: 中文标题 / English Title
- Core terminology: 中文术语（English translation）
- Reading content: Chinese paragraph first, blank line, then English paragraph
- Classical citations: Original Chinese + (English translation, source)
- Tables: Bilingual headers, Chinese-English content
- Numbers, ratings, years: Write once only, no duplication
- NO pure-English, NO pure-Chinese, NO machine-translation tone

## Output Requirements
- Use markdown formatting with tables where appropriate
- Cite classical sources where applicable
- Include danger ratings (★☆ to ★★★★★) for unfavorable years
- Follow the 10-chapter structure exactly

## Bazi Methodology (from SKILL.md)
Follow the 15-step chart analysis: encode birth info, identify day master, observe month command, assess strength, temperature regulation, pattern determination, image analysis, useful gods, temperament, health, six relations, wealth/career, luck cycles, auxiliary stars, comprehensive judgment.

Use the Four Masters voting method: Xu Lewu (徐乐吾, pattern + seasonal), Liang Xiangrun (梁湘润, three-track system), Yuan Shushan (袁树珊, sixteen-character method), Wei Qianli (韦千里, eight-step method).

## Zi Wei Dou Shu
Include Life Palace (命宫), Body Palace (身宫), Three Parties Four Courts (三方四正), 14 Major Stars, auxiliary stars, Four Transformations (四化), and major luck analysis.

## Cross Validation
Compare Bazi and Zi Wei across 8 dimensions: wealth (财运), career (事业), marriage (婚姻), travel (迁移), health (健康), noble people (贵人), golden period (黄金期), worst period (最差期)."""


class BirthInfo(BaseModel):
    name: str = Field(..., description="User name or nickname")
    birth_date: str = Field(..., description="Birth date in YYYY-MM-DD format")
    birth_time: str = Field(..., description="Birth time in HH:MM format")
    birth_place: str = Field(..., description="City, Country")
    gender: str = Field(..., description="Gender: male or female")


def build_user_prompt(info: BirthInfo) -> str:
    return f"""Generate a complete Bazi + Zi Wei Dou Shu destiny report for the following person.

**Name**: {info.name}
**Birth Date (Gregorian)**: {info.birth_date}
**Birth Time**: {info.birth_time}
**Gender**: {info.gender}
**Birth Place**: {info.birth_place}

You MUST produce the output as a structured report with EXACTLY the following 10 chapters. Each chapter must begin with "## Chapter N: Title / 中文标题" (where N is 1-10) so it can be parsed:

## Chapter 1: Bazi Chart Setup / 八字排盘
Include: Four Pillars table (Year/Month/Day/Hour with Heavenly Stem + Earthly Branch), Hidden Stems, Na Yin, Void (空亡), Five Elements distribution count, Day Master identification with strength assessment.

## Chapter 2: Day Master Strength & Pattern / 日主强弱与格局
Include: Month command analysis (当令之气), Day Master strength assessment with allied/opposing forces, Pattern determination (格局), Favorable elements (用神/喜神), Unfavorable elements (忌神/仇神).

## Chapter 3: Image, Temperament & Health / 形象、性情与健康
Include: Chart image analysis (清浊真假源流), Temperament profile (十神突出), Health indicators (五行受克 — which organs to watch).

## Chapter 4: Family Relations & Wealth/Career / 六亲与财官
Include: Six Relations (宫位+十神 — parents 父母, siblings 兄弟, spouse 配偶, children 子女), Wealth analysis (财星状态), Career analysis (官星状态).

## Chapter 5: Major Luck Cycles & Annual Years / 大运流年
Include: Starting age calculation (起运岁数), Full major luck pillars table (8 pillars, each 10 years, with Ten Gods), Current major luck analysis, Next 3 annual years with danger ratings (凶度评分).

## Chapter 6: Supplementary Calculations / 补充推算
Include: Life Palace (命宫), Minor Limit (小限), Auspicious Stars (神煞 — Tian Yi Nobleman 天乙贵人, Traveling Horse 驿马, etc.), Illness & Remedy theory (病药说).

## Chapter 7: Four Masters Voting Results / 四家投票
Include a table showing how each master (Xu Lewu 徐乐吾, Liang Xiangrun 梁湘润, Yuan Shushan 袁树珊, Wei Qianli 韦千里) independently assesses: Pattern, Day Master strength, Favorable elements, Current luck outlook, Wealth outlook. Include a consensus row with confidence level.

## Chapter 8: Zi Wei Dou Shu Analysis / 紫微斗数分析
Include: Life Palace (命宫) main star(s) and Three Parties Four Courts (三方四正), Body Palace (身宫) analysis, Major Stars and auxiliary stars in key palaces, Current major luck direction, Key patterns observed.

## Chapter 9: Dual-System Cross Validation / 双系统交叉验证
Include a table comparing Bazi vs Zi Wei across 8 dimensions (Wealth 财运, Career 事业, Marriage 婚姻, Travel 迁移, Health 健康, Noble People 贵人, Golden Period 黄金期, Worst Period 最差期). For each: Bazi finding, Zi Wei finding, Combined judgment. Summary of consistent dimensions.

## Chapter 10: Comprehensive Advice / 综合建议
Include: Breakthrough direction (破局方向), Golden window (黄金窗口), Caution points (注意事项), Life theme (格局总评).

IMPORTANT FORMATTING RULES:
- Each chapter MUST start with "## Chapter N: English / 中文" exactly
- BILINGUAL: Every title in Chinese+English; core terms as 中文（English）; readings as Chinese paragraph then English; tables with bilingual headers
- Classical citations: Original Chinese + (English translation, source name)
- Numbers/ratings/years: Write once only, no duplication
- No machine-translation tone — natural Chinese first, then natural English
- No emojis
- Clear, professional language for educated readers
- Cite classical sources (Di Tian Sui 滴天髓, Zi Ping Zhen Quan 子平真诠, Qiong Tong Bao Jian 穷通宝鉴, etc.)
- Be specific and detailed — this is a premium report"""


@app.get("/health")
async def health_check():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    return {
        "status": "healthy" if api_key else "degraded",
        "api_key_configured": bool(api_key),
        "skill_md_loaded": bool(SKILL_CONTENT),
    }


@app.post("/generate-report")
def generate_report(info: BirthInfo):
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="DASHSCOPE_API_KEY not configured",
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    user_prompt = build_user_prompt(info)

    def event_stream():
        """Sync generator — FastAPI runs it in a thread pool automatically."""
        full_text = ""
        batch = []
        chunk_count = 0
        start_time = time.time()
        last_heartbeat = time.time()
        HEARTBEAT_INTERVAL = 5  # seconds — prevents Railway HTTP timeout

        try:
            response = client.chat.completions.create(
                model="qwen3.6-plus",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=16384,
                temperature=0,
                stream=True,
            )

            for chunk in response:
                now = time.time()

                # Send heartbeat if no data sent for HEARTBEAT_INTERVAL seconds
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    yield f"data: {json.dumps({'heartbeat': True, 'elapsed': round(now - start_time, 1)})}\n\n"
                    last_heartbeat = now

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Content chunks
                if delta.content:
                    content = delta.content
                    full_text += content
                    batch.append(content)
                    chunk_count += 1

                    # Send accumulated batch every 5 chunks
                    if chunk_count % 5 == 0:
                        data = {"chunk": "".join(batch), "elapsed": round(time.time() - start_time, 1)}
                        batch.clear()
                        line = json.dumps(data).replace("\n", "\\n")
                        yield f"data: {line}\n\n"
                        last_heartbeat = time.time()

            # Flush remaining
            if batch:
                data = {"chunk": "".join(batch), "elapsed": round(time.time() - start_time, 1)}
                batch.clear()
                line = json.dumps(data).replace("\n", "\\n")
                yield f"data: {line}\n\n"
                last_heartbeat = time.time()

            # Send final event with parsed structure
            chapters = _parse_chapters(full_text)
            pillars = _extract_pillars(chapters.get("ch1", ""))
            done_data = {
                "done": True,
                "pillars": pillars,
                "chapters": list(chapters.keys()),
                "total_chars": len(full_text),
                "elapsed": round(time.time() - start_time, 1),
            }
            yield f"data: {json.dumps(done_data)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_chapters(text: str) -> dict:
    """Parse report text into chapter dictionary {ch1: content, ch2: content, ...}."""
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


def _extract_pillars(ch1_content: str) -> dict:
    """Extract pillar information from Chapter 1 content."""
    return {
        "year": {"stem": "—", "branch": "—"},
        "month": {"stem": "—", "branch": "—"},
        "day": {"stem": "—", "branch": "—"},
        "hour": {"stem": "—", "branch": "—"},
        "day_master": "—",
        "strength": "—",
    }


# ── Static page routes ──
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/cases")
@app.get("/cases.html")
async def serve_cases():
    return FileResponse(str(FRONTEND_DIR / "cases.html"))


@app.get("/what-is-bazi")
@app.get("/what-is-bazi.html")
async def serve_what_is_bazi():
    return FileResponse(str(FRONTEND_DIR / "what-is-bazi.html"))


@app.get("/reading")
@app.get("/reading.html")
async def serve_reading():
    return FileResponse(str(FRONTEND_DIR / "reading.html"))


@app.get("/sample-report")
@app.get("/sample-report.html")
async def serve_sample_report():
    return FileResponse(str(FRONTEND_DIR / "sample-report.html"))
