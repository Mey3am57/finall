from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import pandas as pd
import os

# ===========================
# 🗄️ تنظیمات دیتابیس
# ===========================
SQLALCHEMY_DATABASE_URL = "sqlite:///./uni_system_final.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ===========================
# 📝 مدل‌های دیتابیس
# ===========================
class AdminUser(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String) 

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String)      
    info_id = Column(String)        
    resource_name = Column(String)
    day_name = Column(String)
    hour = Column(Integer)
    booking_type = Column(String)

class Resource(Base):
    __tablename__ = "resources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

class Day(Base):
    __tablename__ = "days"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    order = Column(Integer)

class Hour(Base):
    __tablename__ = "hours"
    id = Column(Integer, primary_key=True, index=True)
    value = Column(Integer, unique=True)
    label = Column(String)

Base.metadata.create_all(bind=engine)

# ===========================
# 📦 ورودی‌ها (Pydantic)
# ===========================
class LoginRequest(BaseModel):
    username: str
    password: str

class AdminCreate(BaseModel):
    username: str
    password: str

class BookingCreate(BaseModel):
    user_name: str
    info_id: str
    resource_name: str
    day_name: str
    hour: int
    booking_type: str 

class ItemCreate(BaseModel):
    name: str

class HourCreate(BaseModel):
    value: int
    label: str

app = FastAPI(title="سیستم جامع مدیریت دانشگاه")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# هدایت خودکار به صفحه اصلی
@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

# ===========================
# 🚀 Startup (ایجاد پیش‌فرض‌ها)
# ===========================
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if not db.query(Day).first():
        days = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه"]
        for i, d in enumerate(days): db.add(Day(name=d, order=i))
    if not db.query(Resource).first():
        db.add(Resource(name="کلاس ۱۰۱"))
    if not db.query(Hour).first():
        for h in range(8, 18): db.add(Hour(value=h, label=f"{h}:00 تا {h+1}:00"))
    
    # ایجاد مدیر پیش‌فرض
    if not db.query(AdminUser).filter(AdminUser.username == "admin").first():
        db.add(AdminUser(username="admin", password="123"))
        
    db.commit()
    db.close()

# ===========================
# 🔑 سیستم لاگین و ادمین
# ===========================
@app.post("/api/login")
def login(creds: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == creds.username).first()
    if not user or user.password != creds.password:
        raise HTTPException(401, "نام کاربری یا رمز عبور اشتباه است")
    return {"msg": "OK", "username": user.username}

@app.get("/api/admins")
def get_admins(db: Session = Depends(get_db)):
    return db.query(AdminUser).all()

@app.post("/api/admins")
def add_admin(admin: AdminCreate, db: Session = Depends(get_db)):
    if db.query(AdminUser).filter(AdminUser.username == admin.username).first():
        raise HTTPException(400, "این نام کاربری تکراری است")
    db.add(AdminUser(username=admin.username, password=admin.password))
    db.commit()
    return {"msg": "Created"}

@app.delete("/api/admins/{username}")
def delete_admin(username: str, db: Session = Depends(get_db)):
    if username == "admin": raise HTTPException(400, "مدیر اصلی قابل حذف نیست")
    db.query(AdminUser).filter(AdminUser.username == username).delete()
    db.commit()
    return {"msg": "Deleted"}

# ===========================
# 📅 جدول هوشمند (اصلاح شده برای چندگانگی)
# ===========================
@app.get("/api/schedule-grid")
def get_grid(type_filter: str = Query("student"), db: Session = Depends(get_db)):
    bookings = db.query(Booking).filter(Booking.booking_type == type_filter).all()
    db_days = db.query(Day).order_by(Day.order).all()
    db_hours = db.query(Hour).order_by(Hour.value).all()
    days_names = [d.name for d in db_days]
    
    grid_data = []
    for h in db_hours:
        row = {"hour_label": h.label}
        for day in days_names:
            # پیدا کردن همه کلاس‌های این ساعت (نه فقط یکی)
            found_list = [b for b in bookings if b.day_name == day and b.hour == h.value]
            
            # تبدیل لیست آبجکت‌ها به دیکشنری
            row[day] = [
                {"id": b.id, "user": b.user_name, "info": b.info_id, "res": b.resource_name}
                for b in found_list
            ]
        grid_data.append(row)

    return {"columns": ["ساعت"] + days_names, "rows": grid_data}

