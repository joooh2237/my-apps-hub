from fastapi import Body

def get_boss_reward_multiplier(stage: int) -> float:
    if stage % 100 == 0:
        return 10.0  # 100단위 대형 보스 10배
    elif stage % 50 == 0:
        return 5.0   # 50단위 중형 보스 5배
    elif stage % 10 == 0:
        return 2.5   # 10단위 일반 보스 2.5배
    return 1.0


MAX_LEVEL = 300

def get_required_exp(level: int) -> int:
    if level >= MAX_LEVEL:
        return 999999999
    # 지수형 레벨업 공식: 100 * (level ^ 1.85)
    return int(100 * (level ** 1.85))


ITEM_TIERS = {
    'normal':    {'name': '일반', 'color': '#a0a0a0', 'min_lvl': 1,   'mult': 1.0},
    'magic':     {'name': '고급', 'color': '#2ecc71', 'min_lvl': 10,  'mult': 1.2},
    'rare':      {'name': '희귀', 'color': '#3498db', 'min_lvl': 30,  'mult': 1.5},
    'epic':      {'name': '영웅', 'color': '#9b59b6', 'min_lvl': 60,  'mult': 2.0},
    'legendary': {'name': '전설', 'color': '#f39c12', 'min_lvl': 100, 'mult': 2.8},
    'mythic':    {'name': '신화', 'color': '#e74c3c', 'min_lvl': 180, 'mult': 4.0},
    'eternal':   {'name': '초월', 'color': '#00f5d4', 'min_lvl': 250, 'mult': 6.0},
}

import os
import math
import random
import asyncio
import requests
import urllib.parse
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional
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
    last_seen = Column(DateTime, nullable=True)

class TodoCategoryModel(Base):
    __tablename__ = "todo_categories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("todo_categories.id"), nullable=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class TodoModel(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("todo_categories.id"), nullable=True)
    content = Column(String, nullable=False)
    done = Column(String, default="false")  # "true" / "false" (Boolean 대신 문자열로 간단히)
    due_date = Column(String, default="")
    notes = Column(String, default="")
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
    groom_account = Column(String, default="")
    bride_account = Column(String, default="")
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst)


class InvitationRsvpModel(Base):
    __tablename__ = "invitation_rsvp"
    id = Column(Integer, primary_key=True, index=True)
    invitation_id = Column(Integer, ForeignKey("invitations.id"), nullable=False)
    name = Column(String, nullable=False)
    attending = Column(String, nullable=False)  # "yes" / "no"
    guest_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=now_kst)


class InvitationGuestbookModel(Base):
    __tablename__ = "invitation_guestbook"
    id = Column(Integer, primary_key=True, index=True)
    invitation_id = Column(Integer, ForeignKey("invitations.id"), nullable=False)
    name = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class GameScoreModel(Base):
    __tablename__ = "game_scores"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    game = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class NoteModel(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, default="")
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst)


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
    response = requests.get(url, headers=headers, params=params, timeout=5)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data["documents"]:
        return None
    return data["documents"][0]["thumbnail_url"]


def kakao_search(query, category_code, size=5):
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "category_group_code": category_code, "size": size}
    response = requests.get(KAKAO_URL, headers=headers, params=params, timeout=5)
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

    response = requests.get(KAKAO_URL, headers=headers, params=params, timeout=5)

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
    response = requests.get(forecast_url, params=params, timeout=5)

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
    due_date: str = ""
    category_id: Optional[int] = None
    notes: str = ""


class TodoUpdate(BaseModel):
    content: Optional[str] = None
    done: Optional[bool] = None
    due_date: Optional[str] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None


# --- 할일 카테고리 ---
class TodoCategoryIn(BaseModel):
    name: str
    parent_id: Optional[int] = None




