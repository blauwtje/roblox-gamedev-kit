"""SPEC schema for one asset: the dict a build.py declares and assetlib.build turns into a mesh.

No bpy import: review_build.py and a plain python3 validator read a SPEC without Blender.
A SPEC is data only; a build.py may compute lists from constants, but every value the
owner may change (a bound, a radius, a role, a count) is a number in this dict.

    SPEC = {
        "slug": "generator",            # file stem: generator.glb, generator_color.png
        "name": "Generator",            # Blender object name
        "design_system": "<path>",      # design-system.json, absolute or relative to build.py
        "tri_budget": 10000,
        "plate_scale": 0.8,             # one Voronoi plate is about this many units
        "volumes": [VOLUME, ...],       # primary form, in merge order, counted against volume_cap
        "cuts": [CUT, ...],             # secondary detail cut into the skin, after every volume
        "studs": [STUDS, ...],          # stud groups, applied last
    }

Every VOLUME carries "kind", "role", "name", optional "bevel" and "segments" (each kind's
own default: box and prism 0.12 and 2, lathe and sweep 0.10 and 2, ring 0.06 and 2, tube 0 and 1),
"at" [x, y, z] translation, "tags" (["exhaust"] marks a soot source; the emissive role
is one by itself) and "joins" (names of volumes it penetrates on purpose). Per kind:

    box      "bounds": [x0, x1, y0, y1, z0, z1]
    lathe    "profile": [[r, z], ...], "sides": 16
    ring     "radius", "thickness", "z": [z0, z1], "sides": 16
    prism_x  "points": [[y, z], ...], "x": [x0, x1]   (prism_y: [[x, z]], "y"; prism_z: [[x, y]], "z")
    sweep    "profile": [[x, z], ...], "stations": [[y, scale_x, scale_z, dx, dz], ...]
    tube     "points": [[x, y, z], ...], "radius", "sides": 8

Every CUT carries "kind", "face" (a FACE selector) and optional "role". Per kind:

    groove       "inset", "depth"
    inset_panel  "inset", "depth"
    plate        "inset", "thickness", optional "region": [u0, u1, v0, v1] (in-plane axes)
    vent_slots   "count", "along": "x" | "y" | "z", "width", "depth", optional "span": [lo, hi]
    grille       "pitch", "bar", "depth"

A FACE selector is {"normal": "+x" | "-x" | "+y" | "-y" | "+z" | "-z" | "radial",
"within": [x0, x1, y0, y1, z0, z1]}; any bound may be null. A face matches when its
normal points that way (dot above 0.9; "radial" is a side wall, |normal.z| under 0.3)
and its centre lies inside the bounds.

Every STUDS group carries "points": [[x, y, z], ...], "axis", "radius", "height", "role",
optional "sides" (8; 6 gives a hex bolt) and "tags".
"""

import math

from palette import ROLES

VOLUME_KINDS = ("box", "lathe", "ring", "prism_x", "prism_y", "prism_z", "sweep", "tube")
CUT_KINDS = ("groove", "inset_panel", "plate", "vent_slots", "grille")
NORMALS = {
    "+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
    "+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0),
}
# In-plane axes of an axis-aligned face, as (u, v).
IN_PLANE = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
REQUIRED_BY_KIND = {
    "box": ("bounds",), "lathe": ("profile",), "ring": ("radius", "thickness", "z"),
    "prism_x": ("points", "x"), "prism_y": ("points", "y"), "prism_z": ("points", "z"),
    "sweep": ("profile", "stations"), "tube": ("points", "radius"),
    "groove": ("face", "inset", "depth"), "inset_panel": ("face", "inset", "depth"),
    "plate": ("face", "inset", "thickness"),
    "vent_slots": ("face", "count", "along", "width", "depth"),
    "grille": ("face", "pitch", "bar", "depth"),
}
# List-valued keys the linter compares for pasted duplicates.
LIST_KEYS = ("profile", "points", "stations")


