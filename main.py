import os
import math
import random
import requests
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7일

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class TodoModel(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(String, nullable=False)
    done = Column(String, default="false")  # "true" / "false" (Boolean 대신 문자열로 간단히)
    created_at = Column(DateTime, default=now_kst)


class InvitationModel(Base):
    __tablename__ = "invitations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    groom_name = Column(String, default="")
    bride_name = Column(String, default="")
    greeting = Column(String, default="")
    wedding_date = Column(String, default="")  # "2026-10-10 13:00" 형식 문자열
    venue_name = Column(String, default="")
    venue_address = Column(String, default="")
    venue_lat = Column(String, default="")
    venue_lng = Column(String, default="")
    photos = Column(String, default="[]")  # JSON 배열 문자열
    hero_photo = Column(String, default="")
    theme_color = Column(String, default="#b08a6a")
    music_url = Column(String, default="")
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst)


class InvitationGuestbookModel(Base):
    __tablename__ = "invitation_guestbook"
    id = Column(Integer, primary_key=True, index=True)
    invitation_id = Column(Integer, ForeignKey("invitations.id"), nullable=False)
    name = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class FolderModel(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class FavoriteModel(Base):
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    fav_type = Column(String, nullable=False)  # "place" or "course"
    data = Column(String, nullable=False)  # JSON 문자열로 저장
    created_at = Column(DateTime, default=now_kst)

class ChatMessageModel(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, nullable=False, index=True)
    nickname = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)

Base.metadata.create_all(bind=engine)

class UserIn(BaseModel):
    username: str
    password: str

def get_current_user_optional(token: str = Depends(oauth2_scheme)):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

def get_current_user(token: str = Depends(oauth2_scheme)):
    username = get_current_user_optional(token)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return username

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
# 우리 서비스 카테고리 <-> 카카오 카테고리 코드 매핑
CATEGORY_MAP = {
    "음식점": "FD6",
    "카페": "CE7",
    "명소": "AT4",
}


def haversine(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 거리를 미터 단위로 계산"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def kakao_image_search(query):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    url = "https://dapi.kakao.com/v2/search/image"
    params = {"query": query, "size": 1}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data["documents"]:
        return None
    return data["documents"][0]["thumbnail_url"]


def kakao_search(query, category_code, size=5):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "category_group_code": category_code, "size": size}
    response = requests.get(KAKAO_URL, headers=headers, params=params)
    if response.status_code != 200:
        return []
    data = response.json()
    places = [
        {
            "name": doc["place_name"],
            "address": doc["road_address_name"] or doc["address_name"],
            "phone": doc["phone"],
            "category": doc["category_name"],
            "url": doc["place_url"],
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
        }
        for doc in data["documents"]
    ]
    for p in places:
        p["image"] = kakao_image_search(p["name"])
    return places


@app.get("/")
def read_root():
    return {"message": "여행추천 API입니다"}


@app.get("/search")
def search_places(region: str, category: str, subcategory: str = None, lat: float = None, lng: float = None):
    if category not in CATEGORY_MAP:
        raise HTTPException(status_code=400, detail="지원하지 않는 카테고리입니다")

    query = region
    if subcategory:
        query = f"{region} {subcategory}"

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {
        "query": query,
        "category_group_code": CATEGORY_MAP[category],
        "size": 15,
    }

    if lat is not None and lng is not None:
        params["x"] = lng
        params["y"] = lat
        params["sort"] = "distance"

    response = requests.get(KAKAO_URL, headers=headers, params=params)

    if response.status_code != 200:
        print(f"[카카오 API 에러] {response.status_code} - {response.text}")
        raise HTTPException(status_code=502, detail="검색 서비스에 일시적인 문제가 발생했습니다")

    data = response.json()
    places = [
        {
            "name": doc["place_name"],
            "address": doc["road_address_name"] or doc["address_name"],
            "phone": doc["phone"],
            "category": doc["category_name"],
            "url": doc["place_url"],
            "lat": doc["y"],
            "lng": doc["x"],
            "distance": doc.get("distance") or None,
        }
        for doc in data["documents"]
    ]

    for p in places:
        p["image"] = kakao_image_search(p["name"])
    return {"region": region, "category": category, "count": len(places), "places": places}

