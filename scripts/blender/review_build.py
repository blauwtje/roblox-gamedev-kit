"""Build linter: mechanical checks on a SPEC before anyone looks at a render.

    python3 scripts/blender/review_build.py <build.py> [--design-system <json>]
    python3 scripts/blender/review_build.py --selftest

Reads SPEC from the build.py under plain python3 (a SPEC build.py keeps its toolkit
imports under __main__), then prints one line per finding:

    REVIEW_FAIL overlap: ...  two volumes share more of a box than join_fraction with no "joins" entry
    REVIEW_FAIL thin: ...     a box, prism, sweep or tube extent under thickness_min
    REVIEW_FAIL seam: ...     a cut inset, slot width or grille bar under seam.min_inset
    REVIEW_FAIL role: ...     a role used on an element kind its recipe "uses" does not list
    REVIEW_WARN cap: ...      more volumes than volume_cap
    REVIEW_WARN repeat: ...   the same profile, points or stations list pasted twice; hoist it
    REVIEW_VALID:true|false   false when any REVIEW_FAIL was printed (exit 1); warnings never fail

The design system comes from SPEC["design_system"] (relative to the build.py) unless
--design-system overrides it. Overlap is measured on axis-aligned boxes, so a cap on a
drum or a stack in a box declares "joins" and the linter trusts it; the collision it
catches is the one nobody declared.
"""

import json
import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette as palette_module  # noqa: E402
import spec as spec_module  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATOR_BUILD = os.path.join(HERE, "examples", "generator", "build.py")
SELFTEST_DESIGN_SYSTEM = os.path.join(HERE, "presets", "chunky-horror-design.json")
SEAM_MEASURE = {"groove": "inset", "inset_panel": "inset", "plate": "inset", "vent_slots": "width", "grille": "bar"}
FLOAT_TOLERANCE = 1e-6

# The generator before its fixes, as the owner corrected it: the control box of
# concept C (half-width 0.30 between drums whose inner walls sit at x 0.23), the
# arch as three thin boxes that run into each other, and a drum profile pasted twice.
PREFIX_SPEC = {
    "name": "GeneratorPreFix",
    "volumes": [
        {"name": "plate", "kind": "box", "role": "body2", "bounds": [-1.6, 1.6, -0.9, 0.9, 0.0, 0.3]},
        {"name": "drum left", "kind": "lathe", "role": "body",
         "profile": [[0.5, 0.3], [0.62, 0.45], [0.62, 1.4], [0.5, 1.55]], "at": [-0.85, 0.0, 0.0]},
        {"name": "drum right", "kind": "lathe", "role": "body",
         "profile": [[0.5, 0.3], [0.62, 0.45], [0.62, 1.4], [0.5, 1.55]], "at": [0.85, 0.0, 0.0]},
        {"name": "control box", "kind": "box", "role": "trim", "bounds": [-0.3, 0.3, -0.5, 0.5, 0.3, 1.0]},
        {"name": "arch left", "kind": "box", "role": "trim", "bounds": [-0.94, -0.76, -0.29, -0.11, 1.55, 2.05]},
        {"name": "arch right", "kind": "box", "role": "trim", "bounds": [0.76, 0.94, -0.29, -0.11, 1.55, 2.05]},
        {"name": "arch top", "kind": "box", "role": "trim", "bounds": [-0.94, 0.94, -0.29, -0.11, 1.87, 2.05]},
    ],
}


def load_spec(build_py):
    namespace = runpy.run_path(build_py)
    spec = namespace.get("SPEC")
    if spec is None:
        raise spec_module.SpecError(f"{build_py} defines no SPEC dict")
    spec_module.validate(spec)
    return spec


def _label(volume):
    return f"'{volume['name']}' ({volume['kind']}, {volume['role']})"


def _box_volume(bounds):
    return max(bounds[1] - bounds[0], 0.0) * max(bounds[3] - bounds[2], 0.0) * max(bounds[5] - bounds[4], 0.0)


def check_overlap(spec, design_system):
    lines = []
    volumes = spec["volumes"]
    boxes = [spec_module.volume_bounds(volume) for volume in volumes]
    for i, first in enumerate(volumes):
        for j in range(i + 1, len(volumes)):
            second = volumes[j]
            a, b = boxes[i], boxes[j]
            depth = [min(a[k + 1], b[k + 1]) - max(a[k], b[k]) for k in (0, 2, 4)]
            if min(depth) <= 0.0:
                continue
            smaller = min(_box_volume(a), _box_volume(b))
            if smaller <= 0.0:
                continue
            fraction = depth[0] * depth[1] * depth[2] / smaller
            if fraction <= design_system["join_fraction"]:
                continue
            if second["name"] in first.get("joins", []) or first["name"] in second.get("joins", []):
                continue
            inner, outer = (first, second) if _box_volume(a) <= _box_volume(b) else (second, first)
            lines.append(f"REVIEW_FAIL overlap: {_label(inner)} sits {fraction * 100:.0f}% inside {_label(outer)} "
                         f"(x {depth[0]:.2f} y {depth[1]:.2f} z {depth[2]:.2f}); move it or declare \"joins\"")
    return lines


def check_thin(spec, design_system):
    minimum = design_system["thickness_min"]
    lines = []
    for volume in spec["volumes"]:
        extent = spec_module.thin_extent(volume)
        # Tolerance: an extent of exactly thickness_min (3.90 minus 3.60) lands under it by 1e-16.
        if extent is not None and extent < minimum - FLOAT_TOLERANCE:
            lines.append(f"REVIEW_FAIL thin: {_label(volume)} is {extent:.2f} thick, under thickness_min {minimum}")
    return lines


