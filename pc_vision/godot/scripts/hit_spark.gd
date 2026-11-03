extends Node2D
## Presentation-only, one-shot spark. The caller owns hit validation and deduplication.
## Add under an unscaled screen-space effects node, place at the published hit point,
## then call burst() with a screen-space direction. This component never infers a hit.

const FLASH_SECONDS := 0.08

@onready var _particles: GPUParticles2D = $Particles
var _flash_left := 0.0

func _ready() -> void:
	_particles.emitting = false
	_particles.finished.connect(_on_particles_finished)
	set_process(false)

func burst(direction: Vector2) -> void:
	if not is_node_ready():
		await ready
	var heading := direction.normalized() if direction.is_finite() and direction.length_squared() > 0.000001 else Vector2.RIGHT
	var process_material := _particles.process_material as ParticleProcessMaterial
	process_material.direction = Vector3(heading.x, heading.y, 0.0)
	_flash_left = FLASH_SECONDS
	set_process(true)
	queue_redraw()
	_particles.restart(true)

func _process(delta: float) -> void:
	_flash_left = maxf(0.0, _flash_left - delta)
	queue_redraw()
	if _flash_left <= 0.0:
		set_process(false)

func _draw() -> void:
	if _flash_left <= 0.0:
		return
	var strength := _flash_left / FLASH_SECONDS
	draw_circle(Vector2.ZERO, 4.0 + (1.0 - strength) * 4.0, Color(1.0, 0.95, 0.74, strength * 0.65))
	draw_circle(Vector2.ZERO, 2.2 * strength, Color(1.0, 1.0, 0.94, strength))

func _on_particles_finished() -> void:
	queue_free()
