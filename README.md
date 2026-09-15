# Conecta 4 — 1vs1 online

Juego multijugador en tiempo real de "conectar 4 fichas propias en línea antes que tu rival" para dos
jugadores. Backend en **FastAPI + Socket.IO** (WebSockets), frontend en
**HTML/CSS/JS** puro.

## Reglas

1. El tablero tiene **7 columnas x 6 filas**. Empieza vacío; quién mueve
   primero se decide al azar al emparejar.
2. Por turnos, cada jugador pulsa una columna para soltar una ficha de su
   color; la ficha cae hasta la posición libre más baja de esa columna
   (gravedad), igual que en el Conecta 4 físico. Tiene 60 segundos para
   jugar; si se le acaba el tiempo, el turno pasa automáticamente al
   rival.
3. Si una columna está completamente llena, no se puede jugar en ella.
4. Gana quien primero consiga **4 fichas propias en línea** — horizontal,
   vertical o en diagonal (en cualquiera de las dos direcciones). Si el
   tablero se llena sin que nadie conecte 4, la partida es un **empate**.
5. El primero en ganar **3 partidas** se corona campeón de la sesión y el
   marcador vuelve a 0-0.

## Funciones

- **Menú principal** con estilo "candy": tarjeta de perfil arriba, accesos
  a Ajustes y Mensajes, dos botones de acción grandes ("Buscar Rival" y
  "Jugar con Amigos") y una barra de navegación inferior fija con 4
  secciones: Inicio, Inventario, Ranking y Tienda.
- **Tablero interactivo** de 7x6 con fichas rojas/amarillas que caen con
  una animación de gravedad y rebote al soltarse; la columna bajo el
  cursor se resalta para indicar dónde caería la próxima ficha, y las 4
  fichas ganadoras brillan al terminar la partida.
- **Monedas e Inventario/Tienda**: cada victoria da 10 monedas; se pueden
  gastar en la Tienda para desbloquear temas de color alternativos para
  toda la app, avatares premium y marcos de avatar, que luego se equipan
  desde el Inventario. Todo se guarda en el navegador (localStorage), sin
  necesidad de cuenta.
- **Ranking personal**: rango (Bronce/Plata/Oro/Platino) según tus
  victorias totales, más victorias/derrotas, % de victorias y mejor
  racha — estadística local de este navegador, no un ranking global entre
  jugadores.
- **Perfil persistente**: nombre y avatar (emoji) se eligen una vez y se
  recuerdan para todas las partidas; se pueden cambiar cuando quieras
  desde "Perfil".
- **Jugar con amigos**: crea una partida privada y comparte el código de 5
  caracteres o el enlace directo (`?room=CÓDIGO`) con quien quieras que
  juegue contigo; al abrir el enlace se entra directamente a la sala, sin
  pasar por el emparejamiento aleatorio.
- **Ajustes**: tema claro/oscuro y sonido, en una pantalla dedicada.
- **Marcador de sesión persistente**, con pantalla especial de "campeón"
  al llegar a 3 victorias.
- **Estadísticas de por vida** (victorias/derrotas totales en este
  navegador), visibles en el Perfil.
- **Revancha instantánea**: al terminar una partida, ambos pulsan "Jugar
  otra vez" y la partida arranca de nuevo con un tablero limpio, sin
  volver a emparejarse. Empieza quien perdió la ronda anterior.
- **Rendirse**: cualquiera puede rendirse durante la partida; el rival
  gana automáticamente.
- **Reconexión**: si recargas la página, cierras la app o se bloquea el
  móvil a mitad de partida, al volver recuperas tu partida en curso
  (mismo rival, mismo tablero) en vez de perderla. Tu rival ve un aviso
  de "esperando a que vuelva" durante 120 segundos.
- **Chat** en la propia partida.
- **Temporizador por turno**, sonidos y confeti al ganar (todo generado en
  el propio navegador, sin ficheros de audio externos).

## Estructura del proyecto