THEME_KEYWORDS = {
    "액티브": "체험",
    "힐링": "공원",
    "실내": "전시",
}

THEME_KEYWORDS = {
    "액티브": "체험",
    "힐링": "공원",
    "실내": "전시",
}

BUDGET_KEYWORDS = {
    "절약형": "분식",
    "보통": None,
    "여유형": "다이닝",
}

DURATION_STEPS = {
    "짧게": 2,
    "보통": 3,
    "하루종일": 4,
}

def budget_amount_to_bucket(amount: int) -> str:
    if amount < 20000:
        return "절약형"
    elif amount < 50000:
        return "보통"
    else:
        return "여유형"


@app.get("/course")
def recommend_course(region: str, theme: str = None, budget: str = None, budget_amount: int = None, duration: str = "보통"):
    step_count = DURATION_STEPS.get(duration, 3)

    if budget_amount is not None:
        budget = budget_amount_to_bucket(budget_amount)

    attraction_query = region
    if theme and theme in THEME_KEYWORDS:
        attraction_query = f"{region} {THEME_KEYWORDS[theme]}"

    restaurant_query = region
    if budget and BUDGET_KEYWORDS.get(budget):
        restaurant_query = f"{region} {BUDGET_KEYWORDS[budget]}"

    attractions = kakao_search(attraction_query, CATEGORY_MAP["명소"], size=8)
    if not attractions:
        attractions = kakao_search(region, CATEGORY_MAP["명소"], size=8)

    restaurants = kakao_search(restaurant_query, CATEGORY_MAP["음식점"], size=8)
    if not restaurants:
        restaurants = kakao_search(region, CATEGORY_MAP["음식점"], size=8)

    cafes = kakao_search(region, CATEGORY_MAP["카페"], size=8)

    if not restaurants or not cafes:
        raise HTTPException(status_code=404, detail="해당 지역에서 충분한 장소를 찾지 못했습니다")

    if step_count == 2:
        # 음식점 + 카페만
        best_combo = None
        best_distance = float("inf")
        for r in restaurants:
            for c in cafes:
                d = haversine(r["lat"], r["lng"], c["lat"], c["lng"])
                if d < best_distance:
                    best_distance = d
                    best_combo = (r, c, d)
        r, c, d = best_combo
        course = [
            {"step": 1, "type": "음식점", "place": r, "distance_to_next": round(d)},
            {"step": 2, "type": "카페", "place": c, "distance_to_next": None},
        ]
        total = d

    elif step_count == 4:
        # 명소 + 음식점 + 명소 + 카페
        if not attractions or len(attractions) < 2:
            raise HTTPException(status_code=404, detail="충분한 명소를 찾지 못했습니다")
        combos = []
        for a1 in attractions:
            for r in restaurants:
                for a2 in attractions:
                    if a1["name"] == a2["name"]:
                        continue
                    for c in cafes:
                        d1 = haversine(a1["lat"], a1["lng"], r["lat"], r["lng"])
                        d2 = haversine(r["lat"], r["lng"], a2["lat"], a2["lng"])
                        d3 = haversine(a2["lat"], a2["lng"], c["lat"], c["lng"])
                        combos.append((d1 + d2 + d3, a1, r, a2, c, d1, d2, d3))
        combos.sort(key=lambda x: x[0])
        total, a1, r, a2, c, d1, d2, d3 = random.choice(combos[:10])
        course = [
            {"step": 1, "type": "명소", "place": a1, "distance_to_next": round(d1)},
            {"step": 2, "type": "음식점", "place": r, "distance_to_next": round(d2)},
            {"step": 3, "type": "명소", "place": a2, "distance_to_next": round(d3)},
            {"step": 4, "type": "카페", "place": c, "distance_to_next": None},
        ]

    else:
        # 기본 3단계: 명소 + 음식점 + 카페
        if not attractions:
            raise HTTPException(status_code=404, detail="충분한 명소를 찾지 못했습니다")
        combos = []
        for a in attractions:
            for r in restaurants:
                for c in cafes:
                    d1 = haversine(a["lat"], a["lng"], r["lat"], r["lng"])
                    d2 = haversine(r["lat"], r["lng"], c["lat"], c["lng"])
                    combos.append((d1 + d2, a, r, c, d1, d2))
        combos.sort(key=lambda x: x[0])
        total, a, r, c, d1, d2 = random.choice(combos[:10])
        course = [
            {"step": 1, "type": "명소", "place": a, "distance_to_next": round(d1)},
            {"step": 2, "type": "음식점", "place": r, "distance_to_next": round(d2)},
            {"step": 3, "type": "카페", "place": c, "distance_to_next": None},
        ]

    return {
        "region": region,
        "theme": theme,
        "budget": budget,
        "duration": duration,
        "total_distance": round(total),
        "course": course
    }
