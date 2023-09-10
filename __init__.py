# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from io import BytesIO
import os
import requests
import bpy

bl_info = {
    "name": "Import Figma",
    "description": "imports figma files into blender",
    "author": "Nick Miles <milesnp@msn.com>",
    "version": (1, 0, 0),
    "blender": (2, 9, 0),
    "location": "3D View > Sidebar > Import",
    "warning": "Addon will freeze on first add as it downloads dependencies.",
    "category": "Import-Export"
}

# SHADELESS or EMISSION
SHADER_OPTION = "EMISSION"
# import scale divisor
PX_TO_METER = 121.92  # 1200 DPI I think? Still ends up huge
# Definite path to image folder if desired, otherwise the location of the\
# .blend file will be used:
#IMAGE_DIR = r"C:/temp/figma-images"
IMAGE_DIR = None
API_KEY = "YOUR_API_KEY"

FIGMA_API_URL = "https://api.figma.com/v1"
HEADERS = {"X-Figma-Token": API_KEY, }

# authenticate with Figma (TODO if I want to use oauth2 and make this a legit project)
# (user provides team ID, retrieve all team projects
# user selects project, retrieve all files
# user selects files, retrieve all nodes and display as a folder structure?
# user selects nodes with checkboxes and a preview? OR user has already prefixed all target nodes with underscores.
# collect position data and export as png
# import all exported images as planes (with shadeless material)
# transform each plane to its position and scale

# bpy.ops.import_image.to_plane(shader=SHADER_OPTION,files=[{"name":r"C:\Users\miles\Downloads\841f34aa-144b-4015-bdfa-0cf1acd92b77.png"}])


class FigmaAddonPanel(bpy.types.Panel):
    bl_label = "Figma Integration"
    bl_idname = "_PT_FigmaAddonPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Import'

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="This tool will only import")
        col.label(text="groups which are prefixed")
        col.label(text="with '_'.")
        col.operator("figma.unregister", text="Unregister")
        col.label(text="Figma Team ID:")
        col.prop(context.scene, "figma_team_id")

        col.operator("figma.retrieve_projects", text="Retrieve Projects")

        if context.scene.figma_projects:
            col.label(text="Select a Project:")
            col.prop(context.scene, "figma_selected_project", text="")

            col.operator("figma.retrieve_files", text="Get Files")

        if context.scene.figma_files:
            col.label(text="Select a File:")
            col.prop(context.scene, "figma_selected_file", text="")

            col.operator("figma.retrieve_nodes", text="Load File")

        if context.scene.figma_pages:
            col.label(text="Select a Page:")
            col.prop(context.scene, "figma_selected_page", text="")

            col.prop(context.scene, "figma_scale", text="Scale")

            col.operator("figma.import_nodes", text="Import")


class FigmaRetrieveProjectsOperator(bpy.types.Operator):
    bl_idname = "figma.retrieve_projects"
    bl_label = "Retrieve Projects"
    bl_options = {'REGISTER'}

    def execute(self, context):
        team_id = context.scene.figma_team_id
        # Send a GET request to retrieve projects
        response = requests.get(
            f"{FIGMA_API_URL}/teams/{team_id}/projects", headers=HEADERS)

        if response.status_code == 200:
            projects = response.json().get("projects", [])
            context.scene.figma_projects.clear()

            for project in projects:
                projectitem = context.scene.figma_projects.add()
                projectitem.name = project['name']
                projectitem.key = project['id']

            self.report(
                {'INFO'}, f"Projects retrieved: {', '.join([project['name'] for project in projects])}")
        else:
            self.report(
                {'ERROR'}, f"Failed to retrieve projects. Status code: {response.status_code}")

        return {'FINISHED'}


class FigmaRetrieveFilesOperator(bpy.types.Operator):
    bl_idname = "figma.retrieve_files"
    bl_label = "Get Files"
    bl_options = {'REGISTER'}

    def execute(self, context):
        items = get_figma_projects(self, context)
        project = items[int(context.scene.figma_selected_project)][1]
        selected_project = context.scene.figma_projects[project]

        response = requests.get(
            f"{FIGMA_API_URL}/projects/{selected_project.key}/files", headers=HEADERS)
        if response.status_code == 200:
            self.report({'INFO'}, str(response.content))
            files = response.json().get("files", [])
            context.scene.figma_files.clear()
            for file in files:
                file_item = context.scene.figma_files.add()
                file_item.name = file['name']
                file_item.key = file['key']

            self.report(
                {'INFO'}, f"Files retrieved: {', '.join([file['name'] for file in files])}")
        else:
            self.report(
                {'ERROR'}, f"Failed to retrieve files. Status code: {response.status_code}")

        return {'FINISHED'}


