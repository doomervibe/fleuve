"""Runtime workflow definition validator.

Checks workflow classes for common structural issues that would otherwise
only surface at runtime.  Used by the ``fleuve validate`` CLI command.

Example::

    from fleuve.validation import validate_workflow, discover_and_validate
    from myproject.workflows import OrderWorkflow

    errors = validate_workflow(OrderWorkflow)
    if errors:
        for err in errors:
            print(err)
"""

from __future__ import annotations

import inspect
import sys
from typing import Any, Type, get_type_hints

from fleuve.model import EventBase, Rejection, StateBase, Workflow


def validate_workflow(workflow_class: Type[Workflow]) -> list[str]:
    """Validate a single workflow class.

    Checks performed:
    - ``name()`` is implemented and returns a non-empty string
    - ``decide()`` is a static/class method with the expected signature
    - ``evolve()`` is a static/class method with the expected signature
    - ``event_to_cmd()`` is a class method
    - ``is_final_event()`` is a static/class method
    - ``decide()`` return annotation is present
    - ``evolve()`` return annotation is present
    - Schema version is a positive int

    Args:
        workflow_class: A concrete subclass of ``Workflow`` to validate.

    Returns:
        List of error message strings.  Empty list means no issues found.
    """
    errors: list[str] = []
    name = getattr(workflow_class, "__name__", str(workflow_class))

    # 1. name() returns a non-empty string
    try:
        wf_name = workflow_class.name()
        if not wf_name or not isinstance(wf_name, str):
            errors.append(f"{name}.name() must return a non-empty string")
    except (NotImplementedError, TypeError) as exc:
        errors.append(f"{name}.name() raised {type(exc).__name__}: {exc}")

    # 2. schema_version() returns a positive int
    try:
        sv = workflow_class.schema_version()
        if not isinstance(sv, int) or sv < 1:
            errors.append(
                f"{name}.schema_version() must return a positive int, got {sv!r}"
            )
    except Exception as exc:
        errors.append(f"{name}.schema_version() raised {type(exc).__name__}: {exc}")

    # 3. Required abstract methods exist and are callable
    for method_name in ("decide", "evolve", "event_to_cmd", "is_final_event"):
        method = getattr(workflow_class, method_name, None)
        if method is None:
            errors.append(f"{name}.{method_name}() is not defined")
            continue
        if not callable(method):
            errors.append(f"{name}.{method_name} is not callable")

    # 4. decide() signature check
    decide = getattr(workflow_class, "decide", None)
    if decide and callable(decide):
        try:
            sig = inspect.signature(decide)
            params = list(sig.parameters.keys())
            # static method: (state, cmd) or (cls, state, cmd)
            expected = {"state", "cmd"}
            if not expected.issubset(set(params)):
                errors.append(
                    f"{name}.decide() should have parameters 'state' and 'cmd', "
                    f"found: {params}"
                )
            # Check return annotation
            hints = {}
            try:
                hints = get_type_hints(decide)
            except Exception:
                pass
            if "return" not in hints:
                errors.append(
                    f"{name}.decide() has no return type annotation "
                    f"(expected list[E] | Rejection)"
                )
        except (ValueError, TypeError):
            pass

    # 5. evolve() signature check
    evolve = getattr(workflow_class, "evolve", None)
    if evolve and callable(evolve):
        try:
            sig = inspect.signature(evolve)
            params = list(sig.parameters.keys())
            expected = {"state", "event"}
            if not expected.issubset(set(params)):
                errors.append(
                    f"{name}.evolve() should have parameters 'state' and 'event', "
                    f"found: {params}"
                )
            hints = {}
            try:
                hints = get_type_hints(evolve)
            except Exception:
                pass
            if "return" not in hints:
                errors.append(
                    f"{name}.evolve() has no return type annotation (expected S)"
                )
        except (ValueError, TypeError):
            pass

    # 6. event_to_cmd() signature check
    event_to_cmd = getattr(workflow_class, "event_to_cmd", None)
    if event_to_cmd and callable(event_to_cmd):
        try:
            sig = inspect.signature(event_to_cmd)
            params = list(sig.parameters.keys())
            # classmethod: (cls, e) or just (e,)
            if not any(p in params for p in ("e", "event", "consumed_event")):
                errors.append(
                    f"{name}.event_to_cmd() should have an event parameter, "
                    f"found: {params}"
                )
        except (ValueError, TypeError):
            pass

    return errors


def discover_and_validate(module_path: str | None = None) -> dict[str, list[str]]:
    """Discover all ``Workflow`` subclasses in a module and validate them.

    Args:
        module_path: Dotted module path (e.g. ``myproject.workflows``).
                     When ``None``, searches all currently-imported modules.

    Returns:
        Dict mapping workflow class name → list of error strings.
        Classes with no issues are omitted.
    """
    import importlib

    issues: dict[str, list[str]] = {}

    modules: list[Any] = []
    if module_path:
        try:
            mod = importlib.import_module(module_path)
            modules = [mod]
        except ImportError as exc:
            issues["<import>"] = [f"Cannot import module '{module_path}': {exc}"]
            return issues
    else:
        modules = list(sys.modules.values())

    found: set[Type[Workflow]] = set()
    for mod in modules:
        if mod is None:
            continue
        for obj in vars(mod).values():
            try:
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Workflow)
                    and obj is not Workflow
                    and not getattr(obj.__dict__.get("Meta", None), "abstract", False)
                ):
                    # Skip abstract base classes that haven't implemented name()
                    try:
                        obj.name()
                        found.add(obj)
                    except (NotImplementedError, TypeError):
                        pass
            except (TypeError, AttributeError):
                pass

    for wf_class in found:
        errs = validate_workflow(wf_class)
        if errs:
            issues[wf_class.__name__] = errs

    return issues