@app.get("/weather")
def get_weather(lat: float, lng: float):
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lng,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "kr",
    }
    response = requests.get(forecast_url, params=params)

    if response.status_code != 200:
        print(f"[날씨 API 에러] {response.status_code} - {response.text}")
        raise HTTPException(status_code=502, detail="날씨 정보를 가져올 수 없습니다")

    data = response.json()

    # 3시간 단위 데이터를 날짜별로 묶기
    daily = {}
    for item in data["list"]:
        date = item["dt_txt"].split(" ")[0]
        hour = item["dt_txt"].split(" ")[1]
        if date not in daily:
            daily[date] = []
        daily[date].append(item)

    indoor_weathers = ["Rain", "Snow", "Thunderstorm", "Drizzle"]

    days = []
    for date, items in list(daily.items())[:5]:
        # 정오(12:00)에 가까운 데이터를 대표값으로 사용, 없으면 첫 항목
        noon_item = next((i for i in items if "12:00:00" in i["dt_txt"]), items[0])
        temps = [i["main"]["temp"] for i in items]
        weather_main = noon_item["weather"][0]["main"]

        days.append({
            "date": date,
            "temp_min": round(min(temps)),
            "temp_max": round(max(temps)),
            "description": noon_item["weather"][0]["description"],
            "weather_main": weather_main,
            "recommended_theme": "실내" if weather_main in indoor_weathers else "실외",
        })

    return {
        "today": days[0] if days else None,
        "days": days,
    }
class ChatRoomManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, room_id: str, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
        self.rooms[room_id].append(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket):
        if room_id in self.rooms and websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    async def broadcast(self, room_id: str, message: dict):
        if room_id not in self.rooms:
            return
        dead_connections = []
        for connection in self.rooms[room_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for dc in dead_connections:
            self.rooms[room_id].remove(dc)


chat_manager = ChatRoomManager()


# --- 회원가입 / 로그인 ---
@app.post("/register")
def register(user: UserIn):
    db = SessionLocal()
    existing = db.query(UserModel).filter(UserModel.username == user.username).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다")
    hashed = hash_password(user.password)
    new_user = UserModel(username=user.username, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.close()
    return {"status": "registered"}


@app.post("/login")
def login(user: UserIn):
    db = SessionLocal()
    db_user = db.query(UserModel).filter(UserModel.username == user.username).first()
    db.close()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


# --- 찜목록 (로그인 필요) ---
import json as _json

@app.get("/favorites")
def get_favorites(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    favs = db.query(FavoriteModel).filter(FavoriteModel.user_id == user.id).order_by(FavoriteModel.created_at.desc()).all()
    result = [
        {
            "id": f.id,
            "type": f.fav_type,
            "data": _json.loads(f.data),
            "folder_id": f.folder_id,
            "created_at": f.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for f in favs
    ]
    db.close()
    return result


class FavoriteIn(BaseModel):
    fav_type: str
    data: dict


@app.post("/favorites")
def add_favorite(fav: FavoriteIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_fav = FavoriteModel(user_id=user.id, fav_type=fav.fav_type, data=_json.dumps(fav.data, ensure_ascii=False))
    db.add(new_fav)
    db.commit()
    fav_id = new_fav.id
    db.close()
    return {"status": "saved", "id": fav_id}


@app.delete("/favorites/{fav_id}")
def delete_favorite(fav_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    fav = db.query(FavoriteModel).filter(FavoriteModel.id == fav_id, FavoriteModel.user_id == user.id).first()
    if not fav:
        db.close()
        raise HTTPException(status_code=404, detail="찜 항목을 찾을 수 없습니다")
    db.delete(fav)
    db.commit()
    db.close()
    return {"status": "deleted"}


# --- 할일 관리 ---
class TodoIn(BaseModel):
    content: str


class TodoUpdate(BaseModel):
    content: str = None
    done: bool = None


@app.get("/todos")
def get_todos(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    todos = db.query(TodoModel).filter(TodoModel.user_id == user.id).order_by(TodoModel.created_at.desc()).all()
    result = [
        {
            "id": t.id,
            "content": t.content,
            "done": t.done == "true",
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for t in todos
    ]
    db.close()
    return result


@app.post("/todos")
def create_todo(todo: TodoIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_todo = TodoModel(user_id=user.id, content=todo.content, done="false")
    db.add(new_todo)
    db.commit()
    todo_id = new_todo.id
    db.close()
    return {"status": "created", "id": todo_id}


@app.put("/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    todo = db.query(TodoModel).filter(TodoModel.id == todo_id, TodoModel.user_id == user.id).first()
    if not todo:
        db.close()
        raise HTTPException(status_code=404, detail="할일을 찾을 수 없습니다")
    if body.content is not None:
        todo.content = body.content
    if body.done is not None:
        todo.done = "true" if body.done else "false"
    db.commit()
    db.close()
    return {"status": "updated"}


@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    todo = db.query(TodoModel).filter(TodoModel.id == todo_id, TodoModel.user_id == user.id).first()
    if not todo:
        db.close()
        raise HTTPException(status_code=404, detail="할일을 찾을 수 없습니다")
    db.delete(todo)
    db.commit()
    db.close()
    return {"status": "deleted"}


# --- 폴더 ---
class FolderIn(BaseModel):
    name: str


@app.get("/folders")
def get_folders(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    folders = db.query(FolderModel).filter(FolderModel.user_id == user.id).order_by(FolderModel.created_at.desc()).all()
    result = []
    for folder in folders:
        count = db.query(FavoriteModel).filter(FavoriteModel.folder_id == folder.id).count()
        result.append({
            "id": folder.id,
            "name": folder.name,
            "item_count": count,
            "created_at": folder.created_at.strftime("%Y-%m-%d %H:%M"),
        })
    db.close()
    return result


@app.post("/folders")
def create_folder(folder: FolderIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_folder = FolderModel(user_id=user.id, name=folder.name)
    db.add(new_folder)
    db.commit()
    folder_id = new_folder.id
    db.close()
    return {"status": "created", "id": folder_id}


@app.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    folder = db.query(FolderModel).filter(FolderModel.id == folder_id, FolderModel.user_id == user.id).first()
    if not folder:
        db.close()
        raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다")
    db.query(FavoriteModel).filter(FavoriteModel.folder_id == folder_id).update({"folder_id": None})
    db.delete(folder)
    db.commit()
    db.close()
    return {"status": "deleted"}


class MoveToFolderIn(BaseModel):
    folder_id: int = None


@app.put("/favorites/{fav_id}/folder")
def move_favorite_to_folder(fav_id: int, body: MoveToFolderIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    fav = db.query(FavoriteModel).filter(FavoriteModel.id == fav_id, FavoriteModel.user_id == user.id).first()
    if not fav:
        db.close()
        raise HTTPException(status_code=404, detail="찜 항목을 찾을 수 없습니다")
    fav.folder_id = body.folder_id
    db.commit()
    db.close()
    return {"status": "updated"}


def suggest_transport(distance_m):
    if distance_m < 500:
        return "도보"
    elif distance_m < 3000:
        return "버스"
    else:
        return "지하철/버스"


@app.get("/folders/{folder_id}/route")
def get_folder_route(folder_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    folder = db.query(FolderModel).filter(FolderModel.id == folder_id, FolderModel.user_id == user.id).first()
    if not folder:
        db.close()
        raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다")

    favs = db.query(FavoriteModel).filter(
        FavoriteModel.folder_id == folder_id,
        FavoriteModel.fav_type == "place"
    ).order_by(FavoriteModel.created_at.asc()).all()
    db.close()

    places = []
    for f in favs:
        data = _json.loads(f.data)
        p = data.get("place", {})
        places.append({
            "name": p.get("name"),
            "address": p.get("address"),
            "lat": float(p.get("lat")),
            "lng": float(p.get("lng")),
        })

    if len(places) < 2:
        return {"folder_name": folder.name, "places": places, "segments": []}

    segments = []
    for i in range(len(places) - 1):
        a, b = places[i], places[i + 1]
        dist = haversine(a["lat"], a["lng"], b["lat"], b["lng"])
        segments.append({
            "from": a["name"],
            "to": b["name"],
            "distance": round(dist),
            "transport": suggest_transport(dist),
            "kakao_map_link": f"https://map.kakao.com/link/from/{a['name']},{a['lat']},{a['lng']}/to/{b['name']},{b['lat']},{b['lng']}",
        })

    return {"folder_name": folder.name, "places": places, "segments": segments}



@app.get("/chat/rooms")
def get_chat_rooms(current_user: str = Depends(get_current_user)):
    from sqlalchemy import func
    db = SessionLocal()
    subquery = (
        db.query(
            ChatMessageModel.room_id,
            func.max(ChatMessageModel.created_at).label("last_time"),
            func.count(ChatMessageModel.id).label("msg_count"),
        )
        .group_by(ChatMessageModel.room_id)
        .order_by(func.max(ChatMessageModel.created_at).desc())
        .limit(20)
        .all()
    )
    result = []
    for room_id, last_time, msg_count in subquery:
        last_msg = (
            db.query(ChatMessageModel)
            .filter(ChatMessageModel.room_id == room_id)
            .order_by(ChatMessageModel.created_at.desc())
            .first()
        )
        result.append({
            "room_id": room_id,
            "last_message": last_msg.message if last_msg else "",
            "last_nickname": last_msg.nickname if last_msg else "",
            "message_count": msg_count,
            "last_time": last_time.strftime("%m/%d %H:%M") if last_time else "",
        })
    db.close()
    return result

# --- 채팅 (로그인 필요, 메시지 DB 저장) ---
@app.websocket("/ws/chat/{room_id}")
async def chat_websocket(websocket: WebSocket, room_id: str, token: str = Query(None)):
    username = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
        except JWTError:
            username = None

    if not username:
        await websocket.close(code=4001)
        return

    await chat_manager.connect(room_id, websocket)

    # 최근 메시지 20개 불러와서 전송
    db = SessionLocal()
    history = db.query(ChatMessageModel).filter(ChatMessageModel.room_id == room_id).order_by(ChatMessageModel.created_at.desc()).limit(20).all()
    db.close()
    for msg in reversed(history):
        await websocket.send_json({
            "nickname": msg.nickname,
            "message": msg.message,
            "history": True,
        })

    try:
        while True:
            data = await websocket.receive_json()
            nickname = data.get("nickname", username)
            message = data.get("message", "")

            db = SessionLocal()
            new_msg = ChatMessageModel(room_id=room_id, nickname=nickname, message=message)
            db.add(new_msg)
            db.commit()
            db.close()

            await chat_manager.broadcast(room_id, {
                "nickname": nickname,
                "message": message,
            })
    except WebSocketDisconnect:
        chat_manager.disconnect(room_id, websocket)


# --- 모바일 청첩장 ---
import shutil
import uuid

class InvitationIn(BaseModel):
    groom_name: str = ""
    bride_name: str = ""
    greeting: str = ""
    wedding_date: str = ""
    venue_name: str = ""
    venue_address: str = ""
    venue_lat: str = ""
    venue_lng: str = ""


def get_or_create_invitation(db, user_id):
    inv = db.query(InvitationModel).filter(InvitationModel.user_id == user_id).first()
    if not inv:
        inv = InvitationModel(user_id=user_id)
        db.add(inv)
        db.commit()
        db.refresh(inv)
    return inv


@app.get("/invitation")
def get_my_invitation(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    inv = get_or_create_invitation(db, user.id)
    result = {
        "id": inv.id,
        "groom_name": inv.groom_name,
        "bride_name": inv.bride_name,
        "greeting": inv.greeting,
        "wedding_date": inv.wedding_date,
        "venue_name": inv.venue_name,
        "venue_address": inv.venue_address,
        "venue_lat": inv.venue_lat,
        "venue_lng": inv.venue_lng,
        "photos": _json.loads(inv.photos),
        "hero_photo": inv.hero_photo,
        "theme_color": inv.theme_color,
        "music_url": inv.music_url,
    }
    db.close()
    return result


@app.put("/invitation")
def update_my_invitation(body: InvitationIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    inv = get_or_create_invitation(db, user.id)
    inv.groom_name = body.groom_name
    inv.bride_name = body.bride_name
    inv.greeting = body.greeting
    inv.wedding_date = body.wedding_date
    inv.venue_name = body.venue_name
    inv.venue_address = body.venue_address
    inv.venue_lat = body.venue_lat
    inv.venue_lng = body.venue_lng
    inv.updated_at = now_kst()
    db.commit()
    db.close()
    return {"status": "updated"}


@app.post("/invitation/photo")
def upload_invitation_photo(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    inv = get_or_create_invitation(db, user.id)

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    user_dir = f"/var/www/uploads/invitations/{user.id}"
    os.makedirs(user_dir, exist_ok=True)
    filepath = f"{user_dir}/{filename}"

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    photo_url = f"/uploads/invitations/{user.id}/{filename}"
    photos = _json.loads(inv.photos)
    photos.append(photo_url)
    inv.photos = _json.dumps(photos)
    db.commit()
    db.close()
    return {"status": "uploaded", "url": photo_url, "photos": photos}


class PhotoDeleteIn(BaseModel):
    url: str


@app.delete("/invitation/photo")
def delete_invitation_photo(body: PhotoDeleteIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    inv = get_or_create_invitation(db, user.id)
    photos = _json.loads(inv.photos)
    if body.url in photos:
        photos.remove(body.url)
    inv.photos = _json.dumps(photos)
    db.commit()
    db.close()

    filepath = f"/var/www{body.url}"
    if os.path.exists(filepath):
        os.remove(filepath)

    return {"status": "deleted", "photos": photos}


@app.get("/venue/search")
def search_venue(query: str):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 5}
    response = requests.get(KAKAO_URL, headers=headers, params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="장소 검색에 실패했습니다")
    data = response.json()
    results = [
        {
            "name": doc["place_name"],
            "address": doc["road_address_name"] or doc["address_name"],
            "lat": doc["y"],
            "lng": doc["x"],
        }
        for doc in data["documents"]
    ]
    return results


@app.get("/invitation/public/{invitation_id}")
def get_public_invitation(invitation_id: int):
    db = SessionLocal()
    inv = db.query(InvitationModel).filter(InvitationModel.id == invitation_id).first()
    if not inv:
        db.close()
        raise HTTPException(status_code=404, detail="청첩장을 찾을 수 없습니다")
    result = {
        "id": inv.id,
        "groom_name": inv.groom_name,
        "bride_name": inv.bride_name,
        "greeting": inv.greeting,
        "wedding_date": inv.wedding_date,
        "venue_name": inv.venue_name,
        "venue_address": inv.venue_address,
        "venue_lat": inv.venue_lat,
        "venue_lng": inv.venue_lng,
        "photos": _json.loads(inv.photos),
        "hero_photo": inv.hero_photo,
        "theme_color": inv.theme_color,
        "music_url": inv.music_url,
    }
    db.close()
    return result


@app.get("/invitation/{invitation_id}/guestbook")
def get_invitation_guestbook(invitation_id: int):
    db = SessionLocal()
    messages = db.query(InvitationGuestbookModel).filter(
        InvitationGuestbookModel.invitation_id == invitation_id
    ).order_by(InvitationGuestbookModel.created_at.desc()).all()
    result = [
        {
            "id": m.id,
            "name": m.name,
            "message": m.message,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for m in messages
    ]
    db.close()
    return result


class GuestbookIn(BaseModel):
    name: str
    message: str


@app.post("/invitation/{invitation_id}/guestbook")
def post_invitation_guestbook(invitation_id: int, body: GuestbookIn):
    db = SessionLocal()
    inv = db.query(InvitationModel).filter(InvitationModel.id == invitation_id).first()
    if not inv:
        db.close()
        raise HTTPException(status_code=404, detail="청첩장을 찾을 수 없습니다")
    new_msg = InvitationGuestbookModel(invitation_id=invitation_id, name=body.name, message=body.message)
    db.add(new_msg)
    db.commit()
    db.close()
    return {"status": "posted"}