def check_seams(spec, design_system):
    floor = design_system["seam"]["min_inset"]
    lines = []
    for index, cut in enumerate(spec.get("cuts", [])):
        measure = SEAM_MEASURE[cut["kind"]]
        if cut[measure] < floor:
            lines.append(f"REVIEW_FAIL seam: cut {index} ({cut['kind']}) {measure} {cut[measure]} is under seam.min_inset {floor}")
    return lines


def check_roles(spec, design_system):
    recipes = design_system["recipes"]
    elements = [("volume", _label(volume), volume["role"]) for volume in spec["volumes"]]
    elements += [("cut", f"cut {index} ({cut['kind']})", cut["role"])
                 for index, cut in enumerate(spec.get("cuts", [])) if cut.get("role")]
    elements += [("stud", f"studs {index}", group["role"]) for index, group in enumerate(spec.get("studs", []))]
    lines = []
    for use, label, role in elements:
        allowed = recipes[role]["uses"]
        if use not in allowed:
            lines.append(f"REVIEW_FAIL role: {label} uses role '{role}' as a {use}; its recipe allows {', '.join(allowed)}")
    return lines


def check_cap(spec, design_system):
    cap = design_system["volume_cap"]
    count = len(spec["volumes"])
    if count > cap:
        return [f"REVIEW_WARN cap: {count} volumes over volume_cap {cap}; merge or drop one"]
    return []


def check_repeats(spec):
    """Equal list literals that are different objects were pasted; one object shared twice came from a constant."""
    seen = {}
    lines = []
    elements = [(_label(volume), volume) for volume in spec["volumes"]]
    elements += [(f"studs {index}", group) for index, group in enumerate(spec.get("studs", []))]
    for label, element in elements:
        for key in spec_module.LIST_KEYS:
            value = element.get(key)
            if not isinstance(value, list) or len(value) < 4:
                continue
            fingerprint = (key, json.dumps(value))
            earlier = seen.get(fingerprint)
            if earlier is None:
                seen[fingerprint] = (label, id(value))
            elif earlier[1] != id(value):
                lines.append(f"REVIEW_WARN repeat: {key!r} of {label} equals that of {earlier[0]}; hoist it to one constant")
    return lines


def review(spec, design_system):
    """Every finding line for one SPEC, FAIL lines first within each check."""
    lines = []
    lines += check_overlap(spec, design_system)
    lines += check_thin(spec, design_system)
    lines += check_seams(spec, design_system)
    lines += check_roles(spec, design_system)
    lines += check_cap(spec, design_system)
    lines += check_repeats(spec)
    return lines


def review_file(build_py, design_system_path=None):
    spec = load_spec(build_py)
    path = design_system_path or spec.get("design_system")
    if path is None:
        raise spec_module.SpecError(f"{build_py}: SPEC names no design_system and --design-system was not given")
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(build_py)), path)
    design_system = palette_module.load_design_system(path)
    problems = palette_module.validate_design_system(design_system)
    if problems:
        raise spec_module.SpecError(f"{path}: " + "; ".join(problems))
    print(f"REVIEW {build_py} volumes={len(spec['volumes'])} cuts={len(spec.get('cuts', []))} studs={len(spec.get('studs', []))}")
    lines = review(spec, design_system)
    for line in lines:
        print(line)
    failed = any(line.startswith("REVIEW_FAIL") for line in lines)
    print(f"REVIEW_VALID:{'false' if failed else 'true'}")
    return not failed


def _selftest():
    design_system = palette_module.load_design_system(SELFTEST_DESIGN_SYSTEM)
    lines = review(PREFIX_SPEC, design_system)
    for line in lines:
        print("  fixture " + line)
    overlaps = [line for line in lines if line.startswith("REVIEW_FAIL overlap")]
    expectations = (
        (sum("'control box'" in line for line in overlaps) == 2, "the control box to collide with both drums"),
        (sum("'arch top'" in line for line in overlaps) == 2, "the arch top to overlap both posts"),
        (sum(line.startswith("REVIEW_FAIL thin") for line in lines) == 3, "three arch boxes under thickness_min"),
        (sum(line.startswith("REVIEW_WARN repeat") for line in lines) == 1, "one pasted drum profile"),
    )
    ok = True
    for passed, what in expectations:
        if not passed:
            ok = False
            print(f"REVIEW_SELFTEST_FAIL: expected {what}")
    if not review_file(GENERATOR_BUILD):
        ok = False
        print("REVIEW_SELFTEST_FAIL: the shipped generator must lint clean")
    print(f"REVIEW_SELFTEST {'ok' if ok else 'failed'}")
    return ok


def main(argv):
    if "--selftest" in argv:
        return 0 if _selftest() else 1
    if len(argv) < 2 or argv[1].startswith("--"):
        print("usage: review_build.py <build.py> [--design-system <json>] | --selftest", file=sys.stderr)
        return 2
    design_system_path = argv[argv.index("--design-system") + 1] if "--design-system" in argv else None
    try:
        return 0 if review_file(argv[1], design_system_path) else 1
    except (spec_module.SpecError, OSError, ValueError) as error:
        print(f"REVIEW_ERROR: {error}")
        print("REVIEW_VALID:false")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
