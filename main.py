import json
import os
import re
import subprocess
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

# ── Knowledge Base paths ──
BOOKS_DIR = os.path.expanduser("~/.hermes/skills/08-external-skills/bazi-ziwei-mingli/books/")
KG_DIR = os.path.expanduser("~/Obsidian/内容创作工作流/20-MATERIALS/bazi-kg/")


def search_knowledge_base(queries: list[str], max_results: int = 8) -> str:
    """Search books/ and KG/ for relevant classical passages."""
    results = []
    for query in queries:
        if not query or len(query) < 2:
            continue
        for search_dir in [BOOKS_DIR, KG_DIR]:
            if not os.path.isdir(search_dir):
                continue
            try:
                # Find matching files
                cmd = ["grep", "-r", "-i", "-l",
                       "--include=*.md", "--include=*.txt",
                       query, search_dir]
                found = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                files = found.stdout.strip().split("\n")
                for f in files[:2]:
                    if not f:
                        continue
                    # Extract relevant context
                    grep_cmd = ["grep", "-i", "-A", "3", "-B", "1", query, f]
                    hits = subprocess.run(grep_cmd, capture_output=True, text=True, timeout=5).stdout
                    if hits:
                        label = os.path.relpath(f, search_dir)
                        results.append(f"[来源: {label}]\n{hits[:500]}")
            except Exception:
                continue
    # Deduplicate by source name
    seen = set()
    deduped = []
    for r in results:
        src = r.split("\n")[0]
        if src not in seen:
            seen.add(src)
            deduped.append(r)
    return "\n\n---\n\n".join(deduped[:max_results]) if deduped else ""


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
    return f"""请为以下用户生成完整的八字+紫微斗数双语命理报告。

## 用户信息
- 姓名：{info.name}
- 出生日期（公历）：{info.birth_date}
- 出生时间：{info.birth_time}
- 出生地点：{info.birth_place}
- 性别：{info.gender}

## 核心要求：十五步流程，不得跳步

你必须严格按照 SKILL.md 中规定的十五步流程执行，每一步都必须输出，不得跳过、不得合并、不得省略：

1. **编码**：阳历→真太阳时→四柱干支+藏干→大运→起运年龄→流年
2. **识日主**：十天干性质、喜忌、阴阳区分
3. **观月令**：节气/季节、透干情况、月令本气
4. **日主强弱**：五行统计、同方/异方加权、当令修正
5. **调候**：穷通宝鉴十干配十二月
6. **格局**：取格依据、相神、成败
7. **形象**：清浊/真假/源流/通关
8. **用神**：用神/喜神/忌神/仇神/闲神
9. **性情**：十神突出→综合个性
10. **疾病**：五行受克→对应脏腑
11. **六亲**：宫位+十神参合
12. **财官**：官星+财星状态
13. **大运流年**：起运计算→大运表（8步）→当前大运→未来3年流年
14. **神煞辅助**：天乙贵人/文昌/驿马/华盖/桃花/羊刃/空亡
15. **综合判断**：多角度验证，必须验证已知事实

补充步骤也必须执行并输出：
- **命宫**：位置+天干+分析
- **小限**：当前年小限
- **空亡**：从日柱推算
- **病药说**：病在何处、药在何方

## 输出结构：10章报告

报告必须包含以下10个章节。每个章节标题格式为：
## Chapter N: 中文标题 / English Title

### Chapter 1: 八字排盘 / Bazi Chart Setup
四柱表（年/月/日/时干支+藏干+纳音+空亡）、五行分布计数、日主识别+强弱评估

### Chapter 2: 日主强弱与格局 / Day Master Strength & Pattern
月令分析、日主强弱评估（同方/异方加权）、格局判定（取格依据+相神+成败）、用神/喜神/忌神

### Chapter 3: 形象、性情与健康 / Image, Temperament & Health
清浊真假源流、十神性情、五行疾病提示

### Chapter 4: 六亲与财官 / Family, Wealth & Career
六亲（父母/兄弟/配偶/子女）、财运、事业

### Chapter 5: 大运流年 / Major Luck Cycles & Annual Years
起运计算、完整大运表（8步×10年）、当前大运分析、未来3年流年+凶度评分

### Chapter 6: 补充推算 / Supplementary Calculations
命宫、小限、神煞（天乙贵人/驿马/华盖等）、病药说

### Chapter 7: 四家投票 / Four Masters Voting
**必须以完整表格形式输出**，不可合并或省略：

| 家 | 格局 | 日主强弱 | 用神/喜神 | 当前大运 | 财运 |
|---|---|---|---|---|---|
| 徐乐吾 | | | | | |
| 梁湘润 | | | | | |
| 袁树珊 | | | | | |
| 韦千里 | | | | | |
| 共识 | | | | | |

### Chapter 8: 紫微斗数分析 / Zi Wei Dou Shu Analysis
**必须完整排盘，不可只给框架**：
- 命宫位置+主星+辅星煞星
- 身宫位置+分析
- 三方四正
- 十二宫位分布
- 四化分布
- 大运方向

### Chapter 9: 双系统交叉验证 / Dual-System Cross Validation
**必须有完整8维度对照表**：

| 维度 | 八字结论 | 紫微结论 | 综合判断 |
|---|---|---|---|
| 财运 | | | |
| 事业 | | | |
| 婚姻 | | | |
| 迁移 | | | |
| 健康 | | | |
| 贵人 | | | |
| 黄金期 | | | |
| 最差期 | | | |

### Chapter 10: 综合建议 / Comprehensive Advice
破局方向、黄金窗口、注意事项、格局总评

## 双语格式规范（强制执行）

**每个段落先写中文，空一行，然后写对应的完整英文翻译。**

英文翻译必须是完整段落的逐句翻译，不是总结、不是概述。

示例格式：
> 庚金日主，生于丑月，月令己土正印透干，得月令之权。土金两旺，日主极强。
>
> Geng Metal Day Master, born in the Chou (丑) month, with Ji Earth Direct Resource revealed in the month stem, commanding the Month Pillar's authority. Both Earth and Metal are strong — the Day Master is extremely powerful.

**术语格式**：
- 正官格（Direct Officer Pattern）
- 用神（Favorable Element）
- 大运（Major Luck Cycle）

**典籍引用格式**：
> 《滴天髓》原文："从强者，势不可挡。"
> As stated in Dripping Sky Marrow (滴天髓): "The extremely strong chart cannot be resisted."

**禁止**：
- 纯英文输出
- 纯中文输出
- 英文只是总结而非完整翻译
- 机器翻译腔

## 重要
- 不用 emoji
- 使用表格呈现数据
- 引用典籍时注明出处
- 凶年用凶度评分（★☆~★★★★★）
- 这是一份付费级别的深度报告，内容必须详尽充实"""


