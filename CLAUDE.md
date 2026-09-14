# Conecta 4 — contexto de proyecto

Juego 1vs1 online de "conectar 4 fichas propias en línea antes que tu rival". Backend FastAPI +
python-socketio, frontend HTML/CSS/JS puro (sin build step, sin framework).
Ver [README.md](README.md) para reglas de juego y despliegue completos —
este archivo es solo para trabajar de forma eficiente en el código.

## Estructura (no releer salvo que cambie algo aquí)

- `app.py` — rutas HTTP + handlers de eventos Socket.IO (join_game,
  create_room, join_room, set_lobby_mode, drop_piece, surrender,
  request_rematch, send_chat, rejoin, disconnect).
- `game.py` — lógica pura de partida: `Room`, `Player`, tablero, reglas del
  juego. Sin nada de red aquí.
- `frontend/index.html` — todas las pantallas (menú, lobby, partida, etc.)
  como `<section>` que se muestran/ocultan con `showScreen()`.
- `frontend/style.css` — un solo archivo, variables CSS por tema en `:root`
  (dark) y `[data-theme="light"]` (claro).
- `frontend/app.js` — todo el cliente: socket, estado, render del tablero,
  pantallas.
- `frontend/assets/` — imágenes (fondos de menú).

No hay `.venv/` ni `__pycache__/` que leer (ver `.claudeignore`).

## Convenciones importantes

- **Cache-busting manual**: `index.html` referencia `style.css?v=N` y
  `app.js?v=N`. Cada vez que edites `style.css` o `app.js`, sube el número
  de versión en el `<link>`/`<script>` de `index.html` — si no, el navegador
  sirve la copia cacheada y el cambio "no se ve" en producción.
- Lo mismo aplica a imágenes referenciadas desde CSS: si reemplazas un JPG
  con el mismo nombre de archivo, sube el `?v=N` en el `url(...)` dentro de
  `style.css` (variable `--bg-photo`), o el navegador seguirá mostrando la
  imagen vieja.
- El estado de las partidas vive **en memoria del proceso** (dict en
  `game.py`), no hay base de datos. Un despliegue debe ser siempre de
  **1 instancia**.
- Estadísticas/preferencias del jugador viven en `localStorage` del
  navegador, no en el servidor.
- El color "rojo = yo / amarillo = rival" en el tablero es fijo
  (`--mine`/`--rival` en style.css) y NO lo tocan los temas de color de la
  Tienda (que solo recolorean `--accent`) — mantener esta separación al
  tocar CSS del tablero o de la Tienda.
- El tablero no tiene variantes de modo: `MODES = ("classic",)` en
  `game.py`, sin selector de modo en el cliente.

## Guía de diseño

Paleta de colores, tipografías y dirección visual documentadas en
[DESIGN.md](DESIGN.md). Consúltalo antes de tocar colores, fondos o tono
visual para mantener consistencia con lo ya aprobado.

## Despliegue

Servicio en Render (`conecta-4-1vs1`, plan Free). Push a `main` en
GitHub despliega automáticamente. Nunca cambies el plan de pago sin
que el usuario lo pida explícitamente.
