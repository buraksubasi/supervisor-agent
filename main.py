"""
Supervisor Agent
================
Gelen kullanıcı sorusunu LangGraph pipeline'ıyla analiz eder,
hangi alt servis(ler)in çağrılması gerektiğine karar verir, onları tetikler
ve sonuçları sentezleyip kullanıcıya tek bir cevap olarak döner.

Çalıştırma (local):
    uvicorn main:app --reload --port 8000
"""

import json
import logging
import time
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_AGENT_STEPS  # noqa: F401
from database.connection import init_db, get_db, AsyncSessionLocal
from database.repository import TraceRepository
from graph.builder import supervisor_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supervisor")

genai.configure(api_key=GEMINI_API_KEY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Supervisor Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _initial_state(question: str) -> dict:
    return {
        "question": question,
        "planned_tools": [],
        "current_tool_index": 0,
        "selected_tool": "unknown",
        "tool_args": {},
        "agent_response": None,
        "all_responses": [],
        "is_sufficient": None,
        "attempts": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "trace": [],
        "final_answer": None,
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    trace: list[dict]
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# POST /ask  (senkron)
# ---------------------------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    start_time = time.time()

    result = await supervisor_graph.ainvoke(_initial_state(req.question))

    latency_ms = int((time.time() - start_time) * 1000)

    trace_items = result.get("trace") or []
    used_tools = list({t["tool"] for t in trace_items})
    agent_type_label = (
        "supervisor" if len(used_tools) > 1
        else (used_tools[0] if used_tools else "supervisor")
    )

    async with AsyncSessionLocal() as db:
        repo = TraceRepository(db)
        trace_record = await repo.create_trace(
            question=req.question,
            agent_type=agent_type_label,
            answer=result.get("final_answer", ""),
            latency_ms=latency_ms,
            input_tokens=result.get("input_tokens") or None,
            output_tokens=result.get("output_tokens") or None,
        )
        if trace_items:
            await repo.add_tool_calls(trace_record.id, trace_items)

    return AskResponse(
        answer=result["final_answer"] or "",
        trace=result["trace"],
        trace_id=trace_record.id,
    )


# ---------------------------------------------------------------------------
# POST /ask/stream  (SSE)
# ---------------------------------------------------------------------------

@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    def emit(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_generator():
        start_time = time.time()
        collected_trace: list[dict] = []
        final_answer = ""

        try:
            yield emit({"type": "thinking", "message": "Sorunuz analiz ediliyor..."})

            final_state: dict = {}

            async for event in supervisor_graph.astream_events(
                _initial_state(req.question),
                version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")

                if kind == "on_chain_start":
                    if name == "classify_intent":
                        yield emit({"type": "thinking", "message": "Soru analiz ediliyor..."})
                    elif name == "run_agent":
                        inp = event.get("data", {}).get("input", {})
                        tool = inp.get("selected_tool", "")
                        tool_labels = {
                            "query_youtube_rag": "YouTube RAG",
                            "query_sql_agent": "SQL Agent",
                            "query_browser_agent": "Browser Agent",
                        }
                        yield emit({
                            "type": "thinking",
                            "message": f"{tool_labels.get(tool, tool)} çağrılıyor...",
                        })
                    elif name == "grade_response":
                        yield emit({"type": "thinking", "message": "Cevap kalitesi değerlendiriliyor..."})
                    elif name == "synthesize":
                        yield emit({"type": "thinking", "message": "Yanıt yazılıyor..."})

                elif kind == "on_chain_end":
                    raw_output = event.get("data", {}).get("output")
                    # LangGraph beta: output bazen dict, bazen string/list olabilir
                    output: dict = raw_output if isinstance(raw_output, dict) else {}

                    if name == "classify_intent":
                        tool = output.get("selected_tool", "")
                        args = output.get("tool_args", {})
                        if tool and tool != "unknown":
                            yield emit({"type": "tool_call", "step": 1, "tool": tool, "args": args})

                    elif name == "run_agent":
                        response_text = output.get("agent_response", "")
                        new_trace = output.get("trace", [])
                        if isinstance(new_trace, list):
                            collected_trace.extend(new_trace)
                        tool = new_trace[-1]["tool"] if new_trace else ""
                        yield emit({
                            "type": "tool_result",
                            "step": len(collected_trace),
                            "tool": tool,
                            "preview": response_text[:300] if response_text else "",
                        })

                    elif name == "grade_response":
                        if not output.get("is_sufficient", True):
                            yield emit({"type": "thinking", "message": "Cevap yetersiz, tekrar deneniyor..."})

                    elif name in ("synthesize", "handle_unknown"):
                        final_answer = output.get("final_answer", "")
                        if final_answer:
                            yield emit({"type": "answer", "content": final_answer})

                    # Son state'i güvenli şekilde biriktir
                    if output:
                        final_state.update(output)

            # Trace'i DB'ye kaydet
            latency_ms = int((time.time() - start_time) * 1000)

            # Çoklu tool kullanıldıysa agent_type = "supervisor",
            # tekil kullanımda gerçek tool adını yaz.
            used_tools = list({t["tool"] for t in collected_trace})
            agent_type_label = (
                "supervisor" if len(used_tools) > 1
                else (used_tools[0] if used_tools else "supervisor")
            )

            async with AsyncSessionLocal() as db:
                repo = TraceRepository(db)
                trace_record = await repo.create_trace(
                    question=req.question,
                    agent_type=agent_type_label,
                    answer=final_answer,
                    latency_ms=latency_ms,
                    input_tokens=final_state.get("input_tokens") or None,
                    output_tokens=final_state.get("output_tokens") or None,
                )
                if collected_trace:
                    await repo.add_tool_calls(trace_record.id, collected_trace)

            yield emit({"type": "done", "trace": collected_trace, "trace_id": trace_record.id})

        except Exception as exc:
            logger.error("Stream hatası: %s", exc, exc_info=True)
            yield emit({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    repo = TraceRepository(db)
    return await repo.get_stats(days=days)


@app.get("/api/traces")
async def get_traces(
    limit: int = 50,
    offset: int = 0,
    agent_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    repo = TraceRepository(db)
    traces = await repo.get_traces(limit=limit, offset=offset, agent_type=agent_type)
    return [
        {
            "id": t.id,
            "question": t.question,
            "answer": t.answer,
            "agent_type": t.agent_type,
            # tool_calls selectinload ile yüklendi — hangi tool'ların çalıştığını listele
            "tools_used": sorted({tc.tool_name for tc in (t.tool_calls or [])}),
            "latency_ms": t.latency_ms,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "cost_usd": t.cost_usd,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in traces
    ]


@app.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    repo = TraceRepository(db)
    trace = await repo.get_trace_by_id(trace_id)
    if not trace:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trace bulunamadı")

    return {
        "id": trace.id,
        "question": trace.question,
        "answer": trace.answer,
        "agent_type": trace.agent_type,
        "latency_ms": trace.latency_ms,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "cost_usd": trace.cost_usd,
        "status": trace.status,
        "error_message": trace.error_message,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
        "tool_calls": [
            {
                "id": tc.id,
                "tool_name": tc.tool_name,
                "tool_args": tc.tool_args,
                "tool_result": tc.tool_result,
                "latency_ms": tc.latency_ms,
                "step_order": tc.step_order,
            }
            for tc in (trace.tool_calls or [])
        ],
        "evaluation": {
            "faithfulness_score": trace.evaluation.faithfulness_score,
            "relevance_score": trace.evaluation.relevance_score,
            "hallucination_score": trace.evaluation.hallucination_score,
            "overall_score": trace.evaluation.overall_score,
            "faithfulness_reason": trace.evaluation.faithfulness_reason,
            "relevance_reason": trace.evaluation.relevance_reason,
            "hallucination_reason": trace.evaluation.hallucination_reason,
            "evaluated_at": trace.evaluation.evaluated_at.isoformat() if trace.evaluation.evaluated_at else None,
        } if trace.evaluation else None,
    }


@app.get("/api/latency-chart")
async def get_latency_chart(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Zaman serisi latency verisi — Recharts için."""
    repo = TraceRepository(db)
    return await repo.get_latency_series(days=days)


@app.get("/api/eval-chart")
async def get_eval_chart(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Zaman serisi eval skor verisi — Recharts için."""
    repo = TraceRepository(db)
    return await repo.get_eval_series(days=days)


@app.post("/api/evaluate/{trace_id}")
async def evaluate_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Belirli bir trace için LLM-as-judge skorlamasını tetikler."""
    from fastapi import HTTPException
    from eval.judge import evaluate

    repo = TraceRepository(db)
    trace = await repo.get_trace_by_id(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace bulunamadı")
    if trace.evaluation:
        return {"message": "Zaten değerlendirilmiş", "trace_id": trace_id}

    # Tool sonuçlarını context olarak birleştir
    context = "\n\n".join(
        f"[{tc.tool_name}]\n{tc.tool_result or ''}"
        for tc in (trace.tool_calls or [])
    )

    result = evaluate(
        question=trace.question,
        answer=trace.answer or "",
        context=context,
    )

    eval_record = await repo.save_evaluation(
        trace_id=trace_id,
        faithfulness_score=result.faithfulness_score,
        relevance_score=result.relevance_score,
        hallucination_score=result.hallucination_score,
        faithfulness_reason=result.faithfulness_reason,
        relevance_reason=result.relevance_reason,
        hallucination_reason=result.hallucination_reason,
    )

    logger.info("[evaluate] trace=%s overall=%.3f", trace_id, result.overall_score)
    return {
        "trace_id": trace_id,
        "faithfulness": result.faithfulness_score,
        "relevance": result.relevance_score,
        "hallucination": result.hallucination_score,
        "overall": result.overall_score,
    }