class FigmaRetrieveNodesOperator(bpy.types.Operator):
    bl_idname = "figma.retrieve_nodes"
    bl_label = "Load File"
    bl_options = {'REGISTER'}

    def get_child_groups(self, groups):
        children = []
        for node in groups:
            children = children + node.get("children", [])
        return children

    def execute(self, context):
        items = get_figma_files(self, context)
        file = items[int(context.scene.figma_selected_file)][1]
        selected_file = context.scene.figma_files[file]

        response = requests.get(
            f"{FIGMA_API_URL}/files/{selected_file.key}", headers=HEADERS)
        if response.status_code == 200:
            pages = response.json().get("document", {}).get("children", [])
            context.scene.figma_pages.clear()
            context.scene.figma_nodes.clear()
            children_to_export = []
            for page in pages:
                page_item = context.scene.figma_pages.add()
                page_item.name = page['name']
                page_item.key = page['id']

                looped_groups = []
                new_child_groups = page.get("children", {})
                while new_child_groups:
                    looped_groups = looped_groups + new_child_groups
                    new_child_groups = self.get_child_groups(new_child_groups)

                children_to_export = children_to_export + \
                    list(filter(lambda x: x['name'][0] == "_", looped_groups))
                children_to_export = children_to_export + \
                    list(filter(lambda x: x['name'][0] == "!", looped_groups))

                self.report(
                    {'INFO'}, f"Exportable nodes retrieved from {page['name']}: {', '.join([group['name'] for group in children_to_export])}")

                for child in children_to_export:
                    child_item = context.scene.figma_nodes.add()
                    child_item.name = child['name']
                    child_item.key = child['id']
                    bounding_box = child['absoluteBoundingBox']
                    child_item.x_bottom_left = bounding_box['x'] / PX_TO_METER
                    child_item.y_bottom_left = -1 * \
                        bounding_box['y'] / PX_TO_METER
                    child_item.height = bounding_box['height'] / PX_TO_METER
                    child_item.width = bounding_box['width'] / PX_TO_METER
                    child_item.use_absolute_bb = child['name'][0] == "!"
                    child_item.parent = page['id']
        else:
            self.report(
                {'ERROR'}, f"Failed to retrieve nodes. Status code: {response.status_code}")

        return {'FINISHED'}


class FigmaImportNodesOperator(bpy.types.Operator):
    bl_idname = "figma.import_nodes"
    bl_label = "Import Nodes"
    bl_options = {'REGISTER', 'UNDO'}

    def set_image_dir(self):
        imagedir = IMAGE_DIR
        if not imagedir:
            blenddir = bpy.path.abspath('//')
            if not blenddir:
                self.report({'ERROR'}, "Save this file as a .blend first!")
                return {'CANCELLED'}
            imagedir = os.path.join(blenddir, "figma_images")
        return imagedir

    def get_image_name(self, node):
        return f"{node.key}.png".replace(":", "_")

    def request_images(self, context, nodes_to_import, use_absolute):
        bb_string = "true" if use_absolute else "false"
        imagedir = self.set_image_dir()
        os.makedirs(imagedir, exist_ok=True)

        ids_to_request = ','.join(group['key'] for group in nodes_to_import)
        print(ids_to_request)
        items = get_figma_files(self, context)
        file = items[int(context.scene.figma_selected_file)][1]
        selected_file = context.scene.figma_files[file]

        response = requests.get(
            f"{FIGMA_API_URL}/images/{selected_file.key}?ids={ids_to_request}&use_absolute_bounds={bb_string}", headers=HEADERS)
        if response.status_code == 200:
            images = response.json().get("images", {})
            for node in nodes_to_import:
                image_response = requests.get(images[node.key])
                if response.status_code == 200:
                    with open(os.path.join(imagedir, self.get_image_name(node)), 'wb') as img:
                        img.write(image_response.content)
                else:
                    self.report(
                        {'ERROR'}, f"Failed to download image. Status code: {response.status_code}")
        else:
            self.report(
                {'ERROR'}, f"Failed to retrieve image URLs. Status code: {response.status_code}. {response.json().get('err')}")

        #image_path = os.path.join(imagedir,f"{node.key}.png")

    def import_plane(self, context, node):
        self.report(
            {"INFO"}, f"Importing {node.name} to {node.x_bottom_left}, {node.y_bottom_left} with {node.height} and {node.width}. abs: {str(node.use_absolute_bb)}")
        imagedir = self.set_image_dir()
        image_path = os.path.join(imagedir, self.get_image_name(node))

        # Import the image as a plane
        bpy.ops.import_image.to_plane(
            shader=SHADER_OPTION,
            align_axis="Z+",
            files=[{"name": image_path}],
            directory="",
            relative=False,
        )

        height = node.height * context.scene.figma_scale
        width = node.width * context.scene.figma_scale
        x_bottom_left = node.x_bottom_left * context.scene.figma_scale
        y_bottom_left = node.y_bottom_left * context.scene.figma_scale

        # Get the last imported object (the plane)
        plane = bpy.context.selected_objects[0]

        plane.scale.x = 1
        plane.scale.y = 1

        # Calculate the scale factors to fit the bounding box
        scale_x = width / plane.dimensions.x
        scale_y = height / plane.dimensions.y
        plane.scale.x = scale_x
        plane.scale.y = scale_y

        # Set the position of the plane based on the bottom-left coordinates
        plane.location.x = x_bottom_left + (width / 2.0)
        plane.location.y = y_bottom_left - (height / 2.0)

        plane.name = node.name

    def execute(self, context):
        # Ensure the "Images As Planes" add-on is enabled
        bpy.ops.preferences.addon_enable(module="io_import_images_as_planes")

        pages = get_figma_pages(self, context)
        page = pages[int(context.scene.figma_selected_page)][1]
        selected_file = context.scene.figma_pages[page]
        nodes_absolute = list(
            filter(lambda x: x.use_absolute_bb, context.scene.figma_nodes))
        nodes_normal = list(
            filter(lambda x: not x.use_absolute_bb, context.scene.figma_nodes))
        nodes_to_import_absolute = list(
            filter(lambda x: x.parent == selected_file.key, nodes_absolute))
        nodes_to_import_normal = list(
            filter(lambda x: x.parent == selected_file.key, nodes_normal))
        self.request_images(context, nodes_to_import_absolute, True)
        self.request_images(context, nodes_to_import_normal, False)
        for node in nodes_to_import_absolute:
            self.import_plane(context, node)
        for node in nodes_to_import_normal:
            self.import_plane(context, node)

        return {'FINISHED'}


