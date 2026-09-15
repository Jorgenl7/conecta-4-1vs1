"""Servidor del juego: FastAPI + Socket.IO.

Igual que game.py, todo lo que NO está en un bloque "GAME-SPECIFIC" es
infraestructura genérica reutilizable (servir el frontend, ciclo de vida de
conexión, emparejamiento, salas de amigos, reconexión, cronómetro de turno,
revancha, chat). Adapta solo los bloques marcados a las reglas del juego
nuevo; todo lo demás se copia tal cual.
"""

import asyncio
import pathlib

import socketio
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from game import (
    DEFAULT_MODE,
    MODES,
    RECONNECT_GRACE_SECONDS,
    TURN_SECONDS,
    GameManager,
)

BASE_DIR = pathlib.Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# ping_timeout más alto que el valor por defecto (60s en vez de 20s):
# los navegadores móviles ralentizan/pausan los timers de una pestaña en
# segundo plano (pantalla bloqueada, cambio de app), retrasando el "pong"
# de Socket.IO — con un timeout corto el servidor daba por perdido al
# jugador de inmediato aunque solo tuviera el móvil bloqueado un momento.
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*", ping_timeout=90, ping_interval=25)
fastapi_app = FastAPI()
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

fastapi_app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

games = GameManager()


@fastapi_app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


def session_score_payload(player, opponent):
    """Marcador de la sesión (victorias de partida a partida, para el campeón). Genérico."""
    return {"scoreYou": player.wins, "scoreOpponent": opponent.wins}


def sanitize_name(raw) -> str:
    return str(raw or "").strip()[:20] or "Jugador"


def sanitize_avatar(raw) -> str:
    avatar = str(raw or "").strip()
    return avatar[:8] if avatar else "🙂"


def sanitize_mode(raw) -> str:
    mode = str(raw or "").strip().lower()
    return mode if mode in MODES else DEFAULT_MODE


# === GAME-SPECIFIC: serialización del estado del tablero para enviarlo al
# cliente. El tablero se manda como una lista plana de fichas ya colocadas
# (en vez del grid completo) porque es más compacto y el cliente ya sabe
# reconstruir el grid a partir de row/col/by. ===
def serialize_board(room):
    pieces = []
    for row in range(len(room.board)):
        for col in range(len(room.board[row])):
            owner = room.board[row][col]
            if owner is not None:
                pieces.append({"row": row, "col": col, "by": owner})
    return pieces


def board_payload(room):
    return {"board": serialize_board(room)}
# === fin GAME-SPECIFIC ===


async def start_room(room):
    """Emite match_found a ambos jugadores y arranca el temporizador de
    turno. Genérico salvo el spread de board_payload/powers_payload."""
    for player_sid, player in room.players.items():
        opponent = room.players[room.opponent_sid(player_sid)]
        await sio.enter_room(player_sid, room.id)
        await sio.emit(
            "match_found",
            {
                "yourTurn": room.turn_sid == player_sid,
                "opponentName": opponent.name,
                "opponentAvatar": opponent.avatar,
                "mode": room.mode,
                "turnSeconds": TURN_SECONDS,
                "piecesYou": player.score,  # GAME-SPECIFIC: nº de fichas colocadas (cosmético)
                "piecesOpponent": opponent.score,
                **board_payload(room),  # GAME-SPECIFIC
                **session_score_payload(player, opponent),
            },
            to=player_sid,
        )
    sio.start_background_task(schedule_turn_timeout, room.id, room.turn_token)


async def schedule_turn_timeout(room_id: str, turn_token: int):
    """Genérico: pasa el turno automáticamente si se agota el tiempo."""
    await asyncio.sleep(TURN_SECONDS)

    result = games.expire_turn(room_id, turn_token)
    if result is None:
        return

    room = result["room"]
    timed_out_sid = result["timed_out_sid"]
    new_turn_sid = room.turn_sid

    await sio.emit(
        "turn_timeout",
        {"by": timed_out_sid, "yourTurn": False, "turnSeconds": TURN_SECONDS},
        to=timed_out_sid,
    )
    await sio.emit(
        "turn_timeout",
        {"by": timed_out_sid, "yourTurn": True, "turnSeconds": TURN_SECONDS},
        to=new_turn_sid,
    )
    sio.start_background_task(schedule_turn_timeout, room.id, room.turn_token)


async def schedule_disconnect_grace(room_id: str, sid: str):
    """Genérico: cierra la sala si el jugador no reconecta a tiempo."""
    await asyncio.sleep(RECONNECT_GRACE_SECONDS)

    room = games.finalize_disconnect(room_id, sid)
    if room is None:
        return

    opponent_sid = next((s for s in room.players if s != sid), None)
    if opponent_sid:
        await sio.emit("opponent_left", {}, to=opponent_sid)


@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")


