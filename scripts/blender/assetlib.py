"""Shared building blocks for one hero asset: one bmesh, one object, role-named materials.

Chunky cartoon by construction: every helper bevels its hard edges (radius 0.10 to
0.35, 2 to 3 segments on the dominant volume), detail is cut INTO a skin
(groove, inset_panel, plate, vent_slots, grille) or placed as a few studs, never
glued on as thin boxes. A pipe is a tube along a real 3D path (sweep bridges a
profile along Y only). tube, plate, vent_slots and grille refuse anything under the
design-system thickness_min or seam floors, because a bar under 0.30 shimmers at
40 studs and a seam under 0.08 does not read there.
Works through bpy.data and bmesh only, so it runs headless (blender -b) and
through the blender MCP bridge alike. Blender 5.x: no use_auto_smooth; shading
is flat and bevels carry the rounding.
"""

import math
import os
import sys

import bmesh
import bpy
import mathutils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette as palette_module  # noqa: E402
import spec as spec_module  # noqa: E402
from spec import ngon  # noqa: E402,F401

MATERIAL_PREFIX = "Role_"


def material_name(role):
    return MATERIAL_PREFIX + role


# Above 1.0 so an emissive surface reads as a glow rather than as paint. The same
# number lights the baked preview material (bake_asset), so a signal looks the same
# before and after the bake.
#
# Measured limit, beacon rounds 2 and 3: this only reaches the Cycles look renders.
# The five rig previews the prop judge scores (front, three-quarter, side, top,
# read-40) render in BLENDER_WORKBENCH with color_type MATERIAL, which reads
# material.diffuse_color and evaluates no shader node, so emission is invisible
# there. Measured on beacon round 3: the brightest warm pixel is luminance 145 in
# front.png against 165 for the brightest neutral pixel, so an emissive unit is
# darker than the lit body beside it. The consequence is that the design-system
# line "one emissive signal at most" cannot be judged from those five shots, and on
# chunky-cartoon, where accent and emissive carry the same rgb, the two roles are
# the same pixel value. Both are owner decisions and neither is fixed here.
EMISSION_PREVIEW_STRENGTH = 2.5