# ===========================
# 📊 خروجی اکسل (اصلاح شده)
# ===========================
@app.get("/api/export-excel")
def export_excel(type_filter: str = Query("student"), db: Session = Depends(get_db)):
    bookings = db.query(Booking).filter(Booking.booking_type == type_filter).all()
    db_days = [d.name for d in db.query(Day).order_by(Day.order).all()]
    db_hours = db.query(Hour).order_by(Hour.value).all()
    hour_values = [h.value for h in db_hours]
    hour_labels = [h.label for h in db_hours]
    
    data = {day: ["---"] * len(db_hours) for day in db_days}
    data["ساعت"] = hour_labels
    
    for i, h_val in enumerate(hour_values):
        for day in db_days:
            found_list = [b for b in bookings if b.day_name == day and b.hour == h_val]
            if found_list:
                # چسباندن متن‌ها با Enter
                texts = [f"📌 {b.user_name} ({b.resource_name})" for b in found_list]
                data[day][i] = "\n".join(texts)

    df = pd.DataFrame(data)
    cols = ["ساعت"] + db_days
    df = df[cols]
    filename = f"schedule_{type_filter}.xlsx"
    df.to_excel(filename, index=False)
    return FileResponse(path=filename, filename=filename)

# ===========================
# 📝 ثبت و حذف رزرو
# ===========================
@app.post("/api/book")
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    if not booking.user_name.strip() or not booking.info_id.strip():
        raise HTTPException(400, detail="ورودی نامعتبر")
    
    # تداخل: آیا دقیقا همین منبع در همین ساعت پر است؟
    existing = db.query(Booking).filter(
        Booking.resource_name == booking.resource_name,
        Booking.day_name == booking.day_name,
        Booking.hour == booking.hour
    ).first()
    
    if existing:
        raise HTTPException(409, detail=f"تداخل! {existing.resource_name} قبلاً رزرو شده.")
        
    db.add(Booking(**booking.dict()))
    db.commit()
    return {"msg": "OK"}

@app.delete("/api/book/{book_id}")
def delete_booking(book_id: int, db: Session = Depends(get_db)):
    db.query(Booking).filter(Booking.id == book_id).delete()
    db.commit()
    return {"msg": "Deleted"}

# ===========================
# ⚙️ CRUD تنظیمات
# ===========================
@app.get("/api/resources")
def get_res(db: Session = Depends(get_db)): return db.query(Resource).all()
@app.post("/api/resources")
def add_res(item: ItemCreate, db: Session = Depends(get_db)):
    if not item.name.strip(): raise HTTPException(400, "نام خالی است")
    db.add(Resource(name=item.name)); db.commit(); return {"msg":"ok"}
@app.delete("/api/resources/{name}")
def del_res(name: str, db: Session = Depends(get_db)): db.query(Resource).filter(Resource.name==name).delete(); db.commit(); return {"msg":"ok"}

@app.get("/api/days")
def get_days(db: Session = Depends(get_db)): return db.query(Day).order_by(Day.order).all()
@app.post("/api/days")
def add_day(item: ItemCreate, db: Session = Depends(get_db)): 
    if not item.name.strip(): raise HTTPException(400, "نام خالی است")
    c = db.query(Day).count(); db.add(Day(name=item.name, order=c)); db.commit(); return {"msg":"ok"}
@app.delete("/api/days/{name}")
def del_day(name: str, db: Session = Depends(get_db)): db.query(Day).filter(Day.name==name).delete(); db.commit(); return {"msg":"ok"}

@app.get("/api/hours")
def get_hours(db: Session = Depends(get_db)): return db.query(Hour).order_by(Hour.value).all()
@app.post("/api/hours")
def add_hour(item: HourCreate, db: Session = Depends(get_db)):
    if not item.label.strip(): raise HTTPException(400, "نام خالی است")
    db.add(Hour(value=item.value, label=item.label)); db.commit(); return {"msg":"ok"}
@app.delete("/api/hours/{val}")
def del_hour(val: int, db: Session = Depends(get_db)): db.query(Hour).filter(Hour.value==val).delete(); db.commit(); return {"msg":"ok"}