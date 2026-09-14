# Guía de diseño — Conecta 4

Dirección visual: **estilo juego móvil amigable / "candy"**, tipo Two Dots
o Toon Blast — no glassmorphism abstracto ni sci-fi. Piezas redondeadas,
colores saturados tipo caramelo, profundidad suave (no plano, pero tampoco
fotorrealista). Mismo lenguaje visual en TODA la app: menú, tablero,
pantallas secundarias — no solo los fondos.

<!-- Rellena esta guía con las decisiones reales tomadas para este juego
     (ver references/design-system.md del skill duel-game-builder para
     cómo elegir cada apartado). Bórrala si el usuario pide un estilo
     distinto a "candy". -->

## Fondos de menú

- `frontend/assets/bg-menu-dark.jpg` — versión oscura.
- `frontend/assets/bg-menu-light.jpg` — versión clara.
- Tema visual: "fichas de caramelo rojo y amarillo cayendo sobre un
  tablero de arcade azul brillante", estilo juego móvil casual — nostalgia
  de Conecta 4 clásico pero con el acabado redondeado y saturado "candy".
  Cualquier fondo nuevo debe generarse para **ambos** temas, no solo uno.
  De momento el proyecto usa solo `--bg-glow` (sin foto) — ver
  `references/design-system.md` del skill → "Fondos de menú".
- Referenciados desde `--bg-photo` en `style.css`. Recuerda subir el
  `?v=N` al reemplazar el archivo (ver [CLAUDE.md](CLAUDE.md)).

## Tipografía

Google Fonts, cargadas en `index.html`:

- **Manrope** (700/800) — `--font-display`, para títulos y marcador.
- **Inter** (400–800) — texto general.
- **JetBrains Mono** (600/700) — códigos de sala / valores monoespaciados.

## Paleta — tema oscuro (`:root`)

| Uso | Variable | Valor |
|---|---|---|
| Fondo base | `--bg` | `#0f1420` |
| Tarjeta | `--card` | `#1a2235` |
| Texto | `--text` | `#eef2ff` |
| Texto secundario | `--muted` | `#94a3c4` |
| Acento (UI, reskineable por Tienda) | `--accent` | `#3b82f6` |
| "Yo" en el tablero (fijo, NO reskineable) | `--mine` | `#ff4757` |
| Rival (fijo) | `--rival` | `#ffd23f` |
| Éxito | `--success` | `#2ecc71` |
| Peligro | `--danger` | `#ef4444` |
| Aviso | `--warning` | `#f59e0b` |

## Paleta — tema claro (`[data-theme="light"]`)

| Uso | Variable | Valor |
|---|---|---|
| Fondo base | `--bg` | `#eef3ff` |
| Tarjeta | `--card` | `#ffffff` |
| Acento | `--accent` | `#2563eb` |
| "Yo" en el tablero (fijo) | `--mine` | `#e11d2e` |
| Rival (fijo) | `--rival` | `#d69a00` |

En ambos temas, el color de `--mine` = jugador propio y `--rival` = rival
**no cambia nunca**, ni siquiera al equipar un tema de la Tienda (que solo
recolorea `--accent`/`--accent-strong`/`--accent-dark`) — ver
[CLAUDE.md](CLAUDE.md) → "Convenciones importantes".

## Colores de acento por sección (chips)

- Amigos: `--chip-friends`
- Perfil: `--chip-profile`
- Ajustes: `--chip-settings`

## Radios y sombras

- Radios: `--radius-lg: 22px`, `--radius-md: 16px`, `--radius-sm: 11px` —
  todo muy redondeado, coherente con el tono "candy".
- Sombras: `--shadow-sm/md/lg`, más marcadas en tema oscuro que en claro.

## El tablero

Rejilla de celdas HTML (7 columnas x 6 filas) dentro de `.board-wrap`, en
vez de SVG — el patrón recomendado en `references/design-system.md` para
tableros de cuadrícula tipo Conecta 4. Cada celda vacía es un círculo
hueco (`background: var(--input-bg)`); al caer una ficha, se rellena con
`--mine`/`--mine-strong` (rojo) o `--rival`/`--rival-strong` (amarillo)
con una animación de "caída" + rebote (`cubic-bezier(0.34, 1.56, 0.64, 1)`)
que simula la gravedad, en vez de aparecer instantáneamente. Al pasar el
ratón por una columna (o al enfocarla en móvil), esa columna entera se
resalta para indicar dónde caería la ficha. Las 4 fichas ganadoras se
resaltan con un brillo/pulso adicional al terminar la partida.

## Iconografía / elementos especiales

Este juego no tiene poderes ni variantes de modo — un único modo
"Clásico" fijo (`MODES = ("classic",)` en `game.py`), sin selector en el
cliente.