def ensure_materials(style):
    """One material per role, in ROLES order, base colour and roughness from the palette.

    The emissive role also emits, at EMISSION_PREVIEW_STRENGTH, so the fixed preview rig
    shows a signal as a signal.

    style is a palette dict or a design system dict (which carries its palette).
    """
    palette = palette_module.palette_of(style)
    materials = []
    for role in palette_module.ROLES:
        name = material_name(role)
        material = bpy.data.materials.get(name)
        if material is None:
            material = bpy.data.materials.new(name)
            material.use_nodes = True
        rgb = palette_module.role_rgb(palette, role)
        material["role"] = role
        material.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
        shader = material.node_tree.nodes.get("Principled BSDF")
        if shader is not None:
            shader.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            shader.inputs["Roughness"].default_value = palette_module.role_roughness(palette, role)
            shader.inputs["Metallic"].default_value = 0.0
            lit = role == "emissive"
            shader.inputs["Emission Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            shader.inputs["Emission Strength"].default_value = EMISSION_PREVIEW_STRENGTH if lit else 0.0
        materials.append(material)
    return materials


class Builder:
    """Collects every sub-volume in one bmesh and delivers one object.

    style is a palette dict or a design system dict; a bare palette borrows the
    chunky-cartoon design constants (thickness floor, seams, soot tags).
    """

    def __init__(self, style):
        self.style = style
        self.palette = palette_module.palette_of(style)
        self.design_system = palette_module.design_system_of(style)
        self.bm = bmesh.new()
        # (x, y, z, extent) per volume that soots its surroundings, in build coordinates.
        self.soot_sources = []

    # ---- internals -------------------------------------------------------

    def _index(self, role):
        return palette_module.role_index(role)

    def _is_soot_source(self, role, tags):
        soot_tags = set(self.design_system["soot"]["tags"])
        return bool((set(tags) | {role}) & soot_tags)

    def _merge(self, bm, role, tags=()):
        index = self._index(role)
        for face in bm.faces:
            face.material_index = index
        if self._is_soot_source(role, tags):
            xs = [vert.co.x for vert in bm.verts]
            ys = [vert.co.y for vert in bm.verts]
            zs = [vert.co.z for vert in bm.verts]
            extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) / 2.0
            centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)
            self.soot_sources.append((centre[0], centre[1], centre[2], extent))
        temp = bpy.data.meshes.new("_assetlib_tmp")
        bm.to_mesh(temp)
        bm.free()
        self.bm.from_mesh(temp)
        bpy.data.meshes.remove(temp)

    @staticmethod
    def _bevel(bm, offset, segments):
        if offset <= 0:
            return
        bmesh.ops.bevel(
            bm,
            geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            offset=offset,
            offset_type="OFFSET",
            segments=segments,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )

    @staticmethod
    def _place(bm, matrix):
        if matrix is not None:
            bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)

    @staticmethod
    def _extrude_profile(bm, verts, vector):
        face = bm.faces.new(verts)
        result = bmesh.ops.extrude_face_region(bm, geom=[face])
        moved = [element for element in result["geom"] if isinstance(element, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=moved, vec=vector)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # ---- primary volumes -------------------------------------------------

    def box(self, x0, x1, y0, y1, z0, z1, role, bevel=0.12, segments=2, matrix=None, tags=()):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for vert in bm.verts:
            vert.co.x = x0 + (vert.co.x + 0.5) * (x1 - x0)
            vert.co.y = y0 + (vert.co.y + 0.5) * (y1 - y0)
            vert.co.z = z0 + (vert.co.z + 0.5) * (z1 - z0)
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def prism_z(self, points_xy, z0, z1, role, bevel=0.12, segments=2, matrix=None, tags=()):
        bm = bmesh.new()
        verts = [bm.verts.new((u, v, z0)) for u, v in points_xy]
        self._extrude_profile(bm, verts, (0.0, 0.0, z1 - z0))
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def prism_x(self, points_yz, x0, x1, role, bevel=0.12, segments=2, matrix=None, tags=()):
        bm = bmesh.new()
        verts = [bm.verts.new((x0, u, v)) for u, v in points_yz]
        self._extrude_profile(bm, verts, (x1 - x0, 0.0, 0.0))
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def prism_y(self, points_xz, y0, y1, role, bevel=0.12, segments=2, matrix=None, tags=()):
        bm = bmesh.new()
        verts = [bm.verts.new((u, y0, v)) for u, v in points_xz]
        self._extrude_profile(bm, verts, (0.0, y1 - y0, 0.0))
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def ring(self, radius, thickness, z0, z1, role, sides=16, bevel=0.06, segments=2, matrix=None, tags=()):
        """Annulus extruded along Z: a band, a rim, a wheel tyre."""
        bm = bmesh.new()
        outer = [bm.verts.new((u, v, z0)) for u, v in ngon(radius, sides)]
        inner = [bm.verts.new((u, v, z0)) for u, v in ngon(radius - thickness, sides)]
        for i in range(sides):
            j = (i + 1) % sides
            bm.faces.new((outer[i], outer[j], inner[j], inner[i]))
        result = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        moved = [element for element in result["geom"] if isinstance(element, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=moved, vec=(0.0, 0.0, z1 - z0))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def lathe(self, profile_rz, role, sides=16, bevel=0.10, segments=2, matrix=None, tags=()):
        """Revolve an (r, z) profile around Z. First and last r must be > 0; the caps are filled."""
        bm = bmesh.new()
        verts = [bm.verts.new((r, 0.0, z)) for r, z in profile_rz]
        edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
        bmesh.ops.spin(
            bm,
            geom=verts + edges,
            cent=(0.0, 0.0, 0.0),
            axis=(0.0, 0.0, 1.0),
            dvec=(0.0, 0.0, 0.0),
            angle=2.0 * math.pi,
            steps=sides,
            use_duplicate=False,
            use_merge=True,
        )
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.holes_fill(bm, edges=bm.edges, sides=sides)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    def sweep(self, profile_xz, stations, role, bevel=0.10, segments=2, matrix=None, tags=()):
        """One continuous skin: the XZ profile placed at each station along Y and bridged.

        stations: list of (y, scale_x, scale_z, dx, dz). Steps between stations, not a
        smooth taper, are what makes a length read as built.
        """
        bm = bmesh.new()
        rings = []
        for y, scale_x, scale_z, dx, dz in stations:
            rings.append([bm.verts.new((u * scale_x + dx, y, v * scale_z + dz)) for u, v in profile_xz])
        count = len(profile_xz)
        for a, b in zip(rings, rings[1:]):
            for i in range(count):
                j = (i + 1) % count
                bm.faces.new((a[i], a[j], b[j], b[i]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    # ---- from a SPEC dict (schema in spec.py) -----------------------------

    def volume(self, volume):
        """One VOLUME dict into the bmesh; kinds not built yet raise."""
        kind = volume["kind"]
        role = volume["role"]
        at = volume.get("at")
        # bevel and segments only when the SPEC states them, so each kind keeps its own
        # default (a tube has none: a bevel on its ring edges degenerates).
        shared = {
            "matrix": mathutils.Matrix.Translation(at) if at is not None else None,
            "tags": tuple(volume.get("tags", ())),
        }
        for key in ("bevel", "segments"):
            if key in volume:
                shared[key] = volume[key]
        if kind == "box":
            self.box(*volume["bounds"], role, **shared)
        elif kind == "lathe":
            self.lathe(volume["profile"], role, sides=volume.get("sides", 16), **shared)
        elif kind == "ring":
            z0, z1 = volume["z"]
            self.ring(volume["radius"], volume["thickness"], z0, z1, role, sides=volume.get("sides", 16), **shared)
        elif kind in ("prism_x", "prism_y", "prism_z"):
            low, high = volume[kind[-1]]
            getattr(self, kind)(volume["points"], low, high, role, **shared)
        elif kind == "sweep":
            self.sweep(volume["profile"], volume["stations"], role, **shared)
        elif kind == "tube":
            self.tube(volume["points"], volume["radius"], role, sides=volume.get("sides", 8), **shared)
        else:
            raise ValueError(f"unknown volume kind {kind!r}")

    def cut(self, cut):
        """One CUT dict into the merged skin; kinds not built yet raise."""
        kind = cut["kind"]
        predicate = spec_module.face_predicate(cut["face"])
        role = cut.get("role")
        if kind == "groove":
            self.groove(predicate, cut["inset"], cut["depth"], role)
        elif kind == "inset_panel":
            self.inset_panel(predicate, cut["inset"], cut["depth"], role)
        elif kind == "plate":
            self.plate(cut["face"], cut["inset"], cut["thickness"], role, region=cut.get("region"))
        elif kind == "vent_slots":
            self.vent_slots(cut["face"], cut["count"], cut["along"], cut["width"], cut["depth"], role, span=cut.get("span"))
        elif kind == "grille":
            self.grille(cut["face"], cut["pitch"], cut["bar"], cut["depth"], role)
        else:
            raise ValueError(f"unknown cut kind {kind!r}")

    def tube(self, points_xyz, radius, role, sides=8, bevel=0.0, segments=1, matrix=None, tags=()):
        """A round pipe along a real 3D polyline: mitred at every corner, capped at both ends.

        The ring frame is parallel-transported from segment to segment so the bridge
        never twists; at a corner the ring is stretched by 1/cos(half angle) along the
        bend so the pipe keeps its radius through the elbow. No bevel by default: a
        round profile carries its own rounding and a bevel on the ring edges degenerates.
        """
        minimum = self.design_system["thickness_min"]
        if 2.0 * radius < minimum:
            raise ValueError(f"tube diameter {2.0 * radius:.2f} is under thickness_min {minimum}")
        points = [mathutils.Vector(point) for point in points_xyz]
        if len(points) < 2:
            raise ValueError("tube needs at least two points")
        directions = [(b - a).normalized() for a, b in zip(points, points[1:])]
        reference = mathutils.Vector((0.0, 0.0, 1.0))
        if abs(directions[0].dot(reference)) > 0.9:
            reference = mathutils.Vector((1.0, 0.0, 0.0))
        side = directions[0].cross(reference).normalized()
        previous_tangent = directions[0]
        bm = bmesh.new()
        rings = []
        for index, point in enumerate(points):
            incoming = directions[max(index - 1, 0)]
            outgoing = directions[min(index, len(directions) - 1)]
            tangent = incoming + outgoing
            tangent = tangent.normalized() if tangent.length > 1e-6 else outgoing
            side = previous_tangent.rotation_difference(tangent) @ side
            side = (side - tangent * side.dot(tangent)).normalized()
            up = tangent.cross(side).normalized()
            previous_tangent = tangent
            bend = outgoing - incoming
            stretch = 1.0 / max(tangent.dot(outgoing), 0.5) - 1.0
            if bend.length > 1e-6:
                bend.normalize()
            ring = []
            for u, v in ngon(radius, sides):
                offset = side * u + up * v
                if bend.length > 1e-6:
                    offset = offset + bend * (offset.dot(bend) * stretch)
                ring.append(bm.verts.new(point + offset))
            rings.append(ring)
        for a, b in zip(rings, rings[1:]):
            for i in range(sides):
                j = (i + 1) % sides
                bm.faces.new((a[i], a[j], b[j], b[i]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        self._bevel(bm, bevel, segments)
        self._place(bm, matrix)
        self._merge(bm, role, tags)

    # ---- secondary detail: cut into the skin ------------------------------

    def _select(self, predicate):
        self.bm.faces.ensure_lookup_table()
        self.bm.normal_update()
        faces = [face for face in self.bm.faces if predicate(face)]
        if not faces:
            raise ValueError("predicate selected no faces; nothing to cut")
        return faces

    def _slice(self, predicate, axis, positions):
        """Split the faces the predicate selects by planes normal to `axis` at every position.

        Only the selected faces are cut; a neighbour merely gains a collinear vertex on
        the shared edge, which flat shading and the GLB exporter both accept.
        """
        index = spec_module.AXIS_INDEX[axis]
        plane_no = [0.0, 0.0, 0.0]
        plane_no[index] = 1.0
        for position in positions:
            faces = self._select(predicate)
            edges = list({edge for face in faces for edge in face.edges})
            verts = list({vert for face in faces for vert in face.verts})
            plane_co = [0.0, 0.0, 0.0]
            plane_co[index] = position
            bmesh.ops.bisect_plane(self.bm, geom=faces + edges + verts, dist=1e-5, plane_co=plane_co,
                                   plane_no=plane_no, use_snap_center=False, clear_outer=False, clear_inner=False)
        return self._select(predicate)

    def _sink(self, faces, depth):
        """Push faces straight into the skin with vertical walls (extrude, drop, delete the lid)."""
        normal = mathutils.Vector((0.0, 0.0, 0.0))
        for face in faces:
            normal += face.normal
        normal.normalize()
        result = bmesh.ops.extrude_face_region(self.bm, geom=faces)
        moved = [element for element in result["geom"] if isinstance(element, bmesh.types.BMVert)]
        bmesh.ops.translate(self.bm, verts=moved, vec=-normal * depth)
        bmesh.ops.delete(self.bm, geom=faces, context="FACES_ONLY")
        self.bm.normal_update()
        return [element for element in result["geom"] if isinstance(element, bmesh.types.BMFace)]

    @staticmethod
    def _extent(faces, axis):
        index = spec_module.AXIS_INDEX[axis]
        values = [vert.co[index] for face in faces for vert in face.verts]
        return min(values), max(values)

    def _recess(self, predicate, inset, depth, role):
        """Inset the faces the predicate selects, then move them along their own normal.

        Vertices go through a set so a vertex shared by two selected faces moves once.
        Negative depth sinks (groove), positive depth raises (panel). Applies to the
        merged bmesh, so call it after the volumes it should cut into. Returns the
        inner faces (inset_region keeps the input faces as the shrunk inner faces).
        """
        faces = self._select(predicate)
        result = bmesh.ops.inset_region(
            self.bm, faces=faces, thickness=inset, depth=0.0,
            use_even_offset=True, use_boundary=True,
        )
        moved = {vert for face in faces for vert in face.verts}
        for vert in moved:
            normal = sum((face.normal for face in vert.link_faces if face in faces), start=vert.co * 0.0)
            if normal.length > 0.0:
                vert.co += normal.normalized() * depth
        if role is not None:
            index = self._index(role)
            for face in faces:
                face.material_index = index
        return faces

    def groove(self, predicate, inset=0.08, depth=0.06, role=None):
        """Sunken band or seam; on a chunky prop keep inset >= 0.08 so it reads at 40 studs."""
        return self._recess(predicate, inset, -abs(depth), role)

    def inset_panel(self, predicate, inset=0.10, depth=0.05, role=None):
        """Raised plate; the one legitimate way to put a second surface on a face."""
        return self._recess(predicate, inset, abs(depth), role)

    def _stamp(self, faces, role):
        if role is not None:
            index = self._index(role)
            for face in faces:
                face.material_index = index

    def plate(self, face, inset, thickness, role=None, region=None):
        """A hatch or label: a sunk seam ring, then a raised plate inside it, on one face.

        face is a FACE selector dict (spec.py). region [u0, u1, v0, v1] in the face's
        in-plane axes first slices the face so the plate covers only that rectangle.
        """
        seam = self.design_system["seam"]
        if inset < seam["min_inset"]:
            raise ValueError(f"plate inset {inset} is under seam.min_inset {seam['min_inset']}")
        if thickness < seam["min_depth"]:
            raise ValueError(f"plate thickness {thickness} is under seam.min_depth {seam['min_depth']}")
        selected = spec_module.face_predicate(face)
        predicate = selected
        if region is not None:
            axis_u, axis_v = spec_module.in_plane_axes(face)
            self._slice(selected, axis_u, region[0:2])
            self._slice(selected, axis_v, region[2:4])
            index_u, index_v = spec_module.AXIS_INDEX[axis_u], spec_module.AXIS_INDEX[axis_v]

            def inside(candidate):
                centre = candidate.calc_center_median()
                return (selected(candidate) and region[0] <= centre[index_u] <= region[1]
                        and region[2] <= centre[index_v] <= region[3])

            predicate = inside
        inner = self._recess(predicate, inset, -seam["min_depth"], role)
        chosen = set(inner)
        self._recess(lambda candidate: candidate in chosen, seam["plate_width"], seam["min_depth"] + thickness, role)
        return inner

    def vent_slots(self, face, count, along, width, depth, role=None, span=None):
        """Parallel slots cut into one axis-aligned face: `count` slots running along `along`,
        stacked evenly across the other in-plane axis (or across `span` [lo, hi])."""
        seam = self.design_system["seam"]
        if width < seam["min_inset"]:
            raise ValueError(f"slot width {width} is under seam.min_inset {seam['min_inset']}")
        axis_u, axis_v = spec_module.in_plane_axes(face)
        if along not in (axis_u, axis_v):
            raise ValueError(f"slots along {along!r} do not lie in a face with normal {face['normal']!r}")
        across = axis_v if along == axis_u else axis_u
        predicate = spec_module.face_predicate(face)
        faces = self._select(predicate)
        low, high = span if span is not None else self._extent(faces, across)
        if span is None:
            low, high = low + seam["min_inset"], high - seam["min_inset"]
        pitch = (high - low) / (count + 1)
        if pitch - width < seam["min_inset"]:
            raise ValueError(f"{count} slots of width {width} leave bars under seam.min_inset {seam['min_inset']}")
        centres = [low + pitch * (i + 1) for i in range(count)]
        positions = [c + offset for c in centres for offset in (-width / 2.0, width / 2.0)]
        sliced = self._slice(predicate, across, positions)
        index = spec_module.AXIS_INDEX[across]
        strips = [candidate for candidate in sliced
                  if any(abs(candidate.calc_center_median()[index] - c) < width / 2.0 for c in centres)]
        if not strips:
            raise ValueError("vent_slots: no strip fell inside the slots")
        sunk = self._sink(strips, depth)
        self._stamp(sunk, role)
        return sunk

    def grille(self, face, pitch, bar, depth, role=None):
        """A grid of square cells sunk into one axis-aligned face; the bars between them stay."""
        seam = self.design_system["seam"]
        if bar < seam["min_inset"] or pitch - bar < seam["min_inset"]:
            raise ValueError(f"grille pitch {pitch} and bar {bar} leave a cell or bar under seam.min_inset {seam['min_inset']}")
        predicate = spec_module.face_predicate(face)
        faces = self._select(predicate)
        axes = spec_module.in_plane_axes(face)
        bar_centres = {}
        for axis in axes:
            low, high = self._extent(faces, axis)
            middle = (low + high) / 2.0
            centres = [middle]
            step = 1
            while middle + step * pitch < high - bar:
                centres += [middle + step * pitch, middle - step * pitch]
                step += 1
            bar_centres[axis] = centres
            positions = [c + offset for c in centres for offset in (-bar / 2.0, bar / 2.0)
                         if low + 1e-6 < c + offset < high - 1e-6]
            faces = self._slice(predicate, axis, positions)

        def on_bar(candidate):
            centre = candidate.calc_center_median()
            return any(abs(centre[spec_module.AXIS_INDEX[axis]] - c) < bar / 2.0
                       for axis in axes for c in bar_centres[axis])

        cells = [candidate for candidate in faces if not on_bar(candidate)]
        if not cells:
            raise ValueError("grille: pitch leaves no cell on this face")
        sunk = self._sink(cells, depth)
        self._stamp(sunk, role)
        return sunk

    def studs(self, points_xyz, axis, radius, height, role, sides=8, tags=()):
        """A few placed rivets or knobs along one axis ('x', 'y' or 'z'); count them, never scatter."""
        for x, y, z in points_xyz:
            profile = ngon(radius, sides)
            if axis == "z":
                self.prism_z([(x + u, y + v) for u, v in profile], z, z + height, role, bevel=radius * 0.3, segments=1, tags=tags)
            elif axis == "y":
                self.prism_y([(x + u, z + v) for u, v in profile], y, y + height, role, bevel=radius * 0.3, segments=1, tags=tags)
            elif axis == "x":
                self.prism_x([(y + u, z + v) for u, v in profile], x, x + height, role, bevel=radius * 0.3, segments=1, tags=tags)
            else:
                raise ValueError("axis must be 'x', 'y' or 'z'")

    # ---- delivery ----------------------------------------------------------

    def finish(self, name, center_xy=True, base_at_zero=True):
        """One object, flat shaded, origin at the centre of the base, materials in role order."""
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        mesh = bpy.data.meshes.new(name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        obj = bpy.data.objects.new(name, mesh)
        for material in ensure_materials(self.palette):
            mesh.materials.append(material)
        bpy.context.scene.collection.objects.link(obj)
        base_x, base_y, base_z = base_centre(mesh)
        dx = base_x if center_xy else 0.0
        dy = base_y if center_xy else 0.0
        dz = base_z if base_at_zero else 0.0
        for vert in mesh.vertices:
            vert.co.x -= dx
            vert.co.y -= dy
            vert.co.z -= dz
        for polygon in mesh.polygons:
            polygon.use_smooth = False
        mesh.update()
        # Soot sources travel with the object so bake_asset needs no Builder:
        # flat [x, y, z, extent, ...] in the final mesh coordinates.
        obj["soot_sources"] = [
            round(value, 4)
            for x, y, z, extent in self.soot_sources
            for value in (x - dx, y - dy, z - dz, extent)
        ]
        return obj


def build(spec, style):
    """One finished object from a SPEC dict: volumes in order, then cuts, then stud groups."""
    spec_module.validate(spec)
    builder = Builder(style)
    for volume in spec["volumes"]:
        builder.volume(volume)
    for cut in spec.get("cuts", []):
        builder.cut(cut)
    for group in spec.get("studs", []):
        builder.studs(group["points"], group["axis"], group["radius"], group["height"], group["role"],
                      sides=group.get("sides", 8), tags=tuple(group.get("tags", ())))
    return builder.finish(spec["name"])


def base_centre(mesh):
    """(x, y, z) of the centre of the bounding box base, in mesh coordinates."""
    xs = [vert.co.x for vert in mesh.vertices]
    ys = [vert.co.y for vert in mesh.vertices]
    zs = [vert.co.z for vert in mesh.vertices]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, min(zs))


def stats(obj):
    mesh = obj.data
    used = set()
    for edge in mesh.edges:
        used.update(edge.vertices)
    loose = len(mesh.vertices) - len(used)
    base = base_centre(mesh)
    return {
        "triangles": sum(len(polygon.vertices) - 2 for polygon in mesh.polygons),
        "dimensions": tuple(round(d, 3) for d in obj.dimensions),
        "vertices": len(mesh.vertices),
        "loose_vertices": loose,
        "materials": [material.name for material in mesh.materials],
        "has_uv": len(mesh.uv_layers) > 0,
        "origin_at_base": all(abs(c) < 1e-3 for c in base),
    }


def export_glb(obj, path):
    """One GLB with only this object, modifiers applied, Y up for the Roblox importer."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Roblox reads the NormalMap only on meshes that carry tangents, and Blender can
    # compute tangents only on triangles and quads: the lathe caps and cut faces are
    # n-gons, so the export applies a temporary Triangulate modifier (export_apply
    # bakes modifiers into the file, the object in the .blend keeps its n-gons).
    triangulate = obj.modifiers.new("_export_triangulate", "TRIANGULATE")
    try:
        bpy.ops.export_scene.gltf(
            filepath=path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_tangents=True,
        )
    finally:
        obj.modifiers.remove(triangulate)
    return path