```
conecta-4-1vs1/
├── app.py              # Servidor FastAPI + Socket.IO (eventos, rutas)
├── game.py              # Lógica de partidas: cola, salas, tablero
├── requirements.txt
├── Procfile             # Comando de arranque para Render/Railway
├── render.yaml          # Configuración de despliegue en Render (Blueprint)
├── .python-version
├── .gitignore
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

El estado completo de la partida (tablero y cualquier estado por jugador)
**vive solo en el servidor** (dentro de `game.py`); el cliente solo recibe
lo que necesita ver, nunca información que deba permanecer oculta del
rival.

## Cómo funciona el emparejamiento

**Buscar Rival**: el jugador entra en una cola de espera en memoria del
servidor (una por cada modo, si el juego tiene variantes). En cuanto hay
dos jugadores esperando con el mismo modo, se emparejan y la partida
arranca al instante (el primer turno se decide al azar).

**Jugar con Amigos**: "Crear partida" genera un código de 5 caracteres (y
un enlace `?room=CÓDIGO`) y deja al creador esperando. "Unirme con
código" comprueba el código y muestra quién ha creado la partida; en
cuanto el anfitrión confirma, la partida arranca al instante para los dos
(sin pasar por la cola aleatoria).

Para probarlo tú solo puedes abrir **dos pestañas** del navegador con la
misma URL y completar el flujo (perfil + Buscar Rival, o Crear partida +
Unirme con código) en cada una.

## Requisitos

- Python 3.10 o superior
- pip

## Instalación y prueba en local

Desde la carpeta del proyecto, en PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Arranca el servidor en modo desarrollo (con recarga automática):

```powershell
uvicorn app:socket_app --reload
```

Abre en el navegador:

```
http://127.0.0.1:8000
```

Para probar una partida completa tú solo, abre **una segunda pestaña** (o
una ventana de incógnito) con la misma URL. Elige un nombre en cada una y
pulsa "Buscar partida" en ambas: se emparejarán automáticamente y podrás
jugar el 1 vs 1 entre las dos pestañas.

## Despliegue gratuito en Render

1. Sube el proyecto a un repositorio de GitHub (ver comandos abajo).
2. Entra en [render.com](https://render.com) y crea una cuenta gratuita.
3. Pulsa **New +** → **Blueprint**, y selecciona tu repositorio. Render
   leerá automáticamente el fichero `render.yaml` y configurará el
   servicio.
   - Si prefieres configurarlo a mano en su lugar, elige **New +** → **Web
     Service**, selecciona el repo y usa:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `uvicorn app:socket_app --host 0.0.0.0 --port $PORT`
     - **Plan:** Free
4. Despliega. Cuando termine el build, Render te dará una URL pública tipo
   `https://conecta-4-1vs1.onrender.com`. Compártela con tu rival para
   jugar online.

> Nota: en el plan gratuito, Render "duerme" el servicio tras un rato de
> inactividad; la primera petición tras dormir tarda unos segundos en
> responder mientras arranca de nuevo.

## Despliegue gratuito en Railway

1. Sube el proyecto a GitHub.
2. Entra en [railway.app](https://railway.app) y crea una cuenta gratuita.
3. **New Project** → **Deploy from GitHub repo** → selecciona tu
   repositorio.
4. Railway detecta Python automáticamente. Si no usa el `Procfile` por
   defecto, ve a **Settings** → **Deploy** y fija manualmente:
   - **Start Command:** `uvicorn app:socket_app --host 0.0.0.0 --port $PORT`
5. Ve a **Settings** → **Networking** → **Generate Domain** para obtener
   una URL pública HTTPS.
6. Comparte la URL para jugar online.

## Subir el proyecto a GitHub (paso previo a desplegar)

```bash
git init
git add .
git commit -m "Conecta 4: juego 1vs1 online"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/<tu-repo>.git
git push -u origin main
```

(Crea antes el repositorio vacío en GitHub desde la web, sin README, para
evitar conflictos al hacer push.)

## Limitaciones conocidas (a tener en cuenta)

- El estado de las partidas se guarda **en memoria** del proceso del
  servidor: si despliegas con varias instancias/réplicas, dos jugadores
  podrían caer en instancias distintas y nunca emparejarse. Usa siempre
  **1 instancia** (es lo que hacen por defecto los planes gratuitos de
  Render/Railway).
- Los códigos de sala de "Jugar con Amigos" viven en memoria del
  servidor: si recargas la página mientras esperas a que se una un
  amigo, el código se pierde y hay que crear uno nuevo (no aplica una vez
  la partida ha empezado, ahí sí funciona la reconexión normal).
- Las estadísticas, preferencias y la reconexión se guardan en el
  navegador (localStorage/sessionStorage) de cada jugador, no en una
  cuenta: si cambias de navegador o dispositivo, empiezan de cero. Si
  abres dos pestañas del juego en el mismo navegador para probarlo tú
  solo, las estadísticas globales de "victorias/derrotas" se mezclarán
  entre ambas pestañas (es solo un efecto de probarlo así; entre dos
  personas en dispositivos distintos no ocurre).
