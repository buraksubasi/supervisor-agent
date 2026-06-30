from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from database.models import Trace, ToolCall, Evaluation
from datetime import datetime, timedelta
import json

class TraceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_trace(
        self,
        question: str,
        agent_type: str,
        answer: str | None = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> Trace:
        # Token maliyeti hesapla (Gemini fiyatı: $0.15/1M input, $0.60/1M output)
        cost_usd = None
        if input_tokens and output_tokens:
            cost_usd = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)

        trace = Trace(
            question=question,
            answer=answer,
            agent_type=agent_type,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(input_tokens or 0) + (output_tokens or 0),
            cost_usd=cost_usd,
            status=status,
            error_message=error_message,
        )
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def add_tool_calls(
        self,
        trace_id: str,
        tool_calls: list[dict],
    ) -> None:
        for i, call in enumerate(tool_calls):
            tool_call = ToolCall(
                trace_id=trace_id,
                tool_name=call.get("tool", ""),
                tool_args=json.dumps(call.get("args", {}), ensure_ascii=False),
                tool_result=str(call.get("result", ""))[:2000],  # max 2000 karakter
                step_order=i,
            )
            self.db.add(tool_call)
        await self.db.commit()

    async def save_evaluation(
        self,
        trace_id: str,
        faithfulness_score: float,
        relevance_score: float,
        hallucination_score: float,
        faithfulness_reason: str = "",
        relevance_reason: str = "",
        hallucination_reason: str = "",
    ) -> Evaluation:
        overall = (faithfulness_score + relevance_score + (1 - hallucination_score)) / 3

        eval_record = Evaluation(
            trace_id=trace_id,
            faithfulness_score=faithfulness_score,
            relevance_score=relevance_score,
            hallucination_score=hallucination_score,
            overall_score=overall,
            faithfulness_reason=faithfulness_reason,
            relevance_reason=relevance_reason,
            hallucination_reason=hallucination_reason,
            evaluated_at=datetime.utcnow(),
        )
        self.db.add(eval_record)
        await self.db.commit()
        await self.db.refresh(eval_record)
        return eval_record

    # ── Dashboard sorguları ──────────────────────────────────────────────────

    async def get_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        agent_type: str | None = None,
    ) -> list[Trace]:
        query = (
            select(Trace)
            .options(selectinload(Trace.tool_calls))  # tool adlarını tek sorguda çek
            .order_by(desc(Trace.created_at))
        )
        if agent_type:
            query = query.where(Trace.agent_type == agent_type)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_trace_by_id(self, trace_id: str) -> Trace | None:
        result = await self.db.execute(
            select(Trace).where(Trace.id == trace_id)
        )
        return result.scalar_one_or_none()

    async def get_stats(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)

        # Toplam istek sayısı
        total_result = await self.db.execute(
            select(func.count(Trace.id)).where(Trace.created_at >= since)
        )
        total_requests = total_result.scalar() or 0

        # Ortalama latency
        latency_result = await self.db.execute(
            select(func.avg(Trace.latency_ms)).where(
                Trace.created_at >= since,
                Trace.latency_ms.isnot(None)
            )
        )
        avg_latency = latency_result.scalar() or 0

        # Toplam maliyet
        cost_result = await self.db.execute(
            select(func.sum(Trace.cost_usd)).where(
                Trace.created_at >= since,
                Trace.cost_usd.isnot(None)
            )
        )
        total_cost = cost_result.scalar() or 0

        # Ortalama eval skoru
        eval_result = await self.db.execute(
            select(func.avg(Evaluation.overall_score)).join(
                Trace, Trace.id == Evaluation.trace_id
            ).where(Trace.created_at >= since)
        )
        avg_eval_score = eval_result.scalar() or 0

        # Agent dağılımı
        agent_result = await self.db.execute(
            select(Trace.agent_type, func.count(Trace.id))
            .where(Trace.created_at >= since)
            .group_by(Trace.agent_type)
        )
        agent_distribution = {row[0]: row[1] for row in agent_result.all()}

        return {
            "total_requests": total_requests,
            "avg_latency_ms": round(avg_latency),
            "total_cost_usd": round(total_cost, 6),
            "avg_eval_score": round(avg_eval_score, 3),
            "agent_distribution": agent_distribution,
            "period_days": days,
        }

    async def get_latency_series(self, days: int = 7) -> list[dict]:
        """Recharts için günlük ortalama latency serisi.

        cast(DateTime, Date) SQLite'ta çalışmaz; func.strftime kullanıyoruz.
        """
        since = datetime.utcnow() - timedelta(days=days)
        date_col = func.strftime("%Y-%m-%d", Trace.created_at).label("date")

        result = await self.db.execute(
            select(
                date_col,
                Trace.agent_type,
                func.avg(Trace.latency_ms).label("avg_latency"),
                func.count(Trace.id).label("count"),
            )
            .where(Trace.created_at >= since, Trace.latency_ms.isnot(None))
            .group_by(date_col, Trace.agent_type)
            .order_by(date_col)
        )
        return [
            {
                "date": row.date,
                "agent_type": row.agent_type,
                "avg_latency_ms": round(row.avg_latency),
                "count": row.count,
            }
            for row in result.mappings().all()
        ]

    async def get_eval_series(self, days: int = 7) -> list[dict]:
        """Recharts için günlük ortalama eval skoru serisi."""
        since = datetime.utcnow() - timedelta(days=days)
        date_col = func.strftime("%Y-%m-%d", Trace.created_at).label("date")

        result = await self.db.execute(
            select(
                date_col,
                func.avg(Evaluation.faithfulness_score).label("faithfulness"),
                func.avg(Evaluation.relevance_score).label("relevance"),
                func.avg(Evaluation.hallucination_score).label("hallucination"),
                func.avg(Evaluation.overall_score).label("overall"),
            )
            .join(Evaluation, Evaluation.trace_id == Trace.id)
            .where(Trace.created_at >= since)
            .group_by(date_col)
            .order_by(date_col)
        )
        return [
            {
                "date": row.date,
                "faithfulness": round(row.faithfulness or 0, 3),
                "relevance": round(row.relevance or 0, 3),
                "hallucination": round(row.hallucination or 0, 3),
                "overall": round(row.overall or 0, 3),
            }
            for row in result.mappings().all()
        ]