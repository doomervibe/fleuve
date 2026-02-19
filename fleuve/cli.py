"""Command-line interface for Fleuve."""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


def validate_project_name(name: str) -> bool:
    """Validate that project name is a valid Python identifier."""
    if not name:
        return False
    # Must start with letter or underscore, followed by letters, digits, underscores
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
    return bool(re.match(pattern, name))


def render_template(content: str, **kwargs) -> str:
    """Render a template string by replacing {{variable}} placeholders."""
    result = content
    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def create_project(
    project_name: str,
    target_dir: Optional[str] = None,
    overwrite: bool = False,
    multi_workflow: bool = False,
    initial_workflow: Optional[str] = None,
    include_ui: bool = False,
) -> None:
    """Create a new Fleuve project.

    Args:
        project_name: Name of the project (must be valid Python identifier)
        target_dir: Directory to create project in. Defaults to current directory.
        overwrite: Whether to overwrite existing directory.
        multi_workflow: Whether to create a multi-workflow project structure.
        initial_workflow: Name of the initial workflow (for multi-workflow projects).
        include_ui: Whether to include web UI setup.
    """
    if not validate_project_name(project_name):
        print(f"Error: '{project_name}' is not a valid project name.")
        print(
            "Project name must be a valid Python identifier (letters, digits, underscores, starting with letter/underscore)."
        )
        sys.exit(1)

    # Determine target directory
    if target_dir:
        base_dir = Path(target_dir)
    else:
        base_dir = Path.cwd()

    project_dir = base_dir / project_name

    # Check if directory exists
    if project_dir.exists():
        if not overwrite:
            print(f"Error: Directory '{project_dir}' already exists.")
            print("Use --overwrite to overwrite existing directory.")
            sys.exit(1)
        else:
            print(f"Warning: Overwriting existing directory '{project_dir}'")
            shutil.rmtree(project_dir)

    # Choose template directory
    template_name = "multi_workflow_template" if multi_workflow else "project_template"
    template_dir = Path(__file__).parent / "templates" / template_name
    if not template_dir.exists():
        print(f"Error: Template directory not found: {template_dir}")
        sys.exit(1)

    # Create project directory
    project_dir.mkdir(parents=True, exist_ok=True)

    if not multi_workflow:
        # Single workflow: create package directory
        package_dir = project_dir / project_name
        package_dir.mkdir(exist_ok=True)
    else:
        # Multi-workflow: create workflows directory
        workflows_dir = project_dir / "workflows"
        workflows_dir.mkdir(exist_ok=True)

    # Template variables for project
    project_title = project_name.replace("_", " ").title()

    if multi_workflow:
        # For multi-workflow, determine initial workflow name
        if not initial_workflow:
            initial_workflow = "example_workflow"

        workflow_name = initial_workflow
        workflow_title = workflow_name.replace("_", " ").title()
        workflow_class_name = workflow_title.replace(" ", "")

        template_vars = {
            "project_name": project_name,
            "project_title": project_title,
            "workflow_name": workflow_name,
            "workflow_title": workflow_title,
            "workflow_class_name": workflow_class_name,
        }
    else:
        # Single workflow variables
        workflow_name = f"{project_name.title().replace('_', '')}Workflow"
        state_name = f"{project_name.title().replace('_', '')}State"
        project_title_no_spaces = project_title.replace(" ", "")

        template_vars = {
            "project_name": project_name,
            "project_title": project_title,
            "project_title_no_spaces": project_title_no_spaces,
            "workflow_name": workflow_name,
            "state_name": state_name,
        }

    # Copy and render template files
    for template_file in template_dir.rglob("*"):
        if template_file.is_dir():
            continue

        # Get relative path from template directory
        rel_path = template_file.relative_to(template_dir)

        # Skip __pycache__ and .pyc files
        if "__pycache__" in rel_path.parts or rel_path.suffix == ".pyc":
            continue

        # Determine target path
        if multi_workflow:
            # Multi-workflow structure
            if (
                rel_path.parts[0] == "workflows"
                and "{{workflow_name}}" in rel_path.parts
            ):
                # Replace workflow placeholder with actual workflow name
                new_parts = [workflows_dir.name] + [
                    workflow_name if p == "{{workflow_name}}" else p
                    for p in rel_path.parts[1:]
                ]
                target_path = project_dir / Path(*new_parts)
            else:
                target_path = project_dir / rel_path
        else:
            # Single workflow structure
            if rel_path.parts[0] == "{{project_name}}":
                # Files in the package directory
                target_path = package_dir / Path(*rel_path.parts[1:])
            else:
                # Files in the root directory
                target_path = project_dir / rel_path

        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Read template content
        content = template_file.read_text(encoding="utf-8")

        # Render template
        rendered = render_template(content, **template_vars)

        # Write to target
        target_path.write_text(rendered, encoding="utf-8")

        # Make scripts executable
        if target_path.suffix in (".sh", ".py") and "main" in target_path.name:
            target_path.chmod(0o755)

    # Copy UI files if requested
    if include_ui:
        ui_template_dir = Path(__file__).parent / "templates" / "ui_addon"
        if ui_template_dir.exists():
            for ui_file in ui_template_dir.rglob("*"):
                if ui_file.is_dir():
                    continue

                # Skip cache and build files
                if any(
                    p in ui_file.parts
                    for p in ["node_modules", "dist", "__pycache__", ".git"]
                ):
                    continue
                if ui_file.suffix in [".pyc", ".pyo"]:
                    continue

                # Get relative path from UI template directory
                rel_path = ui_file.relative_to(ui_template_dir)
                target_path = project_dir / rel_path

                # Create parent directories
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Read and render template if text file
                try:
                    content = ui_file.read_text(encoding="utf-8")
                    rendered = render_template(content, **template_vars)
                    target_path.write_text(rendered, encoding="utf-8")
                except (UnicodeDecodeError, ValueError):
                    # Binary file, just copy
                    shutil.copy2(ui_file, target_path)

                # Make scripts executable
                if target_path.suffix == ".sh":
                    target_path.chmod(0o755)

            print(f"✓ UI files added (FastAPI backend + React frontend)")

    if multi_workflow:
        print(
            f"✓ Created multi-workflow Fleuve project '{project_name}' in {project_dir}"
        )
        print(f"✓ Initial workflow '{workflow_name}' created")
        print(f"\nNext steps:")
        print(f"  1. cd {project_name}")
        print(f"  2. Update db_models.py to import your workflow types")
        print(f"  3. Update main.py to set up your workflow runners")
        print(f"  4. Copy .env.example to .env and configure")
        print(f"  5. docker-compose up -d  # Start PostgreSQL and NATS")
        if include_ui:
            print(f"  6. pip install -e '.[ui]'  # Install project + UI dependencies")
            print(f"  7. python main.py  # Run your workflows")
            print(f"\nUI Setup:")
            print(f"  8. cd ui/frontend && npm install && npm run build")
            print(f"  9. ./start_ui.sh  # Start UI server on http://localhost:8001")
        else:
            print(f"  6. pip install -e .  # Install project")
            print(f"  7. python main.py  # Run your workflows")
        print(f"\nAdd more workflows with: fleuve addworkflow <workflow_name>")
    else:
        print(f"✓ Created Fleuve project '{project_name}' in {project_dir}")
        print(f"\nNext steps:")
        print(f"  1. cd {project_name}")
        print(f"  2. Copy .env.example to .env and configure")
        print(f"  3. docker-compose up -d  # Start PostgreSQL and NATS")
        if include_ui:
            print(f"  4. pip install -e '.[ui]'  # Install project + UI dependencies")
            print(f"  5. python main.py  # Run your workflow")
            print(f"\nUI Setup:")
            print(f"  6. cd ui/frontend && npm install && npm run build")
            print(f"  7. ./start_ui.sh  # Start UI server on http://localhost:8001")
        else:
            print(f"  4. pip install -e .  # Install project")
            print(f"  5. python main.py  # Run your workflow")