class FigmaItem(bpy.types.PropertyGroup):
    key: bpy.props.StringProperty(name="Figma ID")
    name: bpy.props.StringProperty(name="Figma Name")


class FigmaNode(FigmaItem):
    parent: bpy.props.StringProperty(name="Parent Page")
    x_bottom_left: bpy.props.FloatProperty(name="Bottom Left X")
    y_bottom_left: bpy.props.FloatProperty(name="Bottom Left Y")
    width: bpy.props.FloatProperty(name="width")
    height: bpy.props.FloatProperty(name="height")
    use_absolute_bb: bpy.props.BoolProperty(name="text?")


class FigmaUnregisterOperator(bpy.types.Operator):
    bl_idname = "figma.unregister"
    bl_label = "Unregister"
    bl_options = {'REGISTER'}

    def execute(self, context):
        unregister()


classes = (
    FigmaItem,
    FigmaNode,
    FigmaAddonPanel,
    FigmaRetrieveFilesOperator,
    FigmaRetrieveProjectsOperator,
    FigmaRetrieveNodesOperator,
    FigmaImportNodesOperator,
    FigmaUnregisterOperator
)


def get_figma_projects(self, context):
    items = []
    for index, project in enumerate(context.scene.figma_projects):
        items.append((str(index), project.name, ""))
    return items


def get_figma_files(self, context):
    items = []
    for index, file in enumerate(context.scene.figma_files):
        items.append((str(index), file.name, ""))
    return items


def get_figma_pages(self, context):
    items = []
    for index, page in enumerate(context.scene.figma_pages):
        items.append((str(index), page.name, ""))
    return items


def register():

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.figma_team_id = bpy.props.StringProperty(
        name="Figma Team ID")
    bpy.types.Scene.figma_projects = bpy.props.CollectionProperty(
        type=FigmaItem)
    bpy.types.Scene.figma_selected_project = bpy.props.EnumProperty(
        items=get_figma_projects, name="Projects")
    bpy.types.Scene.figma_files = bpy.props.CollectionProperty(type=FigmaItem)
    bpy.types.Scene.figma_selected_file = bpy.props.EnumProperty(
        items=get_figma_files, name="Files")
    bpy.types.Scene.figma_pages = bpy.props.CollectionProperty(type=FigmaItem)
    bpy.types.Scene.figma_selected_page = bpy.props.EnumProperty(
        items=get_figma_pages, name="Pages")
    bpy.types.Scene.figma_nodes = bpy.props.CollectionProperty(type=FigmaNode)
    bpy.types.Scene.figma_scale = bpy.props.FloatProperty(
        name="Import Scale", default=1.0)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.figma_team_id
    del bpy.types.Scene.figma_projects
    del bpy.types.Scene.figma_selected_project
    del bpy.types.Scene.figma_files
    del bpy.types.Scene.figma_selected_file
    del bpy.types.Scene.figma_pages
    del bpy.types.Scene.figma_selected_page
    del bpy.types.Scene.figma_nodes
    del bpy.types.Scene.figma_scale

# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
