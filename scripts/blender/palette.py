"""Palette as data: roles, linear RGB, roughness, and the style rules a preset must obey.

No bpy import: this file also runs under plain python3 as a validator.
Role order is stable and is the material slot order in every built asset.
"""

import json
import os
import sys

ROLES = ("body", "body2", "trim", "accent", "emissive")
REQUIRED_RULES = (
    "min_luminance_contrast_body_body2",
    "max_saturation_body",
    "min_saturation_accent",
    "roughness_range",
)


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def role_index(role):
    if role not in ROLES:
        raise KeyError(f"unknown palette role {role!r}; roles are {ROLES}")
    return ROLES.index(role)


def role_rgb(palette, role):
    return tuple(palette["roles"][role]["rgb"])


def role_roughness(palette, role):
    return float(palette["roles"][role]["roughness"])


def luminance(rgb):
    red, green, blue = rgb
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def saturation(rgb):
    highest = max(rgb)
    lowest = min(rgb)
    if highest <= 0.0:
        return 0.0
    return (highest - lowest) / highest


def validate(palette):
    problems = []
    roles = palette.get("roles", {})
    rules = palette.get("rules", {})
    for role in ROLES:
        if role not in roles:
            problems.append(f"missing role {role!r}")
            continue
        entry = roles[role]
        rgb = entry.get("rgb")
        if not (isinstance(rgb, list) and len(rgb) == 3
                and all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0 for c in rgb)):
            problems.append(f"role {role!r}: rgb must be three floats in [0, 1]")
        roughness = entry.get("roughness")
        if not isinstance(roughness, (int, float)):
            problems.append(f"role {role!r}: roughness missing")
    for rule in REQUIRED_RULES:
        if rule not in rules:
            problems.append(f"missing rule {rule!r}")
    roughness_range = rules.get("roughness_range")
    if roughness_range is not None and not (
        isinstance(roughness_range, list) and len(roughness_range) == 2
        and all(isinstance(bound, (int, float)) for bound in roughness_range)
    ):
        problems.append("rule 'roughness_range' must be two numbers")
    if problems:
        return problems

    low, high = rules["roughness_range"]
    for role in ROLES:
        roughness = role_roughness(palette, role)
        if not low <= roughness <= high:
            problems.append(f"role {role!r}: roughness {roughness} outside {low}..{high}")

    contrast = abs(luminance(role_rgb(palette, "body")) - luminance(role_rgb(palette, "body2")))
    if contrast < rules["min_luminance_contrast_body_body2"]:
        problems.append(
            f"body/body2 luminance contrast {contrast:.3f} below "
            f"{rules['min_luminance_contrast_body_body2']}"
        )
    body_saturation = saturation(role_rgb(palette, "body"))
    if body_saturation > rules["max_saturation_body"]:
        problems.append(f"body saturation {body_saturation:.3f} above {rules['max_saturation_body']}")
    accent_saturation = saturation(role_rgb(palette, "accent"))
    if accent_saturation < rules["min_saturation_accent"]:
        problems.append(f"accent saturation {accent_saturation:.3f} below {rules['min_saturation_accent']}")
    return problems


# ---- design system: the palette widened to every style constant a game shares ----

DESIGN_SYSTEM_KEYS = ("palette", "scale", "bevel", "seam", "thickness_min", "join_fraction", "volume_cap",
                      "recipes", "wear", "dirt", "rust_rgb", "soot", "motifs", "forbidden")
RECIPE_STRENGTHS = ("wear", "rust", "grime", "soot", "metal")
USES = ("volume", "cut", "stud")
DEFAULT_DESIGN_SYSTEM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets", "chunky-cartoon-design.json")


def is_design_system(data):
    return isinstance(data, dict) and "recipes" in data


def load_design_system(path):
    """The design system with its palette loaded in place; 'palette' resolves relative to the file."""
    design_system = load(path)
    if not is_design_system(design_system):
        raise ValueError(f"{path}: not a design system (no 'recipes' key)")
    palette_path = design_system.get("palette", "palette.json")
    if not isinstance(palette_path, str):
        raise ValueError(f"{path}: 'palette' must be a path string")
    if not os.path.isabs(palette_path):
        palette_path = os.path.join(os.path.dirname(os.path.abspath(path)), palette_path)
    design_system["palette_path"] = palette_path
    design_system["palette"] = load(palette_path)
    return design_system


def palette_of(style):
    """Builder and bake take a palette or a design system; this is the palette either way."""
    return style["palette"] if is_design_system(style) else style


def design_system_of(style):
    """The design system of a style; a bare palette borrows the chunky-cartoon design constants."""
    if is_design_system(style):
        return style
    design_system = load(DEFAULT_DESIGN_SYSTEM_PATH)
    design_system["palette"] = style
    return design_system


def recipe(style, role):
    return design_system_of(style)["recipes"][role]


def _is_rgb(value):
    return (isinstance(value, list) and len(value) == 3
            and all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0 for c in value))


