from langgraph.graph import StateGraph, START, END
from graph.state import SupervisorState
from graph.nodes import (
    classify_intent,
    run_agent,
    grade_response,
    synthesize,
    handle_unknown,
)
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("supervisor")

def route_after_classify(state: SupervisorState) -> str:
    if state["selected_tool"] == "unknown":
        return "unknown"
    return "agent"

def route_after_grade(state: SupervisorState) -> str:
    if not state.get("is_sufficient", True):
        # Aynı tool'u tekrar dene — classify'a dönme, aksi hâlde
        # current_tool_index sıfırlanır ve ilk tool baştan çalışır.
        return "retry"

    # Sıradaki tool var mı?
    planned = state.get("planned_tools", [])
    current_index = state.get("current_tool_index", 0)
    next_index = current_index + 1

    if next_index < len(planned):
        return "next_tool"  # sıradaki tool'a geç

    return "synthesize"  # hepsi tamamlandı

def advance_to_next_tool(state: SupervisorState) -> SupervisorState:
    """Sıradaki tool'u active yap."""
    planned = state["planned_tools"]
    next_index = state["current_tool_index"] + 1
    next_tool = planned[next_index]
    
    logger.info("[advance] Sıradaki tool: %s", next_tool["tool"])
    
    return {
        "current_tool_index": next_index,
        "selected_tool": next_tool["tool"],
        "tool_args": next_tool.get("args", {}),
        "is_sufficient": None,  # reset
        "attempts": 0,          # yeni tool için deneme sayacını sıfırla
    }

def build_supervisor_graph():
    graph = StateGraph(SupervisorState)
    
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("run_agent", run_agent)
    graph.add_node("grade_response", grade_response)
    graph.add_node("advance_to_next_tool", advance_to_next_tool)
    graph.add_node("synthesize", synthesize)
    graph.add_node("handle_unknown", handle_unknown)
    
    graph.add_edge(START, "classify_intent")
    
    graph.add_conditional_edges(
        "classify_intent",
        lambda s: "unknown" if s["selected_tool"] == "unknown" else "agent",
        {"agent": "run_agent", "unknown": "handle_unknown"}
    )
    
    graph.add_edge("run_agent", "grade_response")
    
    graph.add_conditional_edges(
        "grade_response",
        route_after_grade,
        {
            "synthesize": "synthesize",
            "retry": "run_agent",           # aynı tool'u tekrar çalıştır
            "next_tool": "advance_to_next_tool",
        }
    )
    
    # Sıradaki tool'a geçince run_agent'a dön
    graph.add_edge("advance_to_next_tool", "run_agent")
    
    graph.add_edge("synthesize", END)
    graph.add_edge("handle_unknown", END)
    
    return graph.compile()

supervisor_graph = build_supervisor_graph()