@app.get("/todo-categories")
def get_todo_categories(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    categories = db.query(TodoCategoryModel).filter(TodoCategoryModel.user_id == user.id).order_by(TodoCategoryModel.created_at.asc()).all()

    def count_for(cat_id):
        # 해당 카테고리 + 그 하위 중주제들에 속한 할일 전부 카운트
        sub_ids = [c.id for c in categories if c.parent_id == cat_id]
        all_ids = [cat_id] + sub_ids
        total = db.query(TodoModel).filter(TodoModel.category_id.in_(all_ids)).count()
        done = db.query(TodoModel).filter(TodoModel.category_id.in_(all_ids), TodoModel.done == "true").count()
        return total, done

    result = []
    for c in categories:
        total, done = count_for(c.id)
        result.append({
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "todo_count": total,
            "done_count": done,
        })
    db.close()
    return result


@app.post("/todo-categories")
def create_todo_category(body: TodoCategoryIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_cat = TodoCategoryModel(user_id=user.id, name=body.name, parent_id=body.parent_id)
    db.add(new_cat)
    db.commit()
    cat_id = new_cat.id
    db.close()
    return {"status": "created", "id": cat_id}


@app.delete("/todo-categories/{category_id}")
def delete_todo_category(category_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    cat = db.query(TodoCategoryModel).filter(TodoCategoryModel.id == category_id, TodoCategoryModel.user_id == user.id).first()
    if not cat:
        db.close()
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")
    # 하위 중주제들도 같이 삭제
    subs = db.query(TodoCategoryModel).filter(TodoCategoryModel.parent_id == category_id).all()
    sub_ids = [s.id for s in subs]
    all_ids = [category_id] + sub_ids
    db.query(TodoModel).filter(TodoModel.category_id.in_(all_ids)).update({"category_id": None}, synchronize_session=False)
    for s in subs:
        db.delete(s)
    db.delete(cat)
    db.commit()
    db.close()
    return {"status": "deleted"}


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
            "due_date": t.due_date,
            "category_id": t.category_id,
            "notes": t.notes,
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
    new_todo = TodoModel(
        user_id=user.id,
        content=todo.content,
        done="false",
        due_date=todo.due_date,
        category_id=todo.category_id,
        notes=todo.notes,
    )
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
    if body.due_date is not None:
        todo.due_date = body.due_date
    if body.category_id is not None:
        todo.category_id = body.category_id
    if body.notes is not None:
        todo.notes = body.notes
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
    hero_photo: str = ""
    theme_color: str = "#b08a6a"
    music_url: str = ""
    groom_account: str = ""
    bride_account: str = ""


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
        "groom_account": inv.groom_account,
        "bride_account": inv.bride_account,
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
    inv.hero_photo = body.hero_photo
    inv.theme_color = body.theme_color
    inv.music_url = body.music_url
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
    response = requests.get(KAKAO_URL, headers=headers, params=params, timeout=5)
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
        "groom_account": inv.groom_account,
        "bride_account": inv.bride_account,
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


# --- RSVP (참석 여부 응답) ---
class RsvpIn(BaseModel):
    name: str
    attending: str  # "yes" / "no"
    guest_count: int = 1


@app.get("/invitation/{invitation_id}/rsvp")
def get_invitation_rsvp(invitation_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    inv = db.query(InvitationModel).filter(InvitationModel.id == invitation_id, InvitationModel.user_id == user.id).first()
    if not inv:
        db.close()
        raise HTTPException(status_code=404, detail="청첩장을 찾을 수 없습니다")

    responses = db.query(InvitationRsvpModel).filter(InvitationRsvpModel.invitation_id == invitation_id).order_by(InvitationRsvpModel.created_at.desc()).all()
    yes_count = sum(r.guest_count for r in responses if r.attending == "yes")
    no_count = sum(1 for r in responses if r.attending == "no")

    result = {
        "total_responses": len(responses),
        "attending_count": yes_count,
        "not_attending_count": no_count,
        "responses": [
            {
                "id": r.id,
                "name": r.name,
                "attending": r.attending,
                "guest_count": r.guest_count,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for r in responses
        ],
    }
    db.close()
    return result


@app.post("/invitation/{invitation_id}/rsvp")
def post_invitation_rsvp(invitation_id: int, body: RsvpIn):
    db = SessionLocal()
    inv = db.query(InvitationModel).filter(InvitationModel.id == invitation_id).first()
    if not inv:
        db.close()
        raise HTTPException(status_code=404, detail="청첩장을 찾을 수 없습니다")
    new_rsvp = InvitationRsvpModel(
        invitation_id=invitation_id,
        name=body.name,
        attending=body.attending,
        guest_count=body.guest_count,
    )
    db.add(new_rsvp)
    db.commit()
    db.close()
    return {"status": "submitted"}


# --- 실시간 로그인 현황 (하트비트 방식) ---
@app.post("/heartbeat")
def heartbeat(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    user.last_seen = now_kst()
    db.commit()
    db.close()
    return {"status": "ok"}


@app.get("/online-users")
def get_online_users(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    cutoff = now_kst() - timedelta(minutes=5)
    users = db.query(UserModel).filter(UserModel.last_seen != None, UserModel.last_seen >= cutoff).all()
    result = [{"username": u.username} for u in users]
    db.close()
    return result


# --- 오목 게임 ---
import random as _random

omok_rooms = {}  # room_id -> {"board": [[None]*15 for _ in range(15)], "players": {ws: color}, "turn": "black", "usernames": {}}

def create_omok_room():
    return {
        "board": [[None for _ in range(15)] for _ in range(15)],
        "connections": [],  # list of (websocket, color_or_None, username)
        "turn": "black",
        "winner": None,
    }

def check_omok_winner(board, row, col, color):
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        r, c = row + dr, col + dc
        while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == color:
            count += 1
            r += dr
            c += dc
        r, c = row - dr, col - dc
        while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == color:
            count += 1
            r -= dr
            c -= dc
        if count >= 5:
            return True
    return False


@app.websocket("/ws/omok/{room_id}")
async def omok_websocket(websocket: WebSocket, room_id: str, token: str = Query(None)):
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

    await websocket.accept()

    if room_id not in omok_rooms:
        omok_rooms[room_id] = create_omok_room()
    room = omok_rooms[room_id]

    assigned_color = None
    existing_colors = [c for (_, c, _) in room["connections"] if c]
    if "black" not in existing_colors:
        assigned_color = "black"
    elif "white" not in existing_colors:
        assigned_color = "white"
    # else: 관전자 (color=None)

    room["connections"].append((websocket, assigned_color, username))

    async def broadcast_state():
        dead = []
        for conn_ws, _, _ in room["connections"]:
            try:
                await conn_ws.send_json({
                    "type": "state",
                    "board": room["board"],
                    "turn": room["turn"],
                    "winner": room["winner"],
                    "players": [{"username": u, "color": c} for (_, c, u) in room["connections"] if c],
                })
            except Exception:
                dead.append(conn_ws)
        for d in dead:
            room["connections"] = [c for c in room["connections"] if c[0] != d]

    try:
        await websocket.send_json({"type": "assigned", "color": assigned_color})
        await broadcast_state()

        while True:
            data = await websocket.receive_json()
            colors_present = set(c for (_, c, _) in room["connections"] if c)
            both_present = "black" in colors_present and "white" in colors_present
            if data.get("type") == "place" and assigned_color and room["winner"] is None and both_present:
                row, col = data.get("row"), data.get("col")
                if 0 <= row < 15 and 0 <= col < 15 and room["board"][row][col] is None and room["turn"] == assigned_color:
                    room["board"][row][col] = assigned_color
                    if check_omok_winner(room["board"], row, col, assigned_color):
                        room["winner"] = assigned_color
                    else:
                        room["turn"] = "white" if assigned_color == "black" else "black"
                    await broadcast_state()
            elif data.get("type") == "reset":
                room["board"] = [[None for _ in range(15)] for _ in range(15)]
                room["turn"] = "black"
                room["winner"] = None
                await broadcast_state()
    except WebSocketDisconnect:
        room["connections"] = [c for c in room["connections"] if c[0] != websocket]
        await broadcast_state()


# --- 게임 랭킹보드 ---
class ScoreIn(BaseModel):
    game: str
    score: int


@app.post("/game-scores")
def submit_score(body: ScoreIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_score = GameScoreModel(user_id=user.id, game=body.game, score=body.score)
    db.add(new_score)
    db.commit()
    db.close()
    return {"status": "submitted"}


@app.get("/game-scores/{game}")
def get_leaderboard(game: str):
    db = SessionLocal()
    from sqlalchemy import func
    subq = (
        db.query(
            GameScoreModel.user_id,
            func.max(GameScoreModel.score).label("best_score")
        )
        .filter(GameScoreModel.game == game)
        .group_by(GameScoreModel.user_id)
        .subquery()
    )
    rows = (
        db.query(UserModel.username, subq.c.best_score)
        .join(subq, UserModel.id == subq.c.user_id)
        .order_by(subq.c.best_score.desc())
        .limit(10)
        .all()
    )
    result = [{"username": r[0], "score": r[1]} for r in rows]
    db.close()
    return result


# --- 노트맵 (개인 위키) ---
import re as _re

class NoteIn(BaseModel):
    title: str
    content: str = ""


def extract_links(content: str):
    return list(set(_re.findall(r'\[\[(.+?)\]\]', content)))


@app.get("/notes")
def get_notes(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    notes = db.query(NoteModel).filter(NoteModel.user_id == user.id).order_by(NoteModel.updated_at.desc()).all()
    result = [
        {
            "id": n.id,
            "title": n.title,
            "content": n.content,
            "links": extract_links(n.content),
            "updated_at": n.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
        for n in notes
    ]
    db.close()
    return result


@app.get("/notes/{note_id}")
def get_note(note_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    note = db.query(NoteModel).filter(NoteModel.id == note_id, NoteModel.user_id == user.id).first()
    if not note:
        db.close()
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")

    all_notes = db.query(NoteModel).filter(NoteModel.user_id == user.id).all()
    backlinks = [
        {"id": n.id, "title": n.title}
        for n in all_notes
        if note.title in extract_links(n.content) and n.id != note.id
    ]

    result = {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "links": extract_links(note.content),
        "backlinks": backlinks,
        "updated_at": note.updated_at.strftime("%Y-%m-%d %H:%M"),
    }
    db.close()
    return result


@app.post("/notes")
def create_note(body: NoteIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    new_note = NoteModel(user_id=user.id, title=body.title, content=body.content)
    db.add(new_note)
    db.commit()
    note_id = new_note.id
    db.close()
    return {"status": "created", "id": note_id}


@app.put("/notes/{note_id}")
def update_note(note_id: int, body: NoteIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    note = db.query(NoteModel).filter(NoteModel.id == note_id, NoteModel.user_id == user.id).first()
    if not note:
        db.close()
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    note.title = body.title
    note.content = body.content
    note.updated_at = now_kst()
    db.commit()
    db.close()
    return {"status": "updated"}


@app.delete("/notes/{note_id}")
def delete_note(note_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    note = db.query(NoteModel).filter(NoteModel.id == note_id, NoteModel.user_id == user.id).first()
    if not note:
        db.close()
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")
    db.delete(note)
    db.commit()
    db.close()
    return {"status": "deleted"}


@app.get("/notes-by-title/{title}")
def get_note_by_title(title: str, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    note = db.query(NoteModel).filter(NoteModel.title == title, NoteModel.user_id == user.id).first()
    result = {"id": note.id} if note else None
    db.close()
    return result


# --- 섯다 (가상 포인트, 실제 화폐 아님) ---
seotda_rooms = {}

SEOTDA_ANTE = 100
SEOTDA_PING_AMOUNT = 200


def create_seotda_deck():
    deck = []
    for month in range(1, 13):
        if month in (1, 3, 8):
            deck.append({"month": month, "is_gwang": True})
            for _ in range(3):
                deck.append({"month": month, "is_gwang": False})
        else:
            for _ in range(4):
                deck.append({"month": month, "is_gwang": False})
    _random.shuffle(deck)
    return deck


def seotda_hand_rank(cards):
    m1, m2 = sorted([cards[0]["month"], cards[1]["month"]])
    g1 = cards[0]["is_gwang"]
    g2 = cards[1]["is_gwang"]

    # 광땡
    if g1 and g2 and m1 != m2 and m1 in (1, 3, 8) and m2 in (1, 3, 8):
        combo_value = {(3, 8): 3, (1, 8): 2, (1, 3): 1}[(m1, m2)]
        name = {3: "38광땡", 2: "18광땡", 1: "13광땡"}[combo_value]
        return (5, combo_value, name)

    # 땡 (페어)
    if m1 == m2:
        return (4, m1, f"{m1}땡")

    # 특수 족보
    special = {
        (1, 2): (3, 5, "알리"),
        (1, 4): (3, 4, "독사"),
        (1, 9): (3, 3, "구삥"),
        (4, 10): (3, 2, "장삼"),
        (4, 6): (3, 1, "세륙"),
    }
    if (m1, m2) in special:
        return special[(m1, m2)]

    # 일반 끗
    value = (m1 + m2) % 10
    if value == 0:
        return (1, 0, "망통")
    return (2, value, f"{value}끗")


def seotda_best_rank(cards):
    """2장이면 그대로, 3장이면 그 중 최고의 2장 조합으로 판정"""
    if len(cards) <= 2:
        return seotda_hand_rank(cards)
    best = None
    n = len(cards)
    for i in range(n):
        for j in range(i + 1, n):
            r = seotda_hand_rank([cards[i], cards[j]])
            if best is None or (r[0], r[1]) > (best[0], best[1]):
                best = r
    return best


def seotda_ai_score(hand):
    """AI 판단용 점수 (1장일 땐 대략적인 감, 2장 이상이면 실제 족보 기반)"""
    if len(hand) == 1:
        c = hand[0]
        score = c["month"]
        if c["is_gwang"]:
            score += 8
        return score
    rank = seotda_best_rank(hand)
    return rank[0] * 10 + rank[1]


def seotda_ai_decide_move(hand, current_max_bet, my_contrib, pot, round_num, max_rounds):
    score = seotda_ai_score(hand)
    if len(hand) == 1:
        strong = score >= 9
        medium = score >= 5
    else:
        strong = score >= 40   # 땡 이상
        medium = score >= 20   # 끗 4 이상

    if current_max_bet == 0:
        if strong:
            r = _random.random()
            if r < 0.55:
                return "ping"
            elif r < 0.85:
                return "half"
            else:
                return "ttadang"
        return "check"

    diff = current_max_bet - my_contrib
    if strong:
        return "ttadang" if _random.random() < 0.5 else "call"
    if medium:
        return "call"
    if round_num < max_rounds and diff <= SEOTDA_PING_AMOUNT:
        return "call"
    return "die"


def create_seotda_room():
    return {
        "chips": {},  # username -> chips
        "seats": [],  # [(websocket, seat, username)]  seat: 'p1'/'p2'/None
        "phase": "idle",  # idle, betting, result
        "mode": "2",  # "2" 또는 "3" - 사용할 카드 장수
        "deck": [],
        "hands": {},  # seat -> [card, ...] (진행 중 계속 늘어남)
        "pot": 0,
        "turn": None,  # 'p1' or 'p2'
        "round_num": 0,  # 현재까지 배분된 카드 라운드 수
        "current_max_bet": 0,  # 이번 베팅라운드 최고 베팅액
        "bet_this_round": {},  # seat -> 이번 베팅라운드에 낸 금액
        "checks_in_row": 0,
        "result": None,
        "ai_seat": None,
    }


def seotda_deal_next(room):
    for seat in ("p1", "p2"):
        room["hands"][seat].append(room["deck"].pop())
    room["round_num"] += 1
    room["current_max_bet"] = 0
    room["bet_this_round"] = {"p1": 0, "p2": 0}
    room["checks_in_row"] = 0
    room["turn"] = "p1"
    room["phase"] = "betting"


def seotda_finish_round_and_advance(room):
    max_rounds = int(room["mode"])
    if room["round_num"] < max_rounds:
        seotda_deal_next(room)
        return

    rank_p1 = seotda_best_rank(room["hands"]["p1"])
    rank_p2 = seotda_best_rank(room["hands"]["p2"])
    p1_user = next(u for (_, s, u) in room["seats"] if s == "p1")
    p2_user = next(u for (_, s, u) in room["seats"] if s == "p2")

    if rank_p1[0] == rank_p2[0] and rank_p1[1] == rank_p2[1]:
        winner_seat = "p1"  # 동점은 선(p1) 승
    else:
        winner_seat = "p1" if rank_p1 > rank_p2 else "p2"

    winner_user = p1_user if winner_seat == "p1" else p2_user
    room["chips"][winner_user] += room["pot"]
    room["phase"] = "result"
    room["result"] = {
        "winner_seat": winner_seat,
        "reason": "showdown",
        "p1_hand_name": rank_p1[2],
        "p2_hand_name": rank_p2[2],
    }


def apply_seotda_move(room, seat, move):
    user = next(u for (_, s, u) in room["seats"] if s == seat)
    opp_seat = "p2" if seat == "p1" else "p1"
    opp_user = next(u for (_, s, u) in room["seats"] if s == opp_seat)

    if move == "die":
        room["chips"][opp_user] += room["pot"]
        room["phase"] = "result"
        room["result"] = {"winner_seat": opp_seat, "reason": "die"}
        return

    if move == "check":
        if room["current_max_bet"] != 0:
            return
        room["checks_in_row"] += 1
        if room["checks_in_row"] >= 2:
            seotda_finish_round_and_advance(room)
        else:
            room["turn"] = opp_seat
        return

    if move == "ping":
        if room["current_max_bet"] != 0:
            return
        amount = max(0, min(SEOTDA_PING_AMOUNT, room["chips"][user]))
        room["chips"][user] -= amount
        room["pot"] += amount
        room["bet_this_round"][seat] = amount
        room["current_max_bet"] = amount
        room["checks_in_row"] = 0
        room["turn"] = opp_seat
        return

    if move == "call":
        diff = room["current_max_bet"] - room["bet_this_round"].get(seat, 0)
        diff = max(0, min(diff, room["chips"][user]))
        room["chips"][user] -= diff
        room["pot"] += diff
        room["bet_this_round"][seat] = room["bet_this_round"].get(seat, 0) + diff
        seotda_finish_round_and_advance(room)
        return

    if move == "half":
        raise_amount = max(SEOTDA_PING_AMOUNT // 2, room["pot"] // 2)
        if room["current_max_bet"] == 0:
            # 오픈 베팅으로 사용
            amount = max(0, min(raise_amount, room["chips"][user]))
            room["chips"][user] -= amount
            room["pot"] += amount
            room["bet_this_round"][seat] = amount
            room["current_max_bet"] = amount
            room["checks_in_row"] = 0
            room["turn"] = opp_seat
            return
        diff = room["current_max_bet"] - room["bet_this_round"].get(seat, 0)
        total = max(0, min(diff + raise_amount, room["chips"][user]))
        room["chips"][user] -= total
        room["pot"] += total
        room["bet_this_round"][seat] = room["bet_this_round"].get(seat, 0) + total
        room["current_max_bet"] = room["bet_this_round"][seat]
        room["checks_in_row"] = 0
        room["turn"] = opp_seat
        return

    if move == "ttadang":
        if room["current_max_bet"] == 0:
            # 오픈 베팅으로 사용 (삥의 2배)
            amount = max(0, min(SEOTDA_PING_AMOUNT * 2, room["chips"][user]))
            room["chips"][user] -= amount
            room["pot"] += amount
            room["bet_this_round"][seat] = amount
            room["current_max_bet"] = amount
            room["checks_in_row"] = 0
            room["turn"] = opp_seat
            return
        new_max = room["current_max_bet"] * 2
        diff = new_max - room["bet_this_round"].get(seat, 0)
        diff = max(0, min(diff, room["chips"][user]))
        room["chips"][user] -= diff
        room["pot"] += diff
        room["bet_this_round"][seat] = room["bet_this_round"].get(seat, 0) + diff
        room["current_max_bet"] = room["bet_this_round"][seat]
        room["checks_in_row"] = 0
        room["turn"] = opp_seat
        return

@app.websocket("/ws/seotda/{room_id}")
async def seotda_websocket(websocket: WebSocket, room_id: str, token: str = Query(None)):
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

    await websocket.accept()

    if room_id not in seotda_rooms:
        seotda_rooms[room_id] = create_seotda_room()
    room = seotda_rooms[room_id]

    if username not in room["chips"]:
        room["chips"][username] = 10000

    assigned_seat = None
    existing_seats = [s for (_, s, _) in room["seats"] if s]
    if "p1" not in existing_seats:
        assigned_seat = "p1"
    elif "p2" not in existing_seats:
        assigned_seat = "p2"

    room["seats"].append((websocket, assigned_seat, username))

    async def broadcast_state():
        dead = []
        for conn_ws, conn_seat, conn_username in room["seats"]:
            if conn_ws is None:
                continue
            payload = {
                "type": "state",
                "phase": room["phase"],
                "mode": room["mode"],
                "pot": room["pot"],
                "turn": room["turn"],
                "chips": room["chips"],
                "seats": [{"seat": s, "username": u} for (_, s, u) in room["seats"] if s],
                "my_seat": conn_seat,
                "result": room["result"],
                "ai_seat": room["ai_seat"],
                "round_num": room["round_num"],
                "max_rounds": int(room["mode"]),
                "current_max_bet": room["current_max_bet"],
                "bet_this_round": room["bet_this_round"],
            }
            my_hand = room["hands"].get(conn_seat) if conn_seat else None
            payload["my_hand"] = my_hand
            if room["phase"] == "result" and room["result"]:
                payload["all_hands"] = room["hands"]
            try:
                await conn_ws.send_json(payload)
            except Exception:
                dead.append(conn_ws)
        for d in dead:
            room["seats"] = [c for c in room["seats"] if c[0] != d]

    async def maybe_ai_turn():
        if not room["ai_seat"]:
            return
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        await asyncio.sleep(1.2)
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        hand = room["hands"][room["ai_seat"]]
        my_contrib = room["bet_this_round"].get(room["ai_seat"], 0)
        move = seotda_ai_decide_move(
            hand, room["current_max_bet"], my_contrib, room["pot"],
            room["round_num"], int(room["mode"])
        )
        apply_seotda_move(room, room["ai_seat"], move)
        await broadcast_state()
        await maybe_ai_turn()

    try:
        await broadcast_state()

        while True:
            data = await websocket.receive_json()
            action = data.get("type")

            if action == "set_mode":
                if room["phase"] == "idle" and data.get("mode") in ("2", "3"):
                    room["mode"] = data.get("mode")
                    await broadcast_state()

            elif action == "add_ai":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if "p2" not in seats_present and "p1" in seats_present:
                    room["seats"].append((None, "p2", "AI 🤖"))
                    room["chips"]["AI 🤖"] = 10000
                    room["ai_seat"] = "p2"
                    await broadcast_state()

            elif action == "start_hand":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if seats_present != {"p1", "p2"}:
                    continue
                if room["phase"] not in ("idle", "result"):
                    continue

                for uname in room["chips"]:
                    if room["chips"][uname] < SEOTDA_ANTE:
                        room["chips"][uname] = 10000

                deck = create_seotda_deck()
                p1_user = next(u for (_, s, u) in room["seats"] if s == "p1")
                p2_user = next(u for (_, s, u) in room["seats"] if s == "p2")
                room["chips"][p1_user] -= SEOTDA_ANTE
                room["chips"][p2_user] -= SEOTDA_ANTE
                room["pot"] = SEOTDA_ANTE * 2
                room["deck"] = deck
                room["hands"] = {"p1": [deck.pop()], "p2": [deck.pop()]}
                room["round_num"] = 1
                room["current_max_bet"] = 0
                room["bet_this_round"] = {"p1": 0, "p2": 0}
                room["checks_in_row"] = 0
                room["phase"] = "betting"
                room["turn"] = "p1"
                room["result"] = None
                await broadcast_state()

            elif action == "action":
                move = data.get("move")
                my_seat = next((s for (ws, s, u) in room["seats"] if ws == websocket), None)
                if room["phase"] != "betting" or my_seat != room["turn"]:
                    continue
                if move not in ("die", "check", "ping", "call", "half", "ttadang"):
                    continue
                apply_seotda_move(room, my_seat, move)
                await broadcast_state()
                await maybe_ai_turn()

    except WebSocketDisconnect:
        room["seats"] = [c for c in room["seats"] if c[0] != websocket]
        await broadcast_state()
# --- 바둑이 (가상 포인트) ---
from itertools import combinations as _combinations

baduki_rooms = {}

def create_baduki_deck():
    deck = []
    for suit in ["S", "H", "D", "C"]:
        for rank in range(1, 14):
            deck.append({"rank": rank, "suit": suit})
    _random.shuffle(deck)
    return deck


def baduki_best_subset(cards):
    for size in [4, 3, 2, 1]:
        candidates = []
        for combo in _combinations(cards, size):
            suits = set(c["suit"] for c in combo)
            ranks = set(c["rank"] for c in combo)
            if len(suits) == size and len(ranks) == size:
                candidates.append(combo)
        if candidates:
            best_combo = min(
                candidates,
                key=lambda combo: tuple(sorted([c["rank"] for c in combo], reverse=True))
            )
            values = tuple(sorted([c["rank"] for c in best_combo], reverse=True))
            return (size, tuple(-v for v in values))  # 비교용: size 클수록 좋고, 값은 작을수록 좋음
    single = min(cards, key=lambda c: c["rank"])
    return (1, (-single["rank"],))


BADUKI_ANTE = 100
BADUKI_BET = 200


def create_baduki_room():
    return {
        "chips": {},
        "seats": [],
        "phase": "idle",  # idle, draw, betting, result
        "hands": {},  # seat -> [4 cards]
        "draw_done": {},
        "pot": 0,
        "turn": None,
        "result": None,
        "ai_seat": None,
        "deck": [],
        "draw_round": 0,  # 1=아침, 2=점심, 3=저녁
        "bet_this_round": False,
    }


def baduki_ai_discard_indices(hand):
    best_size, _ = baduki_best_subset(hand)
    for combo in _combinations(range(4), best_size):
        combo_cards = [hand[i] for i in combo]
        suits = set(c["suit"] for c in combo_cards)
        ranks = set(c["rank"] for c in combo_cards)
        if len(suits) == best_size and len(ranks) == best_size:
            return [i for i in range(4) if i not in combo]
    return []


def baduki_ai_decide(hand):
    size, _ = baduki_best_subset(hand)
    if size >= 3:
        return True
    if size == 2:
        return _random.random() < 0.5
    return False


@app.websocket("/ws/baduki/{room_id}")
async def baduki_websocket(websocket: WebSocket, room_id: str, token: str = Query(None)):
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

    await websocket.accept()

    if room_id not in baduki_rooms:
        baduki_rooms[room_id] = create_baduki_room()
    room = baduki_rooms[room_id]

    if username not in room["chips"]:
        room["chips"][username] = 10000

    assigned_seat = None
    existing_seats = [s for (_, s, _) in room["seats"] if s]
    if "p1" not in existing_seats:
        assigned_seat = "p1"
    elif "p2" not in existing_seats:
        assigned_seat = "p2"

    room["seats"].append((websocket, assigned_seat, username))

    async def broadcast_state():
        dead = []
        for conn_ws, conn_seat, conn_username in room["seats"]:
            if conn_ws is None:
                continue
            payload = {
                "type": "state",
                "phase": room["phase"],
                "pot": room["pot"],
                "turn": room["turn"],
                "chips": room["chips"],
                "seats": [{"seat": s, "username": u} for (_, s, u) in room["seats"] if s],
                "my_seat": conn_seat,
                "result": room["result"],
                "ai_seat": room["ai_seat"],
                "draw_done": room["draw_done"],
            }
            my_hand = room["hands"].get(conn_seat) if conn_seat else None
            payload["my_hand"] = my_hand
            if room["phase"] == "result" and room["result"]:
                payload["all_hands"] = room["hands"]
            try:
                await conn_ws.send_json(payload)
            except Exception:
                dead.append(conn_ws)
        for d in dead:
            room["seats"] = [c for c in room["seats"] if c[0] != d]

    def apply_baduki_move(seat, move):
        user = next(u for (_, s, u) in room["seats"] if s == seat)
        opp_seat = "p2" if seat == "p1" else "p1"
        opp_user = next(u for (_, s, u) in room["seats"] if s == opp_seat)
        if move == "fold":
            room["chips"][opp_user] += room["pot"]
            room["phase"] = "result"
            room["result"] = {"winner_seat": opp_seat, "reason": "fold"}
        elif move == "bet":
            room["chips"][user] -= BADUKI_BET
            room["pot"] += BADUKI_BET
            room["turn"] = opp_seat
            room["bet_this_round"] = True
        elif move == "call":
            room["chips"][user] -= BADUKI_BET
            room["pot"] += BADUKI_BET
            if room["draw_round"] >= 3:
                rank_p1 = baduki_best_subset(room["hands"]["p1"])
                rank_p2 = baduki_best_subset(room["hands"]["p2"])
                winner_seat = "p1" if rank_p1 >= rank_p2 else "p2"
                winner_user = next(u for (_, s, u) in room["seats"] if s == winner_seat)
                room["chips"][winner_user] += room["pot"]
                room["phase"] = "result"
                room["result"] = {
                    "winner_seat": winner_seat,
                    "reason": "showdown",
                    "p1_size": rank_p1[0],
                    "p2_size": rank_p2[0],
                }
            else:
                room["draw_round"] += 1
                room["draw_done"] = {"p1": False, "p2": False}
                room["bet_this_round"] = False
                room["phase"] = "draw"
                room["turn"] = None

    async def maybe_ai_bet_turn():
        if not room["ai_seat"]:
            return
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        await asyncio.sleep(1.2)
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        hand = room["hands"][room["ai_seat"]]
        should_act = baduki_ai_decide(hand)
        if not room["bet_this_round"]:
            move = "bet" if should_act else "fold"
        else:
            move = "call" if should_act else "fold"
        apply_baduki_move(room["ai_seat"], move)
        await broadcast_state()
        if room["phase"] == "draw":
            await maybe_ai_draw()

    async def maybe_ai_draw():
        if not room["ai_seat"]:
            return
        if room["phase"] != "draw" or room["draw_done"].get(room["ai_seat"]):
            return
        await asyncio.sleep(1.0)
        if room["phase"] != "draw" or room["draw_done"].get(room["ai_seat"]):
            return
        ai_seat = room["ai_seat"]
        hand = room["hands"][ai_seat]
        discard_idx = baduki_ai_discard_indices(hand)
        for i in discard_idx:
            hand[i] = room["deck"].pop()
        room["hands"][ai_seat] = hand
        room["draw_done"][ai_seat] = True
        if all(room["draw_done"].values()):
            room["phase"] = "betting"
            room["turn"] = "p1"
        await broadcast_state()

    try:
        await broadcast_state()

        while True:
            data = await websocket.receive_json()
            action = data.get("type")

            if action == "add_ai":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if "p2" not in seats_present and "p1" in seats_present:
                    room["seats"].append((None, "p2", "AI 🤖"))
                    room["chips"]["AI 🤖"] = 10000
                    room["ai_seat"] = "p2"
                    await broadcast_state()

            elif action == "start_hand":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if seats_present != {"p1", "p2"}:
                    continue
                if room["phase"] not in ("idle", "result"):
                    continue

                for uname in room["chips"]:
                    if room["chips"][uname] < BADUKI_ANTE:
                        room["chips"][uname] = 10000

                deck = create_baduki_deck()
                p1_user = next(u for (_, s, u) in room["seats"] if s == "p1")
                p2_user = next(u for (_, s, u) in room["seats"] if s == "p2")
                room["chips"][p1_user] -= BADUKI_ANTE
                room["chips"][p2_user] -= BADUKI_ANTE
                room["pot"] = BADUKI_ANTE * 2
                room["hands"] = {
                    "p1": [deck.pop() for _ in range(4)],
                    "p2": [deck.pop() for _ in range(4)],
                }
                room["deck"] = deck
                room["draw_done"] = {"p1": False, "p2": False}
                room["draw_round"] = 1
                room["bet_this_round"] = False
                room["phase"] = "draw"
                room["turn"] = None
                room["result"] = None
                await broadcast_state()
                await maybe_ai_draw()

            elif action == "draw":
                my_seat = next((s for (ws, s, u) in room["seats"] if ws == websocket), None)
                if room["phase"] != "draw" or not my_seat or room["draw_done"].get(my_seat):
                    continue
                discard = data.get("discard", [])
                hand = room["hands"][my_seat]
                for i in discard:
                    if 0 <= i < 4:
                        hand[i] = room["deck"].pop()
                room["hands"][my_seat] = hand
                room["draw_done"][my_seat] = True
                if all(room["draw_done"].values()):
                    room["phase"] = "betting"
                    room["turn"] = "p1"
                    room["bet_this_round"] = False
                await broadcast_state()
                await maybe_ai_bet_turn()

            elif action == "action":
                move = data.get("move")
                my_seat = next((s for (ws, s, u) in room["seats"] if ws == websocket), None)
                if room["phase"] != "betting" or my_seat != room["turn"]:
                    continue
                apply_baduki_move(my_seat, move)
                await broadcast_state()
                if room["phase"] == "draw":
                    await maybe_ai_draw()
                else:
                    await maybe_ai_bet_turn()

    except WebSocketDisconnect:
        room["seats"] = [c for c in room["seats"] if c[0] != websocket]
        await broadcast_state()


# --- 세븐포커 (가상 포인트) ---
sevenpoker_rooms = {}

POKER_HAND_NAMES = {
    8: "스트레이트 플러시",
    7: "포카드",
    6: "풀하우스",
    5: "플러시",
    4: "스트레이트",
    3: "트리플",
    2: "투페어",
    1: "원페어",
    0: "하이카드",
}


def create_poker_deck():
    deck = []
    for suit in ["S", "H", "D", "C"]:
        for rank in range(2, 15):  # 2~14 (14=A)
            deck.append({"rank": rank, "suit": suit})
    _random.shuffle(deck)
    return deck


def evaluate_5cards(cards):
    ranks = sorted([c["rank"] for c in cards], reverse=True)
    suits = [c["suit"] for c in cards]
    is_flush = len(set(suits)) == 1

    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts = sorted(rank_counts.items(), key=lambda x: (-x[1], -x[0]))
    count_pattern = [c[1] for c in counts]

    unique_ranks = sorted(set(ranks), reverse=True)
    is_straight = False
    straight_high = None
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
            straight_high = unique_ranks[0]
        elif unique_ranks == [14, 5, 4, 3, 2]:
            is_straight = True
            straight_high = 5

    if is_straight and is_flush:
        return (8, straight_high)
    if count_pattern == [4, 1]:
        return (7, counts[0][0], counts[1][0])
    if count_pattern == [3, 2]:
        return (6, counts[0][0], counts[1][0])
    if is_flush:
        return (5,) + tuple(ranks)
    if is_straight:
        return (4, straight_high)
    if count_pattern == [3, 1, 1]:
        kickers = sorted([counts[1][0], counts[2][0]], reverse=True)
        return (3, counts[0][0]) + tuple(kickers)
    if count_pattern == [2, 2, 1]:
        pairs = sorted([counts[0][0], counts[1][0]], reverse=True)
        return (2,) + tuple(pairs) + (counts[2][0],)
    if count_pattern == [2, 1, 1, 1]:
        kickers = sorted([counts[1][0], counts[2][0], counts[3][0]], reverse=True)
        return (1, counts[0][0]) + tuple(kickers)
    return (0,) + tuple(ranks)


def evaluate_best_hand(cards7):
    best = None
    for combo in _combinations(cards7, 5):
        score = evaluate_5cards(list(combo))
        if best is None or score > best:
            best = score
    return best


POKER_ANTE = 100
POKER_BET = 200


def create_poker_room():
    return {
        "chips": {},
        "seats": [],
        "phase": "idle",  # idle, betting, result
        "hands": {},  # seat -> [7 cards]
        "pot": 0,
        "turn": None,
        "result": None,
        "ai_seat": None,
    }


def poker_ai_decide(hand7):
    score = evaluate_best_hand(hand7)
    category = score[0]
    if category >= 3:
        return True
    if category >= 1:
        return _random.random() < 0.6
    return _random.random() < 0.25


@app.websocket("/ws/sevenpoker/{room_id}")
async def sevenpoker_websocket(websocket: WebSocket, room_id: str, token: str = Query(None)):
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

    await websocket.accept()

    if room_id not in sevenpoker_rooms:
        sevenpoker_rooms[room_id] = create_poker_room()
    room = sevenpoker_rooms[room_id]

    if username not in room["chips"]:
        room["chips"][username] = 10000

    assigned_seat = None
    existing_seats = [s for (_, s, _) in room["seats"] if s]
    if "p1" not in existing_seats:
        assigned_seat = "p1"
    elif "p2" not in existing_seats:
        assigned_seat = "p2"

    room["seats"].append((websocket, assigned_seat, username))

    async def broadcast_state():
        dead = []
        for conn_ws, conn_seat, conn_username in room["seats"]:
            if conn_ws is None:
                continue
            payload = {
                "type": "state",
                "phase": room["phase"],
                "pot": room["pot"],
                "turn": room["turn"],
                "chips": room["chips"],
                "seats": [{"seat": s, "username": u} for (_, s, u) in room["seats"] if s],
                "my_seat": conn_seat,
                "result": room["result"],
                "ai_seat": room["ai_seat"],
            }
            my_hand = room["hands"].get(conn_seat) if conn_seat else None
            payload["my_hand"] = my_hand
            if room["phase"] == "result" and room["result"]:
                payload["all_hands"] = room["hands"]
            try:
                await conn_ws.send_json(payload)
            except Exception:
                dead.append(conn_ws)
        for d in dead:
            room["seats"] = [c for c in room["seats"] if c[0] != d]

    def apply_poker_move(seat, move):
        user = next(u for (_, s, u) in room["seats"] if s == seat)
        opp_seat = "p2" if seat == "p1" else "p1"
        opp_user = next(u for (_, s, u) in room["seats"] if s == opp_seat)

        if move == "fold":
            room["chips"][opp_user] += room["pot"]
            room["phase"] = "result"
            room["result"] = {"winner_seat": opp_seat, "reason": "fold"}

        elif move == "bet":
            room["chips"][user] -= POKER_BET
            room["pot"] += POKER_BET
            room["turn"] = opp_seat

        elif move == "call":
            room["chips"][user] -= POKER_BET
            room["pot"] += POKER_BET
            score_p1 = evaluate_best_hand(room["hands"]["p1"])
            score_p2 = evaluate_best_hand(room["hands"]["p2"])
            winner_seat = "p1" if score_p1 >= score_p2 else "p2"
            winner_user = next(u for (_, s, u) in room["seats"] if s == winner_seat)
            room["chips"][winner_user] += room["pot"]
            room["phase"] = "result"
            room["result"] = {
                "winner_seat": winner_seat,
                "reason": "showdown",
                "p1_hand_name": POKER_HAND_NAMES[score_p1[0]],
                "p2_hand_name": POKER_HAND_NAMES[score_p2[0]],
            }

    async def maybe_ai_turn():
        if not room["ai_seat"]:
            return
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        await asyncio.sleep(1.2)
        if room["phase"] != "betting" or room["turn"] != room["ai_seat"]:
            return
        hand = room["hands"][room["ai_seat"]]
        should_act = poker_ai_decide(hand)
        if room["pot"] == POKER_ANTE * 2:
            move = "bet" if should_act else "fold"
        else:
            move = "call" if should_act else "fold"
        apply_poker_move(room["ai_seat"], move)
        await broadcast_state()

    try:
        await broadcast_state()

        while True:
            data = await websocket.receive_json()
            action = data.get("type")

            if action == "add_ai":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if "p2" not in seats_present and "p1" in seats_present:
                    room["seats"].append((None, "p2", "AI 🤖"))
                    room["chips"]["AI 🤖"] = 10000
                    room["ai_seat"] = "p2"
                    await broadcast_state()

            elif action == "start_hand":
                seats_present = set(s for (_, s, _) in room["seats"] if s)
                if seats_present != {"p1", "p2"}:
                    continue
                if room["phase"] not in ("idle", "result"):
                    continue

                for uname in room["chips"]:
                    if room["chips"][uname] < POKER_ANTE:
                        room["chips"][uname] = 10000

                deck = create_poker_deck()
                p1_user = next(u for (_, s, u) in room["seats"] if s == "p1")
                p2_user = next(u for (_, s, u) in room["seats"] if s == "p2")
                room["chips"][p1_user] -= POKER_ANTE
                room["chips"][p2_user] -= POKER_ANTE
                room["pot"] = POKER_ANTE * 2
                room["hands"] = {
                    "p1": [deck.pop() for _ in range(7)],
                    "p2": [deck.pop() for _ in range(7)],
                }
                room["phase"] = "betting"
                room["turn"] = "p1"
                room["result"] = None
                await broadcast_state()

            elif action == "action":
                move = data.get("move")
                my_seat = next((s for (ws, s, u) in room["seats"] if ws == websocket), None)
                if room["phase"] != "betting" or my_seat != room["turn"]:
                    continue
                apply_poker_move(my_seat, move)
                await broadcast_state()
                await maybe_ai_turn()

    except WebSocketDisconnect:
        room["seats"] = [c for c in room["seats"] if c[0] != websocket]
        await broadcast_state()
# ==================== RPG V3 BULLETPROOF SAVE SYSTEM ====================
import json, os, re as _rpg_re


def _rpg_safe_user_id(username):
    return _rpg_re.sub(r'[^A-Za-z0-9_\-]', '_', username)


RPG_V3_LIMITS = {
    "level": (1, 5000),
    "gold": (0, 10**11),
    "exp": (0, 10**12),
    "stage": (1, 5000),
    "max_stage": (1, 5000),
    "stat_points": (0, 10**6),
    "str": (0, 10**6), "vit": (0, 10**6), "dex": (0, 10**6), "agi": (0, 10**6),
    "luk": (0, 10**6), "exp_stat": (0, 10**6),
    "atk": (0, 10**9), "hp": (0, 10**9), "max_hp": (0, 10**9),
    "rebirth_count": (0, 100000), "rebirthPoints": (0, 10**7), "rebirthCount": (0, 100000),
    "soul_shards": (0, 10**7), "scroll_count": (0, 10**7),
}


def _rpg_validate_save(data):
    if not isinstance(data, dict):
        raise ValueError("잘못된 데이터 형식입니다")
    for key, (lo, hi) in RPG_V3_LIMITS.items():
        if key in data and data[key] is not None:
            val = data[key]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"{key} 값 형식이 올바르지 않습니다")
            if val < lo or val > hi:
                raise ValueError(f"{key} 값이 허용 범위를 벗어났습니다")
    inv = data.get("inventory")
    if inv is not None and (not isinstance(inv, list) or len(inv) > 60):
        raise ValueError("인벤토리 데이터가 올바르지 않습니다")
    return True


@app.get("/rpg/sync/v3")
def get_rpg_v3(current_user: str = Depends(get_current_user)):
    safe_id = _rpg_safe_user_id(current_user)
    try:
        save_path = f"/home/ubuntu/travel-app/rpg_save_v3_{safe_id}.json"
        if os.path.exists(save_path):
            with open(save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {"ok": True, "character": data}
    except Exception:
        pass

    default_data = {
        "name": current_user, "level": 1, "exp": 0, "gold": 0, "stage": 1, "max_stage": 1,
        "atk": 10, "hp": 100, "max_hp": 100, "str": 10, "vit": 10, "dex": 10, "luk": 10, "stat_points": 0,
        "inventory": [], "equipped": {}, "rebirth_count": 0, "rebirth_points": 0, "rebirth_perks": {}, "skills": {}
    }
    return {"ok": True, "character": default_data}


@app.post("/rpg/sync/v3")
def post_rpg_v3(payload: dict = Body(...), current_user: str = Depends(get_current_user)):
    safe_id = _rpg_safe_user_id(current_user)
    save_path = f"/home/ubuntu/travel-app/rpg_save_v3_{safe_id}.json"
    client_data = payload.get("data")

    if client_data is None:
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    try:
        _rpg_validate_save(client_data)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    try:
        tmp_path = save_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(client_data, f, ensure_ascii=False)
        os.replace(tmp_path, save_path)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ==================== 국내 주식 검색/시세 조회 ====================
import json as _stock_json

STOCK_LIST_PATH = "/home/ubuntu/travel-app/stock_list.json"


def _load_stock_list():
    try:
        with open(STOCK_LIST_PATH, "r", encoding="utf-8") as f:
            return _stock_json.load(f)
    except Exception:
        return []


_STOCK_LIST_CACHE = _load_stock_list()


@app.get("/stock/search")
def stock_search(q: str = "", current_user: str = Depends(get_current_user)):
    q = q.strip()
    if not q:
        return []
    results = [s for s in _STOCK_LIST_CACHE if q in s["name"] or q == s["code"]]
    return results[:15]


@app.get("/stock/price/{code}")
def stock_price(code: str, current_user: str = Depends(get_current_user)):
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="올바른 종목코드가 아닙니다")
    try:
        resp = requests.get(
            f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        data = resp.json()
        item = data["datas"][0]
    except Exception:
        raise HTTPException(status_code=502, detail="시세 조회에 실패했습니다")
    return {
        "code": code,
        "name": item.get("stockName"),
        "price": item.get("closePrice"),
        "change": item.get("compareToPreviousClosePrice"),
        "changeDirection": (item.get("compareToPreviousPrice") or {}).get("text"),
        "changeRate": item.get("fluctuationsRatio"),
        "open": item.get("openPrice"),
        "high": item.get("highPrice"),
        "low": item.get("lowPrice"),
        "volume": item.get("accumulatedTradingVolume"),
        "marketStatus": item.get("marketStatus"),
        "market": (item.get("stockExchangeType") or {}).get("nameKor"),
        "updatedAt": item.get("localTradedAt"),
    }


# ==================== 주식 찜목록 ====================
class StockWatchlistModel(Base):
    __tablename__ = "stock_watchlist"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    market = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)


class StockWatchlistIn(BaseModel):
    code: str
    name: str
    market: str


@app.get("/stock/watchlist")
def get_stock_watchlist(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    items = db.query(StockWatchlistModel).filter(
        StockWatchlistModel.user_id == user.id
    ).order_by(StockWatchlistModel.created_at.desc()).all()
    result = [{"code": i.code, "name": i.name, "market": i.market} for i in items]
    db.close()
    return result


@app.post("/stock/watchlist")
def add_stock_watchlist(body: StockWatchlistIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    existing = db.query(StockWatchlistModel).filter(
        StockWatchlistModel.user_id == user.id,
        StockWatchlistModel.code == body.code,
    ).first()
    if existing:
        db.close()
        return {"ok": True, "already_exists": True}
    item = StockWatchlistModel(user_id=user.id, code=body.code, name=body.name, market=body.market)
    db.add(item)
    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/stock/watchlist/{code}")
def remove_stock_watchlist(code: str, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    db.query(StockWatchlistModel).filter(
        StockWatchlistModel.user_id == user.id,
        StockWatchlistModel.code == code,
    ).delete()
    db.commit()
    db.close()
    return {"ok": True}


# ==================== 이력서 ====================
class ResumeModel(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    data = Column(String, default="{}")  # JSON 문자열
    updated_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)

import json as _resume_json
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.pdfgen import canvas as _rl_canvas
from reportlab.lib.pagesizes import A4 as _RL_A4
from reportlab.pdfbase import pdfmetrics as _rl_pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as _rl_ttfont
from fastapi.responses import StreamingResponse
import io as _resume_io

RESUME_FONT_PATH = "/home/ubuntu/travel-app/NanumGothic.ttf"
_rl_pdfmetrics.registerFont(_rl_ttfont("NanumGothic", RESUME_FONT_PATH))


class ResumeIn(BaseModel):
    data: dict


@app.get("/resume")
def get_resume(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    resume = db.query(ResumeModel).filter(ResumeModel.user_id == user.id).first()
    if not resume:
        db.close()
        return {"data": {}}
    result = {"data": _resume_json.loads(resume.data)}
    db.close()
    return result


@app.post("/resume")
def save_resume(body: ResumeIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    resume = db.query(ResumeModel).filter(ResumeModel.user_id == user.id).first()
    data_str = _resume_json.dumps(body.data, ensure_ascii=False)
    if resume:
        resume.data = data_str
        resume.updated_at = now_kst()
    else:
        resume = ResumeModel(user_id=user.id, data=data_str, updated_at=now_kst())
        db.add(resume)
    db.commit()
    db.close()
    return {"ok": True}


def _resume_get_data(current_user):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    resume = db.query(ResumeModel).filter(ResumeModel.user_id == user.id).first()
    db.close()
    if not resume:
        raise HTTPException(status_code=404, detail="저장된 이력서가 없습니다")
    return _resume_json.loads(resume.data)



# ==================== 이력서/포트폴리오 문서 생성 (개선판) ====================
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from docx.enum.text import WD_ALIGN_PARAGRAPH as _DOCX_ALIGN
from docx.shared import RGBColor as _DocxRGBColor
from docx.oxml.ns import qn as _docx_qn

_rl_pdfmetrics.registerFont(_rl_ttfont("NanumGothic-Bold", RESUME_FONT_PATH))

_ACCENT_COLOR = colors.HexColor("#2563eb")
_TEXT_COLOR = colors.HexColor("#1e293b")
_MUTED_COLOR = colors.HexColor("#64748b")

_style_title = ParagraphStyle("title", fontName="NanumGothic-Bold", fontSize=22, alignment=TA_CENTER, textColor=_TEXT_COLOR, spaceAfter=14, leading=28)
_style_subtitle = ParagraphStyle("subtitle", fontName="NanumGothic", fontSize=10, alignment=TA_CENTER, textColor=_MUTED_COLOR, spaceAfter=18)
_style_section = ParagraphStyle("section", fontName="NanumGothic-Bold", fontSize=13, textColor=_ACCENT_COLOR, spaceBefore=14, spaceAfter=8)
_style_item_title = ParagraphStyle("item_title", fontName="NanumGothic-Bold", fontSize=10.5, textColor=_TEXT_COLOR, spaceAfter=2)
_style_item_meta = ParagraphStyle("item_meta", fontName="NanumGothic", fontSize=9, textColor=_MUTED_COLOR, spaceAfter=4)
_style_body = ParagraphStyle("body", fontName="NanumGothic", fontSize=9.5, textColor=_TEXT_COLOR, leading=15, spaceAfter=6)
_style_chip = ParagraphStyle("chip", fontName="NanumGothic", fontSize=9, textColor=_TEXT_COLOR, leading=14)


def _pdf_section_header(text):
    return [Paragraph(text, _style_section), HRFlowable(width="100%", thickness=1, color=_ACCENT_COLOR, spaceAfter=8)]


def _pdf_safe(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


import re as _pdf_re
from datetime import date as _pdf_date


def _parse_period_to_months(period_str):
    """'2022.03 - 2023.08 (1년 6개월)' 또는 '2026.03 - 재직중' 형태에서 개월수를 계산"""
    if not period_str:
        return 0
    dates = _pdf_re.findall(r"(\d{4})[.\-](\d{1,2})", period_str)
    if len(dates) == 0:
        return 0
    start_year, start_month = int(dates[0][0]), int(dates[0][1])
    if len(dates) >= 2:
        end_year, end_month = int(dates[1][0]), int(dates[1][1])
    else:
        today = _pdf_date.today()
        end_year, end_month = today.year, today.month
    months = (end_year - start_year) * 12 + (end_month - start_month) + 1
    return max(0, months)


def _format_total_career(career_list):
    total_months = sum(_parse_period_to_months(c.get("period", "")) for c in career_list)
    if total_months <= 0:
        return ""
    years, months = divmod(total_months, 12)
    parts = []
    if years > 0:
        parts.append(f"{years}년")
    if months > 0:
        parts.append(f"{months}개월")
    return " ".join(parts) if parts else "1개월 미만"


def _pdf_body_paragraphs(text, style=None):
    """문단(빈 줄로 구분된 \n\n)마다 별도 Paragraph로 분리해서, 문단 사이 간격이 실제로 보이게 함"""
    if style is None:
        style = _style_body
    if not text:
        return []
    paragraphs = [p for p in str(text).split("\n\n") if p.strip()]
    result = []
    for p in paragraphs:
        result.append(Paragraph(_pdf_safe(p), style))
    return result


def _build_resume_pdf_elements(data):
    personal = data.get("personal", {})
    elements = []

    elements.append(Paragraph("이 력 서", _style_title))
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email"), personal.get("address")] if p]
    elements.append(Paragraph("  |  ".join(_pdf_safe(p) for p in contact_parts), _style_subtitle))

    education = data.get("education", [])
    if education:
        elements += _pdf_section_header("학력")
        rows = [["학교", "전공", "기간"]]
        for e in education:
            rows.append([_pdf_safe(e.get("school", "")), _pdf_safe(e.get("major", "")), _pdf_safe(e.get("period", ""))])
        t = Table(rows, colWidths=[70 * mm, 60 * mm, 45 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
            ("FONTNAME", (0, 0), (-1, 0), "NanumGothic-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT_COLOR),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    career = data.get("career", [])
    if career:
        total_career = _format_total_career(career)
        section_title = f"경력 (총 {total_career})" if total_career else "경력"
        elements += _pdf_section_header(section_title)
        for c in career:
            elements.append(Paragraph(_pdf_safe(c.get("company", "")), _style_item_title))
            meta = " · ".join(x for x in [c.get("position", ""), c.get("period", "")] if x)
            if meta:
                elements.append(Paragraph(_pdf_safe(meta), _style_item_meta))
            if c.get("description"):
                elements += _pdf_body_paragraphs(c["description"])
            elements.append(Spacer(1, 6))

    certificates = data.get("certificates", [])
    if certificates:
        elements += _pdf_section_header("자격증 / 어학")
        for cert in certificates:
            line = f"• {cert.get('name', '')}" + (f"  ({cert.get('date', '')})" if cert.get("date") else "")
            elements.append(Paragraph(_pdf_safe(line), _style_body))
        elements.append(Spacer(1, 6))

    skills = data.get("skills", [])
    if skills:
        elements += _pdf_section_header("기술 스택")
        elements.append(Paragraph(_pdf_safe(", ".join(skills)), _style_chip))
        elements.append(Spacer(1, 6))

    projects = data.get("projects", [])
    if projects:
        elements += _pdf_section_header("경력기술서")
        for p in projects:
            title_line = _pdf_safe(p.get("name", ""))
            if p.get("period"):
                title_line += f"  ({_pdf_safe(p['period'])})"
            elements.append(Paragraph(title_line, _style_item_title))
            if p.get("description"):
                elements += _pdf_body_paragraphs(p["description"])
            elements.append(Spacer(1, 6))

    cover_letter = data.get("coverLetter", [])
    if cover_letter:
        elements += _pdf_section_header("자기소개서")
        for item in cover_letter:
            if item.get("question"):
                elements.append(Paragraph(_pdf_safe(item["question"]), _style_item_title))
            if item.get("answer"):
                elements += _pdf_body_paragraphs(item["answer"])
            elements.append(Spacer(1, 8))

    return elements


_style_card_title = ParagraphStyle("card_title", fontName="NanumGothic-Bold", fontSize=12.5, textColor=_ACCENT_COLOR, spaceAfter=3)

_PDF_NUMBER_PATTERN = _pdf_re.compile(r"(약\s*)?(\d+[~\-]?\d*\s*(건|개소|대|명|년|개월|곳))")


def _pdf_highlight_numbers(text):
    """문장 안의 숫자+단위(예: 월 15건, 80개소, 10~30대)를 굵게 강조 표시"""
    safe = _pdf_safe(text)

    def _wrap(m):
        return f'<b><font color="#dc2626">{m.group(0)}</font></b>'

    return _PDF_NUMBER_PATTERN.sub(lambda m: _wrap_plain(m), text)


def _wrap_plain(m):
    return f'<b><font color="#dc2626">{m.group(0)}</font></b>'


def _pdf_body_with_highlight(text):
    escaped = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    highlighted = _PDF_NUMBER_PATTERN.sub(_wrap_plain, escaped)
    return highlighted


def _pdf_build_skill_tags_table(skills):
    """기술스택을 태그(칩) 형태로 보이게 만드는 미니 테이블"""
    tag_style = ParagraphStyle("tag", fontName="NanumGothic-Bold", fontSize=8.5, textColor=colors.HexColor("#1d4ed8"), alignment=TA_CENTER)
    tag_cells = []
    for s in skills:
        tag_cells.append(Paragraph(_pdf_safe(s), tag_style))
    t = Table([tag_cells], hAlign="LEFT")
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]
    for i in range(len(tag_cells)):
        style_cmds.append(("BACKGROUND", (i, 0), (i, 0), colors.HexColor("#bfdbfe")))
        style_cmds.append(("BOX", (i, 0), (i, 0), 0.75, colors.HexColor("#93c5fd")))
        style_cmds.append(("ROUNDEDCORNERS", (i, 0), (i, 0), [10, 10, 10, 10]))
    t.setStyle(TableStyle(style_cmds))
    return t


def _build_portfolio_pdf_elements(data, personal):
    elements = []
    elements.append(Paragraph("포 트 폴 리 오", _style_title))
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email")] if p]
    elements.append(Paragraph("  |  ".join(_pdf_safe(p) for p in contact_parts), _style_subtitle))
    for proj in data.get("projects", []):
        card_content = []
        card_content.append(Paragraph(_pdf_safe(proj.get("title", "")), _style_card_title))
        meta = " · ".join(x for x in [proj.get("period", ""), proj.get("role", "")] if x)
        if meta:
            card_content.append(Paragraph(_pdf_safe(meta), _style_item_meta))
        if proj.get("skills"):
            card_content.append(Spacer(1, 4))
            card_content.append(_pdf_build_skill_tags_table(proj["skills"]))
            card_content.append(Spacer(1, 8))
        achievements = [a for a in proj.get("achievements", []) if a]
        if achievements:
            for a in achievements:
                highlighted = _pdf_body_with_highlight(a)
                card_content.append(Paragraph(f"• {highlighted}", _style_body))
        if proj.get("link"):
            card_content.append(Paragraph(_pdf_safe("링크: " + proj["link"]), _style_body))
        card_table = Table([[card_content]], colWidths=[174 * mm])
        card_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#e2e8f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), [8, 8, 8, 8]),
        ]))
        elements.append(card_table)
        elements.append(Spacer(1, 14))
    return elements
def _render_pdf(elements, filename_base):
    buf = _resume_io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=_RL_A4,
        topMargin=20 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    doc.build(elements)
    buf.seek(0)
    filename = f"{filename_base}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


def _docx_set_korean_font(run, name="맑은 고딕", size=None, bold=False, color=None):
    run.font.name = name
    run.font.bold = bold
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(_docx_qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(_docx_qn("w:rFonts"), {})
        rPr.append(rFonts)
    rFonts.set(_docx_qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color


def _docx_section_heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    _docx_set_korean_font(run, size=13, bold=True, color=_DocxRGBColor(0x25, 0x63, 0xeb))
    border_p = doc.add_paragraph()
    border_p.paragraph_format.space_after = Pt(6)
    pPr = border_p._p.get_or_add_pPr()
    pBdr = pPr.makeelement(_docx_qn("w:pBdr"), {})
    bottom = pPr.makeelement(_docx_qn("w:bottom"), {
        _docx_qn("w:val"): "single", _docx_qn("w:sz"): "8", _docx_qn("w:color"): "2563EB"
    })
    pBdr.append(bottom)
    pPr.append(pBdr)


def _build_resume_docx(data):
    personal = data.get("personal", {})
    doc = Document()
    for section_name in ["Normal"]:
        style = doc.styles[section_name]
        style.font.size = Pt(10)

    title_p = doc.add_paragraph()
    title_p.alignment = _DOCX_ALIGN.CENTER
    run = title_p.add_run("이 력 서")
    _docx_set_korean_font(run, size=22, bold=True)

    contact_p = doc.add_paragraph()
    contact_p.alignment = _DOCX_ALIGN.CENTER
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email"), personal.get("address")] if p]
    run = contact_p.add_run("  |  ".join(contact_parts))
    _docx_set_korean_font(run, size=10, color=_DocxRGBColor(0x64, 0x74, 0x8b))

    education = data.get("education", [])
    if education:
        _docx_section_heading(doc, "학력")
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        for i, h in enumerate(["학교", "전공", "기간"]):
            hdr[i].text = h
        for e in education:
            row = table.add_row().cells
            row[0].text = e.get("school", "")
            row[1].text = e.get("major", "")
            row[2].text = e.get("period", "")
        doc.add_paragraph()

    career = data.get("career", [])
    if career:
        _docx_section_heading(doc, "경력")
        for c in career:
            p = doc.add_paragraph()
            run = p.add_run(c.get("company", ""))
            _docx_set_korean_font(run, size=11, bold=True)
            meta = " · ".join(x for x in [c.get("position", ""), c.get("period", "")] if x)
            if meta:
                mp = doc.add_paragraph()
                run = mp.add_run(meta)
                _docx_set_korean_font(run, size=9, color=_DocxRGBColor(0x64, 0x74, 0x8b))
            if c.get("description"):
                dp = doc.add_paragraph()
                run = dp.add_run(c["description"])
                _docx_set_korean_font(run, size=10)
            doc.add_paragraph()

    certificates = data.get("certificates", [])
    if certificates:
        _docx_section_heading(doc, "자격증 / 어학")
        for cert in certificates:
            line = f"· {cert.get('name', '')}" + (f" ({cert.get('date', '')})" if cert.get("date") else "")
            p = doc.add_paragraph()
            run = p.add_run(line)
            _docx_set_korean_font(run, size=10)

    skills = data.get("skills", [])
    if skills:
        _docx_section_heading(doc, "기술 스택")
        p = doc.add_paragraph()
        run = p.add_run(", ".join(skills))
        _docx_set_korean_font(run, size=10)

    projects = data.get("projects", [])
    if projects:
        _docx_section_heading(doc, "경력기술서")
        for proj in projects:
            p = doc.add_paragraph()
            title_line = proj.get("name", "")
            if proj.get("period"):
                title_line += f"  ({proj['period']})"
            run = p.add_run(title_line)
            _docx_set_korean_font(run, size=11, bold=True)
            if proj.get("description"):
                dp = doc.add_paragraph()
                run = dp.add_run(proj["description"])
                _docx_set_korean_font(run, size=10)
            doc.add_paragraph()

    cover_letter = data.get("coverLetter", [])
    if cover_letter:
        _docx_section_heading(doc, "자기소개서")
        for item in cover_letter:
            if item.get("question"):
                p = doc.add_paragraph()
                run = p.add_run(item["question"])
                _docx_set_korean_font(run, size=11, bold=True)
            if item.get("answer"):
                ap = doc.add_paragraph()
                run = ap.add_run(item["answer"])
                _docx_set_korean_font(run, size=10)
            doc.add_paragraph()

    return doc


def _build_portfolio_docx(data, personal):
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)

    title_p = doc.add_paragraph()
    title_p.alignment = _DOCX_ALIGN.CENTER
    run = title_p.add_run("포 트 폴 리 오")
    _docx_set_korean_font(run, size=22, bold=True)

    contact_p = doc.add_paragraph()
    contact_p.alignment = _DOCX_ALIGN.CENTER
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email")] if p]
    run = contact_p.add_run("  |  ".join(contact_parts))
    _docx_set_korean_font(run, size=10, color=_DocxRGBColor(0x64, 0x74, 0x8b))

    for proj in data.get("projects", []):
        _docx_section_heading(doc, proj.get("title", ""))
        meta = " · ".join(x for x in [proj.get("period", ""), proj.get("role", "")] if x)
        if meta:
            mp = doc.add_paragraph()
            run = mp.add_run(meta)
            _docx_set_korean_font(run, size=9, color=_DocxRGBColor(0x64, 0x74, 0x8b))
        if proj.get("skills"):
            sp = doc.add_paragraph()
            run = sp.add_run("기술스택: " + ", ".join(proj["skills"]))
            _docx_set_korean_font(run, size=10)
        for a in proj.get("achievements", []):
            if not a:
                continue
            ap = doc.add_paragraph()
            run = ap.add_run("· " + a)
            _docx_set_korean_font(run, size=10)
        if proj.get("link"):
            lp = doc.add_paragraph()
            run = lp.add_run("링크: " + proj["link"])
            _docx_set_korean_font(run, size=10)
        doc.add_paragraph()

    return doc

@app.get("/resume/download/docx")
def download_resume_docx(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    doc = _build_resume_docx(data)
    buf = _resume_io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    personal = data.get("personal", {})
    filename = f"{personal.get('name', 'resume')}_이력서.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


@app.get("/resume/download/pdf")
def download_resume_pdf(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    elements = _build_resume_pdf_elements(data)
    personal = data.get("personal", {})
    return _render_pdf(elements, f"{personal.get('name', 'resume')}_이력서")


def _build_cover_letter_pdf_elements(data):
    personal = data.get("personal", {})
    elements = []
    elements.append(Paragraph("자 기 소 개 서", _style_title))
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email")] if p]
    elements.append(Paragraph("  |  ".join(_pdf_safe(p) for p in contact_parts), _style_subtitle))

    cover_letter = data.get("coverLetter", [])
    for item in cover_letter:
        if item.get("question"):
            elements.append(Paragraph(_pdf_safe(item["question"]), _style_item_title))
        if item.get("answer"):
            elements += _pdf_body_paragraphs(item["answer"])
        elements.append(Spacer(1, 12))
    return elements


def _build_cover_letter_docx(data):
    personal = data.get("personal", {})
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)

    title_p = doc.add_paragraph()
    title_p.alignment = _DOCX_ALIGN.CENTER
    run = title_p.add_run("자 기 소 개 서")
    _docx_set_korean_font(run, size=22, bold=True)

    contact_p = doc.add_paragraph()
    contact_p.alignment = _DOCX_ALIGN.CENTER
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email")] if p]
    run = contact_p.add_run("  |  ".join(contact_parts))
    _docx_set_korean_font(run, size=10, color=_DocxRGBColor(0x64, 0x74, 0x8b))

    doc.add_paragraph()
    for item in data.get("coverLetter", []):
        if item.get("question"):
            p = doc.add_paragraph()
            run = p.add_run(item["question"])
            _docx_set_korean_font(run, size=12, bold=True)
        if item.get("answer"):
            ap = doc.add_paragraph()
            run = ap.add_run(item["answer"])
            _docx_set_korean_font(run, size=10)
        doc.add_paragraph()
    return doc


@app.get("/resume/download/cover-letter/pdf")
def download_cover_letter_pdf(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    elements = _build_cover_letter_pdf_elements(data)
    personal = data.get("personal", {})
    return _render_pdf(elements, f"{personal.get('name', 'resume')}_자기소개서")


@app.get("/resume/download/cover-letter/docx")
def download_cover_letter_docx(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    doc = _build_cover_letter_docx(data)
    buf = _resume_io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    personal = data.get("personal", {})
    filename = f"{personal.get('name', 'resume')}_자기소개서.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


def _build_resume_only_pdf_elements(data):
    """자기소개서를 제외한 이력서 전용 PDF (인적사항~경력기술서까지만)"""
    personal = data.get("personal", {})
    elements = []

    elements.append(Paragraph("이 력 서", _style_title))
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email"), personal.get("address")] if p]
    elements.append(Paragraph("  |  ".join(_pdf_safe(p) for p in contact_parts), _style_subtitle))

    education = data.get("education", [])
    if education:
        elements += _pdf_section_header("학력")
        rows = [["학교", "전공", "기간"]]
        for e in education:
            rows.append([_pdf_safe(e.get("school", "")), _pdf_safe(e.get("major", "")), _pdf_safe(e.get("period", ""))])
        t = Table(rows, colWidths=[70 * mm, 60 * mm, 45 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "NanumGothic"),
            ("FONTNAME", (0, 0), (-1, 0), "NanumGothic-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT_COLOR),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    career = data.get("career", [])
    if career:
        total_career = _format_total_career(career)
        section_title = f"경력 (총 {total_career})" if total_career else "경력"
        elements += _pdf_section_header(section_title)
        for c in career:
            elements.append(Paragraph(_pdf_safe(c.get("company", "")), _style_item_title))
            meta = " · ".join(x for x in [c.get("position", ""), c.get("period", "")] if x)
            if meta:
                elements.append(Paragraph(_pdf_safe(meta), _style_item_meta))
            if c.get("description"):
                elements += _pdf_body_paragraphs(c["description"])
            elements.append(Spacer(1, 6))

    certificates = data.get("certificates", [])
    if certificates:
        elements += _pdf_section_header("자격증 / 어학")
        for cert in certificates:
            line = f"• {cert.get('name', '')}" + (f"  ({cert.get('date', '')})" if cert.get("date") else "")
            elements.append(Paragraph(_pdf_safe(line), _style_body))
        elements.append(Spacer(1, 6))

    skills = data.get("skills", [])
    if skills:
        elements += _pdf_section_header("기술 스택")
        elements.append(Paragraph(_pdf_safe(", ".join(skills)), _style_chip))
        elements.append(Spacer(1, 6))

    projects = data.get("projects", [])
    if projects:
        elements += _pdf_section_header("경력기술서")
        for p in projects:
            title_line = _pdf_safe(p.get("name", ""))
            if p.get("period"):
                title_line += f"  ({_pdf_safe(p['period'])})"
            elements.append(Paragraph(title_line, _style_item_title))
            if p.get("description"):
                elements += _pdf_body_paragraphs(p["description"])
            elements.append(Spacer(1, 6))

    return elements


def _build_resume_only_docx(data):
    """자기소개서를 제외한 이력서 전용 워드 (인적사항~경력기술서까지만)"""
    personal = data.get("personal", {})
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)

    title_p = doc.add_paragraph()
    title_p.alignment = _DOCX_ALIGN.CENTER
    run = title_p.add_run("이 력 서")
    _docx_set_korean_font(run, size=22, bold=True)

    contact_p = doc.add_paragraph()
    contact_p.alignment = _DOCX_ALIGN.CENTER
    contact_parts = [p for p in [personal.get("name"), personal.get("phone"), personal.get("email"), personal.get("address")] if p]
    run = contact_p.add_run("  |  ".join(contact_parts))
    _docx_set_korean_font(run, size=10, color=_DocxRGBColor(0x64, 0x74, 0x8b))

    education = data.get("education", [])
    if education:
        _docx_section_heading(doc, "학력")
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        for i, h in enumerate(["학교", "전공", "기간"]):
            hdr[i].text = h
        for e in education:
            row = table.add_row().cells
            row[0].text = e.get("school", "")
            row[1].text = e.get("major", "")
            row[2].text = e.get("period", "")
        doc.add_paragraph()

    career = data.get("career", [])
    if career:
        _docx_section_heading(doc, "경력")
        for c in career:
            p = doc.add_paragraph()
            run = p.add_run(c.get("company", ""))
            _docx_set_korean_font(run, size=11, bold=True)
            meta = " · ".join(x for x in [c.get("position", ""), c.get("period", "")] if x)
            if meta:
                mp = doc.add_paragraph()
                run = mp.add_run(meta)
                _docx_set_korean_font(run, size=9, color=_DocxRGBColor(0x64, 0x74, 0x8b))
            if c.get("description"):
                dp = doc.add_paragraph()
                run = dp.add_run(c["description"])
                _docx_set_korean_font(run, size=10)
            doc.add_paragraph()

    certificates = data.get("certificates", [])
    if certificates:
        _docx_section_heading(doc, "자격증 / 어학")
        for cert in certificates:
            line = f"· {cert.get('name', '')}" + (f" ({cert.get('date', '')})" if cert.get("date") else "")
            p = doc.add_paragraph()
            run = p.add_run(line)
            _docx_set_korean_font(run, size=10)

    skills = data.get("skills", [])
    if skills:
        _docx_section_heading(doc, "기술 스택")
        p = doc.add_paragraph()
        run = p.add_run(", ".join(skills))
        _docx_set_korean_font(run, size=10)

    projects = data.get("projects", [])
    if projects:
        _docx_section_heading(doc, "경력기술서")
        for proj in projects:
            p = doc.add_paragraph()
            title_line = proj.get("name", "")
            if proj.get("period"):
                title_line += f"  ({proj['period']})"
            run = p.add_run(title_line)
            _docx_set_korean_font(run, size=11, bold=True)
            if proj.get("description"):
                dp = doc.add_paragraph()
                run = dp.add_run(proj["description"])
                _docx_set_korean_font(run, size=10)
            doc.add_paragraph()

    return doc


@app.get("/resume/download/resume-only/pdf")
def download_resume_only_pdf(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    elements = _build_resume_only_pdf_elements(data)
    personal = data.get("personal", {})
    return _render_pdf(elements, f"{personal.get('name', 'resume')}_이력서(자소서제외)")


@app.get("/resume/download/resume-only/docx")
def download_resume_only_docx(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    doc = _build_resume_only_docx(data)
    buf = _resume_io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    personal = data.get("personal", {})
    filename = f"{personal.get('name', 'resume')}_이력서(자소서제외).docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


def _build_career_only_pdf_elements(data):
    """경력기술서(프로젝트)만 담은 PDF - 회사별 업무 내용만"""
    elements = []
    elements.append(Paragraph("경 력 기 술 서", _style_title))

    projects = data.get("projects", [])
    for p in projects:
        title_line = _pdf_safe(p.get("name", ""))
        if p.get("period"):
            title_line += f"  ({_pdf_safe(p['period'])})"
        elements.append(Paragraph(title_line, _style_item_title))
        if p.get("description"):
            elements += _pdf_body_paragraphs(p["description"])
        elements.append(Spacer(1, 10))

    return elements


def _build_career_only_docx(data):
    """경력기술서(프로젝트)만 담은 워드 - 회사별 업무 내용만"""
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)

    title_p = doc.add_paragraph()
    title_p.alignment = _DOCX_ALIGN.CENTER
    run = title_p.add_run("경 력 기 술 서")
    _docx_set_korean_font(run, size=22, bold=True)

    doc.add_paragraph()
    for p in data.get("projects", []):
        title_line = p.get("name", "")
        if p.get("period"):
            title_line += f"  ({p['period']})"
        tp = doc.add_paragraph()
        run = tp.add_run(title_line)
        _docx_set_korean_font(run, size=12, bold=True)
        if p.get("description"):
            dp = doc.add_paragraph()
            run = dp.add_run(p["description"])
            _docx_set_korean_font(run, size=10)
        doc.add_paragraph()

    return doc


@app.get("/resume/download/career-only/pdf")
def download_career_only_pdf(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    elements = _build_career_only_pdf_elements(data)
    personal = data.get("personal", {})
    return _render_pdf(elements, f"{personal.get('name', 'resume')}_경력기술서")


@app.get("/resume/download/career-only/docx")
def download_career_only_docx(current_user: str = Depends(get_current_user)):
    data = _resume_get_data(current_user)
    doc = _build_career_only_docx(data)
    buf = _resume_io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    personal = data.get("personal", {})
    filename = f"{personal.get('name', 'resume')}_경력기술서.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )
class PortfolioModel(Base):
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    data = Column(String, default="{}")
    updated_at = Column(DateTime, default=now_kst)


class PortfolioIn(BaseModel):
    data: dict


@app.get("/portfolio")
def get_portfolio(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    portfolio = db.query(PortfolioModel).filter(PortfolioModel.user_id == user.id).first()
    resume = db.query(ResumeModel).filter(ResumeModel.user_id == user.id).first()
    personal = {}
    if resume:
        resume_data = _resume_json.loads(resume.data)
        personal = resume_data.get("personal", {})
    if not portfolio:
        db.close()
        return {"data": {"projects": []}, "personal": personal}
    result = {"data": _resume_json.loads(portfolio.data), "personal": personal}
    db.close()
    return result


@app.post("/portfolio")
def save_portfolio(body: PortfolioIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    portfolio = db.query(PortfolioModel).filter(PortfolioModel.user_id == user.id).first()
    data_str = _resume_json.dumps(body.data, ensure_ascii=False)
    if portfolio:
        portfolio.data = data_str
        portfolio.updated_at = now_kst()
    else:
        portfolio = PortfolioModel(user_id=user.id, data=data_str, updated_at=now_kst())
        db.add(portfolio)
    db.commit()
    db.close()
    return {"ok": True}


def _portfolio_get_data(current_user):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    portfolio = db.query(PortfolioModel).filter(PortfolioModel.user_id == user.id).first()
    resume = db.query(ResumeModel).filter(ResumeModel.user_id == user.id).first()
    db.close()
    if not portfolio:
        raise HTTPException(status_code=404, detail="저장된 포트폴리오가 없습니다")
    data = _resume_json.loads(portfolio.data)
    personal = {}
    if resume:
        resume_data = _resume_json.loads(resume.data)
        personal = resume_data.get("personal", {})
    return data, personal



@app.get("/portfolio/download/docx")
def download_portfolio_docx(current_user: str = Depends(get_current_user)):
    data, personal = _portfolio_get_data(current_user)
    doc = _build_portfolio_docx(data, personal)
    buf = _resume_io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    filename = f"{personal.get('name', 'portfolio')}_포트폴리오.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


@app.get("/portfolio/download/pdf")
def download_portfolio_pdf(current_user: str = Depends(get_current_user)):
    data, personal = _portfolio_get_data(current_user)
    elements = _build_portfolio_pdf_elements(data, personal)
    return _render_pdf(elements, f"{personal.get('name', 'portfolio')}_포트폴리오")


# ==================== 식단 화이트보드 ====================
class MealBoardEntryModel(Base):
    __tablename__ = "meal_board_entries"
    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=월 ~ 6=일
    slot = Column(String, nullable=False)  # "lunch" or "dinner"
    menu = Column(String, nullable=False)
    servings = Column(Integer, default=2)
    author = Column(String, nullable=False)
    week_key = Column(String, nullable=False, index=True)  # "2026-W35" 형식
    created_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)


# 메뉴 -> 2인분 기준 재료 매핑 (자주 먹는 메뉴 위주)
MEAL_INGREDIENT_DB = {
    "김치찌개": ["돼지고기 200g", "김치 300g", "두부 1/2모", "대파 1대", "양파 1/2개", "고춧가루 1큰술"],
    "된장찌개": ["된장 2큰술", "두부 1/2모", "애호박 1/3개", "감자 1개", "양파 1/2개", "청양고추 1개"],
    "부대찌개": ["소시지 200g", "햄 150g", "김치 200g", "두부 1/2모", "라면사리 1개", "베이크드빈 1/2캔"],
    "미역국": ["건미역 20g", "소고기 100g", "국간장 2큰술", "다진마늘 1작은술", "참기름 1큰술"],
    "순두부찌개": ["순두부 1봉", "돼지고기 100g", "애호박 1/3개", "양파 1/2개", "계란 1개", "고춧가루 1큰술"],
    "제육볶음": ["돼지고기 앞다리살 400g", "양파 1개", "대파 1대", "고추장 2큰술", "고춧가루 1큰술", "설탕 1큰술"],
    "불고기": ["소고기 불고기용 400g", "양파 1개", "당근 1/2개", "대파 1대", "간장 4큰술", "설탕 2큰술", "배즙 1/4개"],
    "닭갈비": ["닭다리살 500g", "양배추 1/4통", "고구마 1개", "떡 200g", "고추장 2큰술", "고춧가루 1큰술"],
    "찜닭": ["닭 1/2마리", "감자 2개", "당근 1/2개", "양파 1개", "당면 100g", "간장 4큰술", "설탕 2큰술"],
    "삼겹살": ["삼겹살 400g", "상추 1팩", "마늘 1줌", "쌈장 적당량", "깻잎 1팩"],
    "돈까스": ["돼지고기 등심 2장", "빵가루 1컵", "계란 1개", "밀가루 1/2컵", "양배추 1/4통"],
    "치킨": ["닭 1마리", "튀김가루 1컵", "식용유 적당량"],
    "카레": ["카레가루 1박스", "감자 2개", "당근 1개", "양파 1개", "돼지고기 또는 닭고기 300g"],
    "짜장밥": ["춘장 1/2컵", "돼지고기 200g", "양파 1개", "감자 1개", "애호박 1/3개"],
    "짬뽕": ["오징어 1/2마리", "새우 6마리", "홍합 200g", "양파 1/2개", "청경채 2포기", "고춧가루 2큰술"],
    "짜장면": ["춘장 1/2컵", "돼지고기 200g", "양파 1개", "면 2인분"],
    "볶음밥": ["밥 2공기", "계란 2개", "당근 1/2개", "양파 1/2개", "대파 1대", "햄 또는 스팸 100g"],
    "비빔밥": ["밥 2공기", "시금치 1줌", "당근 1/2개", "콩나물 1줌", "계란 2개", "고추장 2큰술"],
    "김밥": ["밥 2공기", "김 4장", "단무지 4줄", "당근 1/2개", "계란 3개", "햄 100g", "시금치 1줌"],
    "떡볶이": ["떡 400g", "어묵 100g", "대파 1대", "고추장 3큰술", "고춧가루 1큰술", "설탕 2큰술"],
    "라면": ["라면 2봉", "계란 2개", "대파 1대"],
    "잡채": ["당면 200g", "소고기 100g", "시금치 1줌", "당근 1/2개", "양파 1/2개", "간장 3큰술", "설탕 1큰술"],
    "갈비찜": ["소갈비 800g", "무 1/4개", "당근 1/2개", "대추 5알", "간장 5큰술", "설탕 2큰술"],
    "냉면": ["냉면 사리 2인분", "육수 또는 동치미국물 1L", "오이 1/2개", "배 1/4개", "삶은계란 1개"],
    "칼국수": ["칼국수 면 2인분", "애호박 1/2개", "감자 1개", "멸치육수 1L", "다진마늘 1작은술"],
    "수제비": ["밀가루 2컵", "감자 1개", "애호박 1/2개", "멸치육수 1L"],
    "된장국": ["된장 2큰술", "두부 1/2모", "무 1/4개", "대파 1대"],
    "계란찜": ["계란 4개", "새우젓 1작은술", "대파 1대", "물 1컵"],
    "감자탕": ["돼지등뼈 700g", "감자 3개", "우거지 200g", "들깨가루 3큰술", "된장 2큰술"],
    "설렁탕": ["사골 800g", "소고기 양지 200g", "대파 2대", "국간장 적당량"],
    "삼계탕": ["영계 2마리", "찹쌀 1/2컵", "대추 6알", "마늘 10알", "황기 약간"],
    "육개장": ["소고기 양지 300g", "고사리 1줌", "숙주 1줌", "대파 3대", "고춧가루 3큰술"],
    "닭볶음탕": ["닭 1마리", "감자 2개", "당근 1개", "양파 1개", "고추장 2큰술", "고춧가루 2큰술"],
    "생선구이": ["고등어 또는 삼치 2마리", "굵은소금 적당량"],
    "장어구이": ["장어 2마리", "양념장 적당량", "생강 약간"],
    "스테이크": ["소고기 스테이크용 400g", "버터 2큰술", "마늘 4쪽", "로즈마리 약간"],
    "파스타": ["파스타면 200g", "마늘 4쪽", "올리브유 3큰술", "베이컨 또는 새우 100g", "파마산치즈 적당량"],
    "피자": ["도우 1장", "토마토소스 적당량", "모짜렐라치즈 200g", "토핑 재료 적당량"],
    "햄버거": ["햄버거빵 2개", "소고기 패티 2장", "양상추 4장", "토마토 1개", "치즈 2장"],
    "샌드위치": ["식빵 4장", "계란 2개", "햄 2장", "치즈 2장", "양상추 4장"],
    "오므라이스": ["밥 2공기", "계란 4개", "케첩 3큰술", "양파 1/2개", "당근 1/2개", "햄 100g"],
    "규동": ["소고기 슬라이스 200g", "양파 1개", "밥 2공기", "간장 3큰술", "설탕 2큰술", "미림 2큰술"],
    "돈부리": ["돼지고기 200g", "양파 1개", "계란 2개", "밥 2공기", "간장 3큰술", "미림 2큰술"],
    "초밥": ["초밥용 밥 2공기", "생선회 300g", "와사비 적당량", "김 약간"],
    "우동": ["우동면 2인분", "유부 4장", "가쓰오부시 육수 1L", "대파 1대"],
    "탕수육": ["돼지고기 등심 400g", "당근 1/2개", "오이 1/2개", "파인애플 약간", "전분 1컵"],
    "마파두부": ["두부 1모", "돼지고기 다짐육 150g", "두반장 2큰술", "대파 1대", "전분물 약간"],
    "동파육": ["삼겹살 덩어리 500g", "대파 2대", "생강 약간", "간장 4큰술", "설탕 2큰술"],
    "쌀국수": ["쌀국수면 2인분", "소고기 슬라이스 150g", "숙주 1줌", "고수 약간", "쌀국수육수 1L"],
    "팟타이": ["쌀국수면 2인분", "새우 8마리", "계란 2개", "숙주 1줌", "피시소스 2큰술"],
    "샐러드": ["양상추 1통", "방울토마토 1팩", "오이 1개", "드레싱 적당량"],
    "곰탕": ["소고기 사태 500g", "무 1/4개", "대파 2대"],
    "만두국": ["만두 15개", "계란 1개", "대파 1대", "다시육수 1L"],
    "떡국": ["떡국떡 400g", "계란 2개", "대파 1대", "사골육수 1L", "김 약간"],
    "낙지볶음": ["낙지 2마리", "양파 1개", "당근 1/2개", "고추장 2큰술", "고춧가루 2큰술"],
    "오징어볶음": ["오징어 2마리", "양파 1개", "당근 1/2개", "고추장 2큰술", "고춧가루 1큰술"],
    "고등어조림": ["고등어 2마리", "무 1/4개", "고춧가루 2큰술", "간장 3큰술", "대파 1대"],
    "동태찌개": ["동태 1마리", "무 1/4개", "두부 1/2모", "미나리 1줌", "고춧가루 2큰술"],
    "닭곰탕": ["닭 1마리", "대파 2대", "마늘 5알"],
    "닭죽": ["닭 1/2마리", "쌀 1컵", "당근 1/4개", "대파 1대"],
    "전복죽": ["전복 4마리", "쌀 1컵", "참기름 1큰술"],
    "소고기무국": ["소고기 국거리 150g", "무 1/4개", "대파 1대", "국간장 2큰술"],
    "부침개": ["부침가루 1컵", "부추 1줌", "당근 1/2개", "양파 1/2개", "해물 약간"],
    "김치전": ["김치 200g", "부침가루 1컵", "대파 1대"],
    "계란말이": ["계란 5개", "당근 1/4개", "대파 1/2대", "소금 약간"],
    "장조림": ["소고기 사태 400g", "메추리알 15개", "간장 5큰술", "마늘 5알"],
    "멸치볶음": ["잔멸치 150g", "견과류 1/2컵", "간장 2큰술", "물엿 2큰술"],
    "콩나물무침": ["콩나물 300g", "참기름 1큰술", "다진마늘 1작은술", "소금 약간"],
    "시금치나물": ["시금치 300g", "참기름 1큰술", "다진마늘 1작은술", "국간장 1큰술"],
}


def _mealboard_get_week_key(offset_weeks=0):
    today = _pdf_date.today()
    target = today + timedelta(weeks=offset_weeks)
    iso = target.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


class MealBoardEntryIn(BaseModel):
    day_of_week: int
    slot: str
    menu: str
    servings: int = 2


@app.get("/mealboard")
def get_mealboard(week_offset: int = 0, current_user: str = Depends(get_current_user)):
    week_key = _mealboard_get_week_key(week_offset)
    db = SessionLocal()
    entries = db.query(MealBoardEntryModel).filter(MealBoardEntryModel.week_key == week_key).all()
    result = [
        {
            "id": e.id, "day_of_week": e.day_of_week, "slot": e.slot,
            "menu": e.menu, "servings": e.servings, "author": e.author,
        }
        for e in entries
    ]
    db.close()
    return {"week_key": week_key, "entries": result}


@app.post("/mealboard")
def add_mealboard_entry(body: MealBoardEntryIn, current_user: str = Depends(get_current_user)):
    if body.day_of_week < 0 or body.day_of_week > 6:
        raise HTTPException(status_code=400, detail="올바르지 않은 요일입니다")
    if body.slot not in ("lunch", "dinner"):
        raise HTTPException(status_code=400, detail="올바르지 않은 슬롯입니다")
    week_key = _mealboard_get_week_key(0)
    db = SessionLocal()
    existing = db.query(MealBoardEntryModel).filter(
        MealBoardEntryModel.week_key == week_key,
        MealBoardEntryModel.day_of_week == body.day_of_week,
        MealBoardEntryModel.slot == body.slot,
    ).first()
    if existing:
        existing.menu = body.menu
        existing.servings = body.servings
        existing.author = current_user
    else:
        entry = MealBoardEntryModel(
            day_of_week=body.day_of_week, slot=body.slot, menu=body.menu,
            servings=body.servings, author=current_user, week_key=week_key,
        )
        db.add(entry)
    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/mealboard/{entry_id}")
def delete_mealboard_entry(entry_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    db.query(MealBoardEntryModel).filter(MealBoardEntryModel.id == entry_id).delete()
    db.commit()
    db.close()
    return {"ok": True}


@app.get("/mealboard/ingredients")
def get_meal_ingredients(menu: str, servings: int = 2, current_user: str = Depends(get_current_user)):
    menu_clean = menu.strip()
    if menu_clean not in MEAL_INGREDIENT_DB:
        return {"found": False, "ingredients": []}
    base_ingredients = MEAL_INGREDIENT_DB[menu_clean]
    if servings == 2:
        return {"found": True, "ingredients": base_ingredients}
    ratio = servings / 2
    scaled = []
    for ing in base_ingredients:
        match = _resume_re.match(r"^(.+?)\s+([\d./]+)(\D*)$", ing)
        if match:
            name, amount_str, unit = match.groups()
            try:
                if "/" in amount_str:
                    num, denom = amount_str.split("/")
                    amount = float(num) / float(denom)
                else:
                    amount = float(amount_str)
                scaled_amount = amount * ratio
                if scaled_amount == int(scaled_amount):
                    scaled_amount_str = str(int(scaled_amount))
                else:
                    scaled_amount_str = f"{scaled_amount:.1f}"
                scaled.append(f"{name} {scaled_amount_str}{unit}")
            except (ValueError, ZeroDivisionError):
                scaled.append(ing)
        else:
            scaled.append(ing)
    return {"found": True, "ingredients": scaled}


@app.get("/mealboard/recommend")
def recommend_next_week_menu(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    recent_weeks = [_mealboard_get_week_key(-i) for i in range(4)]
    recent_entries = db.query(MealBoardEntryModel).filter(
        MealBoardEntryModel.week_key.in_(recent_weeks)
    ).all()
    recently_eaten = set(e.menu.strip() for e in recent_entries)
    db.close()

    available = [m for m in MEAL_INGREDIENT_DB.keys() if m not in recently_eaten]
    if len(available) < 7:
        available = list(MEAL_INGREDIENT_DB.keys())

    _random.shuffle(available)
    return {"recommendations": available[:7]}


# ==================== 자기소개서 버전 관리 ====================
class CoverLetterVersionModel(Base):
    __tablename__ = "cover_letter_versions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    data = Column(String, default="[]")  # coverLetter 배열 JSON
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)


class CoverLetterVersionIn(BaseModel):
    name: str
    coverLetter: list


@app.get("/resume/cover-letter-versions")
def list_cover_letter_versions(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    versions = db.query(CoverLetterVersionModel).filter(
        CoverLetterVersionModel.user_id == user.id
    ).order_by(CoverLetterVersionModel.updated_at.desc()).all()
    result = [
        {"id": v.id, "name": v.name, "updated_at": v.updated_at.strftime("%Y-%m-%d %H:%M")}
        for v in versions
    ]
    db.close()
    return {"versions": result}


@app.get("/resume/cover-letter-versions/{version_id}")
def get_cover_letter_version(version_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    version = db.query(CoverLetterVersionModel).filter(
        CoverLetterVersionModel.id == version_id,
        CoverLetterVersionModel.user_id == user.id,
    ).first()
    db.close()
    if not version:
        raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다")
    return {"id": version.id, "name": version.name, "coverLetter": _resume_json.loads(version.data)}


@app.post("/resume/cover-letter-versions")
def save_cover_letter_version(body: CoverLetterVersionIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    existing = db.query(CoverLetterVersionModel).filter(
        CoverLetterVersionModel.user_id == user.id,
        CoverLetterVersionModel.name == body.name,
    ).first()
    data_str = _resume_json.dumps(body.coverLetter, ensure_ascii=False)
    if existing:
        existing.data = data_str
        existing.updated_at = now_kst()
    else:
        version = CoverLetterVersionModel(
            user_id=user.id, name=body.name, data=data_str,
            created_at=now_kst(), updated_at=now_kst(),
        )
        db.add(version)
    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/resume/cover-letter-versions/{version_id}")
def delete_cover_letter_version(version_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    db.query(CoverLetterVersionModel).filter(
        CoverLetterVersionModel.id == version_id,
        CoverLetterVersionModel.user_id == user.id,
    ).delete()
    db.commit()
    db.close()
    return {"ok": True}


# ==================== 지원 현황 관리 ====================
class JobApplicationModel(Base):
    __tablename__ = "job_applications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company = Column(String, nullable=False)
    position = Column(String, default="")
    apply_date = Column(String, default="")
    distance = Column(String, default="")
    jobplanet_rating = Column(String, default="")
    status = Column(String, default="지원함")  # 지원함, 열람, 미열람, 서류통과, 불합격
    memo = Column(String, default="")
    link = Column(String, default="")
    apply_channel = Column(String, default="")
    created_at = Column(DateTime, default=now_kst)
    updated_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)


class JobApplicationIn(BaseModel):
    company: str
    position: str = ""
    apply_date: str = ""
    distance: str = ""
    jobplanet_rating: str = ""
    status: str = "지원함"
    memo: str = ""
    link: str = ""
    apply_channel: str = ""


@app.get("/job-applications")
def list_job_applications(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    apps = db.query(JobApplicationModel).filter(
        JobApplicationModel.user_id == user.id
    ).order_by(JobApplicationModel.apply_date.desc()).all()
    result = [
        {
            "id": a.id, "company": a.company, "position": a.position,
            "apply_date": a.apply_date, "distance": a.distance,
            "jobplanet_rating": a.jobplanet_rating, "status": a.status, "memo": a.memo, "link": a.link,
            "apply_channel": a.apply_channel,
        }
        for a in apps
    ]
    db.close()
    return {"applications": result}


@app.post("/job-applications")
def create_job_application(body: JobApplicationIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    app_row = JobApplicationModel(
        user_id=user.id, company=body.company, position=body.position,
        apply_date=body.apply_date, distance=body.distance,
        jobplanet_rating=body.jobplanet_rating, status=body.status, memo=body.memo, link=body.link,
        apply_channel=body.apply_channel,
        created_at=now_kst(), updated_at=now_kst(),
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    result_id = app_row.id
    db.close()
    return {"ok": True, "id": result_id}


@app.put("/job-applications/{app_id}")
def update_job_application(app_id: int, body: JobApplicationIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    app_row = db.query(JobApplicationModel).filter(
        JobApplicationModel.id == app_id, JobApplicationModel.user_id == user.id
    ).first()
    if not app_row:
        db.close()
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
    app_row.company = body.company
    app_row.position = body.position
    app_row.apply_date = body.apply_date
    app_row.distance = body.distance
    app_row.jobplanet_rating = body.jobplanet_rating
    app_row.status = body.status
    app_row.memo = body.memo
    app_row.link = body.link
    app_row.apply_channel = body.apply_channel
    app_row.updated_at = now_kst()
    db.commit()
    db.close()
    return {"ok": True}


@app.delete("/job-applications/{app_id}")
def delete_job_application(app_id: int, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    db.query(JobApplicationModel).filter(
        JobApplicationModel.id == app_id, JobApplicationModel.user_id == user.id
    ).delete()
    db.commit()
    db.close()
    return {"ok": True}


# ==================== Pig Bills (돼지 부수기 생존 게임) ====================
class PigBillsUpgradeModel(Base):
    __tablename__ = "pigbills_upgrades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    points = Column(Integer, default=0)  # 보유 강화 포인트
    attack_speed_lv = Column(Integer, default=0)   # 공격속도 증가 레벨
    coin_drop_lv = Column(Integer, default=0)      # 코인 드랍 증가 레벨
    wave_size_lv = Column(Integer, default=0)      # 웨이브 크기 증가 레벨
    max_days_survived = Column(Integer, default=0) # 역대 최고 생존일
    updated_at = Column(DateTime, default=now_kst)


class PigBillsRunModel(Base):
    __tablename__ = "pigbills_runs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    days_survived = Column(Integer, nullable=False)
    final_gold = Column(Integer, default=0)
    created_at = Column(DateTime, default=now_kst)


Base.metadata.create_all(bind=engine)


UPGRADE_COSTS = {
    "attack_speed": [10, 25, 50, 100, 200],  # 레벨별 필요 포인트
    "coin_drop": [10, 25, 50, 100, 200],
    "wave_size": [20, 50, 100, 200, 400],    # 레벨당 웨이브 돼지 +1마리
}


@app.get("/pigbills/state")
def get_pigbills_state(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    upgrade = db.query(PigBillsUpgradeModel).filter(PigBillsUpgradeModel.user_id == user.id).first()
    if not upgrade:
        upgrade = PigBillsUpgradeModel(user_id=user.id)
        db.add(upgrade)
        db.commit()
        db.refresh(upgrade)
    result = {
        "points": upgrade.points,
        "attack_speed_lv": upgrade.attack_speed_lv,
        "coin_drop_lv": upgrade.coin_drop_lv,
        "wave_size_lv": upgrade.wave_size_lv,
        "max_days_survived": upgrade.max_days_survived,
        "total_gold_earned": upgrade.total_gold_earned or 0,
        "upgrade_costs": UPGRADE_COSTS,
    }
    db.close()
    return result


class PigBillsPurchaseIn(BaseModel):
    upgrade_type: str  # "attack_speed" or "coin_drop"


@app.post("/pigbills/upgrade")
def purchase_pigbills_upgrade(body: PigBillsPurchaseIn, current_user: str = Depends(get_current_user)):
    if body.upgrade_type not in UPGRADE_COSTS:
        raise HTTPException(status_code=400, detail="올바르지 않은 강화 종류입니다")
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    upgrade = db.query(PigBillsUpgradeModel).filter(PigBillsUpgradeModel.user_id == user.id).first()
    if not upgrade:
        db.close()
        raise HTTPException(status_code=404, detail="유저 데이터가 없습니다")

    lv_field_map = {
        "attack_speed": "attack_speed_lv",
        "coin_drop": "coin_drop_lv",
        "wave_size": "wave_size_lv",
    }
    lv_field = lv_field_map[body.upgrade_type]
    current_lv = getattr(upgrade, lv_field)
    costs = UPGRADE_COSTS[body.upgrade_type]
    if current_lv >= len(costs):
        db.close()
        raise HTTPException(status_code=400, detail="이미 최대 레벨입니다")

    cost = costs[current_lv]
    if upgrade.points < cost:
        db.close()
        raise HTTPException(status_code=400, detail="포인트가 부족합니다")

    upgrade.points -= cost
    setattr(upgrade, lv_field, current_lv + 1)
    upgrade.updated_at = now_kst()
    db.commit()
    db.close()
    return {"ok": True}


class PigBillsRunEndIn(BaseModel):
    days_survived: int
    final_gold: int = 0


@app.post("/pigbills/run-end")
def end_pigbills_run(body: PigBillsRunEndIn, current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()

    run = PigBillsRunModel(
        user_id=user.id, days_survived=body.days_survived,
        final_gold=body.final_gold, created_at=now_kst(),
    )
    db.add(run)

    upgrade = db.query(PigBillsUpgradeModel).filter(PigBillsUpgradeModel.user_id == user.id).first()
    if not upgrade:
        upgrade = PigBillsUpgradeModel(user_id=user.id)
        db.add(upgrade)

    earned_points = body.days_survived * 2  # 생존일수 * 2 포인트 획득
    upgrade.points += earned_points
    upgrade.total_gold_earned = (upgrade.total_gold_earned or 0) + body.final_gold
    if body.days_survived > upgrade.max_days_survived:
        upgrade.max_days_survived = body.days_survived
    upgrade.updated_at = now_kst()

    db.commit()
    db.close()
    return {"ok": True, "earned_points": earned_points}


# ==================== 돼지청구서 스킬트리 (4분면 특성) ====================
SKILL_TREE = {
    # 좌상단: 치명타 계열
    "crit_chance_1": {"quadrant": "crit", "prereq": None, "max_lv": 3, "costs": [15, 30, 60]},
    "crit_chance_2": {"quadrant": "crit", "prereq": "crit_chance_1", "max_lv": 3, "costs": [40, 80, 150]},
    "crit_damage": {"quadrant": "crit", "prereq": "crit_chance_2", "max_lv": 3, "costs": [80, 160, 300]},

    # 좌하단: 돈 계열
    "coin_drop": {"quadrant": "gold", "prereq": None, "max_lv": 5, "costs": [10, 25, 50, 100, 200]},
    "gold_interest": {"quadrant": "gold", "prereq": "coin_drop", "max_lv": 3, "costs": [50, 100, 200]},
    "bill_discount": {"quadrant": "gold", "prereq": "gold_interest", "max_lv": 3, "costs": [100, 200, 400]},

    # 우상단: 돼지수 계열
    "wave_size": {"quadrant": "pigs", "prereq": None, "max_lv": 5, "costs": [20, 50, 100, 200, 400]},
    "pig_lifetime": {"quadrant": "pigs", "prereq": "wave_size", "max_lv": 3, "costs": [30, 60, 120]},
    "golden_pig": {"quadrant": "pigs", "prereq": "pig_lifetime", "max_lv": 3, "costs": [100, 200, 400]},

    # 우하단: 특수스킬 계열
    "attack_speed": {"quadrant": "skill", "prereq": None, "max_lv": 5, "costs": [10, 25, 50, 100, 200]},
    "lightning_strike": {"quadrant": "skill", "prereq": "attack_speed", "max_lv": 3, "costs": [60, 120, 240]},
    "chain_lightning": {"quadrant": "skill", "prereq": "lightning_strike", "max_lv": 3, "costs": [150, 300, 600]},
}

SKILL_FIELD_MAP = {
    "crit_chance_1": "crit_chance_1_lv",
    "crit_chance_2": "crit_chance_2_lv",
    "crit_damage": "crit_damage_lv",
    "coin_drop": "coin_drop_lv",
    "gold_interest": "gold_interest_lv",
    "bill_discount": "bill_discount_lv",
    "wave_size": "wave_size_lv",
    "pig_lifetime": "pig_lifetime_lv",
    "golden_pig": "golden_pig_lv",
    "attack_speed": "attack_speed_lv",
    "lightning_strike": "lightning_strike_lv",
    "chain_lightning": "chain_lightning_lv",
}


@app.get("/pigbills/skilltree")
def get_pigbills_skilltree(current_user: str = Depends(get_current_user)):
    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    upgrade = db.query(PigBillsUpgradeModel).filter(PigBillsUpgradeModel.user_id == user.id).first()
    if not upgrade:
        upgrade = PigBillsUpgradeModel(user_id=user.id)
        db.add(upgrade)
        db.commit()
        db.refresh(upgrade)

    skills = {}
    for key, info in SKILL_TREE.items():
        field = SKILL_FIELD_MAP[key]
        current_lv = getattr(upgrade, field, 0) or 0
        skills[key] = {
            "quadrant": info["quadrant"],
            "prereq": info["prereq"],
            "max_lv": info["max_lv"],
            "costs": info["costs"],
            "current_lv": current_lv,
        }

    result = {"points": upgrade.points, "skills": skills}
    db.close()
    return result


class PigBillsSkillPurchaseIn(BaseModel):
    skill_key: str


@app.post("/pigbills/skilltree/upgrade")
def purchase_pigbills_skill(body: PigBillsSkillPurchaseIn, current_user: str = Depends(get_current_user)):
    if body.skill_key not in SKILL_TREE:
        raise HTTPException(status_code=400, detail="올바르지 않은 특성입니다")

    db = SessionLocal()
    user = db.query(UserModel).filter(UserModel.username == current_user).first()
    upgrade = db.query(PigBillsUpgradeModel).filter(PigBillsUpgradeModel.user_id == user.id).first()
    if not upgrade:
        db.close()
        raise HTTPException(status_code=404, detail="유저 데이터가 없습니다")

    info = SKILL_TREE[body.skill_key]
    field = SKILL_FIELD_MAP[body.skill_key]
    current_lv = getattr(upgrade, field, 0) or 0

    if current_lv >= info["max_lv"]:
        db.close()
        raise HTTPException(status_code=400, detail="이미 최대 레벨입니다")

    # 선행조건 체크
    if info["prereq"]:
        prereq_field = SKILL_FIELD_MAP[info["prereq"]]
        prereq_lv = getattr(upgrade, prereq_field, 0) or 0
        if prereq_lv <= 0:
            db.close()
            raise HTTPException(status_code=400, detail="선행 특성을 먼저 찍어야 합니다")

    cost = info["costs"][current_lv]
    if upgrade.points < cost:
        db.close()
        raise HTTPException(status_code=400, detail="포인트가 부족합니다")

    upgrade.points -= cost
    setattr(upgrade, field, current_lv + 1)
    upgrade.updated_at = now_kst()
    db.commit()
    db.close()
    return {"ok": True}