def startproject(args: argparse.Namespace) -> None:
    """Handle the startproject command."""
    project_name = args.name
    target_dir = args.directory
    overwrite = args.overwrite
    multi_workflow = args.multi
    initial_workflow = args.workflow if multi_workflow else None
    include_ui = args.ui

    if not project_name:
        # Interactive mode
        while True:
            project_name = input("Project name: ").strip()
            if validate_project_name(project_name):
                break
            print("Invalid project name. Please use a valid Python identifier.")

    create_project(
        project_name,
        target_dir,
        overwrite,
        multi_workflow,
        initial_workflow,
        include_ui,
    )


def add_workflow(
    workflow_name: str,
    project_dir: Optional[str] = None,
) -> None:
    """Add a new workflow to an existing multi-workflow project.

    Args:
        workflow_name: Name of the workflow to add (must be valid Python identifier)
        project_dir: Project directory. Defaults to current directory.
    """
    if not validate_project_name(workflow_name):
        print(f"Error: '{workflow_name}' is not a valid workflow name.")
        print(
            "Workflow name must be a valid Python identifier (letters, digits, underscores, starting with letter/underscore)."
        )
        sys.exit(1)

    # Determine project directory
    if project_dir:
        proj_dir = Path(project_dir)
    else:
        proj_dir = Path.cwd()

    # Check if this is a multi-workflow project
    workflows_dir = proj_dir / "workflows"
    if not workflows_dir.exists():
        print(
            f"Error: '{proj_dir}' does not appear to be a multi-workflow Fleuve project."
        )
        print("The 'workflows/' directory is missing.")
        print(
            "\nTo create a multi-workflow project, use: fleuve startproject myproject --multi"
        )
        sys.exit(1)

    # Check if workflow already exists
    workflow_dir = workflows_dir / workflow_name
    if workflow_dir.exists():
        print(f"Error: Workflow '{workflow_name}' already exists in {workflow_dir}")
        sys.exit(1)

    # Get workflow template from multi-workflow template
    template_dir = (
        Path(__file__).parent
        / "templates"
        / "multi_workflow_template"
        / "workflows"
        / "{{workflow_name}}"
    )
    if not template_dir.exists():
        print(f"Error: Workflow template not found: {template_dir}")
        sys.exit(1)

    # Create workflow directory
    workflow_dir.mkdir(parents=True, exist_ok=True)

    # Template variables
    workflow_title = workflow_name.replace("_", " ").title()
    workflow_class_name = workflow_title.replace(" ", "")

    template_vars = {
        "workflow_name": workflow_name,
        "workflow_title": workflow_title,
        "workflow_class_name": workflow_class_name,
    }

    # Copy and render workflow template files
    for template_file in template_dir.rglob("*"):
        if template_file.is_dir():
            continue

        # Get relative path from workflow template directory
        rel_path = template_file.relative_to(template_dir)

        # Skip __pycache__ and .pyc files
        if "__pycache__" in rel_path.parts or rel_path.suffix == ".pyc":
            continue

        target_path = workflow_dir / rel_path

        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Read template content
        content = template_file.read_text(encoding="utf-8")

        # Render template
        rendered = render_template(content, **template_vars)

        # Write to target
        target_path.write_text(rendered, encoding="utf-8")

    print(f"✓ Added workflow '{workflow_name}' to {proj_dir}")
    print(f"\nNext steps:")
    print(f"  1. Update db_models.py:")
    print(
        f"     - Import: from workflows.{workflow_name}.models import {workflow_class_name}Event, {workflow_class_name}Command"
    )
    print(f"     - Add to AllEvents union: ... | {workflow_class_name}Event")
    print(f"     - Add to AllCommands union: ... | {workflow_class_name}Command")
    print(f"  2. Update main.py to set up the workflow runner")
    print(f"  3. Implement your workflow logic in workflows/{workflow_name}/")


