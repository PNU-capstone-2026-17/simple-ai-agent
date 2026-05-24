GENERATE_PROMPT = """
You are generating a minimal runnable Python FastAPI backend.

Rules:
- Return only valid JSON.
- Do not include markdown fences.
- Do not include explanations.
- Keep the project minimal and coherent.
- Use FastAPI.
- Use SQLite for storage.
- Store hashed passwords, not raw passwords.
- All class names and function names must be unique within each file.
- Avoid duplicate names across files unless intentionally representing the same concept.
- Use clear suffixes when needed:
  - request schemas: RegisterRequest, LoginRequest
  - response schemas: UserResponse
  - db models: UserModel
  - helper functions: hash_password, verify_password, create_access_token
  - route handlers: register_user, login_user, list_users
- Do not define the same class or function twice.
- Include:
  - user registration endpoint
  - login endpoint
  - admin user list endpoint
- If details are missing, use short TODO comments in code.
- Prefer a small codebase.

Return JSON with exactly this shape:
{{
  "app/main.py": "string",
  "requirements.txt": "string"
}}

Requirements JSON:
{requirements_json}
""".strip()