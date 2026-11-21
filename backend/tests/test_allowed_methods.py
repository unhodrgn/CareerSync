"""`app/core/allowed_methods.py` (M4 S4.4; docs/DECISIONS.md D67, D69): a 405 on a path with more than one route lists every method of the path.

These are mechanism tests on throwaway applications, so that they do not depend on which interview routes exist: the route class of one router
makes the `Allow` of a 405 name all the methods that the router has for the path (in a fixed order), whichever route was registered first
and whatever the prefix; and it changes nothing else: a supported request, a 404, a 422, the body, content type and other headers of the 405,
the OpenAPI document, an exception that an endpoint raises itself (a 405 of its own included), and the other routers of the application are
exactly what they are without it. The routes of the real interview router, against their OpenAPI methods, are checked in
test_interview_api_contract.py and test_interview_api_session_common.py. The last test is a canary: the class catches the base
`starlette.exceptions.HTTPException`, which is what FastAPI raises, and an upgrade that changes that has to be reviewed."""
import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.core.allowed_methods import all_methods_route_class

WRONG = ("POST", "PUT", "PATCH", "HEAD", "OPTIONS")


def read_thing(thing_id: int):
    return {"id": thing_id}


def put_thing(thing_id: int):
    return {"put": thing_id}


def delete_thing(thing_id: int):
    return None


def end_thing(thing_id: int):
    return {"ended": thing_id}


def list_things():
    return []


def register(router: APIRouter, method: str) -> None:
    if method == "get":
        router.get("/things/{thing_id}", summary="read")(read_thing)
    elif method == "put":
        router.put("/things/{thing_id}", summary="put")(put_thing)
    else:
        router.delete("/things/{thing_id}", status_code=204, summary="delete")(delete_thing)


def build(route_class, *, methods=("get", "delete"), prefix="/api", plain_router=False) -> FastAPI:
    router = APIRouter(tags=["things"], route_class=route_class) if route_class else APIRouter(tags=["things"])
    for method in methods:
        register(router, method)
    router.post("/things/{thing_id}/end", summary="end")(end_thing)
    router.get("/things", summary="list")(list_things)
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    if plain_router:
        plain = APIRouter()
        plain.get("/plain/{thing_id}")(read_thing)
        plain.delete("/plain/{thing_id}", status_code=204)(delete_thing)
        app.include_router(plain, prefix=prefix)
    return app


def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def answer(response):
    """Everything of a response that must not change: status, body, and every header."""
    return response.status_code, response.text, dict(response.headers)


# ── Allow lists every method of the path ──


@pytest.mark.parametrize("order", [("get", "delete"), ("delete", "get")], ids=["get first", "delete first"])
def test_allow_lists_every_method_of_the_path_whichever_route_was_registered_first(order):
    web = client(build(all_methods_route_class(), methods=order))
    for method in WRONG:
        response = web.request(method, "/api/things/1")
        assert response.status_code == 405 and response.headers["allow"] == "DELETE, GET", method  # sorted, so the same on every run
    assert web.get("/api/things/1").status_code == 200 and web.delete("/api/things/1").status_code == 204


def test_a_path_with_three_methods_lists_all_three():
    web = client(build(all_methods_route_class(), methods=("get", "put", "delete")))
    assert {m: web.request(m, "/api/things/1").headers["allow"] for m in ("POST", "PATCH", "HEAD")} == dict.fromkeys(("POST", "PATCH", "HEAD"), "DELETE, GET, PUT")


def test_a_path_does_not_borrow_the_methods_of_another_path():
    web = client(build(all_methods_route_class()))
    assert web.post("/api/things").headers["allow"] == "GET"  # the collection
    assert web.put("/api/things/1").headers["allow"] == "DELETE, GET"  # the item
    assert web.get("/api/things/1/end").headers["allow"] == "POST"  # what hangs off the item
    assert web.delete("/api/things/1/end").status_code == 405


@pytest.mark.parametrize("prefix", ["/api", "/v2/x", ""])
def test_the_prefix_of_the_inclusion_does_not_matter(prefix):
    web = client(build(all_methods_route_class(), prefix=prefix))
    assert web.post(f"{prefix}/things/1").headers["allow"] == "DELETE, GET"


def test_two_routers_with_the_class_do_not_share_a_registry():
    first, second = APIRouter(route_class=all_methods_route_class()), APIRouter(route_class=all_methods_route_class())
    first.get("/things/{thing_id}")(read_thing)
    second.delete("/things/{thing_id}", status_code=204)(delete_thing)  # the same path template, in another router
    app = FastAPI()
    app.include_router(first, prefix="/a")
    app.include_router(second, prefix="/b")
    web = client(app)
    assert (web.post("/a/things/1").headers["allow"], web.post("/b/things/1").headers["allow"]) == ("GET", "DELETE")


def test_each_call_makes_its_own_route_class_and_it_is_an_api_route():
    one, two = all_methods_route_class(), all_methods_route_class()
    assert one is not two and issubclass(one, APIRoute) and one is not APIRoute