class SpecError(ValueError):
    pass


def ngon(radius, sides, phase=0.0):
    """Regular polygon in a plane, as (u, v) pairs."""
    return [
        (radius * math.cos(phase + 2.0 * math.pi * i / sides),
         radius * math.sin(phase + 2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_tuples(value, length, minimum=1):
    return (isinstance(value, list) and len(value) >= minimum
            and all(isinstance(item, (list, tuple)) and len(item) == length
                    and all(is_number(coordinate) for coordinate in item) for item in value))


def _is_numbers(value, length):
    return isinstance(value, list) and len(value) == length and all(is_number(item) for item in value)


def validate_selector(selector, where, problems):
    if not isinstance(selector, dict) or selector.get("normal") not in (*NORMALS, "radial"):
        problems.append(f"{where}: 'face' needs 'normal' in {tuple(NORMALS)} or 'radial'")
        return
    within = selector.get("within")
    if within is not None and not (isinstance(within, list) and len(within) == 6
                                   and all(bound is None or is_number(bound) for bound in within)):
        problems.append(f"{where}: 'within' must be six numbers or nulls")


def _validate_volume(index, volume, names, problems):
    where = f"volume {index}"
    if not isinstance(volume, dict):
        problems.append(f"{where}: must be a dict")
        return
    kind = volume.get("kind")
    if kind not in VOLUME_KINDS:
        problems.append(f"{where}: kind {kind!r} not in {VOLUME_KINDS}")
        return
    name = volume.get("name")
    if not isinstance(name, str) or not name:
        problems.append(f"{where}: needs a non-empty 'name'")
    elif name in names:
        problems.append(f"{where}: duplicate name {name!r}")
    else:
        names.add(name)
    if volume.get("role") not in ROLES:
        problems.append(f"{where}: role {volume.get('role')!r} not in {ROLES}")
    for key in REQUIRED_BY_KIND[kind]:
        if key not in volume:
            problems.append(f"{where}: {kind} needs {key!r}")
    if kind == "box" and "bounds" in volume and not _is_numbers(volume["bounds"], 6):
        problems.append(f"{where}: 'bounds' must be six numbers")
    if kind == "lathe" and "profile" in volume and not _is_tuples(volume["profile"], 2, 2):
        problems.append(f"{where}: 'profile' must be at least two [r, z] pairs")
    if kind == "ring" and "z" in volume and not _is_numbers(volume["z"], 2):
        problems.append(f"{where}: 'z' must be [z0, z1]")
    if kind in ("prism_x", "prism_y", "prism_z"):
        axis = kind[-1]
        if "points" in volume and not _is_tuples(volume["points"], 2, 3):
            problems.append(f"{where}: 'points' must be at least three pairs")
        if axis in volume and not _is_numbers(volume[axis], 2):
            problems.append(f"{where}: {axis!r} must be two numbers")
    if kind == "sweep":
        if "profile" in volume and not _is_tuples(volume["profile"], 2, 3):
            problems.append(f"{where}: 'profile' must be at least three [x, z] pairs")
        if "stations" in volume and not _is_tuples(volume["stations"], 5, 2):
            problems.append(f"{where}: 'stations' must be at least two [y, scale_x, scale_z, dx, dz]")
    if kind == "tube":
        if "points" in volume and not _is_tuples(volume["points"], 3, 2):
            problems.append(f"{where}: 'points' must be at least two [x, y, z]")
        if "radius" in volume and not (is_number(volume["radius"]) and volume["radius"] > 0):
            problems.append(f"{where}: 'radius' must be a positive number")
    at = volume.get("at")
    if at is not None and not _is_numbers(at, 3):
        problems.append(f"{where}: 'at' must be [x, y, z]")
    for key in ("tags", "joins"):
        value = volume.get(key, [])
        if not (isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value)):
            problems.append(f"{where}: {key!r} must be a list of strings")


def _validate_cut(index, cut, problems):
    where = f"cut {index}"
    if not isinstance(cut, dict):
        problems.append(f"{where}: must be a dict")
        return
    kind = cut.get("kind")
    if kind not in CUT_KINDS:
        problems.append(f"{where}: kind {kind!r} not in {CUT_KINDS}")
        return
    for key in REQUIRED_BY_KIND[kind]:
        if key not in cut:
            problems.append(f"{where}: {kind} needs {key!r}")
    if "face" in cut:
        validate_selector(cut["face"], where, problems)
    role = cut.get("role")
    if role is not None and role not in ROLES:
        problems.append(f"{where}: role {role!r} not in {ROLES}")
    for key in ("inset", "depth", "thickness", "width", "pitch", "bar"):
        if key in cut and not (is_number(cut[key]) and cut[key] > 0):
            problems.append(f"{where}: {key!r} must be a positive number")
    if kind == "vent_slots":
        if "count" in cut and not (isinstance(cut["count"], int) and cut["count"] >= 1):
            problems.append(f"{where}: 'count' must be an integer of at least 1")
        if "along" in cut and cut["along"] not in AXIS_INDEX:
            problems.append(f"{where}: 'along' must be 'x', 'y' or 'z'")
        if cut.get("span") is not None and not _is_numbers(cut["span"], 2):
            problems.append(f"{where}: 'span' must be [lo, hi]")
    if kind == "plate" and cut.get("region") is not None and not _is_numbers(cut["region"], 4):
        problems.append(f"{where}: 'region' must be [u0, u1, v0, v1]")


def _validate_studs(index, group, problems):
    where = f"studs {index}"
    if not isinstance(group, dict):
        problems.append(f"{where}: must be a dict")
        return
    if not _is_tuples(group.get("points"), 3, 1):
        problems.append(f"{where}: 'points' must be at least one [x, y, z]")
    if group.get("axis") not in AXIS_INDEX:
        problems.append(f"{where}: 'axis' must be 'x', 'y' or 'z'")
    if group.get("role") not in ROLES:
        problems.append(f"{where}: role {group.get('role')!r} not in {ROLES}")
    for key in ("radius", "height"):
        if not (is_number(group.get(key)) and group[key] > 0):
            problems.append(f"{where}: {key!r} must be a positive number")
    sides = group.get("sides", 8)
    if not (isinstance(sides, int) and sides >= 3):
        problems.append(f"{where}: 'sides' must be an integer of at least 3")
    tags = group.get("tags", [])
    if not (isinstance(tags, (list, tuple)) and all(isinstance(item, str) for item in tags)):
        problems.append(f"{where}: 'tags' must be a list of strings")


def validate(spec):
    """Every schema problem at once, as one SpecError; silence means the dict is buildable."""
    if not isinstance(spec, dict):
        raise SpecError("SPEC must be a dict")
    problems = []
    if not isinstance(spec.get("name"), str) or not spec["name"]:
        problems.append("'name' must be a non-empty string")
    volumes = spec.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        problems.append("'volumes' must be a non-empty list")
        volumes = []
    names = set()
    for index, volume in enumerate(volumes):
        _validate_volume(index, volume, names, problems)
    for index, cut in enumerate(spec.get("cuts", [])):
        _validate_cut(index, cut, problems)
    for index, group in enumerate(spec.get("studs", [])):
        _validate_studs(index, group, problems)
    for volume in volumes:
        if isinstance(volume, dict):
            for other in volume.get("joins", []):
                if other not in names:
                    problems.append(f"volume {volume.get('name')!r}: joins unknown volume {other!r}")
    if problems:
        raise SpecError("; ".join(problems))


def face_predicate(selector):
    """A callable on a BMFace (needs .normal and .calc_center_median()) for a FACE selector."""
    normal = selector["normal"]
    within = selector.get("within") or [None] * 6
    axis = NORMALS.get(normal)

    def matches(face):
        if axis is None:
            if abs(face.normal.z) >= 0.3:
                return False
        elif face.normal.x * axis[0] + face.normal.y * axis[1] + face.normal.z * axis[2] <= 0.9:
            return False
        centre = face.calc_center_median()
        for coordinate, low, high in zip((centre.x, centre.y, centre.z), within[0::2], within[1::2]):
            if low is not None and coordinate < low:
                return False
            if high is not None and coordinate > high:
                return False
        return True

    return matches


def in_plane_axes(selector):
    """(u, v) axis names of an axis-aligned face; a radial wall has none."""
    normal = selector["normal"]
    if normal not in NORMALS:
        raise SpecError("this cut needs an axis-aligned face, not 'radial'")
    return IN_PLANE[normal[1]]


def _shift(bounds, at):
    if at is None:
        return tuple(bounds)
    return (bounds[0] + at[0], bounds[1] + at[0], bounds[2] + at[1], bounds[3] + at[1], bounds[4] + at[2], bounds[5] + at[2])


def volume_bounds(volume):
    """Axis-aligned bounding box (x0, x1, y0, y1, z0, z1) of a VOLUME, translation applied."""
    kind = volume["kind"]
    if kind == "box":
        bounds = volume["bounds"]
    elif kind == "lathe":
        radius = max(r for r, _ in volume["profile"])
        zs = [z for _, z in volume["profile"]]
        bounds = (-radius, radius, -radius, radius, min(zs), max(zs))
    elif kind == "ring":
        radius = volume["radius"]
        bounds = (-radius, radius, -radius, radius, volume["z"][0], volume["z"][1])
    elif kind in ("prism_x", "prism_y", "prism_z"):
        axis = kind[-1]
        us = [u for u, _ in volume["points"]]
        vs = [v for _, v in volume["points"]]
        low, high = volume[axis]
        if axis == "x":
            bounds = (low, high, min(us), max(us), min(vs), max(vs))
        elif axis == "y":
            bounds = (min(us), max(us), low, high, min(vs), max(vs))
        else:
            bounds = (min(us), max(us), min(vs), max(vs), low, high)
    elif kind == "sweep":
        xs, zs, ys = [], [], []
        for y, scale_x, scale_z, dx, dz in volume["stations"]:
            ys.append(y)
            for u, v in volume["profile"]:
                xs.append(u * scale_x + dx)
                zs.append(v * scale_z + dz)
        bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    elif kind == "tube":
        radius = volume["radius"]
        xs = [p[0] for p in volume["points"]]
        ys = [p[1] for p in volume["points"]]
        zs = [p[2] for p in volume["points"]]
        bounds = (min(xs) - radius, max(xs) + radius, min(ys) - radius, max(ys) + radius, min(zs) - radius, max(zs) + radius)
    else:
        raise SpecError(f"unknown volume kind {kind!r}")
    return _shift(bounds, volume.get("at"))


def thin_extent(volume):
    """Smallest extent that must clear thickness_min, or None for rims and caps (ring, lathe)."""
    kind = volume["kind"]
    if kind == "box":
        x0, x1, y0, y1, z0, z1 = volume["bounds"]
        return min(x1 - x0, y1 - y0, z1 - z0)
    if kind in ("prism_x", "prism_y", "prism_z"):
        us = [u for u, _ in volume["points"]]
        vs = [v for _, v in volume["points"]]
        low, high = volume[kind[-1]]
        return min(high - low, max(us) - min(us), max(vs) - min(vs))
    if kind == "sweep":
        us = [u for u, _ in volume["profile"]]
        vs = [v for _, v in volume["profile"]]
        return min(max(us) - min(us), max(vs) - min(vs))
    if kind == "tube":
        return 2.0 * volume["radius"]
    return None
