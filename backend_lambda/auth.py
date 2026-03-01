import json
import time
import urllib.request
from datetime import datetime, timedelta

from jose import jwk, jwt
from jose.utils import base64url_decode
from psycopg2.extras import RealDictCursor

from config import (
    AWS_REGION, COGNITO_CLIENT_ID, COGNITO_USER_POOL_ID,
    REFRESH_TOKEN_DAYS, TOKEN_USE_ALLOWED, cognito, logger,
)
from db import get_db_connection, release_db_connection
from helpers import _hash_token, api_response

jwks_cache = None


def get_jwks():
    global jwks_cache
    if jwks_cache is None:
        if not COGNITO_USER_POOL_ID:
            raise RuntimeError("COGNITO_USER_POOL_ID is missing")
        keys_url = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        with urllib.request.urlopen(keys_url) as response:
            jwks_cache = json.loads(response.read())
    return jwks_cache


def verify_jwt(token):
    try:
        if not token or not isinstance(token, str):
            return None
        token = token.strip()
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            return None
        keys = get_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == kid), None)
        if not key:
            return None
        public_key = jwk.construct(key)
        message, encoded_signature = token.rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
        if not public_key.verify(message.encode("utf-8"), decoded_signature):
            return None
        claims = jwt.get_unverified_claims(token)
        if time.time() > claims.get("exp", 0):
            return None
        issuer = claims.get("iss", "")
        if COGNITO_USER_POOL_ID and COGNITO_USER_POOL_ID not in issuer:
            return None
        if COGNITO_CLIENT_ID:
            token_client = claims.get("client_id") or claims.get("aud")
            if token_client != COGNITO_CLIENT_ID:
                return None
        token_use = claims.get("token_use")
        if TOKEN_USE_ALLOWED and token_use not in TOKEN_USE_ALLOWED:
            return None
        return claims
    except Exception:
        return None


def _ensure_user_record(claims, fallback_full_name=None):
    conn = get_db_connection()
    try:
        sub = claims.get("sub")
        email = claims.get("email") or claims.get("username") or ""
        full_name = claims.get("name") or fallback_full_name
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO user_data (cognito_sub, email, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (cognito_sub)
                DO UPDATE SET email = EXCLUDED.email, full_name = COALESCE(EXCLUDED.full_name, user_data.full_name)
                RETURNING id, cognito_sub, email, full_name, created_at""",
                (sub, email, full_name),
            )
            user = cur.fetchone()
            conn.commit()
            return user
    finally:
        release_db_connection(conn)


def _save_refresh_token(user_id, refresh_token):
    if not refresh_token:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM refresh_tokens WHERE user_id=%s OR expires_at < NOW()", (user_id,))
            cur.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, _hash_token(refresh_token), datetime.utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)),
            )
            conn.commit()
    except Exception as exc:
        logger.warning(f"Refresh token save skipped: {exc}")
        conn.rollback()
    finally:
        release_db_connection(conn)


def handle_auth_register(body):
    email = (body or {}).get("email")
    password = (body or {}).get("password")
    full_name = (body or {}).get("full_name")
    if not email or not password:
        return api_response(400, {"error": "email and password are required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "Authentication service not configured"})
    try:
        attributes = [
            {"Name": "email", "Value": email},
            {"Name": "name", "Value": full_name or email.split('@')[0]},
            {"Name": "nickname", "Value": full_name or email.split('@')[0]},
        ]
        logger.info(f"Registering user: {email}")
        response = cognito.sign_up(
            ClientId=COGNITO_CLIENT_ID, Username=email,
            Password=password, UserAttributes=attributes,
        )
        return api_response(201, {
            "message": "Registration successful",
            "user_sub": response.get("UserSub"),
            "user_confirmed": response.get("UserConfirmed", False),
        })
    except cognito.exceptions.UsernameExistsException:
        return api_response(409, {"error": "User with this email already exists"})
    except Exception as exc:
        logger.error(f"Registration failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Registration failed"})


def handle_auth_confirm(body):
    email = (body or {}).get("email")
    code = (body or {}).get("code")
    if not email or not code:
        return api_response(400, {"error": "email and code are required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "Authentication service not configured"})
    try:
        cognito.confirm_sign_up(ClientId=COGNITO_CLIENT_ID, Username=email, ConfirmationCode=code)
        return api_response(200, {"message": "Account confirmed successfully"})
    except cognito.exceptions.CodeMismatchException:
        return api_response(400, {"error": "Invalid confirmation code"})
    except cognito.exceptions.ExpiredCodeException:
        return api_response(400, {"error": "Confirmation code expired"})
    except Exception as exc:
        logger.error(f"Confirmation failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Confirmation failed"})


def handle_auth_login(body):
    email = (body or {}).get("email")
    password = (body or {}).get("password")
    if not email or not password:
        return api_response(400, {"error": "email and password are required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "Authentication service not configured"})
    try:
        auth_resp = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            ClientId=COGNITO_CLIENT_ID,
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        auth = auth_resp.get("AuthenticationResult", {})
        id_token = auth.get("IdToken")
        access_token = auth.get("AccessToken")
        refresh_token = auth.get("RefreshToken")
        if not id_token or not access_token:
            return api_response(401, {"error": "Authentication failed"})
        claims = jwt.get_unverified_claims(id_token)
        user = _ensure_user_record(claims, fallback_full_name=(body or {}).get("full_name"))
        _save_refresh_token(user["id"], refresh_token)
        return api_response(200, {
            "tokens": {
                "access_token": access_token, "id_token": id_token,
                "refresh_token": refresh_token, "expires_in": auth.get("ExpiresIn"),
                "token_type": auth.get("TokenType", "Bearer"),
            },
            "user": {
                "id": str(user["id"]), "email": user.get("email"),
                "full_name": user.get("full_name"), "cognito_sub": user.get("cognito_sub"),
            },
        })
    except cognito.exceptions.NotAuthorizedException:
        return api_response(401, {"error": "Invalid credentials"})
    except cognito.exceptions.UserNotConfirmedException:
        return api_response(403, {"error": "User is not confirmed"})
    except Exception as exc:
        logger.error(f"Login failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Login failed"})


def handle_auth_refresh(body):
    refresh_token = (body or {}).get("refresh_token")
    if not refresh_token:
        return api_response(400, {"error": "refresh_token is required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "Authentication service not configured"})
    try:
        auth_resp = cognito.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            ClientId=COGNITO_CLIENT_ID,
            AuthParameters={"REFRESH_TOKEN": refresh_token},
        )
        auth = auth_resp.get("AuthenticationResult", {})
        return api_response(200, {
            "tokens": {
                "access_token": auth.get("AccessToken"), "id_token": auth.get("IdToken"),
                "refresh_token": refresh_token, "expires_in": auth.get("ExpiresIn"),
                "token_type": auth.get("TokenType", "Bearer"),
            }
        })
    except cognito.exceptions.NotAuthorizedException:
        return api_response(401, {"error": "Invalid refresh token"})
    except Exception as exc:
        logger.error(f"Token refresh failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Token refresh failed"})


def handle_auth_me(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, cognito_sub, email, full_name, created_at FROM user_data WHERE id=%s",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                return api_response(404, {"error": "User not found"})
            return api_response(200, {"user": user})
    finally:
        release_db_connection(conn)
