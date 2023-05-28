from sqlalchemy import Float, DateTime
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# Создание подключения к базе данных auth.db
auth_engine = create_engine("sqlite:///auth.db")
AuthSession = sessionmaker(bind=auth_engine)
auth_session = AuthSession()

# Создание подключения к базе данных order.db
order_engine = create_engine("sqlite:///order.db")
OrderSession = sessionmaker(bind=order_engine)
order_session = OrderSession()

Base = declarative_base()


# Модель User
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String)
    email = Column(String)
    password = Column(String)
    role = Column(String)


# Модель Order
class Order(Base):
    __tablename__ = "order"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    status = Column(String)
    special_requests = Column(String)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    user = relationship("User")  # Связь с таблицей User


# Модель Dish
class Dish(Base):
    __tablename__ = "dish"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    description = Column(String)
    price = Column(Float)
    quantity = Column(Integer)


# Модель OrderDish
class OrderDish(Base):
    __tablename__ = "order_dish"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("order.id"))
    dish_id = Column(Integer, ForeignKey("dish.id"))
    quantity = Column(Integer)
    price = Column(Float)


# Создание таблиц в базе данных order.db
Base.metadata.create_all(bind=order_engine)

# Конфигурация приложения FastAPI
app = FastAPI()


# Функция для работы с базой данных
def get_db():
    db = OrderSession()
    try:
        yield db
    finally:
        db.close()


# Конечная точка для создания заказа
@app.post("/orders")
def create_order(user_id: int, dish_data: list, special_requests: str = "", db=Depends(get_db)):
    order = Order(user_id=user_id, status="в ожидании", special_requests=special_requests)
    db.add(order)
    db.commit()
    db.refresh(order)

    for dish in dish_data:
        dish_id = dish["dish_id"]
        quantity = dish["quantity"]
        dish_price = dish["price"]
        dish_db = db.query(Dish).get(dish_id)

        if not dish_db:
            raise HTTPException(status_code=400, detail=f"Dish with ID {dish_id} does not exist")
        if quantity > dish_db.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient quantity for dish with ID {dish_id}")

        order_dish = OrderDish(order_id=order.id, dish_id=dish_id, quantity=quantity, price=dish_price)
        db.add(order_dish)

        dish_db.quantity -= quantity

    db.commit()

    return {"message": "Order created successfully"}


# Конечная точка для обработки заказов
@app.post("/process_orders")
def process_orders(token: str, db=Depends(get_db)):
    back_token = jwt.decode(token, "secret_key", algorithms=["HS256"])

    if back_token["role"] != "manager":
        raise  HTTPException(status_code=403, detail="Not granted")

    orders = db.query(Order).filter(Order.status == "в ожидании").all()

    for order in orders:
        # Логика обработки заказа...
        order.status = "выполнен"
        db.commit()
    return {"message": "Orders processed successfully"}


# Конечная точка для получения информации о заказе
@app.get("/orders/{order_id}")
def get_order(order_id: int, db=Depends(get_db)):
    order = db.query(Order).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": order.id, "status": order.status}


# Конечная точка для управления блюдами
@app.get("/dishes/{dish_id}")
def get_dish(dish_id: int, db=Depends(get_db)):
    dish = db.query(Dish).get(dish_id)
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")
    return {"dish_id": dish.id, "name": dish.name, "description": dish.description, "price": dish.price,
            "quantity": dish.quantity}


@app.post("/dishes")
def create_dish(name: str, description: str, price: float, quantity: int, db=Depends(get_db)):
    dish = Dish(name=name, description=description, price=price, quantity=quantity)
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return {"message": "Dish created successfully"}


@app.put("/dishes/{dish_id}")
def update_dish(dish_id: int, name: str, description: str, price: float, quantity: int, db=Depends(get_db)):
    dish = db.query(Dish).get(dish_id)
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")
    dish.name = name
    dish.description = description
    dish.price = price
    dish.quantity = quantity
    db.commit()
    return {"message": "Dish updated successfully"}


@app.delete("/dishes/{dish_id}")
def delete_dish(dish_id: int, db=Depends(get_db)):
    dish = db.query(Dish).get(dish_id)
    if not dish:
        raise HTTPException(status_code=404, detail="Dish not found")
    db.delete(dish)
    db.commit()
    return {"message": "Dish deleted successfully"}


# Конечная точка для получения меню
@app.get("/menu")
def get_menu(db=Depends(get_db)):
    menu = db.query(Dish).filter(Dish.quantity > 0).all()
    return menu


# Запуск приложения
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
