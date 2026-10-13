import json
from typing import Any, Callable, Coroutine

from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute


class GlobalResponseHandler(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response = await original_route_handler(request)

            if isinstance(response, StreamingResponse):
                return response

            if "application/json" not in response.headers.get("content-type", ""):
                return response

            try:
                payload = json.loads(response.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return response

            if (
                isinstance(payload, dict)
                and payload.get("status") in {"success", "error"}
                and isinstance(payload.get("message"), str)
                and "data" in payload
            ):
                return response

            if response.status_code >= 400:
                if isinstance(payload, dict):
                    detail = payload.get("detail", payload)
                    issue = payload.get("issue", "http_error")
                else:
                    detail = payload
                    issue = "http_error"
                formatted = {
                    "status": "error",
                    "message": "Request failed",
                    "data": [{"issue": str(issue), "detail": str(detail)}],
                }
            else:
                message = "Operation successful"
                data = payload
                if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                    message = payload["message"]
                    data = {key: value for key, value in payload.items() if key != "message"}
                    if not data:
                        data = None
                formatted = {
                    "status": "success",
                    "message": message,
                    "data": data,
                }

            return JSONResponse(
                content=formatted,
                status_code=response.status_code,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in {"content-length", "content-type"}
                },
            )

        return custom_route_handler