def _is_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _is_unit(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def validate_design_system(design_system):
    """Problems with the design system itself; the palette it names is validated by validate()."""
    problems = [f"missing key {key!r}" for key in DESIGN_SYSTEM_KEYS if key not in design_system]
    if problems:
        return problems
    if not isinstance(design_system["palette"], (str, dict)):
        problems.append("'palette' must be a path or a loaded palette")
    scale = design_system["scale"]
    if not (isinstance(scale, dict) and _is_positive(scale.get("studs_per_unit"))):
        problems.append("'scale.studs_per_unit' must be a positive number")
    bevel = design_system["bevel"]
    if not (isinstance(bevel, dict) and _is_positive(bevel.get("min")) and _is_positive(bevel.get("max"))
            and bevel["min"] <= bevel["max"] and _is_positive(bevel.get("detail"))
            and isinstance(bevel.get("segments"), list) and len(bevel["segments"]) == 2
            and all(isinstance(s, int) and s >= 1 for s in bevel["segments"])):
        problems.append("'bevel' needs min <= max, detail, and segments [low, high]")
    seam = design_system["seam"]
    if not (isinstance(seam, dict) and all(_is_positive(seam.get(key)) for key in ("min_inset", "min_depth", "plate_width"))):
        problems.append("'seam' needs positive min_inset, min_depth and plate_width")
    if not _is_positive(design_system["thickness_min"]):
        problems.append("'thickness_min' must be a positive number")
    if not _is_unit(design_system["join_fraction"]):
        problems.append("'join_fraction' must be in [0, 1]")
    if not (isinstance(design_system["volume_cap"], int) and design_system["volume_cap"] >= 1):
        problems.append("'volume_cap' must be an integer of at least 1")
    recipes = design_system["recipes"]
    for role in ROLES:
        entry = recipes.get(role) if isinstance(recipes, dict) else None
        if not isinstance(entry, dict):
            problems.append(f"recipe {role!r} missing")
            continue
        for strength in RECIPE_STRENGTHS:
            if not _is_unit(entry.get(strength)):
                problems.append(f"recipe {role!r}: {strength!r} must be in [0, 1]")
        uses = entry.get("uses")
        if not (isinstance(uses, list) and uses and all(use in USES for use in uses)):
            problems.append(f"recipe {role!r}: 'uses' must be a non-empty subset of {USES}")
    wear = design_system["wear"]
    if not (isinstance(wear, dict) and _is_positive(wear.get("radius")) and _is_unit(wear.get("max"))
            and _is_rgb(wear.get("bare_metal_rgb"))):
        problems.append("'wear' needs radius, max in [0, 1] and bare_metal_rgb")
    dirt = design_system["dirt"]
    if not (isinstance(dirt, dict) and _is_positive(dirt.get("height")) and _is_unit(dirt.get("strength"))
            and _is_rgb(dirt.get("rgb"))):
        problems.append("'dirt' needs height, strength in [0, 1] and rgb")
    if not _is_rgb(design_system["rust_rgb"]):
        problems.append("'rust_rgb' must be three floats in [0, 1]")
    soot = design_system["soot"]
    if not (isinstance(soot, dict) and _is_positive(soot.get("radius")) and _is_unit(soot.get("strength"))
            and _is_rgb(soot.get("rgb")) and isinstance(soot.get("tags"), list)
            and all(isinstance(tag, str) for tag in soot["tags"])):
        problems.append("'soot' needs radius, strength in [0, 1], rgb and a tags list")
    for key in ("motifs", "forbidden"):
        value = design_system[key]
        if not (isinstance(value, list) and all(isinstance(item, str) and item for item in value)):
            problems.append(f"{key!r} must be a list of non-empty strings")
    return problems


def _check_design_system(path):
    try:
        design_system = load_design_system(path)
    except (OSError, ValueError) as error:
        print(f"DESIGN_SYSTEM_ERROR: cannot load {path}: {error}")
        print("DESIGN_SYSTEM_VALID:false")
        return 1
    palette_problems = validate(design_system["palette"])
    for problem in palette_problems:
        print(f"PALETTE_ERROR: {problem}")
    print(f"PALETTE_VALID:{'true' if not palette_problems else 'false'}")
    problems = validate_design_system(design_system)
    for problem in problems:
        print(f"DESIGN_SYSTEM_ERROR: {problem}")
    print(f"DESIGN_SYSTEM_VALID:{'true' if not problems else 'false'}")
    return 1 if (problems or palette_problems) else 0


def main(argv):
    if len(argv) != 3 or argv[1] != "--check":
        print("usage: palette.py --check <palette.json | design-system.json>", file=sys.stderr)
        return 2
    try:
        data = load(argv[2])
    except (OSError, ValueError) as error:
        print(f"PALETTE_ERROR: cannot read {argv[2]}: {error}")
        print("PALETTE_VALID:false")
        return 1
    if not isinstance(data, dict):
        print("PALETTE_ERROR: top level must be a JSON object")
        print("PALETTE_VALID:false")
        return 1
    if is_design_system(data):
        return _check_design_system(argv[2])
    problems = validate(data)
    for problem in problems:
        print(f"PALETTE_ERROR: {problem}")
    print(f"PALETTE_VALID:{'true' if not problems else 'false'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
