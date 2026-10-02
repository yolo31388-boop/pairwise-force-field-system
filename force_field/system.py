"""
pairwise-force-field-system - ForceFieldSystem

A force field system for the physics group:

- apply_force_field: range check + distance falloff + per-type behavior
  (attract / repel / wind).
- check_occlusion: raycast occlusion with wall-thickness penetration and
  per-frame result caching.
- apply_area_effect: sphere / box / capsule shapes, damage-over-time and
  immunity support.
- combine_force_fields: priority ordering, element conflicts (fire vs ice)
  and a magnitude cap.
- debug_force_field: direction/magnitude reporting, type filtering and
  magnitude history for trend visualization.
"""

import math


def _vec_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vec_scale(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def _vec_length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec_normalize(v):
    length = _vec_length(v)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _vec_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class ForceFieldSystem:
    # Element pairs that cancel each other when combined.
    CONFLICTING_ELEMENTS = (frozenset(("fire", "ice")),)

    # Hard cap for the magnitude of a combined force field.
    MAX_COMBINED_MAGNITUDE = 100.0

    def __init__(self):
        self.state = {}
        self._occlusion_cache = {}
        self._active_effects = {}
        self._debug_history = {}

    # ------------------------------------------------------------------
    # Force application
    # ------------------------------------------------------------------
    def _falloff(self, distance, radius, mode):
        """Distance falloff multiplier in [0, 1]."""
        if radius <= 0.0:
            return 0.0
        t = min(distance / radius, 1.0)
        if mode == "none":
            return 1.0
        if mode == "linear":
            return 1.0 - t
        if mode == "quadratic":
            return 1.0 - t * t
        raise ValueError(f"unknown falloff mode: {mode!r}")

    def apply_force_field(self, field=None, obj=None, dt=1.0):
        """Apply a single force field to an object.

        Performs a range check (objects outside ``radius`` feel nothing),
        applies distance falloff, and picks the force direction from the
        field type: ``attract`` pulls toward the center, ``repel`` pushes
        away, ``wind`` pushes along the field's direction vector.
        """
        result = {
            "force": (0.0, 0.0, 0.0),
            "in_range": False,
            "distance": 0.0,
            "falloff": 0.0,
            "type": None,
        }
        if field is None or obj is None:
            return result

        field_pos = field.get("position", (0.0, 0.0, 0.0))
        obj_pos = obj.get("position", (0.0, 0.0, 0.0))
        radius = float(field.get("radius", 0.0))
        strength = float(field.get("strength", 0.0))
        field_type = field.get("type", "attract")
        falloff_mode = field.get("falloff", "linear")

        offset = _vec_sub(obj_pos, field_pos)
        distance = _vec_length(offset)
        result["distance"] = distance
        result["type"] = field_type

        # Range check: nothing outside the radius is affected.
        if distance > radius:
            return result

        scale = strength * self._falloff(distance, radius, falloff_mode)
        result["in_range"] = True
        result["falloff"] = self._falloff(distance, radius, falloff_mode)

        if field_type == "attract":
            direction = _vec_normalize(_vec_scale(offset, -1.0))
        elif field_type == "repel":
            direction = _vec_normalize(offset)
        elif field_type == "wind":
            direction = _vec_normalize(field.get("direction", (0.0, 0.0, 0.0)))
        else:
            raise ValueError(f"unknown field type: {field_type!r}")

        result["force"] = _vec_scale(direction, scale * dt)
        return result

    # ------------------------------------------------------------------
    # Occlusion
    # ------------------------------------------------------------------
    @staticmethod
    def _ray_box_penetration(origin, target, box):
        """Thickness of ``box`` crossed by the segment origin->target.

        Slab method; returns 0.0 when the segment misses the box.
        """
        center = box.get("position", (0.0, 0.0, 0.0))
        half = box.get("half_extents", (0.0, 0.0, 0.0))
        direction = _vec_sub(target, origin)
        t_enter, t_exit = 0.0, 1.0
        for axis in range(3):
            d = direction[axis]
            lo = center[axis] - half[axis]
            hi = center[axis] + half[axis]
            if abs(d) <= 1e-12:
                if origin[axis] < lo or origin[axis] > hi:
                    return 0.0
                continue
            t1 = (lo - origin[axis]) / d
            t2 = (hi - origin[axis]) / d
            t1, t2 = min(t1, t2), max(t1, t2)
            t_enter = max(t_enter, t1)
            t_exit = min(t_exit, t2)
            if t_enter > t_exit:
                return 0.0
        chord = (t_exit - t_enter) * _vec_length(direction)
        return max(chord, 0.0)

    def check_occlusion(self, field=None, obj=None, obstacles=None):
        """Check whether obstacles block a field from reaching an object.

        Casts a ray from the field center to the object, accumulates the
        wall thickness penetrated (thin walls attenuate less than thick
        ones) and caches the result so identical queries within a frame
        do not recompute the raycast.
        """
        result = {
            "occluded": False,
            "attenuation": 1.0,
            "penetration": 0.0,
            "cached": False,
        }
        if field is None or obj is None:
            return result

        origin = field.get("position", (0.0, 0.0, 0.0))
        target = obj.get("position", (0.0, 0.0, 0.0))
        obstacles = list(obstacles or [])

        cache_key = (
            field.get("id", id(field)),
            obj.get("id", id(obj)),
            tuple(origin),
            tuple(target),
            tuple(
                (
                    tuple(o.get("position", (0.0, 0.0, 0.0))),
                    tuple(o.get("half_extents", (0.0, 0.0, 0.0))),
                )
                for o in obstacles
            ),
        )
        if cache_key in self._occlusion_cache:
            cached = dict(self._occlusion_cache[cache_key])
            cached["cached"] = True
            return cached

        # Penetration: attenuation decays exponentially with the total
        # wall thickness the ray has to cross.
        penetration = 0.0
        for obstacle in obstacles:
            penetration += self._ray_box_penetration(origin, target, obstacle)

        attenuation = math.exp(-penetration)
        result.update(
            occluded=attenuation < 0.5,
            attenuation=attenuation,
            penetration=penetration,
        )
        self._occlusion_cache[cache_key] = dict(result)
        return result

    def clear_occlusion_cache(self):
        """Drop cached raycasts (call once per frame / scene change)."""
        self._occlusion_cache.clear()

    # ------------------------------------------------------------------
    # Area effects
    # ------------------------------------------------------------------
    @staticmethod
    def _inside_shape(effect, point):
        shape = effect.get("shape", "sphere")
        center = effect.get("position", (0.0, 0.0, 0.0))
        local = _vec_sub(point, center)

        if shape == "sphere":
            radius = float(effect.get("radius", 0.0))
            return _vec_length(local) <= radius

        if shape == "box":
            half = effect.get("half_extents", (0.0, 0.0, 0.0))
            return all(abs(local[i]) <= half[i] for i in range(3))

        if shape == "capsule":
            radius = float(effect.get("radius", 0.0))
            height = float(effect.get("height", 0.0))
            half_segment = max(height * 0.5, 0.0)
            clamped_y = max(-half_segment, min(local[1], half_segment))
            closest = (0.0, clamped_y, 0.0)
            return _vec_length(_vec_sub(local, closest)) <= radius

        raise ValueError(f"unknown effect shape: {shape!r}")

    def apply_area_effect(self, effect=None, obj=None, dt=1.0):
        """Apply an area-of-effect (sphere / box / capsule) to an object.

        Damage is dealt continuously (damage_per_second * dt) for every
        tick the object stays inside, and objects immune to the effect
        type are never affected.
        """
        result = {
            "inside": False,
            "affected": False,
            "damage": 0.0,
            "immune": False,
            "accumulated_damage": 0.0,
        }
        if effect is None or obj is None:
            return result

        obj_pos = obj.get("position", (0.0, 0.0, 0.0))
        inside = self._inside_shape(effect, obj_pos)
        result["inside"] = inside

        effect_id = effect.get("id", id(effect))
        obj_id = obj.get("id", id(obj))
        key = (effect_id, obj_id)
        accumulated = self._active_effects.get(key, 0.0)

        if not inside:
            self._active_effects.pop(key, None)
            return result

        # Immunity: immune objects are tracked as inside but unaffected.
        effect_type = effect.get("effect_type")
        immunities = obj.get("immune_to", ())
        if effect_type in immunities:
            result["immune"] = True
            return result

        # Damage over time: ticks every frame while inside, not only on
        # entry.
        damage = float(effect.get("damage_per_second", 0.0)) * dt
        accumulated += damage
        self._active_effects[key] = accumulated

        result.update(
            affected=True,
            damage=damage,
            accumulated_damage=accumulated,
        )
        return result

    # ------------------------------------------------------------------
    # Field combination
    # ------------------------------------------------------------------
    def combine_force_fields(self, fields=None, max_magnitude=None):
        """Combine several force fields into one resultant vector.

        Higher-priority fields are applied first; conflicting elements
        (fire vs ice) cancel each other instead of naively adding up, and
        the final magnitude is capped at ``max_magnitude``.
        """
        result = {
            "vector": (0.0, 0.0, 0.0),
            "magnitude": 0.0,
            "fields_used": 0,
            "conflicts_resolved": 0,
            "capped": False,
        }
        if not fields:
            return result

        cap = self.MAX_COMBINED_MAGNITUDE if max_magnitude is None else float(max_magnitude)

        # Priority: strongest-priority fields win the budget first.
        ordered = sorted(fields, key=lambda f: f.get("priority", 0), reverse=True)

        # Element conflicts: opposing elements cancel the weaker side
        # instead of both being added.
        cancelled = set()
        conflicts = 0
        for pair in self.CONFLICTING_ELEMENTS:
            present = [
                (i, f) for i, f in enumerate(ordered)
                if f.get("element") in pair and i not in cancelled
            ]
            by_element = {}
            for i, f in present:
                by_element.setdefault(f.get("element"), []).append((i, f))
            if len(by_element) < 2:
                continue
            strengths = {
                element: sum(abs(float(f.get("strength", 0.0))) for _, f in group)
                for element, group in by_element.items()
            }
            loser = min(strengths, key=lambda e: (strengths[e], e))
            for i, _f in by_element[loser]:
                cancelled.add(i)
                conflicts += 1

        total = (0.0, 0.0, 0.0)
        used = 0
        for i, f in enumerate(ordered):
            if i in cancelled:
                continue
            direction = _vec_normalize(f.get("direction", (0.0, 0.0, 0.0)))
            strength = float(f.get("strength", 0.0))
            total = _vec_add(total, _vec_scale(direction, strength))
            used += 1

        magnitude = _vec_length(total)
        capped = magnitude > cap
        if capped:
            total = _vec_scale(_vec_normalize(total), cap)
            magnitude = cap

        result.update(
            vector=total,
            magnitude=magnitude,
            fields_used=used,
            conflicts_resolved=conflicts,
            capped=capped,
        )
        return result

    # ------------------------------------------------------------------
    # Debugging
    # ------------------------------------------------------------------
    def debug_force_field(self, field=None, filter_type=None, sample=None):
        """Collect debug info for a force field.

        Reports range plus force direction and magnitude, supports
        filtering by field type, and keeps a magnitude history so trends
        can be visualized instead of raw numbers only.
        """
        info = {
            "field_id": None,
            "type": None,
            "radius": 0.0,
            "direction": (0.0, 0.0, 0.0),
            "magnitude": 0.0,
            "filtered_out": False,
            "history": [],
            "trend": "flat",
        }
        if field is None:
            return info

        field_type = field.get("type")
        info["field_id"] = field.get("id", id(field))
        info["type"] = field_type
        info["radius"] = float(field.get("radius", 0.0))

        # Filtering: skip fields whose type is not requested.
        if filter_type is not None and field_type != filter_type:
            info["filtered_out"] = True
            return info

        direction = field.get("direction")
        if direction is None:
            direction = _vec_scale(
                _vec_normalize(field.get("position", (0.0, 0.0, 0.0))), -1.0
            )
        else:
            direction = _vec_normalize(direction)
        magnitude = float(sample if sample is not None else field.get("strength", 0.0))

        info["direction"] = direction
        info["magnitude"] = magnitude

        # Visualization: keep a magnitude history and derive a trend.
        history = self._debug_history.setdefault(info["field_id"], [])
        history.append(magnitude)
        del history[:-50]
        info["history"] = list(history)
        if len(history) >= 2:
            delta = history[-1] - history[0]
            if delta > 1e-9:
                info["trend"] = "rising"
            elif delta < -1e-9:
                info["trend"] = "falling"
        return info
