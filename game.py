"""Lógica pura de partida: cola de emparejamiento, salas, reconexión y reglas
del juego (Conecta 4). Cero red aquí (eso vive en app.py) — así la lógica se
puede razonar y testear sin un socket de por medio.

Todo lo que NO está dentro de un bloque "GAME-SPECIFIC" es infraestructura
genérica de partida 1vs1 online (emparejamiento, salas de amigos con código,
reconexión, revancha, cronómetro de turno, campeón a N victorias) reutilizada
tal cual del scaffold de referencia.
"""

import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

# === GAME-SPECIFIC: tamaño del tablero y condición de victoria ===
ROWS = 6
COLS = 7
CONNECT_N = 4
# === fin GAME-SPECIFIC ===

TURN_SECONDS = 60
RECONNECT_GRACE_SECONDS = 60
CHAMPION_WINS = 3

# Conecta 4 clásico no tiene variantes de modo: un único modo fijo, sin
# pantalla de selección en el cliente.
MODES = ("classic",)
DEFAULT_MODE = "classic"

ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin caracteres ambiguos (0/O, 1/I)
ROOM_CODE_LENGTH = 5


def generate_room_code() -> str:
    return "".join(random.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


def is_valid_mode(value) -> bool:
    return value in MODES


# === GAME-SPECIFIC: reglas del tablero de Conecta 4 ===
def empty_board():
    return [[None for _ in range(COLS)] for _ in range(ROWS)]


def is_valid_col(col: int) -> bool:
    return 0 <= col < COLS


def lowest_empty_row(board, col: int) -> Optional[int]:
    """Busca la fila más baja libre de la columna (la ficha "cae" por
    gravedad). Devuelve None si la columna está llena."""
    for row in range(ROWS - 1, -1, -1):
        if board[row][col] is None:
            return row
    return None


def board_is_full(board) -> bool:
    return all(board[0][col] is not None for col in range(COLS))


def check_connect(board, row: int, col: int, owner) -> bool:
    """Comprueba si la ficha recién colocada en (row, col) completa 4 en
    línea (horizontal, vertical o cualquiera de las dos diagonales)."""
    directions = ((0, 1), (1, 0), (1, 1), (1, -1))
    for dr, dc in directions:
        count = 1
        r, c = row + dr, col + dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == owner:
            count += 1
            r += dr
            c += dc
        r, c = row - dr, col - dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == owner:
            count += 1
            r -= dr
            c -= dc
        if count >= CONNECT_N:
            return True
    return False
# === fin GAME-SPECIFIC ===


@dataclass
class Player:
    sid: str
    name: str
    avatar: str
    token: str
    score: int = 0  # GAME-SPECIFIC: nº de fichas colocadas por este jugador (solo cosmético)
    wins: int = 0


@dataclass
class Lobby:
    """Sala de amigos: primero se unen los dos jugadores y luego el anfitrión
    confirma, lo que arranca la partida al instante. 100% genérico, no hace
    falta tocar esta clase para un juego nuevo."""

    code: str
    host_sid: str
    host_name: str
    host_avatar: str
    host_token: str
    guest_sid: Optional[str] = None
    guest_name: Optional[str] = None
    guest_avatar: Optional[str] = None
    guest_token: Optional[str] = None

    def other_sid(self, sid: str) -> Optional[str]:
        if sid == self.host_sid:
            return self.guest_sid
        if sid == self.guest_sid:
            return self.host_sid
        return None


@dataclass
class Room:
    id: str
    mode: str
    players: dict  # sid -> Player
    turn_sid: str
    # === GAME-SPECIFIC: estado del tablero de Conecta 4 ===
    board: list = field(default_factory=empty_board)  # ROWS x COLS -> sid propietario o None
    # === fin GAME-SPECIFIC ===
    finished: bool = False
    turn_token: int = 0
    last_winner_sid: Optional[str] = None
    rematch_ready: set = field(default_factory=set)
    disconnected_sid: Optional[str] = None
    last_result: Optional[dict] = None  # {"reason", "winner_token", "draw"}

    def opponent_sid(self, sid: str) -> str:
        return next(s for s in self.players if s != sid)


class GameManager:
    """Mantiene en memoria la cola de espera y las partidas activas. Vive
    un único proceso (sin base de datos) — el despliegue debe ser siempre
    de 1 instancia. La mayoría de estos métodos son genéricos y no hace
    falta tocarlos; los que sí son específicos del juego están marcados."""

    def __init__(self):
        self.waiting: dict[str, dict] = {}
        self.rooms: dict[str, Room] = {}
        self.sid_to_room: dict[str, str] = {}
        self.token_to_room: dict[str, str] = {}
        self.lobbies: dict[str, Lobby] = {}
        self.sid_to_lobby: dict[str, str] = {}

    # ---------- Emparejamiento (genérico) ----------

    def join(self, sid: str, name: str, mode: str, avatar: str, token: str):
        """Añade al jugador a la cola de su modo o, si ya había alguien esperando
        con el mismo modo, crea la sala directamente.

        Devuelve (estado, room) con estado "waiting" o "matched".
        """
        self.cancel_lobby(sid)
        pending = self.waiting.get(mode)
        if pending is None:
            self.waiting[mode] = {"sid": sid, "name": name, "avatar": avatar, "token": token}
            return "waiting", None

        del self.waiting[mode]
        room = self._build_room(pending, {"sid": sid, "name": name, "avatar": avatar, "token": token}, mode)
        return "matched", room

    def cancel_waiting(self, sid: str) -> None:
        for mode, pending in list(self.waiting.items()):
            if pending["sid"] == sid:
                del self.waiting[mode]

    def _build_room(self, info1: dict, info2: dict, mode: str) -> Room:
        room_id = uuid.uuid4().hex[:8]
        p1 = Player(sid=info1["sid"], name=info1["name"], avatar=info1["avatar"], token=info1["token"])
        p2 = Player(sid=info2["sid"], name=info2["name"], avatar=info2["avatar"], token=info2["token"])
        first_sid = random.choice([p1.sid, p2.sid])

        room = Room(
            id=room_id,
            mode=mode,
            players={p1.sid: p1, p2.sid: p2},
            turn_sid=first_sid,
        )
        self.rooms[room_id] = room
        self.sid_to_room[p1.sid] = room_id
        self.sid_to_room[p2.sid] = room_id
        self.token_to_room[p1.token] = room_id
        self.token_to_room[p2.token] = room_id
        return room

    def get_room(self, sid: str) -> Optional[Room]:
        room_id = self.sid_to_room.get(sid)
        return self.rooms.get(room_id) if room_id else None

    # ---------- Jugadas ----------

    # === GAME-SPECIFIC: soltar una ficha en una columna. (1) comprueba que
    # la sala existe, no ha terminado y es el turno de `sid`; (2) valida la
    # columna y encuentra la fila donde cae la ficha; (3) comprueba si esa
    # jugada conecta 4 (gana) o si el tablero queda lleno (empate); (4) si
    # no, pasa el turno al rival. Devuelve None si la jugada no es válida. ===
    def drop_piece(self, sid: str, col: int) -> Optional[dict]:
        room = self.get_room(sid)
        if not room or room.finished or room.turn_sid != sid:
            return None
        if not is_valid_col(col):
            return None

        row = lowest_empty_row(room.board, col)
        if row is None:
            return None

        room.board[row][col] = sid
        player = room.players[sid]
        opponent = room.players[room.opponent_sid(sid)]
        player.score += 1

        result = {
            "room": room,
            "mover": player,
            "opponent": opponent,
            "move": {"row": row, "col": col, "by": sid},
            "finished": False,
            "winner": None,
            "draw": False,
            "champion": False,
        }

        if check_connect(room.board, row, col, sid):
            winner, champion = self._finish_room(room, winner_sid=sid)
            result["finished"] = True
            result["winner"] = winner
            result["draw"] = False
            result["champion"] = champion
            return result

        if board_is_full(room.board):
            winner, champion = self._finish_room(room, winner_sid=None)
            result["finished"] = True
            result["winner"] = None
            result["draw"] = True
            result["champion"] = champion
            return result

        room.turn_sid = opponent.sid
        room.turn_token += 1
        return result

    def _finish_room(self, room: Room, winner_sid: Optional[str] = None, reason: str = "complete"):
        """A diferencia del patrón genérico (comparar player.score), en
        Conecta 4 el ganador se conoce en el momento exacto de la jugada que
        conecta 4 — así que se recibe explícitamente en vez de calcularse
        comparando marcadores. `winner_sid=None` significa empate (tablero
        lleno sin conexión)."""
        room.finished = True
        winner = room.players[winner_sid] if winner_sid else None

        champion = False
        if winner:
            winner.wins += 1
            room.last_winner_sid = winner.sid
            champion = winner.wins >= CHAMPION_WINS

        room.last_result = {
            "reason": reason,
            "winner_token": winner.token if winner else None,
            "draw": winner is None,
        }
        return winner, champion
    # === fin GAME-SPECIFIC (jugada) ===

    def surrender(self, sid: str) -> Optional[dict]:
        """Rinde la partida: el rival gana automáticamente. Genérico."""
        room = self.get_room(sid)
        if not room or room.finished:
            return None

        quitter = room.players[sid]
        winner = room.players[room.opponent_sid(sid)]
        room.finished = True
        room.last_winner_sid = winner.sid
        winner.wins += 1
        room.last_result = {"reason": "surrender", "winner_token": winner.token, "draw": False}
        champion = winner.wins >= CHAMPION_WINS
        return {"room": room, "quitter": quitter, "winner": winner, "champion": champion}

    def expire_turn(self, room_id: str, expected_token: int) -> Optional[dict]:
        """Si el turno sigue vigente tras agotarse el tiempo, lo pasa al
        rival. Genérico — funciona igual para cualquier juego de turnos."""
        room = self.rooms.get(room_id)
        if not room or room.finished or room.turn_token != expected_token:
            return None

        timed_out_sid = room.turn_sid
        opponent = room.players[room.opponent_sid(timed_out_sid)]
        room.turn_sid = opponent.sid
        room.turn_token += 1
        return {"room": room, "timed_out_sid": timed_out_sid}

    def submit_rematch_ready(self, sid: str):
        """Marca a `sid` listo para la revancha. Cuando ambos lo están, reinicia
        el tablero.

        Devuelve (estado, room) con estado "waiting" o "started", o None si no procede.
        """
        room = self.get_room(sid)
        if not room or not room.finished:
            return None

        room.rematch_ready.add(sid)
        if len(room.rematch_ready) < 2:
            return "waiting", room

        for player in room.players.values():
            player.score = 0

        # === GAME-SPECIFIC: vaciar el tablero para la revancha ===
        room.board = empty_board()
        # === fin GAME-SPECIFIC ===

        loser_sid = (
            room.opponent_sid(room.last_winner_sid) if room.last_winner_sid else random.choice(list(room.players))
        )
        room.turn_sid = loser_sid
        room.turn_token += 1
        room.finished = False
        room.rematch_ready.clear()
        room.last_result = None
        return "started", room

    # ---------- Salas de amigos (genérico) ----------

    def create_lobby(self, sid: str, name: str, avatar: str, token: str) -> str:
        """Crea una sala de amigos vacía, pendiente de que se una un invitado."""
        self.cancel_waiting(sid)
        self.cancel_lobby(sid)
        code = generate_room_code()
        while code in self.lobbies:
            code = generate_room_code()
        self.lobbies[code] = Lobby(code=code, host_sid=sid, host_name=name, host_avatar=avatar, host_token=token)
        self.sid_to_lobby[sid] = code
        return code

    def get_lobby(self, sid: str) -> Optional[Lobby]:
        code = self.sid_to_lobby.get(sid)
        return self.lobbies.get(code) if code else None

    def join_lobby(self, code: str, sid: str, name: str, avatar: str, token: str) -> Optional[Lobby]:
        """Une a un segundo jugador a la sala `code`. Devuelve la Lobby, o None si no procede."""
        lobby = self.lobbies.get(code)
        if not lobby or lobby.guest_sid is not None or lobby.host_sid == sid:
            return None

        self.cancel_waiting(sid)
        self.cancel_lobby(sid)
        lobby = self.lobbies.get(code)
        if not lobby or lobby.guest_sid is not None:
            return None

        lobby.guest_sid = sid
        lobby.guest_name = name
        lobby.guest_avatar = avatar
        lobby.guest_token = token
        self.sid_to_lobby[sid] = code
        return lobby

    def set_lobby_mode(self, sid: str, mode: str) -> Optional[Room]:
        """El anfitrión confirma y arranca la partida al instante (Conecta 4
        no tiene variantes de modo que elegir)."""
        lobby = self.get_lobby(sid)
        if not lobby or lobby.host_sid != sid or lobby.guest_sid is None:
            return None

        del self.lobbies[lobby.code]
        self.sid_to_lobby.pop(lobby.host_sid, None)
        self.sid_to_lobby.pop(lobby.guest_sid, None)

        info1 = {
            "sid": lobby.host_sid,
            "name": lobby.host_name,
            "avatar": lobby.host_avatar,
            "token": lobby.host_token,
        }
        info2 = {
            "sid": lobby.guest_sid,
            "name": lobby.guest_name,
            "avatar": lobby.guest_avatar,
            "token": lobby.guest_token,
        }
        return self._build_room(info1, info2, mode)

    def cancel_lobby(self, sid: str) -> Optional[str]:
        """Cierra la sala de amigos de `sid` (si la hay) y devuelve el sid del otro
        jugador (si ya se había unido), para poder avisarle."""
        code = self.sid_to_lobby.pop(sid, None)
        if not code:
            return None
        lobby = self.lobbies.pop(code, None)
        if not lobby:
            return None
        other_sid = lobby.other_sid(sid)
        if other_sid:
            self.sid_to_lobby.pop(other_sid, None)
        return other_sid

    def remove_room(self, room_id: str) -> None:
        room = self.rooms.pop(room_id, None)
        if room:
            for player in room.players.values():
                self.sid_to_room.pop(player.sid, None)
                self.token_to_room.pop(player.token, None)

    def disconnect(self, sid: str):
        """Gestiona la desconexión de un socket: sale de la cola, cierra su sala de
        amigos pendiente (si la había) y marca su partida como pendiente de
        reconexión (no se borra al instante).

        Devuelve (room, lobby_other_sid): `room` si estaba en una partida activa,
        y el sid del otro jugador de su sala de amigos (si la había) para avisarle.
        """
        self.cancel_waiting(sid)
        lobby_other_sid = self.cancel_lobby(sid)
        room = self.get_room(sid)
        if room:
            room.disconnected_sid = sid
        return room, lobby_other_sid

    def finalize_disconnect(self, room_id: str, sid: str) -> Optional[Room]:
        """Tras agotarse el tiempo de gracia sin reconexión, cierra la sala definitivamente."""
        room = self.rooms.get(room_id)
        if not room or room.disconnected_sid != sid:
            return None
        self.remove_room(room_id)
        return room

    def rejoin(self, token: str, new_sid: str) -> Optional[Room]:
        """Reasocia una sala existente a una nueva conexión (tras recargar la página)."""
        room_id = self.token_to_room.get(token)
        room = self.rooms.get(room_id) if room_id else None
        if not room:
            return None

        old_sid = next((p.sid for p in room.players.values() if p.token == token), None)
        if old_sid is None:
            return None

        player = room.players.pop(old_sid)
        player.sid = new_sid
        room.players[new_sid] = player

        self.sid_to_room.pop(old_sid, None)
        self.sid_to_room[new_sid] = room.id

        # === GAME-SPECIFIC: el sid antiguo queda grabado como propietario de
        # fichas ya colocadas en el tablero: hay que actualizarlo para que el
        # cliente que reconecta pueda distinguir sus propias fichas
        # comparando con su nuevo socket.id. ===
        for r in range(ROWS):
            for c in range(COLS):
                if room.board[r][c] == old_sid:
                    room.board[r][c] = new_sid
        # === fin GAME-SPECIFIC ===

        if room.turn_sid == old_sid:
            room.turn_sid = new_sid
        if room.last_winner_sid == old_sid:
            room.last_winner_sid = new_sid
        if room.disconnected_sid == old_sid:
            room.disconnected_sid = None
        if old_sid in room.rematch_ready:
            room.rematch_ready.discard(old_sid)
            room.rematch_ready.add(new_sid)

        return room
