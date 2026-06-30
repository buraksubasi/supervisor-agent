from sqlalchemy import (
    Column, String, Integer, Float, 
    DateTime, Text, Boolean, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    pass

class Trace(Base):
    __tablename__ = "traces"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # İstek bilgileri
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    
    # Agent bilgisi
    agent_type = Column(String, nullable=False)  # youtube, sql, browser, supervisor
    
    # Performans
    latency_ms = Column(Integer, nullable=True)
    
    # Token kullanımı
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    
    # Durum
    status = Column(String, default="success")  # success, error
    error_message = Column(Text, nullable=True)
    
    # Zaman
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # İlişkiler
    tool_calls = relationship("ToolCall", back_populates="trace", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="trace", uselist=False, cascade="all, delete-orphan")


class ToolCall(Base):
    __tablename__ = "tool_calls"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String, ForeignKey("traces.id"), nullable=False)
    
    # Tool bilgisi
    tool_name = Column(String, nullable=False)
    tool_args = Column(Text, nullable=True)   # JSON string
    tool_result = Column(Text, nullable=True) # JSON string
    
    # Performans
    latency_ms = Column(Integer, nullable=True)
    step_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trace = relationship("Trace", back_populates="tool_calls")


class Evaluation(Base):
    __tablename__ = "evaluations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String, ForeignKey("traces.id"), nullable=False, unique=True)
    
    # LLM-as-judge skorları (0.0 - 1.0)
    faithfulness_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    hallucination_score = Column(Float, nullable=True)  # düşük = iyi
    
    # Genel skor
    overall_score = Column(Float, nullable=True)
    
    # Judge'ın gerekçesi
    faithfulness_reason = Column(Text, nullable=True)
    relevance_reason = Column(Text, nullable=True)
    hallucination_reason = Column(Text, nullable=True)
    
    # Değerlendirme durumu
    evaluated_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trace = relationship("Trace", back_populates="evaluation")