@app.get("/health")
async def health_check():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    return {
        "status": "healthy" if api_key else "degraded",
        "api_key_configured": bool(api_key),
        "skill_md_loaded": bool(SKILL_CONTENT),
        "books_dir_exists": os.path.isdir(BOOKS_DIR),
        "kg_dir_exists": os.path.isdir(KG_DIR),
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

    # ── Knowledge base retrieval layer ──
    # Build search queries from birth info
    year = int(info.birth_date.split("-")[0])
    # Map year to heavenly stem
    stems = ["庚", "辛", "壬", "癸", "甲", "乙", "丙", "丁", "戊", "己"]
    heavenly_stem = stems[year % 10]

    search_queries = [
        heavenly_stem,           # e.g. "庚" for 1990
        "用神",
        "格局",
        "大运",
        "日主",
        "调候",
    ]
    kb_context = search_knowledge_base(search_queries)

    # Enhance system prompt with retrieved classical references
    active_system = SYSTEM_PROMPT
    if kb_context:
        active_system += f"""

## 本次相关典籍参考（请在报告中引用这些原典段落）

以下是从原典和知识图谱中检索出的相关参考材料。请在报告的相应章节中引用原文，注明出处，以增强报告的学术权威性。

{kb_context}

引用规则：
- 在分析相关章节时引用上述典籍原文
- 引用格式：「原文」（English translation — 出处书名）
- 不要编造典籍中没有的内容"""

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
