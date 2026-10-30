from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.core.config import settings
from app.core.rate_limit import SlidingWindowLimiter
from app.schemas.auth import (
    ActivateRequest,
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
)
from app.schemas.user import UserSummary
from app.services.auth import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = f"{settings.API_V1_PREFIX}/auth"

login_limiter = SlidingWindowLimiter(settings.LOGIN_RATE_LIMIT)

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _client(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _token_response(response: Response, issued: IssuedTokens) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=settings.REFRESH_TOKEN_DAYS * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="strict",
    )
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=UserSummary.model_validate(issued.user),
    )


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(
    payload: LoginRequest, request: Request, response: Response, auth: AuthServiceDep
) -> TokenResponse:
    ip, user_agent = _client(request)
    key = f"{ip}|{payload.email.strip().lower()}"
    login_limiter.hit(key)
    issued = await auth.login(payload.email, payload.password, ip=ip, user_agent=user_agent)
    login_limiter.reset(key)
    return _token_response(response, issued)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the refresh token")
async def refresh(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    refresh_token: RefreshCookie = None,
) -> TokenResponse:
    ip, user_agent = _client(request)
    issued = await auth.refresh(refresh_token, ip=ip, user_agent=user_agent)
    return _token_response(response, issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
async def logout(auth: AuthServiceDep, refresh_token: RefreshCookie = None) -> Response:
    await auth.logout(refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="strict",
    )
    return response


@router.post("/activate", status_code=status.HTTP_204_NO_CONTENT, summary="Activate account")
async def activate(payload: ActivateRequest, auth: AuthServiceDep) -> Response:
    await auth.activate(payload.token, payload.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password", response_model=TokenResponse, summary="Change password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    auth: AuthServiceDep,
) -> TokenResponse:
    ip, user_agent = _client(request)
    issued = await auth.change_password(
        user, payload.current_password, payload.new_password, ip=ip, user_agent=user_agent
    )
    return _token_response(response, issued)