# ── Nothing else changes ──


def test_a_plain_router_of_the_same_application_keeps_the_frameworks_allow():
    web = client(build(all_methods_route_class(), plain_router=True))
    assert web.post("/api/plain/1").headers["allow"] == "GET"  # the first route of the path only: not widened, not our router
    assert web.post("/api/things/1").headers["allow"] == "DELETE, GET"


def test_supported_requests_a_404_and_a_422_are_exactly_as_without_the_class():
    with_class, without = client(build(all_methods_route_class())), client(build(None))
    for method, path in (
        ("GET", "/api/things/7"), ("DELETE", "/api/things/7"), ("POST", "/api/things/7/end"), ("GET", "/api/things"),
        ("GET", "/api/things/abc"), ("DELETE", "/api/things/1.5"), ("GET", "/api/nothing"), ("POST", "/api/things/abc/end"),
    ):
        assert answer(with_class.request(method, path)) == answer(without.request(method, path)), (method, path)


def test_the_405_is_the_same_as_without_the_class_except_for_allow():
    with_class, without = client(build(all_methods_route_class())), client(build(None))
    for method in WRONG:
        a, b = with_class.request(method, "/api/things/1"), without.request(method, "/api/things/1")
        assert (a.status_code, a.text, a.headers["content-type"] if a.text else None) == (b.status_code, b.text, b.headers["content-type"] if b.text else None), method
        drop = lambda response: {k: v for k, v in response.headers.items() if k != "allow"}
        assert drop(a) == drop(b), method  # every other header
    assert with_class.post("/api/things/1").json() == {"detail": "Method Not Allowed"}


def test_the_openapi_document_is_identical():
    def canonical(app):
        return json.dumps(app.openapi(), sort_keys=True)

    assert canonical(build(all_methods_route_class())) == canonical(build(None))


def test_an_exception_of_the_endpoint_itself_is_not_touched_even_a_405_of_its_own():
    def odd():
        raise FastAPIHTTPException(405, detail="mine", headers={"Allow": "X"})

    def teapot():
        raise FastAPIHTTPException(418, detail="short and stout")

    def build_odd(route_class) -> FastAPI:
        router = APIRouter(route_class=route_class) if route_class else APIRouter()
        router.get("/odd")(odd)  # a supported method whose endpoint answers 405 itself
        router.delete("/odd", status_code=204)(delete_thing_odd)
        router.get("/tea")(teapot)
        app = FastAPI()
        app.include_router(router)
        return app

    def delete_thing_odd():
        return None

    with_class, without = client(build_odd(all_methods_route_class())), client(build_odd(None))
    for path in ("/odd", "/tea"):
        mine, stock = with_class.get(path), without.get(path)
        assert answer(mine) == answer(stock), path
    assert with_class.get("/odd").headers["allow"] == "X" and with_class.get("/odd").json() == {"detail": "mine"}  # not widened to `DELETE, GET`
    assert with_class.post("/odd").headers["allow"] == "DELETE, GET"  # while a real wrong method is


def test_a_405_that_the_normal_handle_raises_for_a_supported_method_is_left_alone(monkeypatch):
    """With this FastAPI an endpoint's own exception never reaches the route class (the route's app turns it into a response first), so the gate
    on the request's method is what keeps a 405 that is not about the method untouched if the framework ever lets one through."""

    async def handle(self, scope, receive, send):
        raise HTTPException(405, detail="not about the method", headers={"Allow": "X"})

    monkeypatch.setattr(APIRoute, "handle", handle)
    response = client(build(all_methods_route_class())).get("/api/things/1")  # GET is a method of the route
    assert response.status_code == 405 and response.headers["allow"] == "X" and response.json() == {"detail": "not about the method"}


def test_the_detail_and_every_other_header_of_the_original_error_are_kept(monkeypatch):
    original = APIRoute.handle

    async def handle(self, scope, receive, send):
        if scope["method"] not in self.methods:
            raise HTTPException(405, detail="custom detail", headers={"Allow": "ONE", "X-Marker": "kept"})
        await original(self, scope, receive, send)

    monkeypatch.setattr(APIRoute, "handle", handle)
    response = client(build(all_methods_route_class())).post("/api/things/1")
    assert response.status_code == 405 and response.json() == {"detail": "custom detail"}
    assert response.headers["x-marker"] == "kept" and response.headers["allow"] == "DELETE, GET"  # only `Allow` is rewritten


# ── The canary ──


def test_the_framework_raises_the_405_as_the_base_starlette_exception():
    seen = []

    def record(request, exc):
        seen.append(type(exc))
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    app = build(None)
    app.add_exception_handler(HTTPException, record)
    assert client(app).post("/api/things/1").status_code == 405
    assert seen == [HTTPException]  # not FastAPI's subclass: an `except` for that one would never see it
    assert FastAPIHTTPException is not HTTPException and issubclass(FastAPIHTTPException, HTTPException)
