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


# Define the URL for the Figma API
FIGMA_API_URL = "https://api.figma.com/v1"

#api_key = REDACTED
headers = {"X-Figma-Token": api_key, }
# SHADELESS or EMISSION
SHADER_OPTION = "EMISSION"

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
    bl_category = 'Tools'

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

            col.operator("figma.import_nodes", text="Import")

        # if context.scene.figma_nodes:


class FigmaRetrieveProjectsOperator(bpy.types.Operator):
    bl_idname = "figma.retrieve_projects"
    bl_label = "Retrieve Projects"
    bl_options = {'REGISTER'}

    def execute(self, context):
        team_id = context.scene.figma_team_id
        # Send a GET request to retrieve projects
        response = requests.get(
            f"{FIGMA_API_URL}/teams/{team_id}/projects", headers=headers)

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
            f"{FIGMA_API_URL}/projects/{selected_project.key}/files", headers=headers)
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
            children = children + \
                list(filter(lambda x: x['type'] ==
                     "GROUP", node.get("children", {})))
        return children

    def execute(self, context):
        items = get_figma_files(self, context)
        file = items[int(context.scene.figma_selected_file)][1]
        selected_file = context.scene.figma_files[file]

        response = requests.get(
            f"{FIGMA_API_URL}/files/{selected_file.key}", headers=headers)
        if response.status_code == 200:
            pages = response.json().get("document", {}).get("children", [])
            context.scene.figma_pages.clear()
            children_to_export = []
            for page in pages:
                page_item = context.scene.figma_pages.add()
                page_item.name = page['name']
                page_item.key = page['id']

                looped_groups = []
                new_child_groups = list(
                    filter(lambda x: x['type'] == "GROUP", page.get("children", {})))
                while new_child_groups:
                    looped_groups = looped_groups + new_child_groups
                    new_child_groups = self.get_child_groups(new_child_groups)

                children_to_export = children_to_export + \
                    list(filter(lambda x: x['name'][0] == "_", looped_groups))

                self.report(
                    {'INFO'}, f"Exportable group nodes retrieved from {page['name']}: {', '.join([group['name'] for group in children_to_export])}")
        else:
            self.report(
                {'ERROR'}, f"Failed to retrieve nodes. Status code: {response.status_code}")

        return {'FINISHED'}


class FigmaImportNodesOperator(bpy.types.Operator):
    bl_idname = "figma.import_nodes"
    bl_label = "Import Nodes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        print("figma balls")
        return {'FINISHED'}


class FigmaItem(bpy.types.PropertyGroup):
    key: bpy.props.StringProperty(name="Figma ID")
    name: bpy.props.StringProperty(name="Figma Name")
    parent: bpy.props.StringProperty(name="Parent Node")
    selected: bpy.props.BoolProperty(name="Selected", default=False)


class FigmaUnregisterOperator(bpy.types.Operator):
    bl_idname = "figma.unregister"
    bl_label = "Unregister"
    bl_options = {'REGISTER'}

    def execute(self, context):
        unregister()


classes = (
    FigmaItem,
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
    # Ensure the "Images As Planes" add-on is enabled
    # bpy.ops.preferences.addon_enable(module="io_import_images_as_planes")

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


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