@sio.event
async def disconnect(sid):
    room, lobby_other_sid = games.disconnect(sid)

    if lobby_other_sid:
        await sio.emit(
            "lobby_cancelled",
            {"message": "Tu amigo se ha desconectado. Vuelve a intentarlo."},
            to=lobby_other_sid,
        )

    if room is None:
        return

    opponent_sid = next((s for s in room.players if s != sid), None)
    if opponent_sid:
        await sio.emit("opponent_disconnected", {"graceSeconds": RECONNECT_GRACE_SECONDS}, to=opponent_sid)
    sio.start_background_task(schedule_disconnect_grace, room.id, sid)


@sio.event
async def join_game(sid, data):
    """Cola de emparejamiento aleatorio. Genérico."""
    data = data or {}
    name = sanitize_name(data.get("name"))
    avatar = sanitize_avatar(data.get("avatar"))
    token = str(data.get("token") or "").strip()
    mode = sanitize_mode(data.get("mode"))

    if not token:
        await sio.emit("join_error", {"message": "Falta identificador de sesión. Recarga la página."}, to=sid)
        return

    status, room = games.join(sid, name, mode, avatar, token)

    if status == "waiting":
        await sio.emit("waiting_for_opponent", {}, to=sid)
        return

    await start_room(room)


@sio.event
async def create_room(sid, data):
    """Jugar con amigos: generar código. Genérico."""
    data = data or {}
    name = sanitize_name(data.get("name"))
    avatar = sanitize_avatar(data.get("avatar"))
    token = str(data.get("token") or "").strip()

    if not token:
        await sio.emit("join_error", {"message": "Falta identificador de sesión. Recarga la página."}, to=sid)
        return

    code = games.create_lobby(sid, name, avatar, token)
    await sio.emit("room_created", {"code": code}, to=sid)


def lobby_ready_payload(lobby, sid):
    is_host = sid == lobby.host_sid
    return {
        "isHost": is_host,
        "opponentName": lobby.guest_name if is_host else lobby.host_name,
        "opponentAvatar": lobby.guest_avatar if is_host else lobby.host_avatar,
    }


@sio.event
async def join_room(sid, data):
    """Jugar con amigos: unirse con código. Genérico."""
    data = data or {}
    code = str(data.get("code") or "").strip().upper()
    name = sanitize_name(data.get("name"))
    avatar = sanitize_avatar(data.get("avatar"))
    token = str(data.get("token") or "").strip()

    if not token:
        await sio.emit("join_room_error", {"message": "Falta identificador de sesión. Recarga la página."}, to=sid)
        return

    lobby = games.join_lobby(code, sid, name, avatar, token)
    if lobby is None:
        await sio.emit("join_room_error", {"message": "Ese código no es válido o ya no está disponible."}, to=sid)
        return

    await sio.emit("lobby_ready", lobby_ready_payload(lobby, lobby.host_sid), to=lobby.host_sid)
    await sio.emit("lobby_ready", lobby_ready_payload(lobby, lobby.guest_sid), to=lobby.guest_sid)


@sio.event
async def set_lobby_mode(sid, data):
    """Genérico — si tu juego no tiene selector de modo, puedes hacer que
    el frontend emita esto con un único modo fijo nada más entrar los dos
    a la sala, sin pantalla de selección."""
    data = data or {}
    mode = sanitize_mode(data.get("mode"))

    room = games.set_lobby_mode(sid, mode)
    if room is None:
        return

    await start_room(room)


@sio.event
async def cancel_lobby(sid, data=None):
    games.cancel_waiting(sid)
    other_sid = games.cancel_lobby(sid)
    if other_sid:
        await sio.emit("lobby_cancelled", {"message": "Tu amigo ha cancelado la sala."}, to=other_sid)


@sio.event
async def rejoin(sid, data):
    """Reconexión tras recargar la página a mitad de partida. Genérico
    salvo el spread de board_payload/powers_payload."""
    data = data or {}
    token = str(data.get("token") or "").strip()
    if not token:
        await sio.emit("rejoin_failed", {}, to=sid)
        return

    room = games.rejoin(token, sid)
    if room is None:
        await sio.emit("rejoin_failed", {}, to=sid)
        return

    await sio.enter_room(sid, room.id)
    player = room.players[sid]
    opponent = room.players[room.opponent_sid(sid)]

    payload = {
        "opponentName": opponent.name,
        "opponentAvatar": opponent.avatar,
        "mode": room.mode,
        "piecesYou": player.score,
        "piecesOpponent": opponent.score,
        **board_payload(room),  # GAME-SPECIFIC
        **session_score_payload(player, opponent),
    }

    if room.finished:
        payload["state"] = "finished"
        last_result = room.last_result or {}
        payload["draw"] = bool(last_result.get("draw"))
        payload["won"] = (not payload["draw"]) and last_result.get("winner_token") == player.token
        payload["reason"] = last_result.get("reason", "complete")
    else:
        payload["state"] = "playing"
        payload["yourTurn"] = room.turn_sid == sid
        payload["turnSeconds"] = TURN_SECONDS

    await sio.emit("rejoined", payload, to=sid)
    await sio.emit("opponent_reconnected", {}, to=opponent.sid)


