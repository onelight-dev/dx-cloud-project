# Cart API Test Project

## 1. 설치
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 환경변수 설정
`.env.example` 참고해서 환경변수 설정

Linux/macOS:
```bash
export DB_HOST=211.46.52.153
export DB_PORT=15432
export DB_NAME=pg_local
export DB_USER=team3
export DB_PASSWORD=비밀번호
```

Windows PowerShell:
```powershell
$env:DB_HOST="211.46.52.153"
$env:DB_PORT="15432"
$env:DB_NAME="pg_local"
$env:DB_USER="team3"
$env:DB_PASSWORD="비밀번호"
```

## 3. 실행
```bash
python app.py
```

## 4. 테스트 헤더
인증 대신 임시로 `X-USER-ID` 헤더 사용

## 5. 엔드포인트
- GET /cart
- POST /cart/items
- PATCH /cart/items/{item_id}
- DELETE /cart/items/{item_id}
- DELETE /cart
