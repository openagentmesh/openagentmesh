# Wildfire demo: 90-second recording storyboard

The recording is the product. This script is timed against measured system
behaviour (detection <1s after a 500°C write, drone flight 0.4 km/s, first
briefing ≤5s after correlation, chaos reclaim ≤11s, narrator 60s cadence)
so there is no dead air and no beat outruns the viewer.

## Prerequisites

- `OPENROUTER_API_KEY` exported in the shell that boots the demo (all LLM
  calls go through OpenRouter). Without it
  every LLM surface degrades honestly (briefings read "Briefing unavailable,
  see KV record", the sandbox shows a styled `llm_unavailable` error), but
  the recording needs the real prose.
- Boot with `uv run python -m demos.wildfire --seed 42`. The runner wipes
  the previous run's JetStream state (clean world, clean registry, terrain
  reproducible from the seed). Same seed, same terrain, same recording.
- Window layout at 1920x1080: scenario UI (http://127.0.0.1:8081) roughly
  the left 2/3, admin UI (http://127.0.0.1:8088) the right 1/3, both at
  100% zoom, no browser chrome (kiosk/app mode reads best on video).
- Admin UI event feed: pre-set the pattern to `mesh.>` and press Subscribe
  before recording starts, then select the tasker row so the sandbox form
  is one click away. Collapse nothing.
- Do a full dry run first. The beats below assume the world is idle at T+0.

## Beats

| T (s) | Action (operator) | What the viewer sees |
|-------|-------------------|----------------------|
| 0-4   | Nothing. Hold the idle frame. | Dark tactical terrain, fleet fanned out at HQ, admin registry: 13 agents grouped by channel, all green. Serious software in five seconds. |
| 4-6   | Double-click a ridge NE of HQ (~65% across, ~30% down). | Fire ignites on click one, intensifies on click two; ember glow starts spreading cell by cell. |
| 6-10  | Hands off. | Pulsing detection ring appears at the fire (UAV). Mission log: `uav thermal detection … sev 0.57`. Admin event feed streams the same cascade from the bus. |
| 8-14  | Hands off. | One drone claims (log: `drone … claimed detection`), its sprite departs HQ, trail drawing toward the fire. Briefing pane shows the labeled skeleton: "briefer is correlating detections…". |
| 12-20 | Hands off. | Briefing card slides in: severity chip on the ember ramp, LLM summary prose, persons/structures/confidence grid, recommended-action chips. |
| 18-24 | Hands off. | Drone arrives; survey completes (amber diamond, log line). Fire keeps growing. |
| 24-42 | Admin UI: the tasker detail is already open. Type `Send the water bomber to the big fire, high priority` into the sandbox and press Call. | "tasker is thinking" row with live elapsed timer (~2-4s), then the typed TaskCommand lands: target_fleet=heli, grounded coords, priority=high, one-line rationale. Natural language to typed contract, on camera. |
| 42-52 | Scenario UI: click the drone that surveyed (or any drone), then KILL PROCESS in the popover. | Popover with unit telemetry; on kill: alarm line in the mission log, sprite crosses out red, admin registry drone row flips to a red 4/5 within ~3 seconds. No refresh. |
| 52-68 | Hands off. | Watchdog reclaims the abandoned detection (`pending` again), a sibling drone claims and flies. The cascade self-heals while the dead instance stays red in the registry. |
| 68-80 | Single-click a second fire far south (~40% across, ~85% down), then double-click it. | Second cascade runs in parallel: new detection ring, second drone launches. Stats strip counters tick (detections, incidents). |
| 80-90 | Hands off. Pull focus to the scenario UI. | Narrator pane fills with the first Narrative paragraph (60s cadence). Fire one decaying, fire two under survey. Hold, cut. |

## Fallbacks

- Narrative not landed by T+85: hold the two-cascade wide shot to T+95;
  the narrator tick is 60s from boot and needs one briefing of material.
- LLM slow (>6s) on the tasker beat: the elapsed timer IS the shot; do not
  cut away, the reply lands.
- Fat-fingered extra fire: click it twice more (magnitude cycles to "off"
  which deletes the cells).

## Pacing dials (already tuned, `demos/wildfire/core/config.py`)

- `SPAWN_MAGNITUDE_MEDIUM = 500` -> double-click crosses the UAV's 450°C
  detection line (`UAV_CONFIDENCE_FLOOR = 0.5`). Single clicks (200°C)
  deliberately do NOT alert: the first click is foreshadowing, not payoff.
- `DRONE_SPEED_KM_S = 0.4` -> ~7s flight to a mid-map fire: long enough to
  read the trail, short enough to hold the beat.
- `BRIEFER_TICK_INTERVAL_S = 30`, first briefing fast-tracked (new incidents
  are immediately due) -> briefing lands ~5s after correlation.
- `STALE_ASSIGNMENT_AFTER_S = 6` + 5s watchdog cadence -> chaos recovery
  visible within ~11s of the kill.
- `NARRATOR_INTERVAL_S = 60` (demo pacing; the spec's 5-minute production
  cadence would never land inside a 90s recording).

## What is NOT in the 90 seconds

Heli/ffunit/medevac dispatch execution. The tasker beat shows the typed
command; actually executing it goes through the firefighter CLI (a third
window) and would crowd the cut. If a longer cut is wanted, insert a
dispatch beat after T+42: run `uv run python -m demos.wildfire.world.firefighter`
in a slim terminal, paste `heli 2.0 -2.2 high`, and the heli flies, drops,
and the cells visibly cool. (+15s.)