# === GAME-SPECIFIC: evento de jugada — soltar una ficha en una columna. El
# patrón (validar -> games.<tu_metodo>() -> si None emitir error, si no
# emitir el resultado a ambos jugadores -> si no terminó, reprogramar el
# cronómetro -> si terminó, emitir game_over a ambos) es el que reutilizas
# siempre, cambie lo que cambie el juego. ===
@sio.event
async def drop_piece(sid, data):
    data = data or {}
    try:
        col = int(data.get("col"))
    except (TypeError, ValueError):
        await sio.emit("drop_error", {"message": "Movimiento no válido."}, to=sid)
        return

    result = games.drop_piece(sid, col)
    if result is None:
        await sio.emit("drop_error", {"message": "No es tu turno o esa columna está llena."}, to=sid)
        return

    room = result["room"]
    mover = result["mover"]

    for target_sid, target_player in room.players.items():
        opponent = room.players[room.opponent_sid(target_sid)]
        await sio.emit(
            "piece_dropped",
            {
                "by": mover.sid,
                "move": result["move"],
                "yourTurn": (not result["finished"]) and room.turn_sid == target_sid,
                "turnSeconds": TURN_SECONDS,
                "piecesYou": target_player.score,
                "piecesOpponent": opponent.score,
            },
            to=target_sid,
        )

    if not result["finished"]:
        sio.start_background_task(schedule_turn_timeout, room.id, room.turn_token)
        return

    winner = result["winner"]
    champion = result["champion"]
    draw = result["draw"]
    p1, p2 = room.players.values()

    for player, opponent in ((p1, p2), (p2, p1)):
        payload = {
            "won": (not draw) and winner is not None and winner.sid == player.sid,
            "draw": draw,
            "piecesYou": player.score,
            "piecesOpponent": opponent.score,
            "winningMove": result["move"] if not draw else None,
            "reason": "complete",
            "champion": champion,
            **session_score_payload(player, opponent),
        }
        await sio.emit("game_over", payload, to=player.sid)

    if champion:
        p1.wins = 0
        p2.wins = 0
# === fin GAME-SPECIFIC (jugada) ===


@sio.event
async def surrender(sid, data=None):
    """Genérico."""
    result = games.surrender(sid)
    if result is None:
        return

    quitter = result["quitter"]
    winner = result["winner"]
    champion = result["champion"]

    payload_quitter = {
        "won": False,
        "draw": False,
        "piecesYou": quitter.score,
        "piecesOpponent": winner.score,
        "reason": "surrender",
        "champion": champion,
        **session_score_payload(quitter, winner),
    }
    payload_winner = {
        "won": True,
        "draw": False,
        "piecesYou": winner.score,
        "piecesOpponent": quitter.score,
        "reason": "surrender",
        "champion": champion,
        **session_score_payload(winner, quitter),
    }
    if champion:
        quitter.wins = 0
        winner.wins = 0
    await sio.emit("game_over", payload_quitter, to=quitter.sid)
    await sio.emit("game_over", payload_winner, to=winner.sid)


@sio.event
async def request_rematch(sid, data=None):
    """Genérico."""
    result = games.submit_rematch_ready(sid)
    if result is None:
        await sio.emit("rematch_error", {"message": "La partida ya no existe. Busca un rival nuevo."}, to=sid)
        return

    status, room = result

    if status == "waiting":
        await sio.emit("rematch_waiting", {}, to=sid)
        return

    for player_sid, player in room.players.items():
        opponent = room.players[room.opponent_sid(player_sid)]
        await sio.emit(
            "rematch_started",
            {
                "yourTurn": room.turn_sid == player_sid,
                "turnSeconds": TURN_SECONDS,
                "piecesYou": player.score,
                "piecesOpponent": opponent.score,
                **session_score_payload(player, opponent),
            },
            to=player_sid,
        )

    sio.start_background_task(schedule_turn_timeout, room.id, room.turn_token)


@sio.event
async def send_chat(sid, data):
    """Chat en partida. Genérico — solo hace falta si incluyes el módulo
    de chat (ver references/feature-modules.md)."""
    data = data or {}
    text = str(data.get("text") or "").strip()[:200]
    if not text:
        return

    room = games.get_room(sid)
    if not room:
        return

    sender = room.players.get(sid)
    if not sender:
        return

    await sio.emit(
        "chat_message",
        {"by": sid, "name": sender.name, "avatar": sender.avatar, "text": text},
        to=room.id,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:socket_app", host="0.0.0.0", port=8000, reload=True)
