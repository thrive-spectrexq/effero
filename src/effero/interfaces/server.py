"""Effero REST and WebSocket API Server powered by FastAPI."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from effero import __version__
from effero.core.agent import Agent
from effero.core.event_bus import Event
from effero.protocols.a2a import AgentCard, TaskMessage, TaskState
from effero.safety.approval import ApprovalRequest, CallbackApprovalHandler

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Request / Response Schemas
# -----------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., description="Message or instruction for the agent")


class ChatResponse(BaseModel):
    response: str
    version: str = __version__


class SkillInvokeRequest(BaseModel):
    skill: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    comment: str | None = None


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    min_score: float = 0.0


class A2ATaskRequest(BaseModel):
    sender: str = "peer-agent"
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Application Factory
# -----------------------------------------------------------------------------


def create_app(agent: Agent | None = None) -> FastAPI:
    """Create and configure FastAPI application bound to an Effero Agent."""
    app = FastAPI(
        title="Effero Agent Runtime API",
        description="Unified REST and WebSocket API for physical-digital AI agency",
        version=__version__,
    )

    # Active agent instance
    if agent is None:
        agent = Agent()

    # Configure CORS securely
    cors_origins = (
        agent.config.server.cors_origins
        if agent.config and agent.config.server and agent.config.server.cors_origins
        else []
    )
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Wildcard origin cannot have allow_credentials=True per CORS specification
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # API Authentication Setup
    # Default-safe: if no api_key is configured and no_auth is False, generate an ephemeral token
    # (Jupyter pattern) so endpoints are never left open to the network by default.
    no_auth_configured = bool(agent.config and agent.config.server and agent.config.server.no_auth)
    raw_api_key = agent.config.server.api_key if agent.config and agent.config.server else None

    if no_auth_configured or raw_api_key == "":
        expected_api_key = None
        logger.warning(
            "Effero API server is running without authentication (--no-auth). "
            "Anyone who can reach this host can invoke skills or resolve approvals."
        )
    elif raw_api_key:
        expected_api_key = raw_api_key
        agent.server_api_key = expected_api_key
    else:
        # Default-safe ephemeral token
        expected_api_key = secrets.token_urlsafe(24)
        if agent.config and agent.config.server:
            agent.config.server.api_key = expected_api_key
        agent.server_api_key = expected_api_key
        logger.info(
            f"Generated ephemeral API key: {expected_api_key} "
            "(pass via 'Authorization: Bearer <token>' or 'X-API-Key: <token>')"
        )

    app.state.api_key = expected_api_key

    async def verify_auth(request: Request) -> None:
        if not expected_api_key:
            return
        auth_header = request.headers.get("authorization")
        api_key_header_val = request.headers.get("x-api-key")
        token = api_key_header_val
        if not token and auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

        if not token or not secrets.compare_digest(token, expected_api_key):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Invalid or missing API key. Provide via "
                    "'Authorization: Bearer <key>' or 'X-API-Key: <key>' header."
                ),
            )

    async def verify_ws_auth(websocket: WebSocket) -> bool:
        if not expected_api_key:
            return True
        token = websocket.query_params.get("token") or websocket.query_params.get("api_key")
        if not token:
            token = websocket.headers.get("x-api-key")
        if not token:
            auth_header = websocket.headers.get("authorization")
            if auth_header and auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()

        if token and secrets.compare_digest(token, expected_api_key):
            return True

        await websocket.close(code=1008, reason="Unauthorized: invalid or missing API key")
        return False

    # Active pending approvals tracking
    pending_approvals: dict[str, ApprovalRequest] = {}
    active_websockets: set[WebSocket] = set()

    # Configure callback approval handler for remote resolution
    def handle_approval_request(req: ApprovalRequest):
        pending_approvals[req.id] = req
        # Broadcast approval request to connected WebSocket clients
        msg = {
            "type": "approval_required",
            "request_id": req.id,
            "skill_name": req.skill_name,
            "arguments": req.arguments,
            "reason": req.reason,
            "safety_class": req.safety_class,
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast_json(msg))
        except RuntimeError:
            pass

    callback_handler = CallbackApprovalHandler(callback=handle_approval_request)
    agent.approval_handler = callback_handler
    agent.planner.approval_handler = callback_handler

    # Broadcast event bus messages to all active WebSockets
    async def event_bus_listener(event: Event):
        data = {
            "type": "event",
            "topic": event.topic,
            "source": event.source,
            "data": event.data,
            "timestamp": event.timestamp,
        }
        await broadcast_json(data)

    agent.event_bus.subscribe("*", event_bus_listener)

    async def broadcast_json(data: dict[str, Any]) -> None:
        to_remove = set()
        for ws in active_websockets:
            try:
                await ws.send_json(data)
            except Exception:
                to_remove.add(ws)
        active_websockets.difference_update(to_remove)

    # State storage for A2A tasks
    tasks: dict[str, TaskMessage] = {}

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await agent.start()
        yield
        await agent.stop()

    app.router.lifespan_context = lifespan

    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard():
        from pathlib import Path

        html_file = Path(__file__).parent / "static" / "index.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Effero Agent Runtime</h1>")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": __version__,
            "agent_name": agent.config.agent.name,
            "skills_count": len(agent.skills.list()),
        }

    @app.get("/v1/agent-card")
    async def get_agent_card():
        return AgentCard(
            name=agent.config.agent.name,
            description="Effero multimodal agent runtime",
            endpoint="/",
            version=__version__,
            skills=agent.available_skills(),
        ).to_dict()

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(verify_auth)])
    async def chat(req: ChatRequest):
        reply = await agent.chat(req.message)
        return ChatResponse(response=reply)

    @app.get("/v1/skills")
    async def list_skills():
        items = []
        for name in agent.skills.list():
            try:
                spec = agent.skills.get(name)
                items.append(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "safety_class": str(spec.safety_class),
                        "parameters": [
                            {
                                "name": p.name,
                                "annotation": str(p.annotation),
                                "default": str(p.default),
                            }
                            for p in spec.signature.parameters.values()
                        ],
                    }
                )
            except Exception:
                items.append({"name": name})
        return {"skills": items}

    @app.post("/v1/skills/invoke", dependencies=[Depends(verify_auth)])
    async def invoke_skill(req: SkillInvokeRequest):
        res = await agent.planner._execute_skill(req.skill, req.arguments)
        return {"skill": req.skill, "result": res}

    @app.get("/v1/approvals", dependencies=[Depends(verify_auth)])
    async def list_approvals():
        return [
            {
                "id": req.id,
                "skill_name": req.skill_name,
                "arguments": req.arguments,
                "reason": req.reason,
                "safety_class": req.safety_class,
                "created_at": req.created_at,
            }
            for req in pending_approvals.values()
        ]

    @app.post("/v1/approvals/{request_id}", dependencies=[Depends(verify_auth)])
    async def resolve_approval(request_id: str, decision: ApprovalDecisionRequest):
        if request_id not in pending_approvals:
            raise HTTPException(status_code=404, detail="Approval request not found")

        resolved = callback_handler.resolve(request_id, decision.approved, decision.comment)
        pending_approvals.pop(request_id, None)
        return {"request_id": request_id, "resolved": resolved, "approved": decision.approved}

    @app.get("/v1/memory/working", dependencies=[Depends(verify_auth)])
    async def get_working_memory():
        return {"messages": agent.working_memory.get_context()}

    @app.get("/v1/memory/episodic", dependencies=[Depends(verify_auth)])
    async def get_episodic_memory(limit: int = 50):
        return {"history": agent.episodic_memory.load_history(limit=limit)}

    @app.post("/v1/memory/semantic/search", dependencies=[Depends(verify_auth)])
    async def search_semantic_memory(req: SemanticSearchRequest):
        records = agent.semantic_memory.search(req.query, top_k=req.top_k, min_score=req.min_score)
        return {"results": [r.to_dict() for r in records]}

    @app.post("/v1/tasks", dependencies=[Depends(verify_auth)])
    async def create_a2a_task(req: A2ATaskRequest):
        task = TaskMessage(
            sender=req.sender,
            instruction=req.instruction,
            context=req.context,
            state=TaskState.PENDING,
        )
        tasks[task.task_id] = task

        # Asynchronously run task
        async def run_task():
            task.state = TaskState.RUNNING
            try:
                out = await agent.run(task.instruction)
                task.result = out
                task.state = TaskState.COMPLETED
            except Exception as e:
                task.error = str(e)
                task.state = TaskState.FAILED

        asyncio.create_task(run_task())
        return task.to_dict()

    @app.get("/v1/tasks/{task_id}", dependencies=[Depends(verify_auth)])
    async def get_a2a_task(task_id: str):
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        return tasks[task_id].to_dict()

    # -------------------------------------------------------------------------
    # WebSocket Endpoints
    # -------------------------------------------------------------------------

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        if not await verify_ws_auth(websocket):
            return
        await websocket.accept()
        active_websockets.add(websocket)
        try:
            while True:
                # Keepalive ping
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            active_websockets.discard(websocket)

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        if not await verify_ws_auth(websocket):
            return
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    user_msg = payload.get("message", "")
                except json.JSONDecodeError:
                    user_msg = data

                if user_msg.strip():
                    response = await agent.chat(user_msg)
                    await websocket.send_json({"type": "chat_response", "text": response})
        except WebSocketDisconnect:
            pass

    return app
