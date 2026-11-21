"""A 405 on a path that more than one route serves lists every method of the path in `Allow` (M4 S4.4; docs/DECISIONS.md D67, D69).

FastAPI keeps one route per method. A request whose method the first matching route does not have is handed to that route (the included
router takes the first partial match and calls `original_route.handle`), and `APIRoute.handle` answers 405 with an `Allow` that holds *that
route's* methods only: `POST /api/interview-sessions/{session_id}` was told `Allow: GET` although the path also has a DELETE. Registering the
DELETE first only swaps the two, so the order of registration cannot fix it.

`all_methods_route_class()` returns an `APIRoute` subclass for ONE router: `APIRouter(route_class=all_methods_route_class())`. Each route of
that router records its methods under its complete path template in a registry that belongs to that class, so another router never shares it,
and its `handle` calls the normal one. When the normal `handle` raises the 405 for a method that this route does not have, the `Allow` of the
exception becomes the sorted union of the methods that the router has for the path, and the exception is raised again, so FastAPI's own
handling still builds the response: its status, body, content type and every other header are the framework's.

Nothing else changes. A supported request is never intercepted (the gate is the request's method), an exception that the endpoint raises
itself, a 405 of its own included, passes as it is, the OpenAPI document is the same, and the other routers of the application keep the
framework's behaviour. What it relies on is checked by tests (`backend/tests/test_allowed_methods.py` and the contract tests of the interview
API): that the 405 is raised as `starlette.exceptions.HTTPException`, the base class, which FastAPI's own subclass of it is not (an `except`
for that subclass would never see it), and that `Allow` of every interview path equals the methods of its OpenAPI path.
"""
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.types import Receive, Scope, Send


def all_methods_route_class() -> type[APIRoute]:
    """A route class for one router; call it once for each router that needs it."""
    methods_at: dict[str, set[str]] = {}

    class AllMethodsRoute(APIRoute):
        def __init__(self, path: str, *args, **kwargs) -> None:
            super().__init__(path, *args, **kwargs)
            methods_at.setdefault(self.path, set()).update(self.methods)

        async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await super().handle(scope, receive, send)
            except HTTPException as error:
                if error.status_code == 405 and scope["method"] not in self.methods:
                    error.headers = {**(error.headers or {}), "Allow": ", ".join(sorted(methods_at[self.path]))}
                raise

    return AllMethodsRoute
