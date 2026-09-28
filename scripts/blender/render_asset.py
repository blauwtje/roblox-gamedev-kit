"""Preview renders for one hero asset: a fixed rig of named angles, Workbench or Cycles.

The rig is fixed so the modeller, the prop judge and the owner always compare the
same five views. Every shot is checked for size: an empty render is a failure,
not a preview (two empty renders in a row went unnoticed on 2026-08-26).
"""

import os

import bpy
import mathutils

FLOOR_NAME = "PreviewFloor"
CAMERA_NAME = "PreviewCamera"
MIN_PNG_BYTES = 10_000

# name -> (direction from target to camera, distance factor on max dimension)
RIG = {
    "front": ((0.0, -1.0, 0.35), 2.3),
    "three-quarter": ((1.0, -1.0, 0.45), 2.3),
    "side": ((1.0, 0.0, 0.30), 2.3),
    "top": ((0.0, -0.01, 1.0), 2.3),
    # The read-distance shot: what a player sees from 40 studs. Whatever does
    # not survive this frame is not detail, it is noise.
    "read-40": ((1.0, -1.0, 0.35), 6.0),
}


class RenderError(RuntimeError):
    pass


def _camera():
    scene = bpy.context.scene
    camera = bpy.data.objects.get(CAMERA_NAME)
    if camera is None:
        camera = bpy.data.objects.new(CAMERA_NAME, bpy.data.cameras.new(CAMERA_NAME))
        scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def _aim(obj, target):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup(background=(0.10, 0.11, 0.13), floor=True):
    """Workbench with material colours and cavity: fast, and honest about silhouette."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_object_outline = False
    scene.display.render_aa = "16"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = background
    camera = _camera()

    plane = bpy.data.objects.get(FLOOR_NAME)
    if floor and plane is None:
        import bmesh

        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=80.0)
        mesh = bpy.data.meshes.new(FLOOR_NAME)
        bm.to_mesh(mesh)
        bm.free()
        material = bpy.data.materials.new("PreviewFloorMat")
        material.use_nodes = True
        material.diffuse_color = (0.26, 0.27, 0.29, 1.0)
        shader = material.node_tree.nodes.get("Principled BSDF")
        if shader is not None:
            shader.inputs["Base Color"].default_value = (0.26, 0.27, 0.29, 1.0)
        mesh.materials.append(material)
        plane = bpy.data.objects.new(FLOOR_NAME, mesh)
        scene.collection.objects.link(plane)
    if plane is not None:
        plane.hide_render = not floor
        plane.location = (0.0, 0.0, -0.001)
    return camera


def cycles_setup(obj, samples=64, world_strength=0.35, background=(0.05, 0.055, 0.07), light_scale=1.0):
    """Three-point lighting around obj, scaled on its size: the 'look' shot with shadows."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Base Contrast"

    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    node = scene.world.node_tree.nodes.get("Background")
    if node is not None:
        node.inputs[0].default_value = (background[0], background[1], background[2], 1.0)
        node.inputs[1].default_value = world_strength

    for old in [candidate for candidate in bpy.data.objects if candidate.type == "LIGHT"]:
        bpy.data.objects.remove(old, do_unlink=True)

    span = max(obj.dimensions)
    centre = (0.0, 0.0, obj.dimensions.z * 0.5)
    lights = (
        ("Key", (span * 0.7, span * 1.1, span * 1.5), (1.0, 0.88, 0.72), 60.0, span * 0.9),
        ("Fill", (-span * 1.3, span * 0.8, span * 0.5), (0.72, 0.80, 0.95), 18.0, span * 1.2),
        ("Rim", (-span * 0.4, -span * 1.4, span * 1.1), (0.95, 0.95, 1.0), 30.0, span * 0.6),
    )
    for name, offset, colour, watts_per_unit, size in lights:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = watts_per_unit * span * span * light_scale
        data.size = size
        data.color = colour
        lamp = bpy.data.objects.new(name, data)
        lamp.location = (centre[0] + offset[0], centre[1] + offset[1], centre[2] + offset[2])
        scene.collection.objects.link(lamp)
        _aim(lamp, centre)
    return _camera()


def solo(name):
    """Only this object plus the floor in frame; other assets stay in the file.

    Returns {object name: previous hide_render} so the caller can restore it.
    """
    previous = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            previous[obj.name] = obj.hide_render
            obj.hide_render = obj.name not in (name, FLOOR_NAME)
    return previous


def unsolo(previous):
    """Puts back the hide_render values that solo() replaced."""
    for name, hidden in previous.items():
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.hide_render = hidden


def shot(obj, out_dir, name, direction, distance_factor=2.3, width=1024, height=1024):
    scene = bpy.context.scene
    camera = _camera()
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    target = mathutils.Vector((0.0, 0.0, obj.dimensions.z * 0.45))
    away = mathutils.Vector(direction).normalized()
    distance = max(obj.dimensions) * distance_factor
    camera.location = target + away * distance
    _aim(camera, target)
    # Blender's default clip_end is 100 m; the read-40 shot on a large prop passes it.
    camera.data.clip_end = max(100.0, distance * 4.0)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name if name.endswith(".png") else name + ".png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size < MIN_PNG_BYTES:
        raise RenderError(f"{path}: {size} bytes, empty render")
    return path


def render_rig(obj, out_dir, angles=None, width=1024, height=1024):
    """All named rig shots of one object; returns {name: path}. Raises on an empty frame."""
    previous = solo(obj.name)
    paths = {}
    try:
        for name in angles or RIG.keys():
            direction, distance_factor = RIG[name]
            paths[name] = shot(obj, out_dir, name, direction, distance_factor, width, height)
    finally:
        unsolo(previous)
    return paths


def render_look(obj, out_dir, name="look", angle="three-quarter", samples=64, width=1024, height=1024,
                world_strength=0.35, light_scale=1.0):
    """One Cycles shot of one object with the three-point rig; other meshes (including a
    startup Cube) stay out of frame exactly as in render_rig."""
    previous = solo(obj.name)
    try:
        cycles_setup(obj, samples=samples, world_strength=world_strength, light_scale=light_scale)
        direction, distance_factor = RIG[angle]
        return shot(obj, out_dir, name, direction, distance_factor, width, height)
    finally:
        unsolo(previous)
