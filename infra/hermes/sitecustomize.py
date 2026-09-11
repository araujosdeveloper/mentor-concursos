"""Project-local bridge for Hermes session context in skill subprocesses.

Hermes v0.20.4 stores Telegram metadata in task-local ContextVars.  Its
``hermes_subprocess_env`` helper historically copied only ``os.environ`` on
one non-terminal spawn path, so the mentor-study process lost the trusted
identity.  Patch that single factory at interpreter startup; the canonical
ContextVar values remain the only source of identity.
"""

from __future__ import annotations

from functools import wraps


def _install_context_bridge() -> None:
    try:
        from tools.environments import local
    except Exception:
        return
    if getattr(local, "_mentor_context_bridge_installed", False):
        return
    original = local.hermes_subprocess_env
    inject = getattr(local, "_inject_session_context_env", None)
    if not callable(inject):
        return

    @wraps(original)
    def bridged_hermes_subprocess_env(*, inherit_credentials: bool = False):
        env = original(inherit_credentials=inherit_credentials)
        # Values come exclusively from the current gateway task's ContextVars;
        # the helper strips unset values when the session machinery is engaged.
        inject(env)
        return env

    local.hermes_subprocess_env = bridged_hermes_subprocess_env
    local._mentor_context_bridge_installed = True


_install_context_bridge()