def addworkflow(args: argparse.Namespace) -> None:
    """Handle the addworkflow command."""
    workflow_name = args.name
    project_dir = args.directory

    if not workflow_name:
        # Interactive mode
        while True:
            workflow_name = input("Workflow name: ").strip()
            if validate_project_name(workflow_name):
                break
            print("Invalid workflow name. Please use a valid Python identifier.")

    add_workflow(workflow_name, project_dir)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fleuve - Workflow Framework for Python",
        prog="fleuve",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # startproject command
    startproject_parser = subparsers.add_parser(
        "startproject",
        help="Create a new Fleuve project",
    )
    startproject_parser.add_argument(
        "name",
        nargs="?",
        help="Project name (must be a valid Python identifier)",
    )
    startproject_parser.add_argument(
        "-d",
        "--directory",
        help="Directory to create project in (default: current directory)",
    )
    startproject_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing directory if it exists",
    )
    startproject_parser.add_argument(
        "--multi",
        action="store_true",
        help="Create a multi-workflow project structure with shared database models",
    )
    startproject_parser.add_argument(
        "-w",
        "--workflow",
        help="Name of the initial workflow for multi-workflow projects (default: example_workflow)",
    )
    startproject_parser.add_argument(
        "--ui",
        action="store_true",
        help="Include web UI setup (FastAPI backend + React frontend)",
    )

    # addworkflow command
    addworkflow_parser = subparsers.add_parser(
        "addworkflow",
        help="Add a new workflow to an existing multi-workflow project",
    )
    addworkflow_parser.add_argument(
        "name",
        nargs="?",
        help="Workflow name (must be a valid Python identifier)",
    )
    addworkflow_parser.add_argument(
        "-d",
        "--directory",
        help="Project directory (default: current directory)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "startproject":
        startproject(args)
    elif args.command == "addworkflow":
        addworkflow(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
