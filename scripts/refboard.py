#!/usr/bin/env python3
"""Reference boards: concept art in, buildable data out.

An owner drops three to six images into `assets/refs/<zone>/` in the game repo
and says "build the map like this". Without a board an agent looks once, forms
an impression, and builds from memory: it copies characters, believes AI
artefacts, invents a colour the palette does not have, and drifts from the
images over ten edits with nothing able to notice. A board makes each of those
a finding.

One `board.json` per zone, three blocks with three owners so they fail apart:

  measured       written only by `--measure`, sealed with a digest over the
                 image bytes, the sampler constants and the block itself.
  declarations   hand written: masks, steal / do_not_steal / cannot_tell,
                 role_map, unmatched resolutions, lights_declared. Checked for
                 form and for agreement with `measured`.
  zone_facts     the only block a builder reads: studs, palette role names and
                 ranges. No hex, no image language.

Character regions are masked out *before* every measurement, so no number in a
board is ever built on a body. Nothing here detects a character in the pixels:
`characters` is a required answer, not a guess.

Colour space. The image is sRGB; `palette.json` is linear RGB (it feeds
Blender's Base Color). Both are converted to CIELab through XYZ, the image via
the sRGB transfer function and the palette directly, so a family and a role are
compared in the same space. A role is fitted on chroma (a*,b*) only: concept art
is a lit render, so L* mostly measures the exposure. A separate ordering check
catches what chroma alone would accept.

CLI

  --init <dir> --zone <id>        write <dir>/board.json, one entry per image
  --measure <board.json>          write the sealed `measured` block
  --check <board.json|dir>        read-only: re-measure, diff, validate
  --sheet <board.json>            write <dir>/sheet.png (annotated + read distance)
  --compare <board.json> --image <id> --shot <png>    measured delta table
  --selftest                      synthetic image with known answers
  --quiet                         findings and the final line only

Markers (stdout, one per line, greppable): REF_MASKED, REF_VALUE, REF_FAMILY,
REF_LIGHT, REF_DRIFT, BOARD_FAIL, BOARD_WARN, SHEET, COMPARE,
`REFBOARD_VALID:true|false` as the last line of --measure and --check, and
`REFBOARD_ERROR: <reason>` on a tool failure.

Exit: 0 valid, 1 findings (a BOARD_FAIL was printed), 2 tool error.

Traps measured on 2026-09-04 and not to be re-tried: a plain `quantize(8)` over the whole frame
returns eight near-black buckets on every one of the five sample
references, because median cut splits by population and the frames are 67-84%
below sRGB 60; and row-luminance band edges peak on the letterbox bars, not on
architecture. There is no perspective solver: a single frame carries no metric
depth, so every stud dimension is a declared range anchored to a constant that
already exists in the project's blueprint.

This is the kit's only script with a third-party dependency (Pillow). It is
deliberately off the hook path and runs as a gate step; without Pillow it exits
2 and nothing else in the kit is affected.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import shutil
import tempfile
from collections import deque
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender"))
import palette as palette_module  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("REFBOARD_ERROR: Pillow required (python3 -m pip install Pillow)")
    raise SystemExit(2)


SCHEMA = "refboard/1"

# The sampler is pinned into every board. A change here must invalidate every
# board at once rather than silently reinterpret it, which is what the digest
# and the `sampler` fail code do together.
SAMPLER = {
    "tool": "refboard.py",
    "version": 1,
    "work_width": 320,
    "resample": "BOX",
    "mid_value": [24, 200],
    "family_max": 6,
    "fine_colors": 48,
    "merge_stop_lab": 18.0,
    "family_min_share": 0.005,
    "lit_value": 200,
    "lit_sat": 0.15,
    "hue_bucket_deg": 30,
    "blob_min_px": 8,
    "light_max": 8,
    "read_width": 96,
    "dark_value": 60,
}

DEFAULT_TOLERANCES = {
    # Measured against chunky-horror on the five sample references:
    # a family that is plainly the same material as a role lands under 12, a
    # family that is plainly a different material lands well above it.
    "chroma_distance_max": 12.0,
    "family_floor": 0.03,
    "range_min_width": 0.15,
    "mask_min_area": 0.01,
}

# Which way each tolerance may move. A board may tighten its own bar and say so;
# loosening one silently is how every check in this file gets disabled at once.
# "ceiling" means the default is the highest allowed value, "floor" the lowest.
TOLERANCE_DIRECTION = {
    "chroma_distance_max": "ceiling",
    "family_floor": "ceiling",
    "range_min_width": "floor",
    "mask_min_area": "floor",
}

CAPS = {"images": 6, "steal": 6, "do_not_steal": 4}

# Generic across games: a world blueprint has no character kind, so a board line
# that reaches the build never names one. Deliberately narrow: every word that
# collides with the kit's own vocabulary is left out (`body` and `body2` are
# palette roles, `face` is a Builder selector, `rig` is the preview rig, `head`
# is in `bulkhead`). This list is the cheap catch, not the enforcement: the mask
# and the design-system `forbidden` entry are.
CHARACTER_TERMS = (
    "npc", "alien", "patron", "creature", "humanoid", "figure", "monster",
    "waiter", "customer", "character", "person", "people", "skin", "limb",
    "torso", "mannequin",
)

RESOLUTIONS = ("light_only", "out_of_camp", "owner_decision", "palette_change")
PRODUCES_PREFIXES = ("zone_facts", "lights_declared", "design_system", "blueprint")
HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
WORD_PATTERN = re.compile(r"[a-z]+")


class ToolError(Exception):
    """Something the board author must fix before any check can mean anything."""


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

def srgb_to_linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def linear_to_lab(rgb):
    """Linear RGB (0..1, sRGB primaries, D65) to CIELab."""
    red, green, blue = rgb
    x = 0.4124564 * red + 0.3575761 * green + 0.1804375 * blue
    y = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
    z = 0.0193339 * red + 0.1191920 * green + 0.9503041 * blue
    white = (0.95047, 1.00000, 1.08883)

    def f(t):
        return t ** (1.0 / 3.0) if t > 216.0 / 24389.0 else (841.0 / 108.0) * t + 4.0 / 29.0

    fx, fy, fz = f(x / white[0]), f(y / white[1]), f(z / white[2])
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def srgb255_to_linear(pixel):
    return tuple(srgb_to_linear(channel / 255.0) for channel in pixel)


def lab_distance(first, second):
    return math.dist(first, second)


def chroma_distance(first, second):
    return math.hypot(first[1] - second[1], first[2] - second[2])


def chroma_of(lab):
    return math.hypot(lab[1], lab[2])


def linear_to_hex(rgb):
    def encode(value):
        value = max(0.0, min(1.0, value))
        srgb = value * 12.92 if value <= 0.0031308 else 1.055 * (value ** (1 / 2.4)) - 0.055
        return int(round(srgb * 255))

    return "#{:02x}{:02x}{:02x}".format(*(encode(channel) for channel in rgb))


def hue_and_saturation(pixel):
    """HSV hue in degrees and saturation, on the same definition as palette.saturation."""
    red, green, blue = (channel / 255.0 for channel in pixel)
    highest, lowest = max(red, green, blue), min(red, green, blue)
    if highest <= 0.0:
        return 0.0, 0.0
    spread = highest - lowest
    saturation = spread / highest
    if spread == 0.0:
        return 0.0, saturation
    if highest == red:
        hue = 60.0 * (((green - blue) / spread) % 6.0)
    elif highest == green:
        hue = 60.0 * (((blue - red) / spread) + 2.0)
    else:
        hue = 60.0 * (((red - green) / spread) + 4.0)
    return hue, saturation


def lab_of_hex(value):
    return linear_to_lab(srgb255_to_linear(tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))))


def role_labs(palette):
    return {role: linear_to_lab(palette_module.role_rgb(palette, role))
            for role in palette_module.ROLES}


def fit_role(lab, labs):
    best, distance = None, None
    for role in palette_module.ROLES:
        candidate = chroma_distance(lab, labs[role])
        if distance is None or candidate < distance - 1e-9:
            best, distance = role, candidate
    return best, distance


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_box(box):
    """[x0, y0, x1, y1] as frame fractions, in order. Reported once, then skipped."""
    return (isinstance(box, list) and len(box) == 4
            and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and 0.0 <= value <= 1.0 for value in box)
            and box[0] < box[2] and box[1] < box[3])


def load_pixels(path, masks):
    """Work-size pixels plus a mask flag per pixel. Masks are fractions of the frame."""
    try:
        image = Image.open(path)
    except OSError as error:
        raise ToolError(f"{path}: cannot read image ({error})")
    image = image.convert("RGB")
    original = image.size
    width = SAMPLER["work_width"]
    height = max(1, int(round(width * image.size[1] / image.size[0])))
    image = image.resize((width, height), Image.Resampling.BOX)
    reader = getattr(image, "get_flattened_data", None) or image.getdata
    pixels = list(reader())

    masked = [False] * (width * height)
    for box in masks:
        x0, y0, x1, y1 = box
        left, right = int(round(x0 * width)), int(round(x1 * width))
        top, bottom = int(round(y0 * height)), int(round(y1 * height))
        for y in range(max(0, top), min(height, bottom)):
            row = y * width
            for x in range(max(0, left), min(width, right)):
                masked[row + x] = True
    return width, height, pixels, masked, original


def merge_clusters(left, right):
    total = left["count"] + right["count"]
    rgb = tuple((left["rgb"][c] * left["count"] + right["rgb"][c] * right["count"]) / total
                for c in range(3))
    return {"count": total, "rgb": rgb, "lab": linear_to_lab(rgb)}


def cluster_families(pixels):
    """Median cut to fine_colors, then agglomerate in CIELab down to family_max."""
    if len(pixels) < SAMPLER["blob_min_px"]:
        return []
    distinct = len(set(pixels))
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    quantized = strip.quantize(colors=min(SAMPLER["fine_colors"], max(1, distinct)),
                               method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    table = quantized.getpalette()
    clusters = []
    for count, index in quantized.getcolors():
        rgb = srgb255_to_linear(tuple(table[index * 3:index * 3 + 3]))
        clusters.append({"count": count, "rgb": rgb, "lab": linear_to_lab(rgb)})

    while len(clusters) > 1:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                distance = lab_distance(clusters[i]["lab"], clusters[j]["lab"])
                if best is None or distance < best[0] - 1e-9:
                    best = (distance, i, j)
        distance, i, j = best
        if distance >= SAMPLER["merge_stop_lab"] and len(clusters) <= SAMPLER["family_max"]:
            break
        merged = merge_clusters(clusters[i], clusters[j])
        clusters = [c for k, c in enumerate(clusters) if k not in (i, j)] + [merged]

    # A cluster of half a percent is anti-aliasing along an edge, not a material.
    # It is folded into its nearest neighbour rather than occupying a family slot.
    total = sum(cluster["count"] for cluster in clusters)
    while len(clusters) > 1:
        smallest = min(range(len(clusters)), key=lambda k: (clusters[k]["count"], k))
        if clusters[smallest]["count"] / total >= SAMPLER["family_min_share"]:
            break
        nearest = min((k for k in range(len(clusters)) if k != smallest),
                      key=lambda k: (lab_distance(clusters[k]["lab"], clusters[smallest]["lab"]), k))
        clusters[nearest] = merge_clusters(clusters[nearest], clusters[smallest])
        clusters.pop(smallest)

    clusters.sort(key=lambda cluster: (-cluster["count"], cluster["lab"][0]))
    return [{"count": cluster["count"], "share": cluster["count"] / total,
             "rgb": cluster["rgb"], "lab": cluster["lab"]} for cluster in clusters]


def find_lights(width, height, pixels, masked):
    """Connected lit blobs, 4-neighbour, keyed by hue bucket (-1 = unsaturated)."""
    lit = [not masked[i] and max(pixels[i]) >= SAMPLER["lit_value"] for i in range(len(pixels))]
    seen = [False] * len(pixels)
    blobs = []
    for start in range(len(pixels)):
        if not lit[start] or seen[start]:
            continue
        seen[start] = True
        queue, members = deque([start]), []
        while queue:
            index = queue.popleft()
            members.append(index)
            y, x = divmod(index, width)
            for neighbour, ok in ((index - 1, x > 0), (index + 1, x < width - 1),
                                  (index - width, y > 0), (index + width, y < height - 1)):
                if ok and lit[neighbour] and not seen[neighbour]:
                    seen[neighbour] = True
                    queue.append(neighbour)
        if len(members) < SAMPLER["blob_min_px"]:
            continue
        rgb = tuple(sum(pixels[i][c] for i in members) / len(members) for c in range(3))
        hue, saturation = hue_and_saturation(rgb)
        bucket = -1 if saturation < SAMPLER["lit_sat"] else int(
            round(hue / SAMPLER["hue_bucket_deg"]) * SAMPLER["hue_bucket_deg"]) % 360
        centre_x = sum(i % width for i in members) / len(members) / width
        centre_y = sum(i // width for i in members) / len(members) / height
        blobs.append({"hue": bucket, "count": len(members), "at": (centre_x, centre_y),
                      "hex": linear_to_hex(srgb255_to_linear(rgb)),
                      "box": (min(i % width for i in members) / width,
                              min(i // width for i in members) / height,
                              (max(i % width for i in members) + 1) / width,
                              (max(i // width for i in members) + 1) / height)})
    blobs.sort(key=lambda blob: (-blob["count"], blob["at"][1], blob["at"][0]))
    return blobs[:SAMPLER["light_max"]]


def percentile(values, fraction):
    if not values:
        return 0
    return values[min(len(values) - 1, int(fraction * len(values)))]


def sample(path, masks, labs=None):
    width, height, pixels, masked, original = load_pixels(path, masks)
    total = width * height
    kept = [pixels[i] for i in range(total) if not masked[i]]
    if not kept:
        raise ToolError(f"{path}: the masks cover the whole frame")

    values = sorted(max(pixel) for pixel in kept)
    low, high = SAMPLER["mid_value"]
    mid = [pixel for pixel in kept if low <= max(pixel) <= high]

    families = cluster_families(mid)
    lights = find_lights(width, height, pixels, masked)

    measured = {
        "masked_out": round(sum(masked) / total, 4),
        "size": list(original),
        "value": {
            "dark_share": round(sum(1 for v in values if v < SAMPLER["dark_value"]) / len(values), 4),
            "mid_share": round(len(mid) / len(kept), 4),
            "lit_share": round(sum(1 for v in values if v >= SAMPLER["lit_value"]) / len(values), 4),
            "p05": percentile(values, 0.05), "p50": percentile(values, 0.50),
            "p90": percentile(values, 0.90), "p99": percentile(values, 0.99),
        },
        "families": [], "lights": [],
    }
    for index, family in enumerate(families):
        entry = {"i": index, "hex": linear_to_hex(family["rgb"]),
                 "share": round(family["share"], 4), "L": int(round(family["lab"][0])),
                 "chroma": round(chroma_of(family["lab"]), 1)}
        if labs is not None:
            role, distance = fit_role(family["lab"], labs)
            entry["nearest"] = role
            entry["d"] = round(distance, 1)
        measured["families"].append(entry)
    for index, blob in enumerate(lights):
        measured["lights"].append({
            "i": index, "hue": blob["hue"], "area": round(blob["count"] / total, 4),
            "at": [round(blob["at"][0], 3), round(blob["at"][1], 3)], "hex": blob["hex"]})
    return measured, {"width": width, "height": height, "pixels": pixels,
                      "masked": masked, "lights": lights, "families": families}


def digest_of(sha256, measured):
    body = {key: value for key, value in measured.items() if key != "digest"}
    payload = json.dumps({"sha256": sha256, "sampler": SAMPLER, "measured": body},
                         sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Board file
# --------------------------------------------------------------------------

def load_board(path):
    if not os.path.isfile(path):
        raise ToolError(f"{path}: no board.json")
    with open(path, "r", encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError as error:
            raise ToolError(f"{path}: not valid JSON ({error})")


def save_board(path, board):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(board, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def board_palette(path, board):
    reference = board.get("design_system") or board.get("palette")
    if not reference:
        raise ToolError(f"{path}: board names neither a palette nor a design_system")
    resolved = reference if os.path.isabs(reference) else os.path.join(os.path.dirname(os.path.abspath(path)), reference)
    if not os.path.isfile(resolved):
        raise ToolError(f"{path}: palette {reference} does not resolve to a file ({resolved})")
    data = palette_module.load(resolved)
    if palette_module.is_design_system(data):
        data = palette_module.load_design_system(resolved)
    return resolved, palette_module.palette_of(data)


def resolve_source(board_path, source):
    """The file a scale_anchor names, searched from the board upwards.

    Not "the .git ancestor": init-project scaffolds a game that may not have
    committed yet, and a correct anchor must not fail for that.
    """
    if os.path.isabs(source):
        return source if os.path.isfile(source) else None
    current = os.path.dirname(os.path.abspath(board_path))
    while True:
        candidate = os.path.join(current, source)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def image_paths(directory):
    names = sorted(name for name in os.listdir(directory)
                   if os.path.splitext(name)[1].lower() in (".png", ".jpg", ".jpeg")
                   and name != "sheet.png")
    return [os.path.join(directory, name) for name in names]


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

class Report:
    def __init__(self, quiet):
        self.quiet = quiet
        self.failures = 0

    def marker(self, line):
        if not self.quiet:
            print(line)

    def fail(self, code, where, message):
        self.failures += 1
        print(f"BOARD_FAIL {code} {where} {message}")

    def warn(self, code, where, message):
        print(f"BOARD_WARN {code} {where} {message}")


def free_text(entry):
    """The author-written strings that must not name a body.

    A mask reason, a do_not_steal line and a cannot_tell line are the three
    places where naming a character is exactly right ("every figure: scale
    rulers only, never geometry"), so those are not scanned. Everything that
    can reach the build is.
    """
    texts = [line.get("line", "") for line in entry.get("steal", [])]
    texts += [item.get("note", "") for item in entry.get("unmatched", [])]
    texts += [light.get("kind", "") + " " + light.get("note", "")
              for light in entry.get("lights_declared", [])]
    return texts


def scan_vocabulary(texts):
    hits = set()
    for text in texts:
        for word in WORD_PATTERN.findall(str(text).lower()):
            stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
            if word in CHARACTER_TERMS or stem in CHARACTER_TERMS:
                hits.add(word)
    return sorted(hits)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_init(directory, zone):
    path = os.path.join(directory, "board.json")
    if os.path.exists(path):
        raise ToolError(f"{path}: already exists; --init never overwrites a board")
    if not os.path.isdir(directory):
        raise ToolError(f"{directory}: not a directory; the owner puts the images there first")
    files = image_paths(directory)
    if not files:
        raise ToolError(f"{directory}: no images found (.png/.jpg)")

    images = []
    for file in files:
        with Image.open(file) as image:
            size = list(image.size)
        images.append({
            "id": os.path.splitext(os.path.basename(file))[0],
            "file": os.path.basename(file), "sha256": sha256_file(file), "size": size,
            "characters": "TODO", "masks": [], "steal": [], "do_not_steal": [],
            "cannot_tell": [], "role_map": {}, "unmatched": [], "lights_declared": [],
        })
    board = {
        "schema": SCHEMA, "zone": zone,
        "palette": "../../blender/palette.json",
        "design_system": "../../blender/design-system.json",
        "scale_anchor": {"constant": "", "source": "", "studs": 0, "reads_as": ""},
        "sampler": dict(SAMPLER), "tolerances": dict(DEFAULT_TOLERANCES),
        "images": images,
        "zone_facts": {"footprint_studs": {}, "openings": [], "surfaces": {},
                       "light_plan": {}, "elements": []},
        "owner": {"decided": [], "open": []},
    }
    save_board(path, board)
    print(f"BOARD {path} images={len(images)}")
    print("Next: answer `characters`, mask every character region, write "
          "do_not_steal, then --measure.")
    return 0


def measure_board(path, board, report, write):
    resolved, palette = board_palette(path, board)
    problems = palette_module.validate(palette)
    if problems:
        for problem in problems:
            report.fail("palette", os.path.basename(resolved), problem)
    labs = role_labs(palette)
    directory = os.path.dirname(os.path.abspath(path))

    for entry in board.get("images", []):
        name = entry.get("id", "?")
        file = os.path.join(directory, entry.get("file", ""))
        if not os.path.isfile(file):
            raise ToolError(f"{path}: image {entry.get('file')!r} of {name} is missing")
        masks = [mask["box"] for mask in entry.get("masks", []) if valid_box(mask.get("box"))]
        measured, _ = sample(file, masks, labs)
        actual = sha256_file(file)
        measured["digest"] = digest_of(actual, measured)

        if write:
            entry["sha256"] = actual
            entry["measured"] = measured
        report.marker(f"REF_MASKED {name} {measured['masked_out']:.4f} {len(masks)}")
        value = measured["value"]
        report.marker(f"REF_VALUE  {name} dark={value['dark_share']:.4f} "
                      f"mid={value['mid_share']:.4f} lit={value['lit_share']:.4f} "
                      f"p50={value['p50']} p90={value['p90']}")
        for family in measured["families"]:
            report.marker(f"REF_FAMILY {name} {family['i']} {family['hex']} "
                          f"share={family['share']:.4f} L={family['L']} "
                          f"chroma={family['chroma']} nearest={family.get('nearest')} "
                          f"d={family.get('d')}")
        for light in measured["lights"]:
            report.marker(f"REF_LIGHT  {name} {light['i']} hue={light['hue']} "
                          f"area={light['area']:.4f} at={light['at'][0]},{light['at'][1]} "
                          f"{light['hex']}")
        yield entry, measured, actual, palette, labs


def cmd_measure(path, report):
    board = load_board(path)
    for _ in measure_board(path, board, report, write=True):
        pass
    save_board(path, board)
    print(f"REFBOARD_VALID:{'false' if report.failures else 'true'}")
    return 1 if report.failures else 0


def is_number_leaf(value):
    """A number, or a string that is nothing but a number."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def check_ranges(where, node, minimum, report, trail=""):
    """Every stud dimension is a range at least range_min_width wide.

    Walked to the leaves and inverted: a bare number, a number in quotes and a
    list that is not exactly two numbers are all refused. A single frame carries
    no metric depth, so a point value claims a precision that is not there, and
    only refusing the one shape `[80, 80]` leaves the cheaper shapes open.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            check_ranges(where, value, minimum, report, f"{trail}.{key}" if trail else key)
        return
    if isinstance(node, list):
        numeric = [item for item in node if isinstance(item, (int, float))
                   and not isinstance(item, bool)]
        if len(numeric) == 2 and len(node) == 2:
            low, high = node
            if high <= low or high <= 0:
                report.fail("scale", where, f"{trail} = {node} is a point value or inverted; a "
                                            "single frame carries no metric depth")
            elif (high - low) / high < minimum:
                report.fail("scale", where, f"{trail} = {node} is narrower than range_min_width "
                                            f"{minimum}")
            return
        if any(is_number_leaf(item) for item in node):
            report.fail("scale", where, f"{trail} = {node} is not a [low, high] range of two "
                                        "numbers")
            return
        for index, item in enumerate(node):
            check_ranges(where, item, minimum, report, f"{trail}[{index}]")
        return
    if is_number_leaf(node):
        report.fail("scale", where, f"{trail} = {node!r} is a bare value; a stud dimension is a "
                                    "[low, high] range")


def check_seal(name, entry, measured, actual, report):
    """Does the stored block still stand: not hand-edited, still the image's own."""
    stored = entry.get("measured")
    if entry.get("sha256") != actual:
        report.fail("stale", name, f"{entry.get('file')} has changed on disk; --measure again")
        return
    if not stored:
        report.fail("stale", name, "no measured block; run --measure")
        return
    # The seal is recomputed over the block as stored, so a hand-typed number
    # breaks it. Drift is the other question: whether the block still describes
    # the pixels, which a changed mask or a changed sampler moves.
    if stored.get("digest") != digest_of(entry.get("sha256", ""), stored):
        report.fail("stale", name, "the measured block does not match its own digest; it was "
                                   "edited by hand. Run --measure, never a text editor")
    for key in ("masked_out", "value", "families", "lights"):
        if stored.get(key) != measured[key]:
            print(f"REF_DRIFT  {name} {key} board={json.dumps(stored.get(key))[:120]} "
                  f"measured={json.dumps(measured[key])[:120]}")
            report.fail("drift", name, f"{key} no longer describes the image")


def check_declarations(name, entry, report, tolerances):
    """The hand-written blocks: answered, masked, bound, and inside the caps."""
    characters = entry.get("characters")
    if characters not in ("present", "absent"):
        report.fail("characters", name, f"`characters` is {characters!r}; answer \"present\" or "
                                        "\"absent\", never leave it TODO")
    elif characters == "present" and not entry.get("masks"):
        report.fail("unmasked", name, "characters are present and no mask box covers them; "
                                      "masks are applied before every measurement")

    for index, mask in enumerate(entry.get("masks", [])):
        box = mask.get("box")
        if not valid_box(box):
            report.fail("unmasked", name, f"mask {index} is not an [x0,y0,x1,y1] of frame "
                                          "fractions in order; it covered nothing")
            continue
        if not mask.get("why"):
            report.fail("unmasked", name, f"mask {index} has no `why`")
        area = (box[2] - box[0]) * (box[3] - box[1])
        if area < tolerances["mask_min_area"]:
            report.warn("thinmask", name, f"mask {index} covers {area:.3f} of the frame, under "
                                          f"mask_min_area {tolerances['mask_min_area']}")

    hits = scan_vocabulary(free_text(entry))
    if hits:
        report.fail("vocabulary", name, "character terms in the declarations: " + ", ".join(hits)
                                        + "; a body is never board content")

    steal = entry.get("steal", [])
    if len(steal) > CAPS["steal"]:
        report.fail("caps", name, f"{len(steal)} steal lines, the cap is {CAPS['steal']}")
    for index, line in enumerate(steal):
        if not line.get("line"):
            report.fail("unbound", name, f"steal {index} has no `line`")
        produces = line.get("produces", "")
        if not produces:
            report.fail("unbound", name, f"steal {index} produces nothing; an observation that "
                                         "names no key is not an instruction")
        elif not produces.startswith(PRODUCES_PREFIXES):
            report.warn("unbound", name, f"steal {index} produces {produces!r}, which starts with "
                                         f"none of {PRODUCES_PREFIXES}")

    do_not_steal = entry.get("do_not_steal", [])
    if not do_not_steal:
        report.fail("notsteal", name, "`do_not_steal` is empty; every reference has something that "
                                      "must not be built")
    if len(do_not_steal) > CAPS["do_not_steal"]:
        report.fail("caps", name, f"{len(do_not_steal)} do_not_steal lines, the cap is "
                                  f"{CAPS['do_not_steal']}")


def check_role_map(name, entry, families, labs, report, tolerances):
    """Each mapped family is close enough in chroma to the role the author chose."""
    by_index = {family["i"]: family for family in families}
    mapped = []
    for key, role in entry.get("role_map", {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            report.fail("chroma", name, f"role_map key {key!r} is not a family index")
            continue
        if index not in by_index:
            report.fail("chroma", name, f"role_map names family {index}, which was not measured")
            continue
        if role not in palette_module.ROLES:
            report.fail("chroma", name, f"role_map maps family {index} to {role!r}, which is not "
                                        "a palette role")
            continue
        family = by_index[index]
        # Distance to the role the author chose, not to the nearest one the tool
        # suggested. Recovered from the printed hex, which costs under one unit
        # against the family's own lab.
        distance = chroma_distance(lab_of_hex(family["hex"]), labs[role])
        if distance > tolerances["chroma_distance_max"]:
            report.fail("chroma", name, f"family {index} {family['hex']} is {distance:.1f} from "
                                        f"{role} in chroma, over chroma_distance_max "
                                        f"{tolerances['chroma_distance_max']}")
        mapped.append((index, role, family))
    return mapped


def check_luminance_order(name, mapped, labs, report):
    """Chroma alone cannot see a family sitting at the wrong end of the value scale.

    Two families on two roles keep the palette's own luminance order, or one of
    them is a light on a material rather than the material.
    """
    for index_a, role_a, family_a in mapped:
        for index_b, role_b, family_b in mapped:
            if index_a == index_b or role_a == role_b:
                continue
            if labs[role_a][0] < labs[role_b][0] - 1e-9 and family_a["L"] > family_b["L"]:
                report.fail("order", name, f"{family_a['hex']} is mapped to {role_a} and "
                                           f"{family_b['hex']} to {role_b}, but {role_a} is the "
                                           "darker role while its family is the lighter one")


def check_unmatched(name, entry, families, mapped, report, tolerances):
    """A family above the floor is either a role or a written resolution."""
    resolutions = {item.get("family"): item for item in entry.get("unmatched", [])}
    mapped_indices = {index for index, _, _ in mapped}
    for family in families:
        if family["i"] in mapped_indices or family["share"] < tolerances["family_floor"]:
            continue
        item = resolutions.get(family["i"])
        if item is None:
            report.fail("unmatched", name, f"family {family['i']} {family['hex']} is "
                                           f"{family['share']:.1%} of the mid band with no role "
                                           "and no resolution")
        elif item.get("resolution") not in RESOLUTIONS:
            report.fail("unmatched", name, f"family {family['i']} resolution is "
                                           f"{item.get('resolution')!r}; one of {RESOLUTIONS}")
        elif not item.get("note"):
            report.fail("unmatched", name, f"family {family['i']} has a resolution and no note")


def check_lights_declared(name, entry, measured, report):
    blobs = {light["i"] for light in measured["lights"]}
    for index, light in enumerate(entry.get("lights_declared", [])):
        for blob in light.get("blobs", []):
            if blob not in blobs:
                report.fail("litrole", name, f"lights_declared {index} names blob {blob}, which "
                                             "was not measured")
        if light.get("role") not in ("emissive", "accent"):
            report.fail("litrole", name, f"lights_declared {index} takes role "
                                         f"{light.get('role')!r}; a lit pixel is a light colour, "
                                         "never a surface role")
        if not light.get("kind"):
            report.fail("litrole", name, f"lights_declared {index} has no `kind`")


def check_legibility(name, measured, report):
    """A frame that carries no material cannot produce a board that means anything.

    Without this the colour half of a board is vacuously satisfied: no family
    means nothing for the role map, the unmatched rule or the ordering rule to
    hold, and the board checks green on a blank frame.
    """
    if not measured["families"]:
        report.fail("families", name, "no surface family in the mid band; this frame carries no "
                                      "material a build can follow")
    value = measured["value"]
    if value["dark_share"] > 0.90:
        report.warn("darkboard", name, f"dark_share {value['dark_share']:.2f}: almost nothing in "
                                       "this frame is legible as material")
    if value["lit_share"] > 0.50:
        report.warn("blownboard", name, f"lit_share {value['lit_share']:.2f}: over half the frame "
                                        "is above the lit threshold, so it measures the exposure")


def check_tolerances(where, declared, report):
    """A board may tighten its own bar, never loosen it, and never in silence.

    `sampler` is pinned hard; tolerances used to be whatever the author typed,
    which turned one edit into an off switch for the chroma, unmatched and range
    rules at once.
    """
    tolerances = dict(DEFAULT_TOLERANCES)
    for key, value in declared.items():
        if key not in DEFAULT_TOLERANCES:
            report.fail("tolerance", where, f"unknown tolerance {key!r}; one of "
                                            f"{tuple(DEFAULT_TOLERANCES)}")
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            report.fail("tolerance", where, f"tolerance {key} is {value!r}, not a number")
            continue
        default = DEFAULT_TOLERANCES[key]
        looser = value > default if TOLERANCE_DIRECTION[key] == "ceiling" else value < default
        if looser:
            report.fail("tolerance", where, f"tolerance {key} = {value} is looser than the "
                                            f"default {default}; a board may only tighten")
            continue
        if value != default:
            report.warn("tolerance", where, f"{key} = {value} instead of the default {default}; "
                                            "the bar was moved, deliberately")
        tolerances[key] = value
    return tolerances


def check_zone(path, board, where, report, tolerances):
    """The block a builder reads: anchored, in ranges, in role names."""
    anchor = board.get("scale_anchor", {})
    constant, source = anchor.get("constant", ""), anchor.get("source", "")
    if not constant or not source:
        report.fail("scale", where, "scale_anchor names no constant and source; frame fractions "
                                    "become studs only through a constant the blueprint already has")
    else:
        full = resolve_source(path, source)
        if full is None:
            report.fail("scale", where, f"scale_anchor source {source} was not found from the "
                                        "board upwards; name it relative to the project root")
        else:
            with open(full, "r", encoding="utf-8") as handle:
                if constant not in handle.read():
                    report.fail("scale", where, f"scale_anchor constant {constant} is not in {source}")

    facts = board.get("zone_facts", {})
    check_ranges(where, facts, tolerances["range_min_width"], report)
    text = json.dumps(facts)
    for hex_value in HEX_PATTERN.findall(text):
        report.fail("litrole", where, f"zone_facts carries the hex {hex_value}; a builder reads "
                                      "palette role names, never a colour from a render")
    hits = scan_vocabulary([text])
    if hits:
        report.fail("vocabulary", where, "character terms in zone_facts: " + ", ".join(hits))
    for surface, role in (facts.get("surfaces") or {}).items():
        if role not in palette_module.ROLES:
            report.fail("litrole", where, f"surfaces.{surface} is {role!r}, not a palette role")


def check_board(path, report):
    board = load_board(path)
    where = board.get("zone", os.path.basename(os.path.dirname(os.path.abspath(path))))
    tolerances = check_tolerances(where, board.get("tolerances", {}), report)

    if board.get("schema") != SCHEMA:
        report.fail("schema", where, f"schema is {board.get('schema')!r}, expected {SCHEMA!r}")
    if board.get("sampler") != SAMPLER:
        report.fail("sampler", where, "the sampler constants differ from this tool; REGENERATE "
                                      "with --measure, this is not a colour failure")
    if len(board.get("images", [])) > CAPS["images"]:
        report.fail("caps", where, f"{len(board['images'])} images, the cap is {CAPS['images']}")

    for entry, measured, actual, _, labs in measure_board(path, board, report, write=False):
        name = entry.get("id", "?")
        check_seal(name, entry, measured, actual, report)
        check_declarations(name, entry, report, tolerances)
        mapped = check_role_map(name, entry, measured["families"], labs, report, tolerances)
        check_luminance_order(name, mapped, labs, report)
        check_unmatched(name, entry, measured["families"], mapped, report, tolerances)
        check_lights_declared(name, entry, measured, report)
        check_legibility(name, measured, report)

    check_zone(path, board, where, report, tolerances)


def cmd_check(target, report):
    boards, orphans = [], []
    if os.path.isdir(target):
        for root, _, files in os.walk(target):
            if "board.json" in files:
                boards.append(os.path.join(root, "board.json"))
            elif image_paths(root):
                orphans.append(root)
        boards.sort()
        orphans.sort()
    elif os.path.isfile(target):
        boards = [target]
    else:
        # Day one a game has no zones, so an absent directory is not a finding.
        # Naming it is what keeps a typo in the gate step from reading as
        # "everything is fine".
        print(f"REFBOARD_VALID:true (0 boards, {target} does not exist)")
        return 0

    for root in orphans:
        report.fail("noboard", os.path.basename(root) or root,
                    f"{root} holds reference images and no board.json; deleting the board is not "
                    "how an image stops being a source")
    if not boards:
        print(f"REFBOARD_VALID:{'false' if report.failures else 'true'} (0 boards)")
        return 1 if report.failures else 0
    for board in boards:
        check_board(board, report)
    print(f"REFBOARD_VALID:{'false' if report.failures else 'true'} ({len(boards)} boards)")
    return 1 if report.failures else 0


PAD, SWATCH_HEIGHT, LABEL_HEIGHT = 6, 46, 14
MASK_INK, LIGHT_INK, LEGEND_INK = (255, 64, 64), (120, 220, 255), (190, 190, 190)


def draw_masks(draw, masks, origin, size):
    """Hatched boxes, clipped to themselves, so the owner can see the cover."""
    left, top = origin
    for mask in masks:
        box = mask.get("box")
        if not valid_box(box):
            continue
        x0, y0 = left + box[0] * size[0], top + box[1] * size[1]
        x1, y1 = left + box[2] * size[0], top + box[3] * size[1]
        draw.rectangle([x0, y0, x1, y1], outline=MASK_INK, width=2)
        for offset in range(0, int((x1 - x0) + (y1 - y0)), 9):
            start = [x1, y0 + (x0 + offset - x1)] if x0 + offset > x1 else [x0 + offset, y0]
            end = [x0 + (y0 + offset - y1), y1] if y0 + offset > y1 else [x0, y0 + offset]
            draw.line([tuple(start), tuple(end)], fill=MASK_INK, width=1)
        draw.text((x0 + 3, y0 + 2), mask.get("why", "")[:34], fill=(255, 210, 210))


def draw_panel(sheet, draw, entry, measured, raw, top):
    """One image row: the annotated frame, the read-distance frame, the families."""
    frame_width = SAMPLER["work_width"]
    frame = Image.new("RGB", (raw["width"], raw["height"]))
    frame.putdata(raw["pixels"])
    sheet.paste(frame, (PAD, top + PAD))

    # Read distance: what still reads at the camera distance the game cares
    # about. A steal line for something that dissolves here is not admissible.
    read_width = SAMPLER["read_width"]
    read_height = max(1, int(round(read_width * raw["height"] / raw["width"])))
    small = frame.resize((read_width, read_height), Image.Resampling.BOX)
    sheet.paste(small.resize((frame_width, raw["height"]), Image.Resampling.NEAREST),
                (PAD * 2 + frame_width, top + PAD))

    draw_masks(draw, entry.get("masks", []), (PAD, top + PAD), (raw["width"], raw["height"]))
    for light in measured["lights"]:
        centre_x = PAD + light["at"][0] * raw["width"]
        centre_y = top + PAD + light["at"][1] * raw["height"]
        draw.ellipse([centre_x - 7, centre_y - 7, centre_x + 7, centre_y + 7],
                     outline=LIGHT_INK, width=1)
        draw.text((centre_x + 9, centre_y - 5), f"{light['i']}:{light['hue']}", fill=LIGHT_INK)

    swatch_top = top + PAD * 2 + raw["height"]
    x = PAD
    for family in measured["families"]:
        box_width = max(18, int(family["share"] * frame_width))
        draw.rectangle([x, swatch_top, x + box_width, swatch_top + 16],
                       fill=tuple(int(family["hex"][i:i + 2], 16) for i in (1, 3, 5)))
        draw.text((x + 2, swatch_top + 3), str(family["i"]), fill=(20, 20, 20))
        x += box_width + 4
    # A joined legend rather than a label per swatch: proportional swatches
    # overlap their own labels as soon as a family is small, and a small family
    # is the interesting one.
    legend = [f"{family['i']}:{family['share']:.0%} {family['hex']} {family.get('nearest')}"
              f" d{family.get('d')}" for family in measured["families"]]
    for line, first in enumerate(range(0, len(legend), 3)):
        draw.text((PAD, swatch_top + 18 + line * 11), "   ".join(legend[first:first + 3]),
                  fill=LEGEND_INK)
    draw.text((PAD, swatch_top + SWATCH_HEIGHT - 2),
              f"{entry.get('id')}  masked {measured['masked_out']:.1%}  "
              f"dark {measured['value']['dark_share']:.0%}  "
              f"lit {measured['value']['lit_share']:.2%}  |  right: read distance "
              f"({read_width}px)", fill=(230, 230, 230))


def cmd_sheet(path):
    board = load_board(path)
    directory = os.path.dirname(os.path.abspath(path))
    _, palette = board_palette(path, board)
    labs = role_labs(palette)

    panels = []
    for entry in board.get("images", []):
        file = os.path.join(directory, entry.get("file", ""))
        if not os.path.isfile(file):
            raise ToolError(f"{path}: image {entry.get('file')!r} is missing")
        masks = [mask["box"] for mask in entry.get("masks", []) if valid_box(mask.get("box"))]
        measured, raw = sample(file, masks, labs)
        panels.append((entry, measured, raw))

    heights = [raw["height"] + SWATCH_HEIGHT + LABEL_HEIGHT + PAD * 3 for _, _, raw in panels]
    sheet = Image.new("RGB", (SAMPLER["work_width"] * 2 + PAD * 3, sum(heights)), (16, 16, 18))
    draw = ImageDraw.Draw(sheet)
    top = 0
    for (entry, measured, raw), height in zip(panels, heights):
        draw_panel(sheet, draw, entry, measured, raw, top)
        top += height

    out = os.path.join(directory, "sheet.png")
    sheet.save(out)
    print(f"SHEET {out}")
    return 0


def cmd_compare(path, image_id, shot):
    board = load_board(path)
    _, palette = board_palette(path, board)
    labs = role_labs(palette)
    entry = next((item for item in board.get("images", []) if item.get("id") == image_id), None)
    if entry is None:
        raise ToolError(f"{path}: no image with id {image_id!r}")
    reference = entry.get("measured")
    if not reference:
        raise ToolError(f"{path}: image {image_id!r} has no measured block; run --measure")
    if not os.path.isfile(shot):
        raise ToolError(f"{shot}: no such shot")

    built, _ = sample(shot, [], labs)
    print("COMPARE is a measured delta, not a similarity score")
    for field in ("dark_share", "mid_share", "lit_share"):
        a, b = reference["value"][field], built["value"][field]
        print(f"COMPARE {field} board={a:.4f} built={b:.4f} delta={b - a:+.4f}")
    for bucket in sorted({light["hue"] for light in reference["lights"]}
                         | {light["hue"] for light in built["lights"]}):
        a = sum(1 for light in reference["lights"] if light["hue"] == bucket)
        b = sum(1 for light in built["lights"] if light["hue"] == bucket)
        print(f"COMPARE lights_hue_{bucket} board={a} built={b} delta={b - a:+d}")
    for role in sorted(set(entry.get("role_map", {}).values())):
        a = sum(family["share"] for index, mapped in entry["role_map"].items()
                if mapped == role for family in reference["families"] if family["i"] == int(index))
        b = sum(family["share"] for family in built["families"] if family.get("nearest") == role)
        print(f"COMPARE role_{role}_share board={a:.4f} built={b:.4f} delta={b - a:+.4f}")
    return 0


# --------------------------------------------------------------------------
# Selftest
# --------------------------------------------------------------------------

def cmd_selftest():
    width, height = 400, 200
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, height], fill=(40, 42, 38))            # 100% ground
    draw.rectangle([0, 0, width // 2, height], fill=(90, 70, 55))       # 50%
    draw.rectangle([0, 0, width // 4, height], fill=(140, 140, 150))    # 25%
    draw.ellipse([300, 40, 340, 80], fill=(250, 220, 90))               # one lit blob
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "synthetic.png")
        image.save(path)

        first, _ = sample(path, [])
        second, _ = sample(path, [])
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True), \
            "two runs of the sampler differ"

        wanted = {"#5a4637": 0.25, "#8c8c96": 0.25, "#282a26": 0.50}
        found = {family["hex"]: family["share"] for family in first["families"]}
        assert len(found) == 3, f"expected 3 families, got {len(found)}: {found}"
        for hex_value, share in wanted.items():
            match = min(found, key=lambda candidate: sum(
                abs(int(candidate[i:i + 2], 16) - int(hex_value[i:i + 2], 16)) for i in (1, 3, 5)))
            drift = max(abs(int(match[i:i + 2], 16) - int(hex_value[i:i + 2], 16)) for i in (1, 3, 5))
            assert drift <= 3, f"{hex_value} recovered as {match} (off by {drift})"
            assert abs(found[match] - share) <= 0.02, \
                f"{hex_value} share {found[match]:.3f}, expected {share}"

        assert len(first["lights"]) == 1, f"expected 1 blob, got {len(first['lights'])}"
        blob = first["lights"][0]
        assert abs(blob["at"][0] - 0.80) <= 0.02 and abs(blob["at"][1] - 0.30) <= 0.02, \
            f"blob at {blob['at']}, expected about [0.80, 0.30]"
        assert blob["hue"] == 60, f"blob hue bucket {blob['hue']}, expected 60"

        # The trap this tool exists to avoid: median cut splits by population, so
        # over a whole dark frame all eight buckets land in the shadow and the
        # saturated minority that carries the zone's character is dropped.
        dark = Image.new("RGB", (200, 100))
        shadow = ImageDraw.Draw(dark)
        for x in range(200):
            level = 4 + (x % 16)
            shadow.line([(x, 0), (x, 100)], fill=(level, level, level + 2))
        shadow.rectangle([90, 40, 110, 60], fill=(200, 60, 60))
        dark_path = os.path.join(directory, "dark.png")
        dark.save(dark_path)
        naive = dark.quantize(colors=8, method=Image.Quantize.MEDIANCUT,
                              dither=Image.Dither.NONE).getpalette()[:24]
        buckets = [naive[i:i + 3] for i in range(0, 24, 3)]
        assert all(max(bucket) < 60 for bucket in buckets), \
            f"the equal-population trap no longer reproduces: {buckets}"
        banded, _ = sample(dark_path, [])
        assert any(int(family["hex"][1:3], 16) > 120 for family in banded["families"]), \
            f"the mid band lost the saturated minority: {banded['families']}"

        masked, _ = sample(path, [[0.0, 0.0, 0.25, 1.0]])
        assert abs(masked["masked_out"] - 0.25) <= 0.01, f"masked_out {masked['masked_out']}"
        assert not any(family["hex"] == "#8c8c96" for family in masked["families"]), \
            "a masked region still reaches the families"

        selftest_guards(directory)

    print("REFBOARD_SELFTEST ok")
    return 0


def _swatch(path, palette, extra=None):
    """A frame painted in the palette's own roles, so the right mapping is known."""
    width, height = 400, 200
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for role, span in (("body2", (0, 400)), ("body", (0, 160)), ("trim", (0, 60))):
        draw.rectangle([span[0], 0, span[1], height],
                       fill=tuple(int(linear_to_hex(palette_module.role_rgb(palette, role))[i:i + 2], 16)
                                  for i in (1, 3, 5)))
    draw.ellipse([340, 40, 380, 80],
                 fill=tuple(int(linear_to_hex(palette_module.role_rgb(palette, "emissive"))[i:i + 2], 16)
                            for i in (1, 3, 5)))
    if extra:
        draw.rectangle(extra, fill=(230, 40, 200))
    image.save(path)


def _run(function, *arguments):
    """A command's exit code plus its output, without printing it."""
    buffer = StringIO()
    with redirect_stdout(buffer):
        try:
            code = function(*arguments)
        except ToolError as error:
            print(f"REFBOARD_ERROR: {error}")
            code = 2
    return code, buffer.getvalue()


def selftest_project(root):
    """A synthetic game repo with two references, declared and measured to green."""
    project = os.path.join(root, "project")
    refs = os.path.join(project, "assets", "refs", "hold")
    blender = os.path.join(project, "assets", "blender")
    source = os.path.join(project, "src")
    for directory in (refs, blender, source, os.path.join(project, ".git")):
        os.makedirs(directory)
    presets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender", "presets")
    shutil.copy(os.path.join(presets, "chunky-horror.json"), os.path.join(blender, "palette.json"))
    design = palette_module.load(os.path.join(presets, "chunky-horror-design.json"))
    design["palette"] = "palette.json"
    with open(os.path.join(blender, "design-system.json"), "w", encoding="utf-8") as handle:
        json.dump(design, handle, indent=2)
    palette = palette_module.load(os.path.join(blender, "palette.json"))
    with open(os.path.join(source, "Blueprint.luau"), "w", encoding="utf-8") as handle:
        handle.write("local Blueprint = {}\nBlueprint.DOOR_HEIGHT_STUDS = 10\nreturn Blueprint\n")
    _swatch(os.path.join(refs, "plain.png"), palette)
    _swatch(os.path.join(refs, "peopled.png"), palette, extra=[200, 60, 300, 160])

    board_path = os.path.join(refs, "board.json")
    code, _ = _run(cmd_init, refs, "hold")
    assert code == 0, "--init did not write a board"
    assert _run(cmd_init, refs, "hold")[0] == 2, "--init overwrote an existing board"

    board = load_board(board_path)
    board["scale_anchor"] = {"constant": "DOOR_HEIGHT_STUDS", "source": "src/Blueprint.luau",
                             "studs": 10, "reads_as": "the door in plain.png"}
    board["zone_facts"] = {
        "footprint_studs": {"length": [30, 40], "width": [20, 26], "height": [12, 16]},
        "surfaces": {"floor": "body2", "wall": "body", "trim": "trim"},
        "light_plan": {"key": "strip", "count": [1, 2], "role": "emissive"},
        "elements": ["crate", "rail"]}
    for entry in board["images"]:
        peopled = entry["id"] == "peopled"
        entry["characters"] = "present" if peopled else "absent"
        entry["masks"] = [{"box": [0.49, 0.29, 0.76, 0.81], "why": "the standing group at the rail"}] if peopled else []
        entry["steal"] = [{"line": "one slab wall, one trim band at knee height",
                           "produces": "zone_facts.elements[rail]"}]
        entry["do_not_steal"] = ["the strip glare: a light, never a surface"]
        entry["cannot_tell"] = ["what the wall does past frame right"]
    save_board(board_path, board)

    code, _ = _run(cmd_measure, board_path, Report(quiet=True))
    assert code == 0, "--measure reported findings on a clean board"

    board = load_board(board_path)
    for entry in board["images"]:
        entry["role_map"] = {str(family["i"]): family["nearest"]
                             for family in entry["measured"]["families"]
                             if family["d"] <= DEFAULT_TOLERANCES["chroma_distance_max"]}
        entry["lights_declared"] = [{"blobs": [light["i"] for light in entry["measured"]["lights"]],
                                     "kind": "strip", "role": "emissive", "count_in_zone": [1, 2]}]
    save_board(board_path, board)
    code, output = _run(cmd_check, board_path, Report(quiet=True))
    assert code == 0, f"a clean board did not check green:\n{output}"
    assert "REFBOARD_VALID:true" in output
    return project


def selftest_guards(root):
    """The guards are the product, so every one of them is proved to bite."""
    project = selftest_project(root)

    def mutated(change, code):
        work = os.path.join(root, "mutation")
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(project, work)
        path = os.path.join(work, "assets", "refs", "hold", "board.json")
        board = load_board(path)
        change(board, os.path.dirname(path))
        save_board(path, board)
        _, output = _run(cmd_check, path, Report(quiet=True))
        found = {line.split()[1] for line in output.splitlines() if line.startswith("BOARD_FAIL")}
        assert code in found, f"mutation for {code!r} produced {sorted(found) or ['nothing']}"

    def with_masks(board):
        return next(entry for entry in board["images"] if entry["masks"])

    def without_masks(board):
        return next(entry for entry in board["images"] if not entry["masks"])

    mutated(lambda board, _: board["images"][0]["measured"]["families"][0].update({"hex": "#ff0000"}), "stale")
    mutated(lambda board, _: with_masks(board)["masks"].clear(), "drift")
    mutated(lambda board, _: board["images"][0].update({"characters": "TODO"}), "characters")
    mutated(lambda board, _: board["images"][0]["do_not_steal"].clear(), "notsteal")
    mutated(lambda board, _: board["images"][0]["steal"][0].pop("produces"), "unbound")
    mutated(lambda board, _: board["images"][0]["steal"][0].update({"line": "steal the alien pose"}), "vocabulary")
    mutated(lambda board, _: board["zone_facts"]["surfaces"].update({"wall": "#502723"}), "litrole")
    mutated(lambda board, _: board["images"][0]["lights_declared"][0].update({"role": "body"}), "litrole")
    mutated(lambda board, _: board["zone_facts"]["footprint_studs"].update({"length": [30, 30]}), "scale")
    mutated(lambda board, _: board["scale_anchor"].update({"constant": "CEILING_STUDS"}), "scale")
    mutated(lambda board, _: board["sampler"].update({"work_width": 256}), "sampler")
    mutated(lambda board, _: board["images"][0]["role_map"].update(
        {str(board["images"][0]["measured"]["families"][0]["i"]): "accent"}), "chroma")
    mutated(lambda board, _: board["images"][0]["role_map"].clear(), "unmatched")

    def invert(board, _):
        entry = board["images"][0]
        families = sorted(entry["measured"]["families"], key=lambda family: family["L"])
        entry["role_map"] = {str(families[0]["i"]): "body", str(families[-1]["i"]): "body2"}
    mutated(invert, "order")

    mutated(lambda board, _: without_masks(board).update({"characters": "present"}), "unmasked")
    mutated(lambda board, _: with_masks(board)["masks"][0].update({"box": [0.5, 0.5]}), "unmasked")
    mutated(lambda board, _: with_masks(board)["masks"][0].pop("why"), "unmasked")
    mutated(lambda board, _: board.setdefault("tolerances", {}).update(
        {"chroma_distance_max": 999.0}), "tolerance")
    mutated(lambda board, _: board["zone_facts"]["footprint_studs"].update({"length": 35}), "scale")
    mutated(lambda board, _: board["zone_facts"]["footprint_studs"].update(
        {"length": ["30", "40"]}), "scale")

    def swap(board, directory):
        image = Image.open(os.path.join(directory, "plain.png"))
        image.crop((0, 0, image.size[0] - 40, image.size[1])).save(os.path.join(directory, "plain.png"))
    mutated(swap, "stale")

    def blank(board, directory):
        Image.new("RGB", (400, 200), (255, 255, 255)).save(os.path.join(directory, "plain.png"))
        entry = next(item for item in board["images"] if item["id"] == "plain")
        entry["role_map"], entry["lights_declared"] = {}, []
    mutated(blank, "families")

    # A deleted board with the images still in place, and a project that has not
    # run git init yet: two ways a green gate used to mean nothing.
    work = os.path.join(root, "tree")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(project, work)
    refs = os.path.join(work, "assets", "refs")
    os.remove(os.path.join(refs, "hold", "board.json"))
    _, output = _run(cmd_check, refs, Report(quiet=True))
    assert "BOARD_FAIL noboard" in output, f"a deleted board with images left behind passed:\n{output}"

    shutil.rmtree(os.path.join(work, ".git"))
    shutil.copy(os.path.join(project, "assets", "refs", "hold", "board.json"),
                os.path.join(refs, "hold", "board.json"))
    code, output = _run(cmd_check, refs, Report(quiet=True))
    assert code == 0, f"a correct board failed without a .git ancestor:\n{output}"


# --------------------------------------------------------------------------

def main(argv):
    parser = argparse.ArgumentParser(description="Reference boards: concept art to buildable data.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init", metavar="DIR")
    group.add_argument("--measure", metavar="BOARD")
    group.add_argument("--check", metavar="BOARD_OR_DIR")
    group.add_argument("--sheet", metavar="BOARD")
    group.add_argument("--compare", metavar="BOARD")
    group.add_argument("--selftest", action="store_true")
    parser.add_argument("--zone")
    parser.add_argument("--image")
    parser.add_argument("--shot")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = Report(args.quiet)
    try:
        if args.selftest:
            return cmd_selftest()
        if args.init:
            if not args.zone:
                raise ToolError("--init needs --zone <id>")
            return cmd_init(args.init, args.zone)
        if args.measure:
            return cmd_measure(args.measure, report)
        if args.check:
            return cmd_check(args.check, report)
        if args.sheet:
            return cmd_sheet(args.sheet)
        if args.compare:
            if not args.image or not args.shot:
                raise ToolError("--compare needs --image <id> and --shot <png>")
            return cmd_compare(args.compare, args.image, args.shot)
    except ToolError as error:
        print(f"REFBOARD_ERROR: {error}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
