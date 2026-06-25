from typing import TypedDict, Literal

AgentType = Literal["query_youtube_rag", "query_sql_agent", "query_browser_agent", "unknown"]

class SupervisorState(TypedDict):
    question: str
    
    # Multi-intent: birden fazla tool planlanabilir
    planned_tools: list[dict]   # [{"tool": "query_youtube_rag", "args": {...}}, ...]
    current_tool_index: int     # şu an hangi tool çalışıyor
    
    # Geriye dönük uyumluluk
    selected_tool: AgentType
    tool_args: dict
    
    agent_response: str | None
    all_responses: list[dict]   # tüm tool sonuçları birikir
    
    is_sufficient: bool | None
    attempts: int
    
    trace: list[dict]
    final_answer: str | None